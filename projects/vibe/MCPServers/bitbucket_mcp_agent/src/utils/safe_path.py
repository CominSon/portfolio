"""Безопасные пути на сетевых дисках (U:\\) — без resolve(), WinError 5."""

from pathlib import Path


def safe_absolute(path):
    p = Path(path)
    try:
        return p.resolve()
    except (OSError, PermissionError):
        return p.absolute()


def package_root(from_file):
    p = Path(from_file).absolute()
    if p.name == "__main__.py":
        return p.parent
    return p.parents[1]
