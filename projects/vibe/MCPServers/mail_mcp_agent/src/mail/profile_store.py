"""Профиль почты: автозаполнение из noterball / pen_is / Outlook."""

import json

from mail_mcp_agent.resources import settings
from mail_mcp_agent.src.utils.safe_path import package_root


def _config_dir():
    base = package_root(__file__) / settings.PROFILE_SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def _profile_path():
    return _config_dir() / settings.PROFILE_FILENAME


def load_profile():
    path = _profile_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return {}


def save_profile(data):
    path = _profile_path()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return {
        "profile_path": str(path),
        "config_directory": str(_config_dir()),
        "saved": True,
    }


def get_my_email():
    return (load_profile().get("my_email") or "").strip()


def get_mail_login_saved():
    return (load_profile().get("mail_login") or "").strip()


def sync_from_noterball():
    """Авто: email и login из pen_is / Outlook. Пароль не сохраняется."""
    from mail_mcp_agent.src.auth import noterball_auth

    creds = noterball_auth.get_mail_credentials()
    data = load_profile()
    data["mail_login"] = creds["login"]
    data["ppt"] = creds.get("ppt")
    data["auto_configured"] = True
    if creds.get("email"):
        data["my_email"] = creds["email"]
    data.pop("mail_password", None)
    save_profile(data)
    return creds


def set_my_email(email):
    """Ручное переопределение (обычно не требуется)."""
    email = (email or "").strip()
    if not email or "@" not in email:
        raise ValueError("Укажите корректный email")
    data = load_profile()
    data["my_email"] = email
    result = save_profile(data)
    result["my_email"] = email
    return result
