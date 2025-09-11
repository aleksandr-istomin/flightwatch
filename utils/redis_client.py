import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_redis_client = None  # type: Optional["redis.Redis"]


def get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    # Импортируем лениво, чтобы не требовать Redis там, где он не нужен
    import redis

    url = os.getenv("REDIS_URL")
    if not url:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        password = os.getenv("REDIS_PASSWORD") or None
        _redis_client = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)
    else:
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


