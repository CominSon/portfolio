from __future__ import annotations 
from typing import Any, Dict, List
from decimal import Decimal
import datetime
import json 

class EvidenceBuilder:
    """Сбор evidence для вывода (актуальный период + сравнение двух date_update)."""

    def __init__(self, logger, trace_manager):
        self.logger = logger
        self.trace = trace_manager

    def _zone(self, pct: float | None) -> str | None:
        if pct is None:
            return None
        return "green" if pct >= 100 else "red"

    def build(self, ctx, widget_meta, fields_meta, raw_rows, versions) -> dict: 
        """
        Универсальный сбор evidence по метаданным (axis_json + policy_json).

        Ожидаем, что raw_rows уже содержит строки:
        - только для выбранного актуального периода (period_field = max(...) по факту)
        - только для двух последних date_update (versions)
        - только для нужного типа строки (обычно Факт)

        Но build дополнительно устойчив к ситуациям, когда строк больше одной.
        """

        def to_num(x):
            if x is None:
                return None
            if isinstance(x, Decimal):
                return float(x)
            # иногда приходит как str
            try:
                return float(x)
            except Exception:
                return None

        def to_str_date(x):
            if x is None:
                return None
            if isinstance(x, (datetime.date, datetime.datetime)):
                return x.isoformat()
            return str(x)

        axis = json.loads(widget_meta.get("axis_json") or {})
        policy = json.loads(widget_meta.get("policy_json") or {})

        # --- Поля из метаданных ---
        period_field = (axis.get("period") or {}).get("field")

        measures = axis.get("measures") or {}
        fact_field = (measures.get("fact") or {}).get("field")
        pct_field = (measures.get("pct") or {}).get("field")
        delta_field = (measures.get("pct_wow_delta") or {}).get("field")

        # Порог зон (по умолчанию 100)
        zones = policy.get("zones") or {}
        green_if_gte = to_num(zones.get("green_if_gte")) or 100

        # Порог недельной динамики (по умолчанию 3)
        highlight = policy.get("highlight") or {}
        wow_delta_threshold = to_num(highlight.get("wow_delta_points_abs_gte")) or 3

        # --- Разложим строки по date_update ---
        by_ver = {}
        for r in (raw_rows or []):
            v = to_str_date(r.get("date_update"))
            by_ver.setdefault(v, []).append(r)

        last_ver = to_str_date(versions[0]) if len(versions) > 0 else None
        prev_ver = to_str_date(versions[1]) if len(versions) > 1 else None

        def pick_row(ver: str | None):
            """
            Берём одну "главную" строку на версию.
            Если несколько — стараемся выбрать ту, где факт/процент не пустые.
            """
            if not ver:
                return None
            rows = by_ver.get(ver, [])
            if not rows:
                return None
            if len(rows) == 1:
                return rows[0]

            # если строк несколько — выбираем наиболее заполненную по ключевым полям
            def score(rr):
                s = 0
                if rr.get(fact_field) is not None:
                    s += 2
                if rr.get(pct_field) is not None:
                    s += 3
                if rr.get(delta_field) is not None:
                    s += 1
                return s

            rows_sorted = sorted(rows, key=score, reverse=True)
            return rows_sorted[0]

        row_last = pick_row(last_ver)
        row_prev = pick_row(prev_ver)

        # --- Значения ---
        period_value = None
        if row_last and row_last.get(period_field) is not None:
            period_value = row_last.get(period_field)
        elif row_prev and row_prev.get(period_field) is not None:
            period_value = row_prev.get(period_field)

        fact = to_num(row_last.get(fact_field)) if row_last else None
        pct_now = to_num(row_last.get(pct_field)) if row_last else None
        pct_prev = to_num(row_prev.get(pct_field)) if row_prev else None
        wow_delta = to_num(row_last.get(delta_field)) if row_last else None

        def zone(pct: float | None):
            if pct is None:
                return None
            return "green" if pct >= green_if_gte else "red"

        zone_now = zone(pct_now)
        zone_prev = zone(pct_prev)

        transition = None
        if zone_prev and zone_now and zone_prev != zone_now:
            transition = f"{zone_prev}_to_{zone_now}"

        wow_delta_big = (abs(wow_delta) >= wow_delta_threshold) if wow_delta is not None else False
        
        evidence = {
            "виджет": {
                "id_widget": widget_meta.get("id_widget"),
                "название": widget_meta.get("widget_title"),
                "группа": widget_meta.get("group_widget"),
                "описание": widget_meta.get("widget_description_short"),
            },
            "метаданные_полей": {
                "period_field": period_field,
                "fact_field": fact_field,
                "pct_field": pct_field,
                "delta_field": delta_field,
            },
            "версии": {
                "последняя": last_ver,
                "предыдущая": prev_ver,
            },
            "актуальный_период": {
                "поле": period_field,
                "значение": to_str_date(period_value),
            },
            "значения": {
                "fact": fact,
                "pct_now": pct_now,
                "pct_prev": pct_prev,
                "pct_wow_delta": wow_delta,
            },
            "зоны": {
                "green_if_gte": green_if_gte,
                "zone_now": zone_now,
                "zone_prev": zone_prev,
                "transition": transition,
                "is_red_now": (zone_now == "red") if zone_now else None,
            },
            "сигналы": {
                "wow_delta_big": wow_delta_big,
                "wow_delta_threshold": wow_delta_threshold,
            },
            "качество_данных": {
                "строк_на_последней_версии": len(by_ver.get(last_ver, [])) if last_ver else 0,
                "строк_на_предыдущей_версии": len(by_ver.get(prev_ver, [])) if prev_ver else 0,
                "есть_предыдущая_версия": row_prev is not None,
                "дельта_может_быть_null": True,
            }
        }

        # Трасса — что реально собрано (это критично для отладки)
        self.trace.event(ctx, "собран_evidence", {
            "last_ver": last_ver,
            "prev_ver": prev_ver,
            "period_field": period_field,
            "period_value": to_str_date(period_value),
            "fact_field": fact_field,
            "pct_field": pct_field,
            "delta_field": delta_field,
            "fact": fact,
            "pct_now": pct_now,
            "pct_prev": pct_prev,
            "transition": transition,
            "wow_delta": wow_delta,
            "wow_delta_big": wow_delta_big,
            "rows_last": len(by_ver.get(last_ver, [])) if last_ver else 0,
            "rows_prev": len(by_ver.get(prev_ver, [])) if prev_ver else 0,
        })

        return evidence


