"""Redis is only the wake-up signal. Postgres owns task state, so anything lost
from Redis is rebuilt by the worker's sweep."""
from functools import lru_cache
from uuid import UUID

import redis

from netforge.config import get_settings

# Must stay longer than the worker's BLPOP timeout, or every idle poll errors.
SOCKET_TIMEOUT_SECONDS = 30


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=5,
    )


def queue_name(engine: str) -> str:
    return f"netforge:queue:{engine}"


def enqueue(engine: str, task_id: UUID) -> None:
    get_redis().rpush(queue_name(engine), str(task_id))


def is_enqueued(engine: str, task_id: UUID) -> bool:
    return get_redis().lpos(queue_name(engine), str(task_id)) is not None
