"""Менеджер подключения к Greenplum через корпоративную библиотеку connectBD."""

import logging
import threading

from typing import Any, Dict, List, Optional

from gp_mcp_agent.resources import settings


logger = logging.getLogger("gp_mcp.db")

_engine = None
_DISPOSE_TIMEOUT_SEC = 3


class DatabaseError(Exception):
    """Ошибка при работе с БД."""


def _sql_text(sql):
    from sqlalchemy import text
    return text(sql)


def _apply_session_settings(conn):
    """statement_timeout на каждое соединение (без commit — только SELECT)."""
    conn.execute(
        _sql_text(
            "SET statement_timeout = {0}".format(settings.GP_STATEMENT_TIMEOUT_MS)
        )
    )


def _rows_to_dicts(result):
    rows = []
    for row in result:
        try:
            rows.append(dict(row._mapping))
        except AttributeError:
            try:
                rows.append(dict(row))
            except Exception:
                rows.append({})
    return rows


def _is_stale_connection_error(message):
    msg = (message or "").lower()
    needles = [
        "ssl",
        "server closed the connection unexpectedly",
        "connection reset",
        "connection refused",
        "connection already closed",
        "broken pipe",
        "terminating connection due to administrator command",
        "named cursor isn't valid anymore",
    ]
    for n in needles:
        if n in msg:
            return True
    return False


def _is_timeout_error(message):
    msg = (message or "").lower()
    return (
        "statement timeout" in msg
        or "querycanceled" in msg
        or "canceling statement due to statement timeout" in msg
    )


def _safe_close_connection(conn):
    if conn is None:
        return
    try:
        conn.invalidate()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


def reset_engine(bounded=True):
    # type: (bool) -> None
    """Сброс пула. bounded=True — не блокировать MCP дольше _DISPOSE_TIMEOUT_SEC."""
    global _engine
    if _engine is None:
        return

    engine = _engine
    _engine = None

    def _dispose():
        try:
            engine.dispose()
        except Exception:
            pass

    if not bounded:
        _dispose()
        return

    thread = threading.Thread(target=_dispose, daemon=True)
    thread.start()
    thread.join(_DISPOSE_TIMEOUT_SEC)
    if thread.is_alive():
        logger.warning(
            "engine.dispose() не завершился за %ss — продолжаем без блокировки MCP",
            _DISPOSE_TIMEOUT_SEC,
        )


def get_engine():
    global _engine
    if _engine is not None:
        return _engine

    try:
        from connectBD import use_new_engine
    except ImportError:
        raise DatabaseError(
            "Модуль connectBD недоступен. Убедитесь, что библиотека в PYTHONPATH."
        )

    logger.info("Подключение к Greenplum: %s", settings.GP_CONNECTION_NAME)
    _engine = use_new_engine(settings.GP_CONNECTION_NAME)

    try:
        with _engine.begin() as conn:
            _apply_session_settings(conn)
            conn.execute(_sql_text("SELECT 1"))
    except Exception as exc:
        logger.exception("Не удалось подключиться к Greenplum")
        raise DatabaseError(str(exc))

    logger.info("Подключение к Greenplum установлено")
    return _engine


def _execute_fetch_all(sql, params):
    # type: (str, Dict) -> List[Dict[str, Any]]
    engine = get_engine()
    with engine.begin() as conn:
        _apply_session_settings(conn)
        result = conn.execute(_sql_text(sql), params)
        return _rows_to_dicts(result)


def fetch_all(sql, params=None):
    # type: (str, Optional[Dict]) -> List[Dict[str, Any]]
    params = params or {}
    logger.debug("SQL: %s | params: %s", sql[:500], list(params.keys()))

    last_exc = None
    for attempt in range(2):
        try:
            rows = _execute_fetch_all(sql, params)
            logger.debug("Получено строк: %d", len(rows))
            return rows
        except Exception as exc:
            last_exc = exc
            message = str(exc)
            if attempt == 0 and _is_stale_connection_error(message):
                logger.warning(
                    "Похоже на протухшее соединение (SSL/idle), переподключаемся"
                )
                reset_engine()
                continue
            if _is_timeout_error(message):
                logger.exception("Ошибка SQL (timeout): %s", message[:300])
            else:
                logger.exception("Ошибка SQL: %s", message[:300])
                reset_engine()
            break

    raise DatabaseError(str(last_exc))


def fetch_iter(sql, params=None, batch_size=None):
    # type: (str, Optional[Dict], Optional[int]) -> Any
    """
    Потоковое чтение SELECT батчами (CSV/XLSX).

    Важно (SQLAlchemy 2.x + psycopg2): stream_results даёт named cursor —
    читать fetchmany нужно ДО выхода из транзакции/with. Иначе:
    "named cursor isn't valid anymore".
    """
    params = params or {}
    if batch_size is None:
        batch_size = settings.GP_EXPORT_BATCH_SIZE

    logger.debug("SQL (stream): %s | batch=%s", sql[:500], batch_size)

    try:
        engine = get_engine()
        # begin() держит транзакцию открытой, пока генератор итерируется
        with engine.begin() as conn:
            _apply_session_settings(conn)
            result = conn.execution_options(stream_results=True).execute(
                _sql_text(sql), params
            )
            while True:
                batch = result.fetchmany(batch_size)
                if not batch:
                    break
                for row in batch:
                    try:
                        yield dict(row._mapping)
                    except AttributeError:
                        try:
                            yield dict(row)
                        except Exception:
                            yield {}
    except Exception as exc:
        message = str(exc)
        if _is_timeout_error(message):
            logger.exception("Ошибка SQL (stream, timeout): %s", message[:300])
        else:
            logger.exception("Ошибка SQL (stream): %s", message[:300])
            if not _is_timeout_error(message):
                reset_engine()
        raise DatabaseError(message)


def fetch_scalar(sql, params=None):
    # type: (str, Optional[Dict]) -> Any
    rows = fetch_all(sql, params)
    if not rows:
        return None
    first_row = rows[0]
    if not first_row:
        return None
    return next(iter(first_row.values()))


def table_exists(schema, table):
    # type: (str, str) -> bool
    count = fetch_scalar(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.tables
        WHERE table_schema = :schema AND table_name = :table
        """,
        {"schema": schema, "table": table},
    )
    return bool(count)


def get_current_user():
    # type: () -> str
    user = fetch_scalar("SELECT current_user AS u")
    if user:
        return str(user)
    return fetch_scalar("SELECT session_user AS u") or "unknown"


def validate_schema(schema):
    # type: (str) -> None
    if schema not in settings.GP_ALLOWED_SCHEMAS:
        allowed = ", ".join(settings.GP_ALLOWED_SCHEMAS)
        raise ValueError(
            "Схема '{0}' не разрешена. Допустимые схемы: {1}".format(schema, allowed)
        )
