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
        # Preserved so complete() can include final scan counts in the payload
        self._last_wallets_scanned: int = 0
        self._last_wallets_total: int = 0
        self._last_qualified: int = 0
        self._last_disqualified: int = 0
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def start(self, stage: int, stage_name: str) -> str:
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._stage = stage
        self._stage_name = stage_name
        self._started_at = time.monotonic()
        self._started_at_iso = datetime.now(timezone.utc).isoformat()
        self._last_wallets_scanned = 0
        self._last_wallets_total = 0
        self._last_qualified = 0
        self._last_disqualified = 0
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
        recent_addresses: list[dict] | None = None,
    ):
        # Track peak values so complete() can include them in the final payload
        if wallets_scanned > self._last_wallets_scanned:
            self._last_wallets_scanned = wallets_scanned
        if wallets_total > self._last_wallets_total:
            self._last_wallets_total = wallets_total
        if qualified_so_far > self._last_qualified:
            self._last_qualified = qualified_so_far
        if disqualified_so_far > self._last_disqualified:
            self._last_disqualified = disqualified_so_far
        self._write(self._payload(
            pct, phase, message,
            wallets_scanned, wallets_total,
            qualified_so_far, disqualified_so_far,
            recent_addresses=recent_addresses,
        ))

    def complete(self):
        # Preserve the peak scan counts so the UI can show a meaningful summary
        data = self._payload(
            100, "complete", "",
            self._last_wallets_scanned, self._last_wallets_total,
            self._last_qualified, self._last_disqualified,
        )
        data["status"] = "complete"
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
        recent_addresses: list[dict] | None = None,
    ) -> dict:
        data: dict = {
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
        if recent_addresses is not None:
            # Short keys keep progress.json small during high-frequency scan writes.
            # a = address, s = "pass" | "fail"
            data["recent_addresses"] = recent_addresses
        return data

    def _write(self, data: dict):
        tmp = _PROGRESS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(str(tmp), str(_PROGRESS_FILE))
