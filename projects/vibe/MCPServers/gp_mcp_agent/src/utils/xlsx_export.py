"""Выгрузка SQL в XLSX с корректными типами колонок для Excel."""

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.utils.csv_export import _cell_value
from gp_mcp_agent.src.utils.export_paths import (
    export_result,
    project_exports_dir,
    timestamped_filename,
)


def _column_kind(column_name, sample_values):
    name = (column_name or "").lower()
    if re.search(r"(id|num|code|inn|ogrn|account|счет|номер)", name):
        return "text"

    non_empty = [v for v in sample_values if v is not None and str(v) != ""]
    if not non_empty:
        return "general"

    if all(isinstance(v, (datetime, date)) for v in non_empty):
        return "date"
    if all(isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) for v in non_empty):
        if any(isinstance(v, int) and abs(v) > 9999999999 for v in non_empty):
            return "text"
        return "number"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_empty):
        if any(abs(v) > 9999999999 for v in non_empty):
            return "text"
        return "number"
    return "text"


def _apply_format(cell, kind):
    if kind == "text":
        cell.number_format = "@"
    elif kind == "date":
        cell.number_format = "yyyy-mm-dd hh:mm:ss"
    elif kind == "number":
        cell.number_format = "#,##0.##########"


def write_sql_to_xlsx(sql, filename_prefix, column_order=None, params=None):
    try:
        from openpyxl import Workbook
    except ImportError:
        raise RuntimeError(
            "Для XLSX нужен пакет openpyxl. Установите: pip install openpyxl"
        )

    params = params or {}
    export_dir = Path(project_exports_dir())
    file_path = export_dir / timestamped_filename(filename_prefix, "xlsx")

    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = "data"

    row_count = 0
    columns = None
    sample_by_col = {}
    max_rows = settings.GP_EXPORT_MAX_ROWS
    data_rows = []

    for row in db_manager.fetch_iter(sql, params):
        if columns is None:
            columns = column_order or list(row.keys())
            ws.append(columns)

        values = []
        for col in columns:
            raw = row.get(col)
            values.append(_cell_value(raw))
            sample_by_col.setdefault(col, []).append(raw)
            if len(sample_by_col[col]) > 200:
                sample_by_col[col] = sample_by_col[col][-200:]

        data_rows.append(values)
        row_count += 1
        if max_rows and row_count > max_rows:
            raise ValueError(
                "Превышен лимит выгрузки GP_EXPORT_MAX_ROWS={0}".format(max_rows)
            )

    if row_count == 0:
        ws.append(["no_rows"])
    else:
        for values in data_rows:
            ws.append(values)

        col_kinds = {
            col: _column_kind(col, sample_by_col.get(col, []))
            for col in (columns or [])
        }
        for row_idx in range(2, row_count + 2):
            for col_idx, col in enumerate(columns or [], start=1):
                _apply_format(ws.cell(row=row_idx, column=col_idx), col_kinds[col])

    wb.save(str(file_path))
    result = export_result(file_path, row_count, columns or [])
    result["format"] = "xlsx"
    result["note"] = "Выгрузка XLSX. Длинные числа и ID — как текст, даты — как даты."
    return result
