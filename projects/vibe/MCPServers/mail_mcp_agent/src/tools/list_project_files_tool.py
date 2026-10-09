import os
from pathlib import Path

from mail_mcp_agent.src.tools.base import BaseTool


class ListProjectFilesTool(BaseTool):
    name = "list_project_files"
    description = (
        "Файлы открытого проекта (cwd из mcpServers): для выбора вложения "
        "или проверки пути перед send_email."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "subpath": {
                    "type": "string",
                    "description": "Подпапка относительно cwd, опционально",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Глубина обхода, по умолчанию 3",
                },
                "glob": {
                    "type": "string",
                    "description": "Маска, например *.csv",
                },
            },
        }

    def execute(self, arguments):
        root = Path(os.getcwd())
        sub = (arguments.get("subpath") or "").strip()
        if sub:
            root = root / sub
        if not root.is_dir():
            raise ValueError("Папка не найдена: {0}".format(root))

        max_depth = arguments.get("max_depth") or 3
        pattern = arguments.get("glob") or "*"
        files = []
        for path in root.rglob(pattern):
            if path.is_file():
                try:
                    rel = path.relative_to(Path(os.getcwd()))
                except ValueError:
                    rel = path
                depth = len(rel.parts)
                if depth <= max_depth:
                    files.append({
                        "path": str(path),
                        "relative": str(rel).replace("\\", "/"),
                        "size_bytes": path.stat().st_size,
                    })
        files.sort(key=lambda x: x["relative"])
        return {
            "working_directory": str(Path(os.getcwd())),
            "root": str(root),
            "files": files[:500],
            "count": len(files),
        }
