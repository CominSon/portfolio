from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def _safe_group_name(group_widget: str) -> str:
    name = (group_widget or "").strip()
    name = re.sub(r"[^\w\-а-яА-ЯёЁ]+", "_", name, flags=re.UNICODE)
    return name.strip("_") or "unknown_group"


class CheckpointManager:
    """
    Промежуточное сохранение по группе.
    Файл: {checkpoint_dir}/checkpoint_{group}.json
    """

    def __init__(self, checkpoint_dir: Optional[str], logger):
        self.checkpoint_dir = (checkpoint_dir or "src/checkpoints").strip() or "src/checkpoints"
        self.logger = logger
        Path(self.checkpoint_dir).mkdir(parents=True, exist_ok=True)

    def path_for(self, group_widget: str) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_{_safe_group_name(group_widget)}.json")

    def load(self, group_widget: str) -> Optional[Dict[str, Any]]:
        path = self.path_for(group_widget)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            if str(data.get("group_widget") or "").strip() != str(group_widget).strip():
                self.logger.warning(
                    f"Checkpoint {path} относится к другой группе "
                    f"({data.get('group_widget')}), игнорирую."
                )
                return None
            return data
        except Exception as e:
            self.logger.warning(f"Не удалось прочитать checkpoint {path}: {type(e).__name__}: {e}")
            return None

    def save(
        self,
        group_widget: str,
        *,
        results: List[Dict[str, Any]],
        processed_widget_ids: List[int],
        stage: str,
        run_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        path = self.path_for(group_widget)
        payload: Dict[str, Any] = {
            "group_widget": group_widget,
            "run_id": run_id,
            "stage": stage,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "processed_widget_ids": sorted({int(x) for x in (processed_widget_ids or [])}),
            "results": results or [],
        }
        if extra:
            payload["extra"] = extra

        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
        os.replace(tmp_path, path)
        self.logger.info(
            f"Checkpoint сохранён: group='{group_widget}', stage={stage}, "
            f"widgets={len(payload['processed_widget_ids'])}, results={len(payload['results'])}, path={path}"
        )
        return path

    def clear(self, group_widget: str) -> None:
        path = self.path_for(group_widget)
        if os.path.exists(path):
            os.remove(path)
            self.logger.info(f"Checkpoint удалён (принудительный перезапуск): {path}")

    def has_checkpoint(self, group_widget: str) -> bool:
        return os.path.exists(self.path_for(group_widget))
