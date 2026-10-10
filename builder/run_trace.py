"""Plain-text, secret-safe builder run traces."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FREYA_KEY_PATTERN = re.compile(r"fak_[A-Za-z0-9_-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceWriter:
    """Collect and write the trace fields required by the starter kit."""

    def __init__(self, path: Path, started_at: str | None = None) -> None:
        self.path = path
        self.lines = [f"start_utc: {started_at or utc_now()}"]
        self._secret_values = tuple(
            value
            for name in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY")
            if (value := os.environ.get(name))
        )

    def _safe(self, value: Any) -> str:
        text = str(value).replace("\r", " ").replace("\n", " ")
        for secret in self._secret_values:
            text = text.replace(secret, "[REDACTED]")
        return FREYA_KEY_PATTERN.sub("[REDACTED]", text)

    def add(self, key: str, value: Any) -> None:
        self.lines.append(f"{self._safe(key)}: {self._safe(value)}")

    def add_input(self, path: Path) -> None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.add("input", f"{path} sha256={digest}")

    def add_model_call(self, model: str, purpose: str, duration_seconds: float) -> None:
        self.add(
            "model_call",
            f"model={model} purpose={purpose} duration_seconds={duration_seconds:.3f}",
        )

    def finish(self, status: str = "ok") -> None:
        self.add("status", status)
        self.add("end_utc", utc_now())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
