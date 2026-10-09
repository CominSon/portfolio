"""Выгрузка произвольного объёма строк в CSV (пакетная чтение из БД)."""

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.utils.export_paths import (
    export_result,
    project_exports_dir,
    timestamped_filename,
)


def _cell_value(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    return value


def write_sql_to_csv(sql, filename_prefix, column_order=None, params=None):
    # type: (str, str, list, dict) -> dict
    """
    Выполнить SELECT и записать все строки в CSV (батчами).
    Лимит строк: GP_EXPORT_MAX_ROWS (0 = без лимита, только statement_timeout БД).
    """
    params = params or {}
    export_dir = Path(project_exports_dir())
    file_path = export_dir / timestamped_filename(filename_prefix, "csv")

    row_count = 0
    columns = None
    max_rows = settings.GP_EXPORT_MAX_ROWS

    with file_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = None
        for row in db_manager.fetch_iter(sql, params):
            if writer is None:
                columns = column_order or list(row.keys())
                writer = csv.DictWriter(
                    handle,
                    fieldnames=columns,
                    extrasaction="ignore",
                    lineterminator="\n",
                )
                writer.writeheader()

            writer.writerow(
                {col: _cell_value(row.get(col)) for col in columns}
            )
            row_count += 1

            if max_rows and row_count > max_rows:
                raise ValueError(
                    "Превышен лимит выгрузки GP_EXPORT_MAX_ROWS={0}".format(
                        max_rows
                    )
                )

    if row_count == 0:
        columns = columns or []
        with file_path.open("w", newline="", encoding="utf-8-sig") as handle:
            csv.writer(handle).writerow(["no_rows"])

    return export_result(file_path, row_count, columns or [])
