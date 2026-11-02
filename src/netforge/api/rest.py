from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from netforge.api import service
from netforge.api.deps import get_session, require_token
from netforge.catalog import TaskDefinition, ValidationFailed, load_catalog
from netforge.models import Task, TaskStatus

router = APIRouter(prefix="/api/v1", tags=["tasks"], dependencies=[Depends(require_token)])


class TaskCreate(BaseModel):
    task_type: str
    variables: dict[str, Any] = Field(default_factory=dict)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_type: str
    engine: str
    variables: dict[str, Any]
    status: TaskStatus
    result: dict[str, Any] | None
    error: str | None
    submitted_via: str
    worker_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line: str
    created_at: datetime


def _describe(definition: TaskDefinition) -> dict[str, Any]:
    return {
        "name": definition.name,
        "title": definition.title,
        "description": definition.description,
        "engine": definition.engine,
        "variables": [asdict(variable) for variable in definition.variables],
    }


def _get_task(session: Session, task_id: UUID) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@router.get("/task-types")
def list_task_types() -> list[dict[str, Any]]:
    return [_describe(definition) for definition in load_catalog().values()]


@router.post("/tasks", status_code=status.HTTP_201_CREATED, response_model=TaskOut)
def create_task(body: TaskCreate, session: Session = Depends(get_session)) -> Task:
    definition = load_catalog().get(body.task_type)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown task type: {body.task_type}")
    try:
        return service.submit_task(session, definition, body.variables, submitted_via="api")
    except ValidationFailed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"variables": exc.errors}) from exc


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    task_status: TaskStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[Task]:
    return service.list_tasks(session, task_status.value if task_status else None, limit)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: UUID, session: Session = Depends(get_session)) -> Task:
    return _get_task(session, task_id)


@router.get("/tasks/{task_id}/logs", response_model=list[TaskLogOut])
def get_task_logs(
    task_id: UUID, after: int = Query(0, ge=0), session: Session = Depends(get_session)
) -> list[Any]:
    _get_task(session, task_id)
    return service.get_logs(session, task_id, after)
