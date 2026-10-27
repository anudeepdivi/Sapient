import json
import os
import time
from openai import RateLimitError, APITimeoutError, APIConnectionError, InternalServerError, BadRequestError
from config import CACHE_DIR

# Every real (non-cached) LLM call lands here, so this is the one place cost is metered.
# SAPIENT_RUN_TAG groups calls per run (e.g. "ADAE-specgen") for per-dataset reports.
USAGE_LOG = CACHE_DIR / "llm_usage.jsonl"


def log_usage(response, model, seconds, wall_seconds, attempts):
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
                    print(f"llm_retry: {kwargs.get('model')} kept timing out, falling back to {fallback_model}")
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
