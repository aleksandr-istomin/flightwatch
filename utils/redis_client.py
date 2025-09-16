import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_redis_client = None  # type: Optional["redis.Redis"]


def get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    import redis

    url = os.getenv("REDIS_URL")
    _redis_client = redis.from_url(url, decode_responses=True)

    return _redis_client


def close_redis():
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None


