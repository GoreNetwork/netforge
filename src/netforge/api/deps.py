import secrets
from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from netforge.config import get_settings
from netforge.db import new_session

_bearer = HTTPBearer(auto_error=False)


def get_session() -> Iterator[Session]:
    with new_session() as session:
        yield session


def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    expected = get_settings().api_token
    supplied = credentials.credentials if credentials else ""
    # An unset token must lock the API, never open it.
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
