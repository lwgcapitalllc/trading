"""The gap gate refuses an export that turns the equal-level exemption on without its settings.

Until 2026-09-10 it fell back to 2 / 0.1 / 6 for such a file - the equal-level settings from before
2026-09-09, an eighth copy of three numbers still on the old values a day after the other seven
moved. No harness here has ever written that shape, so the fallback could only ever run on a file
it would guess wrong about.

The fixture is the committed golden export with columns REMOVED, never a hand-built one, so it
cannot answer anything the real harness does not write (rule 13).

Mutation (watched RED): put the fallback back - build the equal-level engine off defaults when a
column is missing - and every case here fails.
"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_TOOL = _HERE.parents[1] / "tools" / "compare_fvg.py"
_GOLDEN = _HERE.parents[1] / "exports" / "golden" / "VANTAGE_XAUUSD_M15_20187bars_plain.csv"
_EQ_COLS = ("cfg_eq_pivotlen", "cfg_eq_atrmult", "cfg_eq_max")


def _tool():
    spec = importlib.util.spec_from_file_location("compare_fvg_under_test", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _export_without(tmp_path, drop, rows=60):
    with open(_GOLDEN, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        body = [r for _, r in zip(range(rows), reader)]
    keep = [i for i, h in enumerate(header) if not h.strip().lower().endswith(drop)]
    out = tmp_path / "export.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([header[i] for i in keep])
        w.writerows([[r[i] for i in keep] for r in body])
    return out


def test_the_premise_the_golden_export_turns_the_exemption_on_and_says_how():
    """Without this the cases below could pass on a file that never reached the refusal."""
    with open(_GOLDEN, newline="") as f:
        reader = csv.DictReader(f)
        rows = [r for _, r in zip(range(5), reader)]
        header = reader.fieldnames
    cfg = _tool()._read_cfg(header, rows)
    assert cfg.get("eq_exempt") == 1
    assert {"eq_pivotlen", "eq_atrmult", "eq_max"} <= set(cfg)


@pytest.mark.parametrize("drop", [(c,) for c in _EQ_COLS] + [_EQ_COLS])
def test_a_missing_equal_level_setting_is_refused_and_named(tmp_path, drop):
    path = _export_without(tmp_path, drop)
    with pytest.raises(SystemExit) as exc:
        _tool().main([str(path)])
    msg = str(exc.value)
    assert "EQ exemption ON" in msg
    for col in drop:
        assert col in msg
    for col in set(_EQ_COLS) - set(drop):
        assert col not in msg
