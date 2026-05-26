"""
Pipeline run progress writer. Atomically updates reports/progress.json so the
command-center can poll it without reading a partial file.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

_REPORTS_DIR = Path(__file__).parent / "reports"
_PROGRESS_FILE = _REPORTS_DIR / "progress.json"


class ProgressWriter:
    def __init__(self):
        self.run_id: str = ""
        self._stage: int = 0
        self._stage_name: str = ""
        self._started_at: float = 0.0
        self._started_at_iso: str = ""
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def start(self, stage: int, stage_name: str) -> str:
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._stage = stage
        self._stage_name = stage_name
        self._started_at = time.monotonic()
        self._started_at_iso = datetime.now(timezone.utc).isoformat()
        self._write(self._payload(0, "starting", f"Stage {stage} starting…"))
        return self.run_id

    def update(
        self,
        pct: int,
        phase: str = "",
        message: str = "",
        wallets_scanned: int = 0,
        wallets_total: int = 0,
        qualified_so_far: int = 0,
        disqualified_so_far: int = 0,
    ):
        self._write(self._payload(
            pct, phase, message,
            wallets_scanned, wallets_total,
            qualified_so_far, disqualified_so_far,
        ))

    def complete(self):
        data = self._payload(100, "complete", "Run complete")
        data["status"] = "complete"
        self._write(data)

    def error(self, message: str):
        data = self._payload(0, "error", message)
        data["status"] = "error"
        self._write(data)

    # ── internal ──────────────────────────────────────────────────────────────

    def _payload(
        self,
        pct: int,
        phase: str,
        message: str,
        wallets_scanned: int = 0,
        wallets_total: int = 0,
        qualified_so_far: int = 0,
        disqualified_so_far: int = 0,
    ) -> dict:
        return {
            "run_id": self.run_id,
            "status": "running",
            "stage": self._stage,
            "stage_name": self._stage_name,
            "phase": phase,
            "pct": max(0, min(100, pct)),
            "wallets_scanned": wallets_scanned,
            "wallets_total": wallets_total,
            "qualified_so_far": qualified_so_far,
            "disqualified_so_far": disqualified_so_far,
            "message": message,
            "started_at": self._started_at_iso,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - self._started_at, 1),
        }

    def _write(self, data: dict):
        tmp = _PROGRESS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(str(tmp), str(_PROGRESS_FILE))
