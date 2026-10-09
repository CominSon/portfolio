"""Разрешение путей к файлам: абсолютные (Windows) и относительно cwd проекта."""

import os
from pathlib import Path

from mail_mcp_agent.src.utils.safe_path import safe_absolute


class PathResolveError(Exception):
    pass


def resolve_attachment_path(path_str, must_exist=True):
    # type: (str, bool) -> Path
    """
    - Абсолютный путь (C:\\, U:\\, \\\\server\\...) — как есть.
    - Относительный — от os.getcwd() (корень проекта из mcpServers.cwd).
    """
    if not path_str or not str(path_str).strip():
        raise PathResolveError("Путь к файлу не указан")

    raw = str(path_str).strip().strip('"').strip("'")
    candidate = Path(raw)

    if not candidate.is_absolute():
        candidate = Path(os.getcwd()) / candidate

    try:
        resolved = safe_absolute(candidate)
    except (OSError, PermissionError):
        resolved = candidate.absolute()

    if must_exist and not resolved.is_file():
        raise PathResolveError(
            "Файл не найден: {0} (cwd={1})".format(resolved, os.getcwd())
        )

    size_mb = resolved.stat().st_size / (1024 * 1024)
    return resolved, size_mb
