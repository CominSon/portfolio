#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сканирует object-проект отчёта и пишет PROJECT_STRUCTURE.md +
agent_registry/structure_summary.json (контекст для LLM).

Запуск:
  python python/create_structure_md.py

Образец логики — полноценное дерево + каталог файлов (как generate_project_map).
"""

from __future__ import print_function

import json
import os
import sys
from datetime import datetime

OUTPUT_FILE_NAME = "PROJECT_STRUCTURE.md"
SUMMARY_NAME = "structure_summary.json"
MANIFEST_NAME = "REPORT_MANIFEST.json"

EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "logs",
    ".gigacode",
    ".gigaide",
}

EXCLUDED_FILES = {
    ".DS_Store",
    OUTPUT_FILE_NAME,
}

INCLUDE_HIDDEN = False


def find_project_root(start=None):
    path = os.path.abspath(start or os.path.dirname(__file__))
    if os.path.basename(path) == "python":
        path = os.path.dirname(path)
    for _ in range(12):
        if os.path.isfile(os.path.join(path, MANIFEST_NAME)):
            return path
        if os.path.isfile(os.path.join(path, "agent_registry", MANIFEST_NAME)):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    raise SystemExit("Не найден REPORT_MANIFEST.json")


def load_manifest(root):
    for rel in (
        os.path.join("agent_registry", MANIFEST_NAME),
        MANIFEST_NAME,
    ):
        fp = os.path.join(root, rel)
        if os.path.isfile(fp):
            with open(fp, "r", encoding="utf-8") as handle:
                return json.load(handle)
    return {}


def is_hidden(name):
    return name.startswith(".")


def should_skip_dir(name):
    if name in EXCLUDED_DIRS:
        return True
    if not INCLUDE_HIDDEN and is_hidden(name):
        return True
    return False


def should_skip_file(name):
    if name in EXCLUDED_FILES:
        return True
    if not INCLUDE_HIDDEN and is_hidden(name):
        return True
    return False


def format_size(size):
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return "{0} {1}".format(int(value), unit)
            return "{0:.1f} {1}".format(value, unit)
        value /= 1024
    return "{0} B".format(size)


def collect_tree_lines(root):
    lines = [os.path.basename(root.rstrip(os.sep)) + "/"]

    def walk(current, prefix=""):
        try:
            entries = sorted(
                os.listdir(current),
                key=lambda n: (os.path.isfile(os.path.join(current, n)), n.lower()),
            )
        except OSError:
            lines.append(prefix + "└── [нет доступа]")
            return

        filtered = []
        for name in entries:
            full = os.path.join(current, name)
            if os.path.isdir(full):
                if should_skip_dir(name):
                    continue
            else:
                if should_skip_file(name):
                    continue
            filtered.append(name)

        for index, name in enumerate(filtered):
            full = os.path.join(current, name)
            is_last = index == len(filtered) - 1
            branch = "└── " if is_last else "├── "
            next_prefix = prefix + ("    " if is_last else "│   ")
            if os.path.isdir(full):
                lines.append("{0}{1}{2}/".format(prefix, branch, name))
                walk(full, next_prefix)
            else:
                lines.append("{0}{1}{2}".format(prefix, branch, name))

    walk(root)
    return lines


def collect_stats(root):
    stats = {"dirs": 0, "files": 0}
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        stats["dirs"] += len(dirnames)
        for filename in filenames:
            if should_skip_file(filename):
                continue
            stats["files"] += 1
    return stats


def collect_file_catalog(root):
    catalog = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            [d for d in dirnames if not should_skip_dir(d)],
            key=str.lower,
        )
        valid_files = sorted(
            [f for f in filenames if not should_skip_file(f)],
            key=str.lower,
        )
        rel_dir = os.path.relpath(current_root, root).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = "/"
        catalog.append("### `{0}`".format(rel_dir))
        if not valid_files:
            catalog.append("- _(нет файлов напрямую в этой папке)_")
            catalog.append("")
            continue
        for filename in valid_files:
            file_path = os.path.join(current_root, filename)
            try:
                size_text = format_size(os.path.getsize(file_path))
            except OSError:
                size_text = "неизвестный размер"
            suffix = os.path.splitext(filename)[1].lower() or "без расширения"
            catalog.append(
                "- `{0}` — тип: `{1}`, размер: {2}".format(
                    filename, suffix, size_text
                )
            )
        catalog.append("")
    return catalog


def collect_file_entries(root):
    entries = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        rel_dir = os.path.relpath(current_root, root)
        if rel_dir == ".":
            rel_dir = ""
        for name in sorted(filenames):
            if should_skip_file(name):
                continue
            rel = os.path.join(rel_dir, name) if rel_dir else name
            full = os.path.join(current_root, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            entries.append({
                "path": rel.replace("\\", "/"),
                "size_bytes": size,
                "kind": "file",
            })
    return entries


def build_markdown(root, manifest):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats = collect_stats(root)
    tree_lines = collect_tree_lines(root)
    catalog_lines = collect_file_catalog(root)
    title = (manifest or {}).get("report_title") or "Проект отчёта"
    final_obj = (manifest or {}).get("final_object") or "—"
    obj_folder = (manifest or {}).get("object_folder") or os.path.basename(root)
    report_folder = (manifest or {}).get("report_folder") or os.path.basename(
        os.path.dirname(root)
    )

    rules = """
Правила при работе с проектом отчёта:
1) Не придумывай DDL/SQL — бери из БД (refresh_project_ddl / sync_all_ddl.py, get_table_ddl, get_function).
2) Структура: `<Название отчёта>/<object_slug>/` — MCP-корень = object_slug (англ.).
3) DDL таблиц: `sql/ddl/objects/sources|intermediate|final/`; функции — `sql/ddl/functions/`.
4) View = шаг lineage как процедура; helper-функции — related_transforms.
5) После правок lineage — обязательно TECHNICAL.md + lineage.svg (render_report_docs).
""".strip()

    lines = [
        "# {0}".format(title),
        "",
        "**Финальный объект:** `{0}`".format(final_obj),
        "",
        "**Папка отчёта:** `{0}`  |  **Object-проект:** `{1}`".format(
            report_folder, obj_folder
        ),
        "",
        "**Корень MCP:** `{0}`".format(root.replace("\\", "/")),
        "",
        "**Сгенерировано:** `{0}`".format(generated_at),
        "",
        "- Папок: **{0}**".format(stats["dirs"]),
        "- Файлов: **{0}**".format(stats["files"]),
        "",
        "## Правила для агента",
        "",
        rules,
        "",
        "## Назначение папок",
        "",
        "| Папка | Назначение |",
        "|-------|------------|",
        "| `README.md` | Обзор object-проекта |",
        "| `docs/` | TECHNICAL, BUSINESS, lineage.svg |",
        "| `sql/ddl/objects/sources/` | DDL источников |",
        "| `sql/ddl/objects/intermediate/` | DDL промежуточных витрин |",
        "| `sql/ddl/objects/final/` | DDL финального объекта |",
        "| `sql/ddl/functions/` | DDL процедур/функций |",
        "| `sql/dml/` | Run order |",
        "| `python/` | sync_all_ddl, create_structure_md |",
        "| `agent_registry/` | REPORT_MANIFEST.json |",
        "",
        "## Дерево проекта",
        "",
        "```text",
    ]
    lines.extend(tree_lines)
    lines.append("```")
    lines.append("")
    lines.append("## Каталог файлов по папкам")
    lines.append("")
    lines.extend(catalog_lines)
    return "\n".join(lines).rstrip() + "\n"


def main():
    root = find_project_root()
    manifest = load_manifest(root)
    md = build_markdown(root, manifest)
    md_path = os.path.join(root, OUTPUT_FILE_NAME)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(md)

    entries = collect_file_entries(root)
    summary = {
        "project_root": root.replace("\\", "/"),
        "generated_at": datetime.now().isoformat(),
        "report_title": manifest.get("report_title"),
        "final_object": manifest.get("final_object"),
        "object_folder": manifest.get("object_folder"),
        "report_folder": manifest.get("report_folder"),
        "file_count": len(entries),
        "files": entries,
    }
    reg = os.path.join(root, "agent_registry")
    if not os.path.isdir(reg):
        os.makedirs(reg)
    summary_path = os.path.join(reg, SUMMARY_NAME)
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    legacy = os.path.join(root, SUMMARY_NAME)
    if os.path.isfile(legacy):
        try:
            os.remove(legacy)
        except OSError:
            pass

    print("OK: {0}".format(md_path))
    print("OK: {0}".format(summary_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
