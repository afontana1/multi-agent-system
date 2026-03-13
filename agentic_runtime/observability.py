from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


@dataclass
class RuntimeTraceLogger:
    log_dir: Path
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    enabled: bool = True

    def __post_init__(self) -> None:
        self.log_dir = Path(self.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._session_file = self.log_dir / f"session-{self.session_id}.jsonl"

    @property
    def session_file(self) -> Path:
        return self._session_file

    def log(self, event_type: str, **payload: Any) -> None:
        if not self.enabled:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            "payload": _json_safe(payload),
        }
        with self._session_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")


def default_trace_logger() -> RuntimeTraceLogger:
    base_dir = Path(os.getenv("AGENTIC_RUNTIME_LOG_DIR", "logs/sessions"))
    enabled = os.getenv("AGENTIC_RUNTIME_LOGGING", "1").strip().lower() in {"1", "true", "yes", "on"}
    return RuntimeTraceLogger(base_dir, enabled=enabled)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)
