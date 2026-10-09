"""MCP tools report-project v3 — workspace + диалог (без оркестратора GP)."""

import logging
import subprocess
import sys
from pathlib import Path

from report_mcp_agent.resources import settings
from report_mcp_agent.src.report import (
    context,
    docs_render,
    files,
    lineage_store,
    manifest,
    path_resolve,
    revisions,
    scaffold,
    validators,
)
from report_mcp_agent.src.tools.base import BaseTool
from report_mcp_agent.src.utils.arg_coerce import coerce_project_args
from report_mcp_agent.src.utils.tool_errors import tool_error

logger = logging.getLogger("report_mcp.tools")


def _root_from_args(arguments, required=True):
    args = coerce_project_args(arguments)
    root = (args.get("project_root") or args.get("project_path") or "").strip()
    if not root and required:
        active = None
        try:
            from mcp_workspace_config.active_report_project import get_active_report_project
            active = get_active_report_project()
        except Exception:
            active = None
        if active and active.get("project_root"):
            root = active["project_root"]
    if required and not root:
        raise ValueError("Укажите project_path / project_root или откройте проект (resume).")
    return root, args


def _activate(project_root, data=None):
    try:
        from mcp_workspace_config.active_report_project import set_active_report_project
        data = data or manifest.load_manifest(project_root) or {}
        set_active_report_project(
            project_root,
            report_title=data.get("report_title"),
            final_object=data.get("final_object"),
        )
    except Exception as exc:
        logger.warning("active project: %s", exc)


class HealthcheckReportTool(BaseTool):
    name = "healthcheck_report"
    description = "Проверка report MCP: шаблоны, запись, активный проект."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        tpl = Path(__file__).resolve().parents[2] / "templates" / "docs"
        missing = [n for n in settings.ALLOWED_DOC_FILES if not (tpl / n).is_file()]
        active = None
        try:
            from mcp_workspace_config.active_report_project import get_active_report_project
            active = get_active_report_project()
        except Exception:
            pass
        return {
            "ok": not missing,
            "server": settings.SERVER_NAME,
            "version": settings.SERVER_VERSION,
            "templates_ok": not missing,
            "missing_templates": missing,
            "active_project": active,
            "mode": "agent-driven",
        }


class StartReportProjectTool(BaseTool):
    name = "start_report_project"
    description = (
        "Создать каркас: <Название отчёта>/<object_slug>/ "
        "(slug из final_table, напр. qs_t_ukp_weeks → ukp_weeks; "
        "или object_folder / просьба пользователя). "
        "Внутри — docs/sql/…; objects делятся на sources|intermediate|final. "
        "Не вызывает GP. Существующая папка: project_path + adopt."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "report_title": {"type": "string"},
                "final_table": {"type": "string"},
                "final_schema": {"type": "string"},
                "project_path": {"type": "string"},
                "parent_path": {
                    "type": "string",
                    "description": "Родитель, внутри создастся <отчёт>/<object_slug>/",
                },
                "folder_name": {
                    "type": "string",
                    "description": "Имя верхней папки отчёта (по умолчанию = report_title)",
                },
                "object_folder": {
                    "type": "string",
                    "description": "Английская подпапка объекта (иначе из final_table)",
                },
                "adopt": {"type": "boolean"},
            },
            "required": ["report_title", "final_table"],
        }

    def execute(self, arguments):
        args = coerce_project_args(arguments)
        title = (args.get("report_title") or "").strip()
        table = (args.get("final_table") or "").strip()
        schema = (args.get("final_schema") or settings.DEFAULT_FINAL_SCHEMA).strip()
        if not title or not table:
            return tool_error("report_title и final_table обязательны")
        if "." in table and not args.get("final_schema"):
            schema, table = table.split(".", 1)
        root = path_resolve.resolve_new_project_path(args)
        adopt = bool(args.get("adopt"))
        if root.is_dir() and (
            (root / settings.AGENT_REGISTRY_DIR / settings.MANIFEST_FILENAME).is_file()
            or (root / settings.MANIFEST_FILENAME).is_file()
        ) and not adopt:
            adopt = True
        result = scaffold.scaffold_project(
            root,
            title,
            schema,
            table,
            adopt=adopt,
            object_folder=args.get("object_folder"),
        )
        _activate(result["project_root"], result.get("manifest"))
        return result


class ResumeReportProjectTool(BaseTool):
    name = "resume_report_project"
    description = (
        "Открыть существующий проект по пути или поиску report_query. "
        "Не пересоздаёт каркас — для продолжения диалога."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "project_root": {"type": "string"},
                "report_query": {"type": "string"},
                "search_root": {"type": "string"},
            },
        }

    def execute(self, arguments):
        args = coerce_project_args(arguments)
        root = (args.get("project_root") or args.get("project_path") or "").strip()
        if not root:
            query = (args.get("report_query") or "").strip()
            search = (args.get("search_root") or str(Path.cwd())).strip()
            hits = path_resolve.find_projects(search, query=query, limit=10)
            if not hits:
                return tool_error(
                    "Проект не найден",
                    hint="Укажите project_path или уточните report_query",
                )
            if len(hits) > 1 and query:
                return {
                    "ok": False,
                    "need_choice": True,
                    "candidates": hits,
                    "message": "Несколько проектов — уточните путь",
                }
            root = hits[0]["project_root"]
        data = manifest.require_manifest(root)
        _activate(root, data)
        return {
            "ok": True,
            "project_root": str(root),
            "report_title": data.get("report_title"),
            "final_object": data.get("final_object"),
            "status": data.get("status"),
            "open_revisions": revisions.list_open_revisions(data),
            "next": "get_report_context",
        }


class FindReportProjectsTool(BaseTool):
    name = "find_report_projects"
    description = "Поиск папок с REPORT_MANIFEST.json."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "search_root": {"type": "string"},
                "report_query": {"type": "string"},
                "limit": {"type": "integer"},
            },
        }

    def execute(self, arguments):
        args = coerce_project_args(arguments)
        search = (args.get("search_root") or str(Path.cwd())).strip()
        query = (args.get("report_query") or args.get("query") or "").strip()
        limit = int(args.get("limit") or 20)
        hits = path_resolve.find_projects(search, query=query, limit=limit)
        return {"ok": True, "projects": hits, "count": len(hits)}


class GetReportStatusTool(BaseTool):
    name = "get_report_status"
    description = "Краткий статус проекта без тяжёлого контекста."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "project_root": {"type": "string"},
            },
        }

    def execute(self, arguments):
        root, _ = _root_from_args(arguments)
        data = manifest.require_manifest(root)
        return {
            "ok": True,
            "project_root": root,
            "report_title": data.get("report_title"),
            "final_object": data.get("final_object"),
            "status": data.get("status"),
            "lineage_steps": len(data.get("lineage_steps") or []),
            "open_revisions": len(revisions.list_open_revisions(data)),
            "ddl_objects": len(data.get("ddl_objects") or []),
            "ddl_functions": len(data.get("ddl_functions") or []),
        }


class GetReportContextTool(BaseTool):
    name = "get_report_context"
    description = (
        "Полный контекст для агента: lineage, открытые revision, пробелы, "
        "playbook, extra_knowledge. Вызывать перед планом доработки."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "project_root": {"type": "string"},
            },
        }

    def execute(self, arguments):
        root, _ = _root_from_args(arguments)
        return context.build_context(root)


class AddReportRevisionTool(BaseTool):
    name = "add_report_revision"
    description = (
        "Зафиксировать замечание пользователя. Агент дорабатывает тот же проект "
        "и каскадно обновляет TECHNICAL/BUSINESS/DDL/SVG/run_order, не только один файл."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "text": {"type": "string"},
                "related_objects": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "author": {"type": "string"},
            },
            "required": ["text"],
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        result = revisions.add_revision(
            root,
            args.get("text"),
            author=args.get("author") or "user",
            related_objects=args.get("related_objects"),
        )
        from report_mcp_agent.src.report.lineage_protocol import protocol_dict

        result["cascade_hint"] = (
            "НЕ полный перезапуск пирамиды. Удалите лишнее через remove_lineage_objects, "
            "затем каскад docs/SVG/DDL по checklist."
        )
        result["cascade_checklist"] = protocol_dict()["revision_mode"]["cascade_checklist"]
        return result


class ResolveReportRevisionTool(BaseTool):
    name = "resolve_report_revision"
    description = "Закрыть revision после доработки."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "revision_id": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["revision_id"],
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return revisions.resolve_revision(
            root, args.get("revision_id"), note=args.get("note")
        )


class UpsertLineageStepTool(BaseTool):
    name = "upsert_lineage_step"
    description = (
        "Добавить/обновить шаг lineage (procedure → writes_to, reads_from). "
        "Данные агент получает из GP get_function / get_link_object."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "procedure": {"type": "string"},
                "writes_to": {"type": "string"},
                "reads_from": {"type": "array", "items": {"type": "string"}},
                "reference_reads": {"type": "array", "items": {"type": "string"}},
                "write_role": {"type": "string"},
                "branch_role": {"type": "string"},
                "notes": {"type": "string"},
                "schedule": {"type": "object"},
            },
            "required": ["procedure", "writes_to"],
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return lineage_store.upsert_lineage_step(
            root,
            procedure=args.get("procedure"),
            writes_to=args.get("writes_to"),
            reads_from=args.get("reads_from"),
            reference_reads=args.get("reference_reads"),
            write_role=args.get("write_role"),
            branch_role=args.get("branch_role"),
            notes=args.get("notes"),
            schedule=args.get("schedule"),
        )


class UpdateInventoryTool(BaseTool):
    name = "update_inventory"
    description = (
        "Обновить inventory: sources (не «терминальные»), intermediate, "
        "related_transforms (helper-функции преобразований), builders, pxf/pcopy."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Реальные источники (не промежуточные витрины/view)",
                },
                "terminal_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Устарело: алиас sources",
                },
                "builders": {"type": "array", "items": {"type": "string"}},
                "loaders": {"type": "array", "items": {"type": "string"}},
                "intermediate": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Промежуточные витрины/таблицы",
                },
                "related_transforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Смежные функции преобразования значений (не writers)",
                },
                "pxf_sources": {"type": "array", "items": {"type": "string"}},
                "pcopy_sources": {"type": "array"},
            },
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return lineage_store.update_inventory(
            root,
            sources=args.get("sources"),
            terminal_sources=args.get("terminal_sources"),
            builders=args.get("builders"),
            loaders=args.get("loaders"),
            intermediate=args.get("intermediate"),
            pxf_sources=args.get("pxf_sources"),
            pcopy_sources=args.get("pcopy_sources"),
            related_transforms=args.get("related_transforms"),
        )


class UpsertScheduleEntryTool(BaseTool):
    name = "upsert_schedule_entry"
    description = (
        "Одна запись расписания на объект (без дублей) для TECHNICAL §5 и SVG. "
        "kind=procedure|pxf|pcopy. Обязательно schedule_label вида «пн–пт 06:15» "
        "(из get_procedure_schedule), не голое «daily». "
        "После правок — обязательно render_report_docs (TECHNICAL)."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "kind": {"type": "string", "description": "procedure | pxf | pcopy"},
                "object": {"type": "string"},
                "target": {
                    "type": "string",
                    "description": "Справочно; не создаёт вторую строку в §5",
                },
                "summary": {"type": "object"},
                "schedule_label": {
                    "type": "string",
                    "description": "пн–пт 06:15 — для SVG и таблицы порядка запуска",
                },
                "last_success": {"type": "string"},
                "cadence": {"type": "string"},
                "note": {"type": "string"},
                "pxf_table_name": {"type": "string"},
            },
            "required": ["kind", "object"],
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return lineage_store.upsert_schedule_entry(
            root,
            kind=args.get("kind"),
            object_name=args.get("object"),
            target=args.get("target"),
            summary=args.get("summary"),
            schedule_label=args.get("schedule_label"),
            last_success=args.get("last_success"),
            cadence=args.get("cadence"),
            note=args.get("note"),
            pxf_table_name=args.get("pxf_table_name"),
        )


class RemoveLineageObjectsTool(BaseTool):
    name = "remove_lineage_objects"
    description = (
        "Удалить лишние процедуры/таблицы из lineage при доработке "
        "(не полный перезапуск). Затем каскад: render_report_docs + BUSINESS."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "objects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "qualified таблицы для удаления",
                },
                "procedures": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "qualified процедуры для удаления",
                },
            },
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return lineage_store.remove_lineage_objects(
            root,
            objects=args.get("objects"),
            procedures=args.get("procedures"),
        )


class SetExtraKnowledgeTool(BaseTool):
    name = "set_extra_knowledge"
    description = (
        "Доп. знания для проекта: заметки, имена таблиц-словарей описаний, "
        "SQL-запросы справочников. Агент использует при BUSINESS/TECHNICAL."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "[{id, kind: note|table|query|dict, title, content?, table?, query?}]"
                    ),
                },
                "replace": {"type": "boolean"},
            },
            "required": ["items"],
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return lineage_store.set_extra_knowledge(
            root, args.get("items") or [], replace=bool(args.get("replace"))
        )


class WriteReportFileTool(BaseTool):
    name = "write_report_file"
    description = (
        "Записать файл в проект (docs/*, sql/ddl/*, sql/dml/*). "
        "Для DDL из GP: register_ddl=true."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "relative_path": {"type": "string"},
                "content": {"type": "string"},
                "register_ddl": {"type": "boolean"},
            },
            "required": ["relative_path", "content"],
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return files.write_project_file(
            root,
            args.get("relative_path"),
            args.get("content"),
            register_ddl=bool(args.get("register_ddl")),
        )


class ReadReportFileTool(BaseTool):
    name = "read_report_file"
    description = "Прочитать файл проекта (для точечной доработки)."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "relative_path": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["relative_path"],
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return files.read_project_file(
            root,
            args.get("relative_path"),
            max_chars=int(args.get("max_chars") or 200000),
        )


class ListReportFilesTool(BaseTool):
    name = "list_report_files"
    description = "Список файлов проекта (опционально prefix=sql/ddl/)."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "prefix": {"type": "string"},
            },
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return files.list_project_files(root, prefix=args.get("prefix"))


class RenderReportDocsTool(BaseTool):
    name = "render_report_docs"
    description = (
        "Собрать TECHNICAL.md, 00_run_order.sql и при необходимости BUSINESS.md "
        "из текущего manifest (mermaid, таблица шагов). BUSINESS по семплам агент "
        "дописывает отдельно через write_report_file."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "overwrite_business": {"type": "boolean"},
            },
        }

    def execute(self, arguments):
        root, args = _root_from_args(arguments)
        return docs_render.render_all(
            root, overwrite_business=bool(args.get("overwrite_business"))
        )


class ValidateReportProjectTool(BaseTool):
    name = "validate_report_project"
    description = "Проверка полноты: docs, lineage, DDL, закрытые revision."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "project_root": {"type": "string"},
            },
        }

    def execute(self, arguments):
        root, _ = _root_from_args(arguments)
        return validators.validate_project(root)


class RefreshProjectStructureTool(BaseTool):
    name = "refresh_project_structure"
    description = "Обновить PROJECT_STRUCTURE.md скриптом python/create_structure_md.py."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
            },
        }

    def execute(self, arguments):
        root, _ = _root_from_args(arguments)
        script = Path(root) / "python" / "create_structure_md.py"
        if not script.is_file():
            return tool_error("Нет python/create_structure_md.py")
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
        }


class RefreshProjectDdlTool(BaseTool):
    name = "refresh_project_ddl"
    description = (
        "Синхронизировать все DDL в sql/ddl с БД через python/sync_all_ddl.py "
        "(pg_get_functiondef сохраняет DEFAULT). Не выдумывать DDL вручную."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
            },
        }

    def execute(self, arguments):
        root, _ = _root_from_args(arguments)
        script = Path(root) / "python" / "sync_all_ddl.py"
        if not script.is_file():
            return tool_error(
                "Нет python/sync_all_ddl.py",
                hint="Пересоздайте каркас или скопируйте шаблон из report_mcp_agent/templates/python/",
            )
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
            "hint": (
                "При ошибке connectBD проверьте PYTHONPATH. "
                "DDL функций берите как есть (DEFAULT аргументов)."
            ),
        }
