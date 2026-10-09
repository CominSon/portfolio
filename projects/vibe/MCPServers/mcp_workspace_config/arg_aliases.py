"""Алиасы параметров tools (GigaCode шлёт разные имена)."""

import json
import re

from gp_mcp_agent.resources import settings as gp_settings

SCHEMA_SHORT = {
    "work": gp_settings.GP_ALLOWED_SCHEMAS[2],
    "in": gp_settings.GP_ALLOWED_SCHEMAS[1],
    "ext": gp_settings.GP_ALLOWED_SCHEMAS[0],
    "2prod": gp_settings.GP_ALLOWED_SCHEMAS[3],
}


def resolve_gp_schema(name):
    s = (name or "").strip()
    if not s:
        return s
    low = s.lower()
    if low in SCHEMA_SHORT:
        return SCHEMA_SHORT[low]
    for full in gp_settings.GP_ALLOWED_SCHEMAS:
        if low == full.lower():
            return full
    return s


def _pick(d, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return None


def normalize_report_arguments(arguments):
    args = _as_dict(arguments)
    out = dict(args)

    title = _pick(args, "report_title", "reportTitle", "title", "report_name", "name")
    if title:
        out["report_title"] = title

    table = _pick(args, "final_table", "finalTable", "table", "table_name", "tableName")
    if table:
        out["final_table"] = table
        if "." in table and not out.get("final_schema"):
            parts = table.split(".", 1)
            out["final_schema"] = resolve_gp_schema(parts[0])
            out["final_table"] = parts[1]

    schema = _pick(args, "final_schema", "finalSchema", "schema")
    if schema:
        out["final_schema"] = resolve_gp_schema(schema)

    pr = _pick(args, "project_root", "projectRoot", "project_path", "projectPath")
    if pr:
        out["project_root"] = pr
        if not out.get("project_path"):
            out["project_path"] = pr

    for alias in (
        "output_path",
        "outputPath",
        "target_path",
        "targetPath",
        "destination",
        "dest_path",
        "destPath",
        "report_path",
        "reportPath",
    ):
        full = _pick(args, alias)
        if full and not out.get("project_path"):
            out["project_path"] = full
            break

    parent = _pick(args, "parent_path", "parentPath", "parent_directory", "parent")
    if parent:
        out["parent_path"] = parent

    folder = _pick(args, "folder_name", "folderName", "folder")
    if folder:
        out["folder_name"] = folder

    query = _pick(args, "report_query", "reportQuery", "query", "search")
    if query:
        out["report_query"] = query

    adopt = _pick(args, "adopt_existing", "adoptExisting", "adopt")
    if adopt is not None:
        out["adopt_existing"] = str(adopt).lower() in ("true", "1", "yes", "да")

    force_new = _pick(args, "force_new_project", "forceNewProject", "force_new")
    if force_new is not None:
        out["force_new_project"] = str(force_new).lower() in ("true", "1", "yes", "да")

    return out


def normalize_gp_arguments(arguments):
    args = _as_dict(arguments)
    out = dict(args)

    qualified = _pick(args, "qualified", "object", "full_name", "table_qualified")
    if qualified:
        out["qualified"] = qualified

    schema = _pick(args, "schema", "schema_name", "final_schema")
    table = _pick(args, "table", "table_name", "name", "final_table", "object_name")
    if schema:
        out["schema"] = resolve_gp_schema(schema)
    if table:
        out["table"] = table

    if qualified and "." in qualified:
        sch, tbl = qualified.split(".", 1)
        out["schema"] = resolve_gp_schema(sch)
        out["table"] = tbl.strip()
        out["qualified"] = "{0}.{1}".format(out["schema"], out["table"])

    if not out.get("qualified") and out.get("schema") and out.get("table"):
        out["qualified"] = "{0}.{1}".format(out["schema"], out["table"])

    proc = _pick(args, "procedure", "function", "function_name", "proc")
    if proc:
        out["procedure"] = proc
        if "." in proc and not out.get("schema"):
            ps, pn = proc.split(".", 1)
            out["schema"] = resolve_gp_schema(ps)
            out["name"] = pn.strip()

    name = _pick(args, "name", "function_name")
    if name:
        out["name"] = name

    writes = _pick(args, "writes_to", "writesTo", "target_table")
    if writes:
        out["writes_to"] = writes
        if "." in writes:
            ws, wt = writes.split(".", 1)
            out["writes_to"] = "{0}.{1}".format(resolve_gp_schema(ws), wt.strip())

    if args.get("exclude_dtl") is True or str(args.get("exclude_dtl", "")).lower() in ("true", "1"):
        out["exclude_dtl"] = True
        sfx = list(out.get("exclude_name_suffixes") or [])
        if "_dtl" not in sfx:
            sfx.append("_dtl")
        out["exclude_name_suffixes"] = sfx

    return out


def _as_dict(arguments):
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        if "arguments" in arguments and isinstance(arguments["arguments"], dict):
            return dict(arguments["arguments"])
        return dict(arguments)
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return _as_dict(parsed)
        except ValueError:
            pass
    return {}
