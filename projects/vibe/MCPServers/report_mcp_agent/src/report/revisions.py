"""Диалоговые revisions (замечания пользователя к проекту)."""

from datetime import datetime
import uuid

from report_mcp_agent.src.report import manifest


def _now():
    return datetime.now().isoformat(timespec="seconds")


def add_revision(project_root, text, author="user", related_objects=None):
    data = manifest.require_manifest(project_root)
    rev = {
        "id": str(uuid.uuid4())[:8],
        "created_at": _now(),
        "author": author or "user",
        "text": (text or "").strip(),
        "status": "open",
        "related_objects": list(related_objects or []),
        "resolved_at": None,
        "resolution_note": None,
    }
    if not rev["text"]:
        raise ValueError("Текст revision пуст")
    data.setdefault("revisions", []).append(rev)
    manifest.touch_status(
        data,
        phase="revision",
        summary="Открыт revision: {0}".format(rev["text"][:120]),
        done=False,
    )
    manifest.save_manifest(project_root, data)
    return {"ok": True, "revision": rev, "open_count": _open_count(data)}


def resolve_revision(project_root, revision_id, note=None):
    data = manifest.require_manifest(project_root)
    found = None
    for rev in data.get("revisions") or []:
        if rev.get("id") == revision_id or (
            not revision_id and rev.get("status") == "open"
        ):
            found = rev
            if revision_id:
                break
    if not found:
        raise ValueError("Revision не найден: {0}".format(revision_id))
    found["status"] = "resolved"
    found["resolved_at"] = _now()
    found["resolution_note"] = note
    open_n = _open_count(data)
    if open_n == 0:
        manifest.touch_status(data, phase="enrichment", summary="Все revision закрыты")
    manifest.save_manifest(project_root, data)
    return {"ok": True, "revision": found, "open_count": open_n}


def list_open_revisions(data):
    return [r for r in (data.get("revisions") or []) if r.get("status") == "open"]


def _open_count(data):
    return len(list_open_revisions(data))
