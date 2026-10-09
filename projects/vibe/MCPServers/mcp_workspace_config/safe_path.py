"""Безопасные пути на сетевых дисках U:\\ — без resolve(), WinError 5."""

import os
from pathlib import Path

ACTIVE_PROJECT_STORE_VERSION = 2


def _windows_path_text(path):
    return str(path).replace("/", "\\")


def _skip_resolve(path):
    """На Windows resolve() на U:\\ и UNC часто даёт PermissionError даже при рабочей записи."""
    if os.name != "nt":
        return False
    text = _windows_path_text(path)
    if text.startswith("\\\\"):
        return True
    if len(text) >= 2 and text[1] == ":":
        return True
    return False


def safe_absolute(path):
    p = Path(path)
    if _skip_resolve(p):
        return p.absolute()
    try:
        return p.resolve()
    except (OSError, PermissionError, RuntimeError):
        return p.absolute()


def safe_module_dir(module_file):
    return Path(module_file).absolute().parent


def probe_write_access(path):
    """Проверка записи: mkdir + тестовый файл."""
    target = safe_absolute(path)
    result = {"path": str(target), "writable": False}
    try:
        target.mkdir(parents=True, exist_ok=True)
        test = target / ".report_mcp_write_probe"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        result["writable"] = True
        result["ok"] = True
    except (OSError, PermissionError) as exc:
        result["ok"] = False
        result["error"] = "{0}: {1}".format(type(exc).__name__, exc)
    return result


def ensure_writable_directory(path, label="папка"):
    """Проверка записи до scaffold/spill. PermissionError → ValueError с диагностикой."""
    probe = probe_write_access(path)
    if probe.get("writable"):
        return safe_absolute(path)
    parent_probe = None
    try:
        parent_probe = probe_write_access(safe_absolute(path).parent)
    except (OSError, ValueError):
        pass
    parts = [
        "Нет прав на запись в {0}: {1}".format(label, path),
        probe.get("error") or "probe failed",
    ]
    if parent_probe:
        parts.append(
            "Родитель {0}: writable={1}".format(
                parent_probe.get("path"), parent_probe.get("writable")
            )
        )
    parts.append(
        "Если папка проекта уже создана вручную — resume_report_project(project_root=...)"
    )
    raise ValueError(" ".join(parts))


def write_text_safe(path, content, encoding="utf-8"):
    """Запись текста с понятной ошибкой (путь в сообщении).

    Для .sql/.md нормализует CRLF→LF, чтобы на Windows не получалось
    визуальных «пустых строк» между каждой строкой DDL (\\r\\r\\n).
    """
    target = Path(path)
    text = content if content is not None else ""
    suffix = target.suffix.lower()
    if suffix in (".sql", ".md", ".txt", ".py", ".svg"):
        try:
            from mcp_workspace_config.text_normalize import normalize_line_endings
            text = normalize_line_endings(text)
        except Exception:
            text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="" + явный \\n: не даём Python на Windows снова превратить \\n в \\r\\n
        with target.open("w", encoding=encoding, newline="\n") as fh:
            fh.write(text)
        return str(target)
    except (OSError, PermissionError) as exc:
        raise PermissionError(
            "Не удалось записать {0}: {1}".format(target, exc)
        ) from exc
