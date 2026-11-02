"""Task operations shared by the REST API and the GUI."""
import logging
from typing import Any
from uuid import UUID

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from netforge import queue
from netforge.catalog import TaskDefinition
from netforge.models import Task, TaskLog

logger = logging.getLogger("netforge.api")


def submit_task(
    session: Session, definition: TaskDefinition, submitted: dict[str, Any], submitted_via: str
) -> Task:
    """Validate and record a task, then signal the queue.

    Raises ValidationFailed. A Redis outage doesn't fail the request: the row
    is committed first and the worker sweep queues it once Redis is back.
    """
    task = Task(
        task_type=definition.name,
        engine=definition.engine,
        variables=definition.validate(submitted),
        submitted_via=submitted_via,
    )
    session.add(task)
    session.commit()
    try:
        queue.enqueue(task.engine, task.id)
    except (redis.RedisError, OSError):
        logger.exception("Could not enqueue %s; the sweep will pick it up", task.id)
    return task


def list_tasks(session: Session, status: str | None = None, limit: int = 50) -> list[Task]:
    query = select(Task).order_by(Task.created_at.desc()).limit(limit)
    if status:
        query = query.where(Task.status == status)
    return list(session.scalars(query))


def get_logs(session: Session, task_id: UUID, after: int = 0) -> list[TaskLog]:
    return list(
        session.scalars(
            select(TaskLog).where(TaskLog.task_id == task_id, TaskLog.id > after).order_by(TaskLog.id)
        )
    )
