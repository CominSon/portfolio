"""HTTP Basic Auth для админских API (создание интервью, работодатели)."""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

_security = HTTPBasic(auto_error=False)


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(_security),
) -> str:
    settings = get_settings()
    expected_user = (settings.admin_username or "").encode("utf-8")
    expected_pass = (settings.admin_password or "").encode("utf-8")
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход в админку",
            headers={"WWW-Authenticate": 'Basic realm="Admin"'},
        )
    user_ok = secrets.compare_digest(credentials.username.encode("utf-8"), expected_user)
    pass_ok = secrets.compare_digest(credentials.password.encode("utf-8"), expected_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": 'Basic realm="Admin"'},
        )
    return credentials.username
