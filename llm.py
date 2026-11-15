"""The one place Sapient talks to a model: client, retries, saved answers, usage log.

Every answer is saved under a hash of what produced it (model, reasoning setting, prompt),
so a rebuild with unchanged prompts makes no model calls. Empty and cut-off answers are
never saved.
"""
import hashlib
import json
import os
import time
from datetime import datetime
from typing import NamedTuple

from openai import (APIConnectionError, APITimeoutError, BadRequestError, InternalServerError,
                    OpenAI, RateLimitError)

from config import (CACHE_DIR, MAX_TOKENS, NO_THINKING, NVIDIA_API_KEY, NVIDIA_BASE_URL,
                    TEMPERATURE, USAGE_LOG)


class Answer(NamedTuple):
    text: str
    truncated: bool = False  # the model stopped at max_tokens


def client(timeout: float = 180.0) -> OpenAI:
    if not NVIDIA_API_KEY:
        raise EnvironmentError("NVIDIA_API_KEY is not set")
    # retries are handled in create_with_retry, so the SDK's own are off
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=timeout, max_retries=0)


def get_cached(cache_key: str) -> str | None:
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())["program"]
    return None


def set_cached(cache_key: str, text: str):
    CACHE_DIR.mkdir(exist_ok=True)
    (CACHE_DIR / f"{cache_key}.json").write_text(
        json.dumps({"program": text, "timestamp": datetime.now().isoformat()}))


def log_usage(response, model, seconds, wall_seconds, attempts):
    """Every real (non-cached) call lands here, so this is the one place cost is metered.
    SAPIENT_RUN_TAG groups calls per run (e.g. "ADAE-specgen") for per-dataset reports."""
    usage = getattr(response, "usage", None)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tag": os.getenv("SAPIENT_RUN_TAG", ""),
        "model": model,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "seconds": round(seconds, 2),
        "wall_seconds": round(wall_seconds, 2),
        "attempts": attempts,
    }
    USAGE_LOG.parent.mkdir(exist_ok=True)
    with USAGE_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")


def create_with_retry(client, retries=5, base_delay=30, fallback_model=None, **kwargs):
    wall_start = time.monotonic()
    for attempt in range(retries):
        try:
            start = time.monotonic()
            response = client.chat.completions.create(**kwargs)
            log_usage(response, kwargs.get("model"), time.monotonic() - start,
                      time.monotonic() - wall_start, attempt + 1)
            return response
        except (APITimeoutError, APIConnectionError):
            if attempt == retries - 1:
                if fallback_model and kwargs.get("model") != fallback_model:
                    print(f"llm: {kwargs.get('model')} kept timing out, falling back to {fallback_model}")
                    return create_with_retry(client, retries=retries, base_delay=base_delay,
                                             **{**kwargs, "model": fallback_model})
                raise
        except (RateLimitError, InternalServerError):
            if attempt == retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
        except BadRequestError as e:
            # NVIDIA marks a down endpoint "DEGRADED function cannot be invoked" (400);
            # transient endpoint state, not a bad request — retry like a 5xx
            if "DEGRADED" not in str(e) or attempt == retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


def complete(prompt: str, model: str, *, thinking: bool = True, fallback: str | None = None,
             timeout: float = 180.0, cache: bool = True, legacy_key: bool = False) -> Answer:
    """One user prompt in, the model's text out, replayed from the saved answers when possible.

    legacy_key: the saved answers of the four oldest call sites are keyed by the prompt alone,
    without the model. The flag keeps those answers reachable; drop it (and re-ask) the next
    time one of those prompts changes.
    """
    parts = [prompt] if legacy_key else [model, *([] if thinking else [str(NO_THINKING)]), prompt]
    key = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    if cache:
        saved = get_cached(key)
        if saved:
            return Answer(saved)
    response = create_with_retry(client(timeout), fallback_model=fallback, model=model,
                                 messages=[{"role": "user", "content": prompt}],
                                 temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                                 **({} if thinking else {"extra_body": NO_THINKING}))
    text = response.choices[0].message.content or ""
    truncated = getattr(response.choices[0], "finish_reason", None) == "length"
    if cache and text and not truncated:
        set_cached(key, text)
    return Answer(text, truncated)
