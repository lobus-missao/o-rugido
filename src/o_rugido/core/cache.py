from __future__ import annotations

import functools
import time


def ttl_cache(seconds: int = 60):
    def decorator(func):
        store: dict = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            if key in store:
                ts, result = store[key]
                if now - ts < seconds:
                    return result
            result = func(*args, **kwargs)
            store[key] = (now, result)
            if len(store) > 50:
                cutoff = now - seconds
                for k in [k for k, (ts, _) in store.items() if ts < cutoff]:
                    store.pop(k, None)
            return result

        wrapper.cache_clear = lambda: store.clear()
        return wrapper

    return decorator
