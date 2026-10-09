from __future__ import annotations
from typing import Any, Dict, List, Optional, Set
import json


class WidgetAnalyzer:
    def __init__(
        self,
        metadata_repo,
        nav_repo,
        evidence_builder,
        summary_agent,
        logger,
        trace_manager,
        checkpoint_manager=None,
    ):
        self.meta = metadata_repo
        self.nav = nav_repo
        self.evidence_builder = evidence_builder
        self.agent = summary_agent
        self.logger = logger
        self.trace = trace_manager
        self.checkpoint = checkpoint_manager

    def run_group(
        self,
        ctx,
        group_widget: str,
        *,
        force_restart: bool = False,
    ) -> List[Dict[str, Any]]:
        ctx.group_widget = group_widget
        widgets = self.meta.get_widgets_by_group(group_widget)
        self.trace.event(ctx, "группа_загружена", {"группа": group_widget, "количество_виджетов": len(widgets)})

        results: List[Dict[str, Any]] = []
        processed_ids: Set[int] = set()

        if force_restart and self.checkpoint:
            self.checkpoint.clear(group_widget)

        checkpoint = None
        if self.checkpoint and not force_restart:
            checkpoint = self.checkpoint.load(group_widget)

        if checkpoint:
            results = list(checkpoint.get("results") or [])
            processed_ids = {int(x) for x in (checkpoint.get("processed_widget_ids") or [])}
            stage = checkpoint.get("stage") or "widgets"
            self.logger.info(
                f"Resume из checkpoint: group='{group_widget}', stage={stage}, "
                f"уже обработано виджетов={len(processed_ids)}, результатов={len(results)}"
            )
            self.trace.event(ctx, "checkpoint_loaded", {
                "group_widget": group_widget,
                "stage": stage,
                "processed_cnt": len(processed_ids),
                "results_cnt": len(results),
            })
            # Если виджеты уже полностью пройдены — сразу возвращаем сохранённые результаты
            if stage in ("widgets_done", "final", "done") and processed_ids:
                widget_ids = {int(w.get("id_widget")) for w in widgets if w.get("id_widget") is not None}
                if widget_ids.issubset(processed_ids):
                    self.logger.info(
                        f"Все виджеты группы '{group_widget}' уже в checkpoint — "
                        f"пропускаю LLM по виджетам, перехожу к финальным этапам."
                    )
                    return results

        for w in widgets:
            ctx.widget_id = int(w.get("id_widget"))
            if ctx.widget_id in processed_ids:
                self.logger.info(f"Виджет {ctx.widget_id} уже в checkpoint — пропуск.")
                self.trace.event(ctx, "widget_resumed_skip", {"id_widget": ctx.widget_id})
                continue

            self.trace.event(ctx, "старт_виджета", {"id_widget": ctx.widget_id, "название": w.get("widget_title")})

            fields = self.meta.get_widget_fields(ctx.widget_id)
            deps = self.meta.get_widget_dependencies(ctx.widget_id)
            self.trace.event(ctx, "зависимости_загружены", {"зависимости": deps})

            axis_json = json.loads(w.get("axis_json") or "{}")
            period_field = (axis_json.get("period") or {}).get("field") or "value1"
            filters = axis_json.get("filters") or {}
            flag_field = filters.get("flag_field") or filters.get("type_field")

            # Берём несколько версий: текущая, прошлая и (при наличии) позапрошлая.
            # Это нужно для устойчивых сравнений недельной динамики.
            versions = self.nav.get_last_versions(ctx.widget_id, limit=3)

            # 1) Берём актуальный период  по последней date_update
            period_value = None
            if versions:
                period_value = self.nav.get_latest_period_value1(
                    widget_id=ctx.widget_id,
                    last_date_update=versions[0],
                    period_field=period_field,
                    flag_field=flag_field,
                )

            # 2) Берём строки только этого периода на последних date_update.
            # Для исторических версий дополнительно отсеиваем пустой факт.
            raw_rows = []
            if period_value and versions:
                fact_field = ((axis_json.get("measures") or {}).get("fact") or {}).get("field")
                raw_rows = self.nav.fetch_rows_for_period_and_versions(
                    widget_id=ctx.widget_id,
                    period_value=period_value,
                    versions=versions,
                    period_field=period_field,
                    flag_field=flag_field,
                    fact_field=fact_field,
                    last_date_update=versions[0],
                )

            self.trace.event(ctx, "выбран_актуальный_период", {
                "date_update_последняя": versions[0] if versions else None,
                "date_update_предыдущая": versions[1] if len(versions) > 1 else None,
                "актуальный_период": str(period_value) if period_value else None,
                "строк_по_периоду": len(raw_rows)
            })

            evidence = self.evidence_builder.build(w, raw_rows, versions, period_value)

            # --- скрываем "необязательные" виджеты до LLM ---
            decision = evidence.get("decision") or {}
            should_write = bool(decision.get("should_write", True))
            if not should_write:
                self.trace.event(ctx, "widget_skipped", {
                    "id_виджета": ctx.widget_id,
                    "reasons": decision.get("reasons", []),
                    "transition": decision.get("transition"),
                    "wow_delta_points": decision.get("wow_delta_points"),
                })
                processed_ids.add(ctx.widget_id)
                self._persist_checkpoint(ctx, group_widget, results, processed_ids, stage="widgets")
                continue

            summary = self.agent.summarize_widget(ctx, w, evidence)

            results.append({"widget_id": ctx.widget_id, "summary": summary, "evidence": evidence})
            processed_ids.add(ctx.widget_id)
            self.trace.event(ctx, "завершение_виджета", {"id_widget": ctx.widget_id, "write_mode": summary.get("write_mode")})
            self._persist_checkpoint(ctx, group_widget, results, processed_ids, stage="widgets")

        self._persist_checkpoint(ctx, group_widget, results, processed_ids, stage="widgets_done")
        return results

    def _persist_checkpoint(
        self,
        ctx,
        group_widget: str,
        results: List[Dict[str, Any]],
        processed_ids: Set[int],
        stage: str,
    ) -> None:
        if not self.checkpoint:
            return
        self.checkpoint.save(
            group_widget,
            results=results,
            processed_widget_ids=sorted(processed_ids),
            stage=stage,
            run_id=getattr(ctx, "run_id", None),
        )
