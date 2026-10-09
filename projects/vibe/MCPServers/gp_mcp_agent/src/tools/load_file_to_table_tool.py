from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.file_loader import load_file_to_table, inspect_load_file


class LoadFileToTableTool(BaseTool):
    name = "load_file_to_table"
    description = (
        "Загрузить CSV или Excel в таблицу Greenplum (COPY), как скрипт LABA_LOAD. "
        "Если пользователь дал только путь к файлу — вернёт questions_for_user; "
        "задайте их в чате и вызовите снова со всеми параметрами."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Полный путь к .csv / .xlsx / .xls",
                },
                "table_name": {
                    "type": "string",
                    "description": "Полное имя schema.table в Greenplum",
                },
                "encoding": {
                    "type": "string",
                    "description": "Кодировка CSV: utf-8, windows-1251",
                },
                "delimiter": {
                    "type": "string",
                    "description": "Разделитель CSV: ; или ,",
                },
                "sheet_name": {
                    "type": "string",
                    "description": "Имя листа Excel",
                },
                "truncate": {
                    "type": "boolean",
                    "description": "Очистить таблицу перед загрузкой (по умолчанию true)",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments):
        file_path = (arguments.get("file_path") or "").strip()
        if not file_path:
            raise ValueError("Укажите путь к файлу (file_path)")

        pending = inspect_load_file(
            file_path,
            table_name=arguments.get("table_name"),
            encoding=arguments.get("encoding"),
            delimiter=arguments.get("delimiter"),
            sheet_name=arguments.get("sheet_name"),
        )
        if pending.get("need_user_input"):
            return pending

        detected = pending.get("detected") or {}
        encoding = arguments.get("encoding") or detected.get("encoding")
        delimiter = arguments.get("delimiter") or detected.get("delimiter")

        truncate = arguments.get("truncate")
        if truncate is None:
            truncate = True
        elif isinstance(truncate, str):
            truncate = truncate.strip().lower() not in ("false", "0", "no")

        return load_file_to_table(
            file_path=file_path,
            table_name=arguments.get("table_name"),
            encoding=encoding,
            delimiter=delimiter,
            sheet_name=arguments.get("sheet_name"),
            truncate=truncate,
        )
