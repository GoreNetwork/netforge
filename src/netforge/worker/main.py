"""Queue consumer. Run more copies to add capacity; claims are atomic."""
import json
import logging
import shutil
import signal
import socket
import tempfile
import threading
import time
import traceback
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import redis
from sqlalchemy import select, update

from netforge import queue
from netforge.catalog import load_catalog
from netforge.config import get_settings
from netforge.db import new_session
from netforge.models import Task, TaskLog, TaskStatus, utcnow
from netforge.worker.engines import Engine, EngineError, RunContext, load_engines

logger = logging.getLogger("netforge.worker")
WORKER_ID = f"{socket.gethostname()}:{time.time_ns()}"
BLPOP_TIMEOUT_SECONDS = 5


def claim(task_id: UUID) -> Task | None:
    """Move a queued task to running. Only one worker can win this update."""
    now = utcnow()
    with new_session() as session:
        task = session.scalars(
            update(Task)
            .where(Task.id == task_id, Task.status == TaskStatus.queued.value)
            .values(status=TaskStatus.running.value, worker_id=WORKER_ID, started_at=now, heartbeat_at=now)
            .returning(Task)
        ).one_or_none()
        session.commit()
        return task


def finish(task_id: UUID, status: TaskStatus, result: dict | None = None, error: str | None = None) -> None:
    with new_session() as session:
        session.execute(
            update(Task)
            .where(Task.id == task_id, Task.status == TaskStatus.running.value)
            .values(status=status.value, result=result, error=error, finished_at=utcnow())
        )
        session.commit()


def append_log(task_id: UUID, line: str) -> None:
    with new_session() as session:
        session.add(TaskLog(task_id=task_id, line=line))
        session.commit()


def heartbeat(task_id: UUID, stop: threading.Event) -> None:
    while not stop.wait(get_settings().heartbeat_seconds):
        try:
            with new_session() as session:
                session.execute(update(Task).where(Task.id == task_id).values(heartbeat_at=utcnow()))
                session.commit()
        except Exception:
            logger.exception("Heartbeat failed for %s", task_id)


def execute(task: Task, engines: dict[str, Engine]) -> None:
    definition = load_catalog().get(task.task_type)
    work_dir = Path(tempfile.mkdtemp(prefix=f"netforge-{task.id}-"))
    stop_heartbeat = threading.Event()
    threading.Thread(target=heartbeat, args=(task.id, stop_heartbeat), daemon=True).start()
    try:
        if definition is None:
            raise EngineError(f"Task type {task.task_type} no longer exists")
        context = RunContext(
            task_id=task.id,
            definition=definition,
            variables=task.variables,
            work_dir=work_dir,
            log=lambda line: append_log(task.id, line),
        )
        context.vars_file.write_text(json.dumps(task.variables), encoding="utf-8")
        result = engines[task.engine].run(context)
    except EngineError as exc:
        finish(task.id, TaskStatus.failed, error=str(exc))
    except Exception:
        logger.exception("Task %s crashed", task.id)
        finish(task.id, TaskStatus.failed, error=traceback.format_exc(limit=5))
    else:
        finish(task.id, TaskStatus.succeeded, result=result)
    finally:
        stop_heartbeat.set()
        shutil.rmtree(work_dir, ignore_errors=True)


def sweep(engine_names: list[str]) -> None:
    """Repair what a crash or a Redis restart left behind."""
    settings = get_settings()
    now = utcnow()
    with new_session() as session:
        # A lost run may have changed real gear part way through, so it is
        # failed for a person to look at and never re-run automatically.
        lost = session.scalars(
            select(Task)
            .where(
                Task.status == TaskStatus.running.value,
                Task.heartbeat_at < now - timedelta(seconds=settings.stale_seconds),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for task in lost:
            logger.warning("Marking %s failed: worker %s stopped responding", task.id, task.worker_id)
            task.status = TaskStatus.failed.value
            task.finished_at = now
            task.error = (
                f"Worker {task.worker_id} stopped responding. The task may have partly "
                "completed, so it was not retried. Check the target before resubmitting."
            )
        session.commit()

        # Nothing has run for a queued task, so requeueing is always safe, and
        # a duplicate entry loses the claim and is dropped.
        waiting = session.scalars(
            select(Task).where(
                Task.status == TaskStatus.queued.value,
                Task.engine.in_(engine_names),
                Task.created_at < now - timedelta(seconds=settings.sweep_seconds),
            )
        ).all()
    for task in waiting:
        if not queue.is_enqueued(task.engine, task.id):
            logger.warning("Requeueing %s, missing from Redis", task.id)
            queue.enqueue(task.engine, task.id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    engines = load_engines(settings.worker_engines)
    queues = {queue.queue_name(name): name for name in engines}
    client = queue.get_redis()

    stopping = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.set())

    logger.info("Worker %s consuming %s", WORKER_ID, sorted(queues))
    next_sweep = 0.0
    while not stopping.is_set():
        try:
            if time.monotonic() >= next_sweep:
                sweep(list(engines))
                next_sweep = time.monotonic() + settings.sweep_seconds
            item = client.blpop(list(queues), timeout=BLPOP_TIMEOUT_SECONDS)
        except (redis.RedisError, OSError):
            logger.exception("Queue unavailable, retrying")
            time.sleep(BLPOP_TIMEOUT_SECONDS)
            continue
        if item is None:
            continue
        task = claim(UUID(item[1]))
        if task is not None:
            logger.info("Running %s (%s)", task.id, task.task_type)
            execute(task, engines)
            logger.info("Finished %s", task.id)


if __name__ == "__main__":
    main()
