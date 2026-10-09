"""Токены подтверждения для commit/push (защита от случайных операций)."""

import hashlib
import time
import uuid
from typing import Dict, Optional

from bitbucket_mcp_agent.resources import settings
from bitbucket_mcp_agent.src.git import git_runner

_store = {}  # type: Dict[str, dict]


def _purge_expired():
    now = time.time()
    expired = [k for k, v in _store.items() if v["expires_at"] < now]
    for key in expired:
        del _store[key]


def _status_fingerprint():
    status = git_runner.git_status()
    porcelain = status.get("porcelain") or ""
    return hashlib.sha256(porcelain.encode("utf-8")).hexdigest()[:16]


def prepare_commit():
    git_runner.assert_wealthhub_repo()
    _purge_expired()
    fp = _status_fingerprint()
    diff = git_runner.git_diff()
    token = str(uuid.uuid4())
    _store[token] = {
        "type": "commit",
        "fingerprint": fp,
        "expires_at": time.time() + settings.CONFIRM_TOKEN_TTL_SEC,
    }
    return {
        "commit_token": token,
        "status_fingerprint": fp,
        "diff_preview": (diff.get("diff") or "")[:8000],
        "expires_in_sec": settings.CONFIRM_TOKEN_TTL_SEC,
        "instruction": (
            "Покажите пользователю diff. Для коммита вызовите git_commit с этим commit_token."
        ),
    }


def validate_commit_token(token):
    # type: (str) -> None
    _purge_expired()
    entry = _store.get(token)
    if not entry or entry.get("type") != "commit":
        raise ValueError("Недействительный commit_token. Вызовите prepare_commit заново.")
    if entry["expires_at"] < time.time():
        del _store[token]
        raise ValueError("commit_token истёк.")
    if entry["fingerprint"] != _status_fingerprint():
        raise ValueError(
            "Рабочая копия изменилась после prepare_commit. Повторите prepare_commit."
        )
    del _store[token]


def prepare_push():
    git_runner.assert_wealthhub_repo()
    info = git_runner.get_repo_info()
    branch = info["current_branch"]
    git_runner.assert_push_allowed(branch, info.get("repo_slug"))

    code, ahead, err = git_runner.run_git([
        "rev-list",
        "--count",
        "origin/{0}..HEAD".format(branch),
    ])
    unpushed = ahead if code == 0 else "?"

    token = str(uuid.uuid4())
    _purge_expired()
    _store[token] = {
        "type": "push",
        "branch": branch,
        "expires_at": time.time() + settings.CONFIRM_TOKEN_TTL_SEC,
    }
    return {
        "push_token": token,
        "branch": branch,
        "unpushed_commits": unpushed,
        "expires_in_sec": settings.CONFIRM_TOKEN_TTL_SEC,
        "instruction": "После согласия пользователя вызовите git_push с push_token.",
    }


def validate_push_token(token):
    # type: (str) -> None
    _purge_expired()
    entry = _store.get(token)
    if not entry or entry.get("type") != "push":
        raise ValueError("Недействительный push_token. Вызовите prepare_push.")
    if entry["expires_at"] < time.time():
        del _store[token]
        raise ValueError("push_token истёк.")
    info = git_runner.get_repo_info()
    if entry["branch"] != info["current_branch"]:
        raise ValueError("Ветка изменилась. Повторите prepare_push.")
    del _store[token]
