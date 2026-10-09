from __future__ import annotations 

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def _jsonable(obj: Any) -> Any:
    """Приводит типы (Decimal/datetime/date) к JSON-совместимому виду."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return str(obj)


def _load_json_maybe(value: Any, default: Optional[dict] = None) -> dict:
    """axis_json / policy_json могут приходить dict / str (TEXT из БД) / None."""
    if default is None:
        default = {}
    if value is None:
        return dict(default)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return dict(default)
        try:
            obj = json.loads(s)
            # защита от двойного кодирования: json внутри строки
            if isinstance(obj, str):
                try:
                    obj2 = json.loads(obj)
                    return obj2 if isinstance(obj2, dict) else dict(default)
                except Exception:
                    return dict(default)
            return obj if isinstance(obj, dict) else dict(default)
        except Exception:
            return dict(default)
    return dict(default)


def _norm_flag(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip().lower()


def _pick_row_by_flag_priority(
    rows: List[Dict[str, Any]],
    flag_field: Optional[str],
    priority: List[str],
) -> Optional[Dict[str, Any]]:
    """Если в одной версии есть несколько строк (Факт/Прогноз), выбираем по приоритету."""
    if not rows:
        return None
    if not flag_field:
        return rows[0]

    pr = [_norm_flag(x) for x in (priority or []) if x is not None]
    if pr:
        for wanted in pr:
            for r in rows:
                if _norm_flag(r.get(flag_field)) == wanted:
                    return r
    return rows[0]


def _group_rows_by_version(
    rows: List[Dict[str, Any]],
    version_field: str = "date_update",
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows or []:
        v = r.get(version_field)
        v_key = v.isoformat() if isinstance(v, (datetime, date)) else str(v) if v is not None else ""
        grouped.setdefault(v_key, []).append(r)
    return grouped


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(str(x).replace(",", ".").strip())
    except Exception:
        return None


def _calc_zone_and_transition(
    policy_json: dict,
    pct_last_raw: Any,
    pct_prev_raw: Any,
) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    """Считает зону и переход зон по per-widget policy.zones."""
    zones_cfg = (policy_json.get("zones") or {}) if isinstance(policy_json, dict) else {}
    green_gte = _to_float(zones_cfg.get("green_if_pct_gte"))
    red_lt = _to_float(zones_cfg.get("red_if_pct_lt"))

    # дефолты — только если в policy не задано (чтобы старые виджеты не ломались)
    if green_gte is None:
        green_gte = 100.0
    if red_lt is None:
        red_lt = green_gte

    pct_last = _to_float(pct_last_raw)
    pct_prev = _to_float(pct_prev_raw)

    def _zone(pct: Optional[float]) -> Optional[str]:
        if pct is None:
            return None
        if pct >= green_gte:
            return "green"
        if pct < red_lt:
            return "red"
        return "unknown"

    zone_last = _zone(pct_last)
    zone_prev = _zone(pct_prev)

    transition = None
    if zone_last and zone_prev and zone_last != zone_prev:
        transition = {"from": zone_prev, "to": zone_last}

    return zone_last, zone_prev, transition


def _transition_code(transition: Optional[dict]) -> Optional[str]:
    if not isinstance(transition, dict):
        return None
    fr = transition.get("from")
    to = transition.get("to")
    if fr in ("green", "red") and to in ("green", "red") and fr != to:
        return f"{fr}_to_{to}"
    return None


@dataclass
class EvidenceBuilder:
    """Сбор доказательной базы (evidence) для LLM."""

    def __init__(self, logger, trace_manager):
        self.logger = logger
        self.trace = trace_manager
        
    def _to_float(self, v): 
        try:
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip().replace(" ", "").replace(",", ".")
            if s == "":
                return None
            return float(s)
        except Exception:
            return None

    def build(
        self,
        widget_meta: Dict[str, Any],
        raw_rows: List[Dict[str, Any]],
        versions: List[Any],
        selected_period_value: Any,
    ) -> Dict[str, Any]:
        axis_json = _load_json_maybe(widget_meta.get("axis_json"), default={})
        policy_json = _load_json_maybe(widget_meta.get("policy_json"), default={})

        # период (по умолчанию value1)
        period_field: str = (axis_json.get("period") or {}).get("field") or "value1"

        # поле сценария (Факт/Прогноз/План)
        filters = axis_json.get("filters") or {}
        flag_field: Optional[str] = filters.get("flag_field") or filters.get("type_field") or None

        # приоритет выбора строки в рамках одной версии
        flag_priority: List[str] = filters.get("flag_priority") or ["Факт", "Прогноз"]

        # build versions keys
        version_keys: List[str] = []
        for v in (versions or []):
            if isinstance(v, (datetime, date)):
                version_keys.append(v.isoformat())
            else:
                version_keys.append(str(v))

        grouped = _group_rows_by_version(raw_rows or [], version_field="date_update")

        last_ver = version_keys[0] if len(version_keys) > 0 else ""
        prev_ver = version_keys[1] if len(version_keys) > 1 else ""

        last_rows = grouped.get(last_ver, [])
        prev_rows = grouped.get(prev_ver, [])

        last_row = _pick_row_by_flag_priority(last_rows, flag_field, flag_priority)
        prev_row = _pick_row_by_flag_priority(prev_rows, flag_field, flag_priority)

        # fallback: если versions пустой/не совпал, берём по max(date_update)
        if last_row is None and grouped:
            all_vers = sorted(grouped.keys(), reverse=True) # ISO даты сортируются корректно
            last_ver = all_vers[0]
            last_row = _pick_row_by_flag_priority(grouped[last_ver], flag_field, flag_priority)
            if len(all_vers) > 1:
                prev_ver = all_vers[1]
                prev_row = _pick_row_by_flag_priority(grouped[prev_ver], flag_field, flag_priority)

        # Явный сценарий: "Факт"/"Прогноз"/...
        scenario = ""
        if flag_field and last_row is not None:
            scenario = str(last_row.get(flag_field) or "").strip()

        # measures config: {metric_name: {field, unit}}
        measures_cfg = axis_json.get("measures") or {}
        measures: Dict[str, Dict[str, Any]] = {}
        for name, cfg in measures_cfg.items():
            if not isinstance(cfg, dict):
                continue
            fld = cfg.get("field")
            if not fld:
                continue
            measures[name] = {
                "field": fld,
                "unit": cfg.get("unit"),
                "last": _jsonable(last_row.get(fld)) if last_row else None,
                "prev": _jsonable(prev_row.get(fld)) if prev_row else None,
            }

        # ---- зоны + переход зон (строго по policy и pct) ----
        pct_last_raw = (measures.get("pct") or {}).get("last")
        pct_prev_raw = (measures.get("pct") or {}).get("prev")
        zone_last, zone_prev, transition = _calc_zone_and_transition(policy_json, pct_last_raw, pct_prev_raw)
        transition_code = _transition_code(transition)

        # Истинное сравнение "с прошлой неделей" возможно только если есть валидная предыдущая строка.
        comparison_available = prev_row is not None

        zones_block = {
            "green_if_pct_gte": (policy_json.get("zones") or {}).get("green_if_pct_gte"),
            "red_if_pct_lt": (policy_json.get("zones") or {}).get("red_if_pct_lt"),
            "zone_last": zone_last,
            "zone_prev": zone_prev,
            "transition": transition,
            "transition_code": transition_code,
            "comparison_available": comparison_available,
        }

        # Русский отладочный лог (коротко)
        try:
            wid = widget_meta.get("id_widget")
            self.logger.info(
                f"Зоны рассчитаны. Виджет={wid}, сценарий={scenario}, last_ver={last_ver}, prev_ver={prev_ver}, "
                f"pct_last={pct_last_raw}, pct_prev={pct_prev_raw}, зона_last={zone_last}, зона_prev={zone_prev}, "
                f"переход={transition}"
            )
        except Exception:
            # логирование не должно ломать расчёт
            pass

        # Недельные дельты:
        # - current_wow_delta_points: дельта в последней версии
        # - prev_wow_delta_points: дельта в предыдущей версии (её уже посчитал источник данных)
        current_wow_delta_points = self._to_float(((measures.get("pct_wow_delta") or {}).get("last")))
        prev_wow_delta_points = self._to_float(((measures.get("pct_wow_delta") or {}).get("prev")))
        if not comparison_available:
            current_wow_delta_points = None
            prev_wow_delta_points = None
            if "pct_wow_delta" in measures:
                measures["pct_wow_delta"]["last"] = None
                measures["pct_wow_delta"]["prev"] = None

        history = {
            "available": comparison_available,
            "current_wow_delta_points": current_wow_delta_points,
            "prev_wow_delta_points": prev_wow_delta_points,
            "negative_two_weeks": (
                current_wow_delta_points is not None
                and prev_wow_delta_points is not None
                and current_wow_delta_points < 0
                and prev_wow_delta_points < 0
            ),
        }

        evidence = {
            "widget_id": widget_meta.get("id_widget"),
            "group_widget": widget_meta.get("group_widget"),
            "widget_title": widget_meta.get("widget_title"),
            "axis": axis_json,
            "policy": policy_json,
            "fields": widget_meta.get("fields", []),
            "versions": version_keys,
            "last_ver": last_ver,
            "prev_ver": prev_ver,
            "selected_period": _jsonable(selected_period_value),
            "period_field": period_field,
            "flag_field": flag_field,
            "scenario": scenario,
            "last_row": _jsonable(last_row) if last_row else None,
            "prev_row": _jsonable(prev_row) if prev_row else None,
            "measures": measures,
            "zones": _jsonable(zones_block),
            "comparison_available": comparison_available,
            "history": _jsonable(history),
            "notes": [],
        }
        
        # ---------------------------
        # decision: показывать/не показывать этот виджет в отчёте
        # ---------------------------
        highlight = (policy_json or {}).get("highlight", {}) or {}
        always_write = bool((policy_json or {}).get("always_write", False))

        zone_transitions_enabled = bool(highlight.get("zone_transitions", True))
        wow_thr = highlight.get("wow_delta_points_abs_gte", None)
        wow_thr = self._to_float(wow_thr)

        transition = _jsonable(zones_block).get("transition_code")
        zone_last = _jsonable(zones_block).get("zone_last")
        wow_last = history.get("current_wow_delta_points")
        negative_two_weeks = bool(history.get("negative_two_weeks"))

        reasons = []
        should_write = False

        if always_write:
            should_write = True
            reasons.append("always_write=true")
        else:
            if zone_transitions_enabled and transition:
                should_write = True
                reasons.append(f"zone_transition={transition}")
            if zone_last == "red":
                should_write = True
                reasons.append("red_zone")
            if (wow_thr is not None) and (wow_last is not None):
                if abs(wow_last) >= wow_thr:
                    should_write = True
                    reasons.append(f"wow_abs_gte={wow_thr}")
            if negative_two_weeks:
                should_write = True
                reasons.append("negative_two_weeks")

        non_zone_reasons = [r for r in reasons if r != "red_zone"]

        decision = {
            "should_write": should_write,
            "reasons": reasons,
            "transition": transition,
            "wow_delta_points": wow_last,
            "comparison_available": comparison_available,
            "has_non_zone_trigger": bool(non_zone_reasons),
            "only_attention": bool(zone_last == "red" and not non_zone_reasons and not always_write),
            "negative_two_weeks": negative_two_weeks,
        }

        evidence["decision"] = decision


        return evidence
