"""Загрузка CSV/Excel в таблицу Greenplum (COPY FROM STDIN)."""

import os
import re
from io import StringIO

from gp_mcp_agent.src.db import db_manager


def _pandas():
    import pandas as pd
    return pd


def _numpy():
    import numpy as np
    return np


def _convert_long(column_):
    try:
        return str(column_) if len(str(int(float(column_)))) == 19 else column_
    except Exception:
        return column_


def _convert_to_best_dtype(dataframe):
    pd = _pandas()
    np = _numpy()
    for column in dataframe.columns[dataframe.dtypes == "datetime64[ns]"]:
        dataframe[column] = pd.to_datetime(dataframe[column])
        dataframe[column] = dataframe[column].dt.date.apply(lambda x: str(x))
        dataframe[column] = dataframe[column].replace("NaT", np.nan)
    return dataframe


def _dbapi_connection(sa_conn):
    """Сырой DBAPI connection (psycopg2) из SQLAlchemy Connection — 1.4/2.x."""
    proxied = getattr(sa_conn, "connection", None)
    if proxied is None:
        raise RuntimeError("SQLAlchemy connection не отдаёт DBAPI connection")
    dbapi = getattr(proxied, "dbapi_connection", None)
    if dbapi is None:
        dbapi = getattr(proxied, "driver_connection", None)
    if dbapi is not None:
        return dbapi
    # SQLAlchemy 1.3: .connection уже DBAPI
    return proxied


def _copy_from_stringio(sa_conn, df, table):
    buffer = StringIO()
    df.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    dbapi_conn = _dbapi_connection(sa_conn)
    cursor = dbapi_conn.cursor()
    try:
        cursor.copy_expert("COPY {0} FROM STDIN WITH CSV".format(table), buffer)
    except Exception as error:
        raise RuntimeError("COPY ошибка: {0}".format(error))
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        buffer.close()


def _table_exists(engine, schema, table):
    try:
        from sqlalchemy import inspect
        return inspect(engine).has_table(table, schema=schema)
    except Exception:
        pass
    # fallback для старых dialect API
    try:
        return engine.dialect.has_table(engine, table, schema=schema)
    except Exception:
        return False


def _create_table_if_not_exists(engine, df, table_name):
    schema, table = table_name.split(".", 1)
    if not _table_exists(engine, schema, table):
        df.head(0).to_sql(table, engine, schema=schema, index=False)


def _detect_csv_params(path):
    with open(path, "rb") as handle:
        sample = handle.read(65536)

    encoding = "utf-8"
    for enc in ("utf-8-sig", "utf-8", "cp1251", "windows-1251"):
        try:
            text = sample.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    else:
        text = sample.decode("utf-8", errors="replace")

    first_line = text.splitlines()[0] if text.splitlines() else ""
    counts = {";": first_line.count(";"), ",": first_line.count(","), "\t": first_line.count("\t")}
    delimiter = max(counts, key=counts.get)
    if counts[delimiter] == 0:
        delimiter = ","
    return encoding, delimiter


def _read_dataframe(file_path, encoding, delimiter, sheet_name):
    pd = _pandas()
    path = os.path.abspath(file_path)
    if not os.path.isfile(path):
        raise ValueError("Файл не найден: {0}".format(path))

    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        if not encoding or not delimiter:
            detected_enc, detected_sep = _detect_csv_params(path)
            encoding = encoding or detected_enc
            delimiter = delimiter or detected_sep
        enc = encoding
        sep = delimiter
        df_headers = pd.read_csv(path, encoding=enc, delimiter=sep, nrows=1)
        num_cols = len(df_headers.columns)
        converts = {i: _convert_long for i in range(num_cols)}
        return pd.read_csv(path, encoding=enc, delimiter=sep, converters=converts)

    if ext in (".xlsx", ".xls"):
        if not sheet_name:
            raise ValueError("Для Excel укажите sheet_name")
        try:
            return pd.read_excel(path, sheet_name=sheet_name)
        except TypeError:
            return pd.read_excel(path, sheetname=sheet_name)

    raise ValueError("Поддерживаются .csv, .xlsx, .xls. Получено: {0}".format(ext))


def inspect_load_file(file_path, table_name=None, encoding=None, delimiter=None, sheet_name=None):
    path = os.path.abspath((file_path or "").strip())
    if not os.path.isfile(path):
        raise ValueError("Файл не найден: {0}".format(path))

    ext = os.path.splitext(path)[1].lower()
    questions = []

    if not (table_name or "").strip():
        questions.append({
            "param": "table_name",
            "question": "Введите полное наименование таблицы в Greenplum (schema.table)",
            "example": "s_grnplm_ld_blago_ubhq_work.my_table",
        })

    if ext == ".csv":
        pass
    elif ext in (".xlsx", ".xls"):
        if not sheet_name:
            questions.append({
                "param": "sheet_name",
                "question": "Введите название листа в файле Excel",
            })
    else:
        raise ValueError("Поддерживаются .csv, .xlsx, .xls. Получено: {0}".format(ext))

    if questions:
        detected = {}
        if ext == ".csv":
            try:
                enc, sep = _detect_csv_params(path)
                detected = {"encoding": enc, "delimiter": sep, "auto_detected": True}
            except Exception:
                detected = {}
        return {
            "ok": False,
            "need_user_input": True,
            "file_path": path,
            "file_type": ext.lstrip("."),
            "detected": detected,
            "questions_for_user": questions,
            "message": (
                "Задайте пользователю вопросы из questions_for_user. "
                "Для CSV кодировку и разделитель агент может определить сам (detected)."
            ),
        }

    return {"ok": True, "need_user_input": False, "file_path": path, "file_type": ext.lstrip(".")}


def load_file_to_table(
    file_path,
    table_name,
    encoding=None,
    delimiter=None,
    sheet_name=None,
    truncate=True,
    batch_size=100000,
):
    from sqlalchemy import text

    table_name = (table_name or "").strip()
    if not table_name:
        raise ValueError("table_name обязателен")
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        raise ValueError("table_name должен быть schema.table")

    df = _read_dataframe(file_path, encoding, delimiter, sheet_name)
    df = _convert_to_best_dtype(df)

    engine = db_manager.get_engine()
    _create_table_if_not_exists(engine, df, table_name)

    # SQLAlchemy 2.x: begin() коммитит в конце; не трогаем raw commit/rollback
    with engine.begin() as conn:
        if truncate:
            conn.execute(text("TRUNCATE TABLE {0}".format(table_name)))

        rows_loaded = 0
        for i in range(0, df.shape[0], batch_size):
            part_df = df.iloc[i : i + batch_size]
            _copy_from_stringio(conn, part_df, table_name)
            rows_loaded += len(part_df)

    return {
        "ok": True,
        "file_path": os.path.abspath(file_path),
        "table_name": table_name,
        "rows_loaded": rows_loaded,
        "columns": list(df.columns),
        "truncated": bool(truncate),
    }
