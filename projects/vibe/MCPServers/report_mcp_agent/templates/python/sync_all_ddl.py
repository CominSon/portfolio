#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизация DDL проекта с Greenplum.

Запуск из корня object-проекта (…/<Отчёт>/<object_slug>/):
  python python/sync_all_ddl.py

Таблицы/view → sql/ddl/objects/{sources|intermediate|final}/
Функции     → sql/ddl/functions/

Классификация по inventory (sources / intermediate / final_object).
DDL: pg_get_functiondef / pg_get_viewdef / CREATE TABLE из каталога
(как GP MCP get_table_ddl / get_view_ddl / export_function_ddl).

Требует: connectBD, sqlalchemy, psycopg2 в PYTHONPATH.
"""

from __future__ import print_function

import json
import os
import re
import sys
import time

MANIFEST_REL = os.path.join("agent_registry", "REPORT_MANIFEST.json")
LEGACY_MANIFEST = "REPORT_MANIFEST.json"
KIND_DIRS = ("sources", "intermediate", "final")


def find_project_root(start=None):
    path = os.path.abspath(start or os.path.dirname(__file__))
    if os.path.basename(path) == "python":
        path = os.path.dirname(path)
    for _ in range(12):
        if os.path.isfile(os.path.join(path, MANIFEST_REL)) or os.path.isfile(
            os.path.join(path, LEGACY_MANIFEST)
        ):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    raise SystemExit("Не найден REPORT_MANIFEST.json (agent_registry/ или корень)")


def load_manifest(root):
    for rel in (MANIFEST_REL, LEGACY_MANIFEST):
        fp = os.path.join(root, rel)
        if os.path.isfile(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f), fp
    raise SystemExit("manifest не найден")


def split_qualified(q):
    parts = (q or "").split(".", 1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def get_engine():
    from connectBD import use_new_engine
    from sqlalchemy import text

    name = os.environ.get("GP_CONNECTION_NAME", "capgp1_in")
    engine = use_new_engine(name)
    return engine, text


def normalize_ddl(ddl):
    if not ddl:
        return ddl
    text = str(ddl).replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_ddl_file(path, ddl):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalize_ddl(ddl))


def safe_filename(qualified):
    return re.sub(r"[^\w.\-]", "_", qualified) + ".sql"


def classify_kind(qualified, data):
    q = (qualified or "").strip()
    inv = data.get("inventory") or {}
    final_obj = (data.get("final_object") or "").strip()
    sources = set(inv.get("sources") or inv.get("terminal_sources") or [])
    intermediate = set(inv.get("intermediate") or [])
    pxf = set(inv.get("pxf_sources") or [])
    if final_obj and q == final_obj:
        return "final"
    if q in sources or q in pxf:
        return "sources"
    if q in intermediate:
        return "intermediate"
    bare = q.split(".")[-1].lower()
    sch = q.split(".")[0].lower() if "." in q else ""
    if bare.startswith("smd_") and sch.endswith("_in"):
        return "sources"
    writes = {
        (s.get("writes_to") or "").strip()
        for s in (data.get("lineage_steps") or [])
    }
    if q == final_obj or (final_obj and q in writes and q == final_obj):
        return "final"
    return "intermediate"


def collect_targets(data):
    tables = set()
    funcs = set()
    inv = data.get("inventory") or {}

    def add_obj(q, as_func=False):
        q = (q or "").strip()
        if not q or "." not in q:
            return
        sch, name = split_qualified(q)
        if not sch:
            return
        if as_func or name.startswith("p_") or name.startswith("f_"):
            funcs.add(q)
        else:
            tables.add(q)

    for rel in data.get("ddl_objects") or []:
        base = os.path.basename(rel).replace(".sql", "")
        if "." in base:
            tables.add(base)
    for rel in data.get("ddl_functions") or []:
        base = os.path.basename(rel).replace(".sql", "")
        if "." in base:
            funcs.add(base)

    for key in ("sources", "terminal_sources", "intermediate", "pxf_sources", "participants"):
        for part in inv.get(key) or []:
            if isinstance(part, dict):
                part = part.get("target") or part.get("object") or ""
            add_obj(part)

    if data.get("final_object"):
        add_obj(data["final_object"])

    for step in data.get("lineage_steps") or []:
        add_obj(step.get("writes_to"))
        add_obj(step.get("procedure"), as_func=True)
        for src in step.get("reads_from") or []:
            add_obj(src)
        for src in step.get("reference_reads") or []:
            add_obj(src)

    # related_transforms — только functions
    for part in inv.get("related_transforms") or []:
        add_obj(part, as_func=True)

    # не класть процедуры в tables
    tables -= funcs
    return sorted(tables), sorted(funcs)


def fetch_relkind(conn, text, schema, name):
    row = conn.execute(
        text(
            """
            SELECT c.relkind
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :name
            LIMIT 1
            """
        ),
        {"schema": schema, "name": name},
    ).fetchone()
    if not row:
        return None
    try:
        return row._mapping["relkind"]
    except AttributeError:
        return row[0]


def fetch_owner(conn, text, schema, name):
    row = conn.execute(
        text(
            """
            SELECT pg_catalog.pg_get_userbyid(c.relowner) AS owner
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :name
            LIMIT 1
            """
        ),
        {"schema": schema, "name": name},
    ).fetchone()
    if not row:
        return None
    try:
        return row._mapping["owner"]
    except AttributeError:
        return row[0]


def fetch_view_ddl(conn, text, schema, name, matview=False):
    if matview:
        row = conn.execute(
            text(
                """
                SELECT definition
                FROM pg_catalog.pg_matviews
                WHERE schemaname = :schema AND matviewname = :name
                """
            ),
            {"schema": schema, "name": name},
        ).fetchone()
        keyword = "CREATE MATERIALIZED VIEW"
        alter = "ALTER MATERIALIZED VIEW"
    else:
        row = conn.execute(
            text(
                """
                SELECT pg_get_viewdef(:qual::regclass, true) AS definition
                """
            ),
            {"qual": "{0}.{1}".format(schema, name)},
        ).fetchone()
        if not row:
            row = conn.execute(
                text(
                    """
                    SELECT definition
                    FROM pg_catalog.pg_views
                    WHERE schemaname = :schema AND viewname = :name
                    """
                ),
                {"schema": schema, "name": name},
            ).fetchone()
        keyword = "CREATE VIEW"
        alter = "ALTER VIEW"
    if not row:
        return None
    try:
        definition = row._mapping.get("definition") or row[0]
    except AttributeError:
        definition = row[0]
    if not definition:
        return None
    body = definition.strip().rstrip(";")
    ddl = "{0} {1}.{2} AS\n{3};".format(keyword, schema, name, body)
    owner = fetch_owner(conn, text, schema, name)
    if owner:
        ddl += "\n\n{0} {1}.{2} OWNER TO {3};".format(alter, schema, name, owner)
    return ddl


def fetch_table_ddl(conn, text, schema, table):
    """CREATE TABLE с типами из information_schema + OWNER (как GP get_table_ddl)."""
    rows = conn.execute(
        text(
            """
            SELECT
                column_name,
                CASE
                  WHEN data_type = 'character varying' THEN
                    'character varying(' || character_maximum_length || ')'
                  WHEN data_type = 'character' THEN
                    'character(' || character_maximum_length || ')'
                  WHEN data_type = 'numeric' AND numeric_precision IS NOT NULL THEN
                    'numeric(' || numeric_precision || ',' || coalesce(numeric_scale, 0) || ')'
                  WHEN data_type = 'ARRAY' THEN udt_name
                  ELSE data_type
                END AS data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
            """
        ),
        {"schema": schema, "table": table},
    ).fetchall()
    if not rows:
        return None
    col_lines = []
    for row in rows:
        try:
            m = row._mapping
            cname, dtype, nullable, default = (
                m["column_name"],
                m["data_type"],
                m["is_nullable"],
                m["column_default"],
            )
        except AttributeError:
            cname, dtype, nullable, default = row[0], row[1], row[2], row[3]
        bit = "    {0} {1}".format(cname, dtype)
        if default is not None:
            bit += " DEFAULT {0}".format(default)
        if (nullable or "").upper() == "NO":
            bit += " NOT NULL"
        col_lines.append(bit)
    ddl = "CREATE TABLE {0}.{1} (\n{2}\n);".format(
        schema, table, ",\n".join(col_lines)
    )
    owner = fetch_owner(conn, text, schema, table)
    if owner:
        ddl += "\n\nALTER TABLE {0}.{1} OWNER TO {2};".format(schema, table, owner)
    return ddl


def fetch_relation_ddl(conn, text, schema, name):
    """Таблица / view / matview — один вход."""
    kind = fetch_relkind(conn, text, schema, name)
    if kind is None:
        # fallback: попробовать как таблицу
        return fetch_table_ddl(conn, text, schema, name), "table"
    if kind == "v":
        return fetch_view_ddl(conn, text, schema, name, matview=False), "view"
    if kind == "m":
        return fetch_view_ddl(conn, text, schema, name, matview=True), "matview"
    return fetch_table_ddl(conn, text, schema, name), "table"


def fetch_function_ddl(conn, text, schema, name):
    row = conn.execute(
        text(
            """
            SELECT pg_get_functiondef(p.oid) AS ddl
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = :schema AND p.proname = :name
            ORDER BY p.oid
            LIMIT 1
            """
        ),
        {"schema": schema, "name": name},
    ).fetchone()
    if not row:
        return None
    try:
        return row._mapping["ddl"]
    except AttributeError:
        return row[0]


def main():
    t0 = time.time()
    root = find_project_root()
    data, mpath = load_manifest(root)
    print("project:", root)
    print("manifest:", mpath)

    engine, text = get_engine()
    tables, funcs = collect_targets(data)
    print("targets: tables/views={0} functions={1}".format(len(tables), len(funcs)))

    for kind in KIND_DIRS:
        os.makedirs(os.path.join(root, "sql", "ddl", "objects", kind), exist_ok=True)
    fun_dir = os.path.join(root, "sql", "ddl", "functions")
    os.makedirs(fun_dir, exist_ok=True)

    written_objects = []
    written_funcs = []
    errors = []

    # одна транзакция на всё — быстрее, чем begin на каждый объект
    with engine.begin() as conn:
        try:
            conn.execute(text("SET statement_timeout = 120000"))
        except Exception:
            pass

        for q in tables:
            sch, name = split_qualified(q)
            if not sch:
                continue
            try:
                ddl, rel_kind = fetch_relation_ddl(conn, text, sch, name)
                if not ddl:
                    errors.append("no ddl for {0}".format(q))
                    print("FAIL", q, "no ddl")
                    continue
                kind = classify_kind(q, data)
                rel = "sql/ddl/objects/{0}/{1}".format(kind, safe_filename(q))
                path = os.path.join(root, rel.replace("/", os.sep))
                write_ddl_file(path, ddl)
                written_objects.append(rel.replace("\\", "/"))
                print("OK {0} [{1}/{2}]".format(q, kind, rel_kind))
            except Exception as exc:
                errors.append("{0}: {1}".format(q, exc))
                print("FAIL", q, exc)

        for q in funcs:
            sch, name = split_qualified(q)
            if not sch:
                continue
            try:
                ddl = fetch_function_ddl(conn, text, sch, name)
                if not ddl:
                    errors.append("no ddl for function {0}".format(q))
                    print("FAIL function", q, "no ddl")
                    continue
                rel = "sql/ddl/functions/{0}".format(safe_filename(q))
                path = os.path.join(root, rel.replace("/", os.sep))
                write_ddl_file(path, ddl)
                written_funcs.append(rel.replace("\\", "/"))
                print("OK function", q)
            except Exception as exc:
                errors.append("{0}: {1}".format(q, exc))
                print("FAIL function", q, exc)

    data["ddl_objects"] = sorted(set(written_objects))
    data["ddl_functions"] = sorted(set(written_funcs))
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    print(
        "written objects={0} functions={1} errors={2} in {3:.1f}s".format(
            len(written_objects), len(written_funcs), len(errors), elapsed
        )
    )
    if errors:
        for e in errors:
            print(" ERR", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
