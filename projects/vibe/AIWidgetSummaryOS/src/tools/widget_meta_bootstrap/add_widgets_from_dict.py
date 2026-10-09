from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from dotenv import load_dotenv

# Запуск как отдельного скрипта: добавляем корень src в sys.path.
SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.common.sql_utils import safe_col
from modules.db.postgres_manager import PostgresManager


def _setup_logger() -> tuple[logging.Logger, str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = os.path.join("logs")
    os.makedirs(logs_dir, exist_ok=True)
    main_log_path = os.path.join(logs_dir, f"widget_meta_bootstrap_{ts}.log")
    skip_log_path = os.path.join(logs_dir, f"widget_meta_bootstrap_skips_{ts}.log")

    logger = logging.getLogger("widget_meta_bootstrap")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(main_log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger, main_log_path, skip_log_path


def _append_skip(skip_file: str, message: str) -> None:
    with open(skip_file, "a", encoding="utf-8") as f:
        f.write(message.strip() + "\n")


def _parse_launch_input(raw: str) -> tuple[list[int], int, bool]:
    """
    Поддерживаем форматы:
      [[1001, 1002], 1006]
      ["all", 1006]
      [all, 1006]
    """
    candidate = raw.strip()
    if not candidate:
        raise ValueError("Пустой ввод.")

    normalized = candidate.replace("'", '"')
    normalized = re.sub(r'(?<=\[|,|\s)all(?=\s|,|\])', '"all"', normalized, flags=re.IGNORECASE)

    payload: Any = None
    try:
        payload = json.loads(normalized)
    except Exception:
        payload = ast.literal_eval(candidate)

    if not isinstance(payload, (list, tuple)) or len(payload) != 2:
        raise ValueError("Ожидался формат из 2 элементов: [<список|all>, <id эталона>].")

    ids_part, etalon_part = payload
    try:
        etalon_id = int(etalon_part)
    except Exception as e:
        raise ValueError(f"Некорректный id эталона: {etalon_part}") from e

    if isinstance(ids_part, str) and ids_part.strip().lower() == "all":
        return [], etalon_id, True

    if not isinstance(ids_part, (list, tuple)):
        raise ValueError("Первый элемент должен быть списком id или all.")

    ids: list[int] = []
    for x in ids_part:
        ids.append(int(x))
    return ids, etalon_id, False


def _parse_excluded_ids(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    parts = re.split(r"[,\s]+", raw.strip())
    out: set[int] = set()
    for p in parts:
        if not p:
            continue
        out.add(int(p))
    return out


def _iter_dicts(obj: Any) -> Iterable[dict]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_dicts(it)


def _extract_value_fields(payload: Any) -> set[str]:
    found: set[str] = set()

    def check(s: Any) -> None:
        if not isinstance(s, str):
            return
        m = re.fullmatch(r"value\d+", s.strip().lower())
        if m:
            found.add(m.group(0))

    if isinstance(payload, dict):
        for k, v in payload.items():
            check(k)
            check(v)
    elif isinstance(payload, list):
        for it in payload:
            check(it)
    return found


def _is_fact_unit_description(text: str) -> bool:
    t = " ".join(str(text).lower().split())
    # Нужна именно единица измерения факта (допускаем частые опечатки "едениц")
    has_target_phrase = bool(
        re.search(r"ед[ие]ниц\w*\s+измер\w*\s+факт\w*", t)
    )
    has_delta = ("дельт" in t) or ("delta" in t)
    return has_target_phrase and not has_delta


def _find_fact_unit_field(json_name_values_raw: Any) -> tuple[Optional[str], str]:
    """
    Возвращает (поле, причина_ошибки).
    Причина пустая, если поле найдено однозначно.
    """
    raw_text = str(json_name_values_raw or "").strip()
    if not raw_text:
        return None, "json_name_values пустой"

    parsed: Any
    try:
        parsed = json.loads(raw_text)
    except Exception:
        # Частый кейс в источнике: одинарный backslash в значениях (например: "Факт\План"),
        # что ломает строгий JSON-парсер. Пытаемся мягко "дочинить" такие escape-последовательности.
        try:
            fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", raw_text)
            parsed = json.loads(fixed)
        except Exception:
            parsed = None

    candidates: set[str] = set()
    if parsed is not None:
        for d in _iter_dicts(parsed):
            # Важно: проверяем связь "конкретный key=valueN -> его описание",
            # а не весь dict целиком, иначе можно ошибочно захватить все value-поля.
            for k, v in d.items():
                if not isinstance(k, str):
                    continue
                key = k.strip().lower()
                if not re.fullmatch(r"value\d+", key):
                    continue
                if isinstance(v, str) and _is_fact_unit_description(v):
                    candidates.add(key)

    # fallback через regex по сырому тексту:
    # сначала пытаемся выделить пары вида valueN -> "описание"
    if not candidates:
        pair_pattern = re.compile(
            r'["]{1,2}(value\d+)["]{1,2}\s*:\s*["]{1,2}([^"\n\r]+)["]{1,2}',
            flags=re.IGNORECASE,
        )
        for m in pair_pattern.finditer(raw_text):
            field = (m.group(1) or "").lower()
            desc = (m.group(2) or "").strip()
            if field and _is_fact_unit_description(desc):
                candidates.add(field)

    # fallback второго уровня: контекстный поиск рядом с valueN
    if not candidates:
        near_pattern = re.compile(
            r"(value\d+)[^\n\r]{0,90}?(ед[ие]ниц\w*\s+измер\w*\s+факт\w*)",
            flags=re.IGNORECASE,
        )
        for m in near_pattern.finditer(raw_text):
            field = (m.group(1) or "").lower()
            desc = (m.group(2) or "").lower()
            if field and _is_fact_unit_description(desc):
                candidates.add(field)

    if len(candidates) == 1:
        return next(iter(candidates)), ""
    if not candidates:
        return None, "не найдено однозначное описание 'Единицы измерения факта'"
    return None, f"найдено несколько полей для единицы факта: {sorted(candidates)}"


def _replace_description_prefix(old_description: str, widget_title: str, unit: str) -> str:
    old_description = old_description or ""
    tail = ""
    if "\n" in old_description:
        _, tail = old_description.split("\n", 1)
        tail = "\n" + tail
    prefix = f"{widget_title}, {unit}.".strip()
    return prefix + tail


def _update_axis_units(axis_json_raw: str, unit: str) -> str:
    axis = json.loads(axis_json_raw) if isinstance(axis_json_raw, str) else (axis_json_raw or {})
    measures = axis.get("measures") or {}
    for key in ("fact", "plan"):
        if isinstance(measures.get(key), dict):
            measures[key]["unit"] = unit
    axis["measures"] = measures
    return json.dumps(axis, ensure_ascii=False)


def main() -> None:
    load_dotenv()
    logger, log_path, skip_path = _setup_logger()
    logger.info("Старт скрипта автодобавления виджетов в ai_os_ub_widget_meta")

    ai_schema = os.getenv("AI_META_SCHEMA")
    nav_table = os.getenv("OS_UB_NAV_TABLE")
    dict_table = os.getenv("OS_UB_DICT_WIDGETS_TABLE") or f"{ai_schema}.os_ub_dict_widgets"
    meta_table = f"{ai_schema}.ai_os_ub_widget_meta"

    if not ai_schema or not nav_table:
        raise RuntimeError("Нужны переменные окружения AI_META_SCHEMA и OS_UB_NAV_TABLE.")

    print("Введите режим: [[id1,id2,...], etalon_id] или [all, etalon_id]")
    raw_mode = input(">>> ").strip()
    requested_ids, etalon_id, all_mode = _parse_launch_input(raw_mode)

    pg = PostgresManager(logger)
    pg.connect()
    try:
        if all_mode:
            dict_ids_rows = pg.execute_sql_query(
                f"SELECT DISTINCT id_widget FROM {dict_table} WHERE id_widget IS NOT NULL",
                fetchall=True,
            ) or []
            meta_ids_rows = pg.execute_sql_query(
                f"SELECT DISTINCT id_widget FROM {meta_table} WHERE id_widget IS NOT NULL",
                fetchall=True,
            ) or []
            dict_ids = {int(r["id_widget"]) for r in dict_ids_rows}
            meta_ids = {int(r["id_widget"]) for r in meta_ids_rows}
            target_ids = sorted(dict_ids - meta_ids)

            print(
                f"Найдено {len(target_ids)} id, отсутствующих в ai_os_ub_widget_meta. "
                "Введите id для исключения через запятую:"
            )
            raw_ex = input(">>> ").strip()
            excluded = _parse_excluded_ids(raw_ex)
            target_ids = [x for x in target_ids if x not in excluded]
        else:
            target_ids = requested_ids

        logger.info(f"Целевые id: {target_ids}")
        logger.info(f"Эталонный id: {etalon_id}")

        etalon = pg.execute_sql_query(
            f"""
            SELECT id_widget, group_widget, widget_title, widget_description_short,
                   axis_json, dependencies_json, policy_json, prompt_template_id
            FROM {meta_table}
            WHERE id_widget = %s
            LIMIT 1
            """,
            etalon_id,
            fetchall=False,
        )
        if not etalon:
            raise RuntimeError(f"Эталонный виджет id={etalon_id} не найден в {meta_table}.")

        inserted = 0
        skipped = 0
        for wid in target_ids:
            # 1) Пропускаем, если уже есть
            exists = pg.execute_sql_query(
                f"SELECT 1 AS ok FROM {meta_table} WHERE id_widget = %s LIMIT 1",
                wid,
                fetchall=False,
            )
            if exists:
                msg = f"id_widget={wid}: уже есть в ai_os_ub_widget_meta, пропуск."
                logger.info(msg)
                _append_skip(skip_path, msg)
                skipped += 1
                continue

            # 2) Берём исходные атрибуты виджета из справочника
            dict_row = pg.execute_sql_query(
                f"""
                SELECT id_widget, group_widget, name_widget, json_name_values
                FROM {dict_table}
                WHERE id_widget = %s
                LIMIT 1
                """,
                wid,
                fetchall=False,
            )
            if not dict_row:
                msg = f"id_widget={wid}: не найден в {dict_table}, пропуск."
                logger.warning(msg)
                _append_skip(skip_path, msg)
                skipped += 1
                continue

            group_widget = (dict_row.get("group_widget") or "").strip()
            widget_title = (dict_row.get("name_widget") or "").strip()
            if not group_widget or not widget_title:
                msg = f"id_widget={wid}: не заполнены group_widget/name_widget в справочнике, пропуск."
                logger.warning(msg)
                _append_skip(skip_path, msg)
                skipped += 1
                continue

            # 3) Определяем поле единицы измерения факта
            unit_field, unit_err = _find_fact_unit_field(dict_row.get("json_name_values"))
            if not unit_field:
                msg = f"id_widget={wid}: {unit_err}, пропуск."
                logger.warning(msg)
                _append_skip(skip_path, msg)
                skipped += 1
                continue

            # 4) Берём саму единицу измерения из основной таблицы данных
            unit_col = safe_col(unit_field)
            unit_row = pg.execute_sql_query(
                f"""
                SELECT {unit_col} AS unit_value
                FROM {nav_table}
                WHERE id_widget = %s
                  AND NULLIF(TRIM(COALESCE({unit_col}::text, '')), '') IS NOT NULL
                ORDER BY date_update DESC
                LIMIT 1
                """,
                wid,
                fetchall=False,
            )
            unit = str((unit_row or {}).get("unit_value") or "").strip()
            if not unit:
                msg = (
                    f"id_widget={wid}: поле единицы факта {unit_field} найдено, "
                    f"но значение unit не получено из {nav_table}, пропуск."
                )
                logger.warning(msg)
                _append_skip(skip_path, msg)
                skipped += 1
                continue

            # 5) Строим запись по эталону
            new_desc = _replace_description_prefix(
                old_description=str(etalon.get("widget_description_short") or ""),
                widget_title=widget_title,
                unit=unit,
            )
            new_axis_json = _update_axis_units(str(etalon.get("axis_json") or "{}"), unit)

            pg.execute_sql_query(
                f"""
                INSERT INTO {meta_table} (
                    id_widget, group_widget, widget_title, widget_description_short,
                    axis_json, dependencies_json, policy_json, prompt_template_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                wid,
                group_widget,
                widget_title,
                new_desc,
                new_axis_json,
                etalon.get("dependencies_json"),
                etalon.get("policy_json"),
                etalon.get("prompt_template_id"),
                fetchall=False,
            )
            logger.info(
                f"id_widget={wid}: вставлен по эталону {etalon_id} "
                f"(group='{group_widget}', title='{widget_title}', unit='{unit}', unit_field='{unit_field}')"
            )
            inserted += 1

        logger.info(f"Готово. Вставлено: {inserted}, пропущено: {skipped}.")
        logger.info(f"Лог: {log_path}")
        logger.info(f"Лог пропусков: {skip_path}")
    finally:
        pg.close()


if __name__ == "__main__":
    main()

