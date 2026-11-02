from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from netforge.api import service
from netforge.api.deps import get_session
from netforge.catalog import TaskDefinition, ValidationFailed, load_catalog
from netforge.config import get_settings
from netforge.models import Task, TaskStatus

router = APIRouter(include_in_schema=False, default_response_class=HTMLResponse)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def same_origin_only(request: Request) -> None:
    """The GUI has no login, so another site must not be able to post to it."""
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-origin request refused")


def _get_definition(name: str) -> TaskDefinition:
    definition = load_catalog().get(name)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown task type")
    return definition


def _get_task(session: Session, task_id: UUID) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


def _render_form(
    request: Request, definition: TaskDefinition, values: dict, errors: dict, code: int = 200
) -> Response:
    return templates.TemplateResponse(
        request,
        "task_form.html",
        {"definition": definition, "values": values, "errors": errors},
        status_code=code,
    )


@router.get("/")
def home(request: Request, session: Session = Depends(get_session)) -> Response:
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "definitions": load_catalog().values(),
            "tasks": service.list_tasks(session),
            "nautobot_url": get_settings().nautobot_public_url,
        },
    )


@router.get("/ui/tasks")
def tasks_table(request: Request, session: Session = Depends(get_session)) -> Response:
    return templates.TemplateResponse(request, "_tasks_table.html", {"tasks": service.list_tasks(session)})


@router.get("/tasks/new/{task_type}")
def new_task(request: Request, task_type: str) -> Response:
    return _render_form(request, _get_definition(task_type), {}, {})


@router.post("/tasks/new/{task_type}", dependencies=[Depends(same_origin_only)])
async def submit_form(
    request: Request, task_type: str, session: Session = Depends(get_session)
) -> Response:
    definition = _get_definition(task_type)
    form = await request.form()
    submitted = {key: value for key, value in form.items() if isinstance(value, str)}
    try:
        task = service.submit_task(session, definition, submitted, submitted_via="gui")
    except ValidationFailed as exc:
        return _render_form(
            request, definition, submitted, exc.errors, status.HTTP_422_UNPROCESSABLE_CONTENT
        )
    return RedirectResponse(f"/tasks/{task.id}", status.HTTP_303_SEE_OTHER)


@router.get("/tasks/{task_id}")
def task_detail(request: Request, task_id: UUID, session: Session = Depends(get_session)) -> Response:
    task = _get_task(session, task_id)
    return templates.TemplateResponse(
        request, "task_detail.html", _detail_context(session, task)
    )


@router.get("/ui/tasks/{task_id}")
def task_panel(request: Request, task_id: UUID, session: Session = Depends(get_session)) -> Response:
    task = _get_task(session, task_id)
    return templates.TemplateResponse(request, "_task_panel.html", _detail_context(session, task))


def _detail_context(session: Session, task: Task) -> dict:
    return {
        "task": task,
        "logs": service.get_logs(session, task.id),
        "active": task.status in (TaskStatus.queued.value, TaskStatus.running.value),
    }
