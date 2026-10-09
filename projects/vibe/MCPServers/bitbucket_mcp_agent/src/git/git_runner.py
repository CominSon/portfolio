"""Обёртка над git в cwd проекта."""

import logging
import os
import subprocess
from typing import List, Optional, Tuple
from urllib.parse import quote, urlparse, urlunparse

from bitbucket_mcp_agent.resources import settings
from bitbucket_mcp_agent.src.auth import noterball_auth
from bitbucket_mcp_agent.src.git import project_store

logger = logging.getLogger("bb_mcp.git")

_GIT_ENV = None
_ASKPASS_PATH = None


def _ensure_askpass_script():
    global _ASKPASS_PATH
    if _ASKPASS_PATH:
        return _ASKPASS_PATH
    import tempfile
    if os.name == "nt":
        path = os.path.join(tempfile.gettempdir(), "bb_mcp_askpass.cmd")
        content = "@echo off\necho %GIT_PASSWORD%\n"
    else:
        path = os.path.join(tempfile.gettempdir(), "bb_mcp_askpass.sh")
        content = "#!/bin/sh\necho \"$GIT_PASSWORD\"\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    if os.name != "nt":
        os.chmod(path, 0o700)
    _ASKPASS_PATH = path
    return path


def _build_env():
    global _GIT_ENV
    if _GIT_ENV is not None:
        return _GIT_ENV
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    password = noterball_auth.get_password()
    user = noterball_auth.get_git_username()
    env["GIT_USERNAME"] = user
    env["GIT_PASSWORD"] = password
    env["GIT_ASKPASS"] = _ensure_askpass_script()
    env["GCM_INTERACTIVE"] = "Never"
    env["GIT_CONFIG_GLOBAL"] = "false"
    _GIT_ENV = env
    return env


def _git_base_args():
    return [
        "-c", "credential.helper=",
        "-c", "credential.useHttpPath=true",
    ]


def configure_ssl_verify_off():
    """http.sslVerify=false для текущего репозитория (если есть)."""
    try:
        require_git_repo()
        run_git(["config", "http.sslVerify", "false"])
    except ValueError:
        pass


def run_git(args, cwd=None, timeout=120):
    # type: (List[str], Optional[str], int) -> Tuple[int, str, str]
    cwd = cwd or project_store.get_effective_cwd()
    cmd = ["git"] + _git_base_args() + args
    logger.debug("git %s (cwd=%s)", " ".join(args), cwd)
    # UTF-8 обязательно: иначе кириллица в путях превращается в mojibake на Windows.
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=_build_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except TypeError:
        # Python < 3.6 без encoding=
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=_build_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            universal_newlines=True,
        )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def to_repo_relative_path(path):
    """Абсолютный Windows-путь → путь относительно корня git (для show/diff/restore)."""
    if not path:
        return path
    raw = path
    if isinstance(raw, dict):
        raw = raw.get("content") or raw.get("text") or raw.get("path") or ""
    raw = str(raw).strip().strip('"').strip("'")
    if not raw:
        return raw
    root = require_git_repo()
    root_n = os.path.normcase(os.path.normpath(root))
    path_n = os.path.normcase(os.path.normpath(raw))
    if path_n.startswith(root_n):
        rel = path_n[len(root_n):].lstrip("\\/")
        return rel.replace("\\", "/")
    # Уже относительный
    if not (len(raw) >= 2 and raw[1] == ":"):
        return raw.replace("\\", "/")
    raise ValueError(
        "Путь вне репозитория {0}: {1}. Укажите файл внутри клона или относительный путь.".format(
            root, raw
        )
    )


def require_git_repo():
    # type: () -> str
    root = project_store.get_effective_cwd()
    code, out, err = run_git(["rev-parse", "--show-toplevel"], cwd=root)
    if code != 0:
        raise ValueError(
            "Git не настроен для project_path={0}. {1} "
            "Вызовите set_project_path.".format(root, err or out)
        )
    return out


def get_repo_info():
    # type: () -> dict
    root = require_git_repo()
    code, branch, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    if code != 0:
        branch = "?"
    code, remote, _ = run_git(["remote", "-v"], cwd=root)
    remotes = remote.splitlines() if remote else []
    slug = _detect_repo_slug(remotes)
    wealthhub_ok = _is_wealthhub_remote(remotes)
    suggested_branch = noterball_auth.get_windows_username()
    _eff, source = project_store.resolve_effective_project_root(allow_missing=True)
    return {
        "repo_root": root,
        "current_branch": branch,
        "suggested_branch": suggested_branch,
        "remotes": remotes,
        "repo_slug": slug,
        "wealthhub_remote": wealthhub_ok,
        "project_path": root,
        "project_path_source": source,
        "mcp_process_cwd": os.getcwd(),
    }


def _detect_repo_slug(remotes):
    for line in remotes:
        lower = line.lower()
        if settings.DASHBOARDS_REPO_SLUG in lower:
            return settings.DASHBOARDS_REPO_SLUG
        if "users_scripts" in lower or "users-scripts" in lower:
            return "users_scripts"
    return None


def _is_wealthhub_remote(remotes):
    host = settings.BITBUCKET_HOST.lower()
    fragments = [f.lower() for f in settings.WEALTHHUB_URL_FRAGMENTS]
    for line in remotes:
        lower = line.lower().replace("\\", "/")
        if host not in lower:
            continue
        for fragment in fragments:
            if fragment.lower() in lower:
                return True
    return False


def _path_has_dot_segment(path):
    for part in path.replace("\\", "/").split("/"):
        if part.startswith("."):
            return True
    return False


def collect_committable_paths():
    """Файлы из status, кроме путей с компонентами, начинающимися с точки."""
    code, out, err = run_git(["status", "--porcelain"])
    if code != 0:
        raise RuntimeError(err or out)
    paths = []
    skipped = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path_part = line[3:].strip()
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1].strip()
        if _path_has_dot_segment(path_part):
            skipped.append(path_part)
            continue
        paths.append(path_part)
    return {"paths": paths, "skipped_dot_paths": skipped}


def _authenticated_push_url():
    code, remote_url, err = run_git(["remote", "get-url", "origin"])
    if code != 0:
        raise RuntimeError(err or "origin не настроен")
    remote_url = remote_url.strip()
    parsed = urlparse(remote_url)
    if parsed.scheme not in ("http", "https"):
        return remote_url
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


def assert_wealthhub_repo():
    info = get_repo_info()
    if not info.get("wealthhub_remote"):
        raise ValueError(
            "Remote не относится к {0} на {1}. Откройте клон WEALTHHUB в IDE.".format(
                settings.WEALTHHUB_PROJECT, settings.BITBUCKET_HOST
            )
        )
    return info


def assert_push_allowed(branch, repo_slug):
    # type: (str, Optional[str]) -> None
    if branch in settings.PROTECTED_BRANCHES and repo_slug == settings.DASHBOARDS_REPO_SLUG:
        raise ValueError(
            "Push в {0} репозитория {1} запрещён. Используйте свою ветку.".format(
                branch, settings.DASHBOARDS_REPO_SLUG
            )
        )


def git_status():
    assert_wealthhub_repo()
    code, out, err = run_git(["status", "--porcelain", "-b"])
    if code != 0:
        raise RuntimeError(err or out)
    committable = collect_committable_paths()
    return {
        "porcelain": out,
        "lines": out.splitlines() if out else [],
        "committable_paths": committable["paths"],
        "skipped_dot_paths": committable["skipped_dot_paths"],
    }


def git_diff(paths=None, staged=False):
    assert_wealthhub_repo()
    args = ["diff"]
    if staged:
        args.append("--cached")
    if paths:
        args.append("--")
        rels = []
        for p in paths:
            rels.append(to_repo_relative_path(p))
        args.extend(rels)
    code, out, err = run_git(args)
    if code != 0 and err:
        raise RuntimeError(err)
    return {"diff": out, "staged": staged, "paths": paths or []}


def git_log(max_count=20, path=None):
    assert_wealthhub_repo()
    args = [
        "log",
        "--oneline",
        "-n",
        str(max_count),
        "--decorate",
    ]
    if path:
        args.extend(["--", to_repo_relative_path(path)])
    code, out, err = run_git(args)
    if code != 0:
        raise RuntimeError(err or out)
    entries = []
    for line in out.splitlines():
        parts = line.split(" ", 1)
        entries.append({
            "sha": parts[0] if parts else "",
            "summary": parts[1] if len(parts) > 1 else "",
            "raw": line,
        })
    return {"entries": entries}


def preview_file_at_commit(commit, path):
    assert_wealthhub_repo()
    rel = to_repo_relative_path(path)
    code, out, err = run_git(["show", "{0}:{1}".format(commit, rel)])
    if code != 0:
        raise ValueError(
            "Не удалось прочитать файл на коммите {0}, path={1}. {2}".format(
                commit, rel, err or ""
            )
        )
    return {"commit": commit, "path": rel, "content": out}


def git_restore(path, source=None):
    assert_wealthhub_repo()
    rel = to_repo_relative_path(path)
    if source:
        code, _, err = run_git(["restore", "--source={0}".format(source), "--", rel])
    else:
        code, _, err = run_git(["restore", "--", rel])
    if code != 0:
        code2, _, err2 = run_git(["checkout", source or "HEAD", "--", rel])
        if code2 != 0:
            raise RuntimeError(err or err2)
    return {"ok": True, "path": rel, "source": source or "HEAD"}


def git_fetch():
    assert_wealthhub_repo()
    auth_url = _authenticated_push_url()
    code, out, err = run_git(["fetch", auth_url, "+refs/heads/*:refs/remotes/origin/*"])
    if code != 0:
        code, out, err = run_git(["fetch", "--all", "--prune"])
        if code != 0:
            raise RuntimeError(err or out)
    return {"ok": True, "output": out or err}


def git_pull():
    info = assert_wealthhub_repo()
    branch = info["current_branch"]
    auth_url = _authenticated_push_url()
    code, out, err = run_git(["pull", auth_url, branch, "--ff-only"])
    if code != 0:
        raise RuntimeError(err or out)
    return {"ok": True, "output": out}


def list_branches():
    assert_wealthhub_repo()
    code, out, err = run_git(["branch", "-a"])
    if code != 0:
        raise RuntimeError(err or out)
    return {"branches": [b.strip() for b in out.splitlines()]}


def checkout_branch(name, create=False):
    assert_wealthhub_repo()
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(name)
    code, out, err = run_git(args)
    if code != 0:
        raise RuntimeError(err or out)
    return {"branch": name, "created": create, "output": out or err}


def git_add(paths=None, exclude_dotfiles=True):
    assert_wealthhub_repo()
    if paths:
        filtered = [p for p in paths if not _path_has_dot_segment(p)]
        if not filtered:
            return {"added": [], "skipped_dot_paths": paths}
        args = ["add", "--"] + filtered
        added = filtered
    elif exclude_dotfiles:
        collected = collect_committable_paths()
        added = collected["paths"]
        if not added:
            return {
                "added": [],
                "skipped_dot_paths": collected["skipped_dot_paths"],
                "message": "Нет файлов для коммита (dot-файлы исключены).",
            }
        args = ["add", "--"] + added
    else:
        args = ["add", "-A"]
        added = ["all"]
    code, _, err = run_git(args)
    if code != 0:
        raise RuntimeError(err)
    return {"added": added}


def git_commit(message):
    assert_wealthhub_repo()
    code, out, err = run_git(["commit", "-m", message])
    if code != 0:
        raise RuntimeError(err or out)
    return {"output": out or err}


def commit_and_push(message, paths=None):
    """Коммит (без dot-файлов) и push с авторизацией noterball — один шаг."""
    info = assert_wealthhub_repo()
    branch = info["current_branch"]
    slug = info.get("repo_slug")
    assert_push_allowed(branch, slug)

    status_before = git_status()
    diff = git_diff()
    add_result = git_add(paths=paths, exclude_dotfiles=True)
    if not add_result.get("added"):
        return {
            "ok": False,
            "message": "Нечего коммитить.",
            "status": status_before,
            "skipped_dot_paths": add_result.get("skipped_dot_paths", []),
        }

    commit_result = git_commit(message)
    push_result = git_push(force=False)
    return {
        "ok": True,
        "branch": branch,
        "added": add_result.get("added"),
        "skipped_dot_paths": add_result.get("skipped_dot_paths", []),
        "diff_preview": (diff.get("diff") or "")[:6000],
        "commit": commit_result,
        "push": push_result,
    }


def git_compare_recent(path=None, commits_back=1):
    """Сравнение последних версий (read-only, без подтверждений)."""
    assert_wealthhub_repo()
    try:
        n = max(1, int(commits_back))
    except (TypeError, ValueError):
        if isinstance(commits_back, dict):
            n = max(1, int(commits_back.get("content") or commits_back.get("text") or 1))
        else:
            n = 1
    left = "HEAD~{0}".format(n)
    right = "HEAD"
    rel = to_repo_relative_path(path) if path else None

    # Проверка, что left существует
    code_chk, _, err_chk = run_git(["rev-parse", "--verify", left])
    if code_chk != 0:
        raise ValueError(
            "Нет коммита {0} (история короче {1}). {2}".format(left, n, err_chk or "")
        )

    args = ["diff", "{0}..{1}".format(left, right)]
    if rel:
        args.extend(["--", rel])
    code, out, err = run_git(args)
    if code != 0 and err:
        raise RuntimeError(err)

    log_args = ["log", "--oneline", "-n", str(n + 1), "--decorate"]
    if rel:
        log_args.extend(["--", rel])
    code2, log_out, err2 = run_git(log_args)
    if code2 != 0:
        log_out = ""

    return {
        "from_ref": left,
        "to_ref": right,
        "path": rel or path,
        "diff": out,
        "recent_commits": log_out.splitlines() if log_out else [],
        "hint": (
            "Пустой diff — версии совпадают. "
            "Для файла используйте относительный путь или полный внутри клона."
            if not (out or "").strip()
            else None
        ),
    }


def git_push(force=False):
    if force:
        raise ValueError("git push --force запрещён политикой сервера.")
    info = assert_wealthhub_repo()
    branch = info["current_branch"]
    slug = info.get("repo_slug")
    assert_push_allowed(branch, slug)

    push_url = _authenticated_push_url()
    code, out, err = run_git(["push", push_url, branch])
    if code != 0:
        raise RuntimeError(
            (err or out or "Push failed") +
            ". Проверьте пароль noterball и доступ к Bitbucket."
        )
    return {"branch": branch, "output": out or err}
