"""Авторизация Bitbucket: pen_is.xlsx + noterball(tim2)."""

import getpass
import logging

from bitbucket_mcp_agent.resources import settings

logger = logging.getLogger("bb_mcp.auth")


class AuthError(Exception):
    pass


def get_windows_username():
    return getpass.getuser().upper()


def get_password():
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
        raise AuthError("Модуль noterball не найден в PYTHONPATH.")

    try:
        import pandas as pd
    except ImportError:
        raise AuthError("Требуется pandas.")

    go_to = settings.NOTERBALL_XLSX
    try:
        data = pd.read_excel(go_to, sheetname=settings.NOTERBALL_SHEET)
    except TypeError:
        data = pd.read_excel(go_to, sheet_name=settings.NOTERBALL_SHEET)
    except Exception as exc:
        raise AuthError("Не удалось прочитать {0}: {1}".format(go_to, exc))

    data = data[data["PPT"].apply(lambda x: x.upper()) == getpass.getuser().upper()]
    if data.empty:
        raise AuthError("Нет строки в pen_is для УЗ {0}".format(getpass.getuser().upper()))

    tim2 = data.loc[data["PPX"] == data["PPX"].max(), "PPZ"]
    if tim2.empty:
        raise AuthError("PPZ не найден для PPX=max({0})".format(data["PPX"].max()))
    # noterball ожидает скаляр — Series[0] даёт IndexError при нестандартном индексе
    password = noterball(tim2.iloc[0])
    if password is None:
        raise AuthError("noterball(tim2) вернул None")
    password = str(password).strip()
    if not password or password.lower() == "nan":
        raise AuthError("noterball(tim2) вернул пустой пароль")
    return password


def get_git_username():
    return getpass.getuser()
