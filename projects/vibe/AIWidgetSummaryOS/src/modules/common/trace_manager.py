import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from decimal import Decimal
import datetime

def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")

@dataclass
class TraceContext:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    group_widget: Optional[str] = None
    widget_id: Optional[int] = None

class TraceManager:
    """Трасса решений агента в формате jsonl."""

    def __init__(self, trace_dir: str, logger):
        self.trace_dir = trace_dir
        self.logger = logger
        Path(self.trace_dir).mkdir(parents=True, exist_ok=True)

    def _file_path(self, ctx: TraceContext) -> str:
        return os.path.join(self.trace_dir, f"трасса_{ctx.run_id}.jsonl")
    
    def _json_defaults(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return str(0)
    
    def event(self, ctx: TraceContext, step: str, payload: Dict[str, Any]):
        rec = {
            "время": _now_iso(),
            "run_id": ctx.run_id,
            "группа": ctx.group_widget,
            "id_виджета": ctx.widget_id,
            "шаг": step,
            "данные": payload,
        }
        fp = self._file_path(ctx)
        with open(fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=self._json_defaults) + "\n")

        self.logger.info(f"[ТРАССА] шаг='{step}' run_id={ctx.run_id} id_виджета={ctx.widget_id}")

    def path(self, ctx: TraceContext) -> str:
        return self._file_path(ctx)
