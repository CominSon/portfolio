"""Авторизация: pen_is.xlsx + noterball(tim2) — как в корпоративном скрипте."""

import getpass
import logging
import os

from mail_mcp_agent.resources import settings

logger = logging.getLogger("mail_mcp.auth")


class AuthError(Exception):
    pass


EMAIL_COLUMN_HINTS = (
    "email", "mail", "MAIL", "PMail", "PMAIL", "E-mail", "Email",
    "Почта", "почта", "SMTP", "smtp",
)


def get_windows_username():
    return getpass.getuser().upper()


def _read_pen_is_data():
    try:
        import pandas as pd
    except ImportError:
        raise AuthError("Требуется pandas для чтения pen_is.xlsx")

    go_to = settings.NOTERBALL_XLSX
    try:
        data = pd.read_excel(go_to, sheetname=settings.NOTERBALL_SHEET)
    except TypeError:
        data = pd.read_excel(go_to, sheet_name=settings.NOTERBALL_SHEET)
    except Exception as exc:
        raise AuthError("Не удалось прочитать {0}: {1}".format(go_to, exc))

    data = data[data["PPT"].apply(lambda x: x.upper()) == getpass.getuser().upper()]
    if data.empty:
        raise AuthError(
            "В pen_is.xlsx нет строки для УЗ {0}".format(getpass.getuser().upper())
        )
    return data


def get_password_from_noterball():
    """
    from noterball import noterball
    data = pd.read_excel(go_to, sheetname='Лист1')
    data = data[data['PPT'].apply(lambda x: x.upper())==getpass.getuser().upper()]
    tim2 = data['PPZ'][(data['PPX'] == max(data['PPX']))]
    password = noterball(tim2)
    """
    try:
        from noterball import noterball
    except ImportError:
        raise AuthError("Модуль noterball не найден. Добавьте путь в PYTHONPATH.")

    data = _read_pen_is_data()
    tim2 = data["PPZ"][(data["PPX"] == max(data["PPX"]))]

    if tim2.empty:
        raise AuthError(
            "PPZ не найден для PPX=max({0})".format(max(data["PPX"]))
        )

    password = noterball(tim2)
    if password is None:
        raise AuthError("noterball(tim2) вернул None")
    password = str(password).strip()
    if not password or password.lower() == "nan":
        raise AuthError("noterball(tim2) вернул пустой пароль")

    logger.debug("Пароль получен: noterball(tim2), len=%s", len(password))
    return password


def _row_for_email(data):
    rows = data[data["PPX"] == max(data["PPX"])]
    if rows.empty:
        return None
    return rows.iloc[0]


def _extract_email_from_row(row):
    if row is None:
        return None
    for col in EMAIL_COLUMN_HINTS:
        if col in row.index:
            val = str(row[col]).strip()
            if "@" in val and val.lower() != "nan":
                return val
    for col in row.index:
        val = str(row[col]).strip()
        if "@" in val and val.lower() != "nan":
            lower = val.lower()
            if "omega" in lower or "sbrf" in lower:
                return val
    return None


def _email_from_outlook():
    try:
        import win32com.client  # type: ignore
        try:
            outlook = win32com.client.GetActiveObject("Outlook.Application")
        except Exception:
            outlook = win32com.client.Dispatch("Outlook.Application")
        for i in range(1, outlook.Session.Accounts.Count + 1):
            account = outlook.Session.Accounts.Item(i)
            smtp = (account.SmtpAddress or "").strip()
            if smtp and "@" in smtp:
                return smtp
        try:
            current = (outlook.Session.CurrentUser.AddressEntry.GetExchangeUser().PrimarySmtpAddress or "").strip()
            if current and "@" in current:
                return current
        except Exception:
            pass
    except Exception as exc:
        logger.debug("Outlook email: %s", exc)
    return None


def get_mail_credentials():
    data = _read_pen_is_data()
    row = _row_for_email(data)
    login = getpass.getuser()
    password = get_password_from_noterball()
    email = (
        _extract_email_from_row(row)
        or _email_from_outlook()
        or os.environ.get("MAIL_MY_EMAIL", "").strip()
        or None
    )
    ppt = str(row["PPT"]) if row is not None else login
    return {
        "login": login,
        "password": password,
        "email": email,
        "ppt": ppt,
    }


def get_mail_login():
    return getpass.getuser()
