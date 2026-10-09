"""Синхронизация U:\\MCP Servers с master веткой wealthhub/python.git."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlparse, urlunparse

from bitbucket_mcp_agent.resources import settings
from bitbucket_mcp_agent.src.auth import noterball_auth
from bitbucket_mcp_agent.src.git import git_runner

logger = logging.getLogger("bb_mcp.mcp_sync")

RESTART_NOTICE = (
    "Для вступления изменений перезапустите MCP Server в настройках GigaIDE "
    "и начните новый чат."
)


def resolve_local_root(explicit: Optional[str] = None) -> Path:
    """Корень локальных MCP Servers (обычно U:\\MCP Servers)."""
    if explicit:
        root = Path(explicit)
    else:
        env = os.environ.get("MCP_SERVERS_ROOT")
        if env:
            root = Path(env)
        else:
            # cwd процесса MCP = U:\MCP Servers; запасной вариант — родитель пакета
            cwd = Path.cwd()
            if (cwd / "bitbucket_mcp_agent").is_dir():
                root = cwd
            else:
                pkg = Path(__file__).resolve().parents[2]  # .../bitbucket_mcp_agent
                candidate = pkg.parent
                if (candidate / "bitbucket_mcp_agent").is_dir():
                    root = candidate
                else:
                    root = Path(settings.MCP_SERVERS_LOCAL_ROOT)
    root = root.resolve() if root.exists() else root
    if not root.is_dir():
        raise ValueError(
            "Локальная папка MCP Servers не найдена: {0}. "
            "Ожидается существующий каталог (обычно U:\\MCP Servers).".format(root)
        )
    return root


def _authenticated_repo_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    if parsed.scheme not in ("http", "https"):
        return repo_url
    user = noterball_auth.get_git_username()
    password = noterball_auth.get_password()
    host = parsed.hostname or ""
    port = ":{0}".format(parsed.port) if parsed.port else ""
    netloc = "{0}:{1}@{2}{3}".format(
        quote(user, safe=""),
        quote(password, safe=""),
        host,
        port,
    )
    return urlunparse((
        parsed.scheme, netloc, parsed.path,
        parsed.params, parsed.query, parsed.fragment,
    ))


def _cache_dir(local_root: Path) -> Path:
    return local_root / "bitbucket_mcp_agent" / settings.PROFILE_SUBDIR / settings.MCP_SYNC_CACHE_DIRNAME


def _run_git_cwd(args: List[str], cwd: str, timeout: int = 300) -> Tuple[int, str, str]:
    return git_runner.run_git(args, cwd=cwd, timeout=timeout)


def ensure_source_checkout(local_root: Path) -> Path:
    """
    Shallow-клон / обновление python.git в кэше.
    Возвращает путь к папке «MCP Servers» внутри клона.
    """
    cache = _cache_dir(local_root)
    cache.parent.mkdir(parents=True, exist_ok=True)
    auth_url = _authenticated_repo_url(settings.MCP_SOURCE_REPO_URL)
    branch = settings.MCP_SOURCE_BRANCH

    if (cache / ".git").is_dir():
        code, out, err = _run_git_cwd(["remote", "get-url", "origin"], str(cache))
        if code != 0:
            shutil.rmtree(cache, ignore_errors=True)
        else:
            # fetch + hard reset на origin/master
            code, out, err = _run_git_cwd(
                ["fetch", "--depth", "1", "origin", branch],
                str(cache),
                timeout=300,
            )
            if code != 0:
                raise RuntimeError(
                    "Не удалось обновить клон python.git: {0}".format(err or out)
                )
            code, out, err = _run_git_cwd(
                ["checkout", "-B", branch, "FETCH_HEAD"],
                str(cache),
            )
            if code != 0:
                code2, out2, err2 = _run_git_cwd(
                    ["reset", "--hard", "origin/{0}".format(branch)],
                    str(cache),
                )
                if code2 != 0:
                    raise RuntimeError(
                        "Не удалось переключить клон на {0}: {1}".format(
                            branch, err2 or out2 or err or out
                        )
                    )
            code, out, err = _run_git_cwd(["clean", "-fd"], str(cache))
            if code != 0:
                logger.warning("git clean: %s", err or out)

    if not (cache / ".git").is_dir():
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
        parent = str(cache.parent)
        name = cache.name
        code, out, err = _run_git_cwd(
            [
                "clone",
                "--depth", "1",
                "--branch", branch,
                "--single-branch",
                auth_url,
                name,
            ],
            parent,
            timeout=600,
        )
        if code != 0:
            raise RuntimeError(
                "Не удалось клонировать {0}: {1}".format(
                    settings.MCP_SOURCE_REPO_URL, err or out
                )
            )

    remote_mcp = cache / settings.MCP_SOURCE_SUBDIR
    if not remote_mcp.is_dir():
        raise RuntimeError(
            "В репозитории python нет папки «{0}» (ветка {1}). "
            "Проверьте структуру на Bitbucket.".format(
                settings.MCP_SOURCE_SUBDIR, branch
            )
        )
    return remote_mcp


def _should_skip_dir(name: str) -> bool:
    if name in settings.MCP_SYNC_SKIP_DIR_NAMES:
        return True
    if name.startswith(".") and name not in (".", ".."):
        return True
    if name.endswith("_mcp_config"):
        return True
    return False


def _should_skip_file(name: str) -> bool:
    if name.startswith("."):
        return True
    lower = name.lower()
    return any(lower.endswith(s) for s in settings.MCP_SYNC_SKIP_FILE_SUFFIXES)


def _iter_files(root: Path) -> List[Path]:
    files: List[Path] = []
    if not root.is_dir():
        return files
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for fn in filenames:
            if _should_skip_file(fn):
                continue
            files.append(Path(dirpath) / fn)
    return files


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _rel_key(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def compare_trees(local_dir: Path, remote_dir: Path) -> Dict[str, Any]:
    """Сравнение двух деревьев файлов (без skip-директорий)."""
    local_map: Dict[str, Path] = {}
    remote_map: Dict[str, Path] = {}
    if local_dir.is_dir():
        for p in _iter_files(local_dir):
            local_map[_rel_key(local_dir, p)] = p
    if remote_dir.is_dir():
        for p in _iter_files(remote_dir):
            remote_map[_rel_key(remote_dir, p)] = p

    added = sorted(set(remote_map) - set(local_map))
    removed = sorted(set(local_map) - set(remote_map))
    changed: List[str] = []
    for key in sorted(set(local_map) & set(remote_map)):
        try:
            if _file_sha256(local_map[key]) != _file_sha256(remote_map[key]):
                changed.append(key)
        except OSError:
            changed.append(key)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "has_diff": bool(added or removed or changed),
    }


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def sync_directory(local_dir: Path, remote_dir: Path, dry_run: bool = False) -> Dict[str, Any]:
    """Скопировать отличающиеся файлы remote → local. Удалённые на remote локально не трогаем."""
    diff = compare_trees(local_dir, remote_dir)
    copied: List[str] = []
    if not dry_run and diff["has_diff"]:
        for key in diff["added"] + diff["changed"]:
            src = remote_dir / Path(*key.split("/"))
            dst = local_dir / Path(*key.split("/"))
            if src.is_file():
                _copy_file(src, dst)
                copied.append(key)
    return {**diff, "copied": copied, "dry_run": dry_run}


def list_mcp_packages(root: Path) -> List[str]:
    """Пакеты-серверы: каталоги с __main__.py (или известные из KNOWN)."""
    names: Set[str] = set()
    if not root.is_dir():
        return []
    for child in root.iterdir():
        if not child.is_dir() or _should_skip_dir(child.name):
            continue
        if child.name in settings.KNOWN_MCP_PACKAGES or (child / "__main__.py").is_file():
            names.add(child.name)
        elif child.name.endswith("_mcp_agent"):
            names.add(child.name)
    return sorted(names)


def _windows_mcp_root_str(local_root: Optional[Path] = None) -> str:
    """Путь для JSON GigaIDE (всегда Windows-стиль U:\\...)."""
    if local_root is not None:
        s = str(local_root)
        if len(s) >= 2 and s[1] == ":":
            return s.replace("/", "\\")
    return str(settings.MCP_SERVERS_LOCAL_ROOT).replace("/", "\\")


def build_gigaide_server_json(package_name: str, local_root: Optional[Path] = None) -> Dict[str, Any]:
    """JSON-фрагмент mcpServers для GigaIDE."""
    meta = settings.KNOWN_MCP_PACKAGES.get(package_name) or {
        "ide_name": package_name.replace("_mcp_agent", "").replace("_", "-"),
        "module": package_name,
        "description": "MCP-сервер {0}.".format(package_name),
    }
    root_json = _windows_mcp_root_str(local_root)
    site = r"U:\Python313\site-packages"
    pythonpath = "{0};{1}".format(root_json, site)
    return {
        meta["ide_name"]: {
            "command": "python",
            "args": ["-u", "-m", meta["module"]],
            "env": {
                "PYTHONPATH": pythonpath,
                "PYTHONUNBUFFERED": "1",
            },
            "cwd": root_json,
        }
    }


def format_new_server_chat_block(package_name: str, local_root: Path) -> str:
    meta = settings.KNOWN_MCP_PACKAGES.get(package_name) or {
        "ide_name": package_name.replace("_mcp_agent", "").replace("_", "-"),
        "description": "Новый MCP-сервер из репозитория python.",
    }
    fragment = build_gigaide_server_json(package_name, local_root)
    return (
        "Добавлен новый MCP-сервер **{pkg}** (в GigaIDE: `{ide}`).\n"
        "Назначение: {desc}\n\n"
        "Добавьте его в Tools → GigaCode → MCP (или в JSON mcpServers):\n\n"
        "```json\n{json}\n```\n\n"
        "{restart}"
    ).format(
        pkg=package_name,
        ide=meta.get("ide_name", package_name),
        desc=meta.get("description", ""),
        json=json.dumps({"mcpServers": fragment}, ensure_ascii=False, indent=2),
        restart=RESTART_NOTICE,
    )


def gigacode_rules_paths(local_root: Path) -> Tuple[Path, Path]:
    source = local_root / settings.GIGACODE_RULES_SOURCE_NAME
    dest = Path.home() / settings.GIGACODE_RULES_REL
    return source, dest


def _normalize_text(data: bytes) -> str:
    text = data.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sync_gigacode_rules(local_root: Path, dry_run: bool = False) -> Dict[str, Any]:
    """Сравнить GIGACODE_MCP_RULES.txt с ~/.gigacode/rules/mcp.md и при необходимости заменить."""
    source, dest = gigacode_rules_paths(local_root)
    result: Dict[str, Any] = {
        "source": str(source),
        "destination": str(dest),
        "updated": False,
        "missing_source": not source.is_file(),
        "dry_run": dry_run,
    }
    if not source.is_file():
        result["message"] = "Файл {0} отсутствует локально — правила не синхронизированы.".format(
            settings.GIGACODE_RULES_SOURCE_NAME
        )
        return result

    src_text = _normalize_text(source.read_bytes())
    if dest.is_file():
        dst_text = _normalize_text(dest.read_bytes())
        if src_text == dst_text:
            result["message"] = "Правила GigaCode актуальны, изменений нет."
            return result
    else:
        result["was_missing"] = True

    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src_text)
    result["updated"] = True
    if dry_run:
        result["message"] = (
            "Правила GigaCode отличаются от {0} — будут записаны в {1}.".format(
                settings.GIGACODE_RULES_SOURCE_NAME, dest
            )
        )
    else:
        result["message"] = (
            "Правила GigaCode обновлены: содержимое {0} записано в {1}.".format(
                settings.GIGACODE_RULES_SOURCE_NAME, dest
            )
        )
    return result


def sync_shared_root_files(
    local_root: Path,
    remote_mcp: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Общие файлы в корне MCP Servers (не пакеты): правила, гайды и т.п."""
    skip_names = set(list_mcp_packages(remote_mcp)) | set(list_mcp_packages(local_root))
    # также не копируем служебные каталоги как «файлы»
    copied: List[str] = []
    changed: List[str] = []
    added: List[str] = []
    for child in sorted(remote_mcp.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            if child.name in skip_names or _should_skip_dir(child.name):
                continue
            # вспомогательные пакеты вроде mcp_workspace_config
            if (child / "__init__.py").is_file() or child.name == "mcp_workspace_config":
                diff = sync_directory(local_root / child.name, child, dry_run=dry_run)
                if diff["has_diff"]:
                    changed.append(child.name + "/")
                    copied.extend("{0}/{1}".format(child.name, k) for k in diff.get("copied", []))
            continue
        if _should_skip_file(child.name):
            continue
        local_file = local_root / child.name
        if not local_file.is_file():
            added.append(child.name)
            if not dry_run:
                _copy_file(child, local_file)
                copied.append(child.name)
        else:
            try:
                if _file_sha256(local_file) != _file_sha256(child):
                    changed.append(child.name)
                    if not dry_run:
                        _copy_file(child, local_file)
                        copied.append(child.name)
            except OSError:
                changed.append(child.name)
                if not dry_run:
                    _copy_file(child, local_file)
                    copied.append(child.name)
    return {
        "added": added,
        "changed": changed,
        "copied": copied,
        "has_diff": bool(added or changed),
        "dry_run": dry_run,
    }


def update_mcp_servers(
    local_root: Optional[str] = None,
    dry_run: bool = False,
    servers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Основная операция «Обнови мои MCP Серверы».
    Сравнивает пакеты с master python.git и копирует отличия в U:\\MCP Servers.
    """
    root = resolve_local_root(local_root)
    remote_mcp = ensure_source_checkout(root)

    remote_pkgs = list_mcp_packages(remote_mcp)
    local_pkgs = list_mcp_packages(root)
    if servers:
        wanted = set(servers)
        remote_pkgs = [p for p in remote_pkgs if p in wanted]

    server_results: List[Dict[str, Any]] = []
    updated_servers: List[str] = []
    new_servers: List[str] = []
    unchanged_servers: List[str] = []
    chat_blocks: List[str] = []

    for pkg in remote_pkgs:
        local_dir = root / pkg
        remote_dir = remote_mcp / pkg
        is_new = not local_dir.is_dir()
        diff = sync_directory(local_dir, remote_dir, dry_run=dry_run)
        entry = {
            "package": pkg,
            "is_new": is_new,
            "has_updates": diff["has_diff"] or is_new,
            "added_files": diff.get("added", []),
            "changed_files": diff.get("changed", []),
            "copied_files": diff.get("copied", []),
        }
        if is_new:
            new_servers.append(pkg)
            if not dry_run:
                chat_blocks.append(format_new_server_chat_block(pkg, root))
            else:
                chat_blocks.append(
                    "[dry_run] Будет добавлен новый сервер {0}.".format(pkg)
                )
        elif diff["has_diff"]:
            updated_servers.append(pkg)
        else:
            unchanged_servers.append(pkg)
        server_results.append(entry)

    # Пакеты только локально (в remote нет) — только информируем
    only_local = sorted(set(local_pkgs) - set(list_mcp_packages(remote_mcp)))

    shared = sync_shared_root_files(root, remote_mcp, dry_run=dry_run)
    rules = sync_gigacode_rules(root, dry_run=dry_run)

    any_change = bool(
        updated_servers or new_servers or shared.get("has_diff") or rules.get("updated")
    )

    messages: List[str] = []
    if not any_change:
        messages.append("Обновлений нет: локальные MCP Servers совпадают с master python.git.")
    else:
        if updated_servers:
            messages.append(
                "Обновлены серверы: {0}.".format(", ".join(updated_servers))
            )
        if new_servers:
            messages.append(
                "Добавлены новые серверы: {0}. См. блоки настройки ниже.".format(
                    ", ".join(new_servers)
                )
            )
        if shared.get("has_diff"):
            parts = shared.get("changed", []) + shared.get("added", [])
            messages.append(
                "Обновлены общие файлы/пакеты корня: {0}.".format(", ".join(parts) or "да")
            )
        if rules.get("updated"):
            messages.append(rules.get("message") or "Правила GigaCode обновлены.")
        messages.append(RESTART_NOTICE)

    if only_local:
        messages.append(
            "Локально есть пакеты, которых нет в remote (не удалялись): {0}.".format(
                ", ".join(only_local)
            )
        )

    return {
        "ok": True,
        "dry_run": dry_run,
        "local_root": str(root),
        "remote_repo": settings.MCP_SOURCE_REPO_URL,
        "remote_branch": settings.MCP_SOURCE_BRANCH,
        "remote_subdir": settings.MCP_SOURCE_SUBDIR,
        "servers": server_results,
        "updated_servers": updated_servers,
        "new_servers": new_servers,
        "unchanged_servers": unchanged_servers,
        "only_local_servers": only_local,
        "shared_root": shared,
        "gigacode_rules": rules,
        "new_server_setup": chat_blocks,
        "messages": messages,
        "user_summary": "\n".join(messages),
        "restart_required": any_change,
    }


def write_all_gigaide_settings_txt(local_root: Path, out_path: Optional[Path] = None) -> Path:
    """Собрать txt: отдельный JSON mcpServers на каждый сервер (добавляются по одному)."""
    packages = list_mcp_packages(local_root)
    known_order = list(settings.KNOWN_MCP_PACKAGES.keys())
    ordered = [p for p in known_order if p in packages]
    ordered += [p for p in packages if p not in ordered]

    lines = [
        "Настройки MCP для GigaIDE (Tools → GigaCode → MCP).",
        "",
        "Каждый сервер добавляется ОТДЕЛЬНО: свой блок JSON.",
        "Общее для всех:",
        "  PYTHONPATH = U:\\MCP Servers;U:\\Python313\\site-packages",
        "  PYTHONUNBUFFERED = 1",
        "  cwd = U:\\MCP Servers",
        "",
        "После настройки: перезапустите MCP Server и начните новый чат.",
        "",
    ]
    for i, pkg in enumerate(ordered, 1):
        fragment = build_gigaide_server_json(pkg, local_root)
        ide_name = next(iter(fragment.keys()))
        module = fragment[ide_name]["args"][-1]
        lines.append("=" * 80)
        lines.append("{0}) {1}".format(i, ide_name))
        lines.append("   Configuration: python -u -m {0}".format(module))
        lines.append("=" * 80)
        lines.append(json.dumps({"mcpServers": fragment}, ensure_ascii=False, indent=2))
        lines.append("")

    lines.extend([
        "=" * 80,
        "Правила GigaCode",
        "=" * 80,
        "Скопируйте содержимое GIGACODE_MCP_RULES.txt (от «--- НАЧАЛО ПРАВИЛ ---»)",
        "в %USERPROFILE%\\.gigacode\\rules\\mcp.md",
        "",
    ])

    dest = out_path or (local_root / "GIGAIDE_MCP_SETTINGS.txt")
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return dest

