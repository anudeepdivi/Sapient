import time
from openai import RateLimitError, APITimeoutError, APIConnectionError


def create_with_retry(client, retries=5, base_delay=30, fallback_model=None, **kwargs):
    for attempt in range(retries):
        try:
            return client.chat.completions.create(**kwargs)
        except (APITimeoutError, APIConnectionError):
            if attempt == retries - 1:
                if fallback_model and kwargs.get("model") != fallback_model:
                    print(f"llm_retry: {kwargs.get('model')} kept timing out, falling back to {fallback_model}")
                    return create_with_retry(client, retries=retries, base_delay=base_delay,
                                             **{**kwargs, "model": fallback_model})
                raise
        except RateLimitError:
            if attempt == retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
