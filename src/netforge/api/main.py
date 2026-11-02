from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from netforge.api import gui, rest
from netforge.api.deps import get_session
from netforge.queue import get_redis

app = FastAPI(title="Netforge", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(rest.router)
app.include_router(gui.router)


@app.get("/livez", include_in_schema=False)
def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz", include_in_schema=False)
def healthz(session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
        get_redis().ping()
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Dependency unavailable") from exc
    return {"status": "ok"}
