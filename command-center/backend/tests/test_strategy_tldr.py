"""The TL;DR at the top of every strategy page — `tldr` in <Strategy>.meta.json.

A bullet may carry `{param}` tokens, filled on the page with that setting's DEFAULT, and a
`show_if`, which shows the bullet only while it holds against the defaults. So the text states no
number of its own and cannot quietly outlive a default that moved.

🔴 EVERY FAILURE HERE IS SILENT ON THE PAGE. A token naming a setting that does not exist renders
as the literal `{typo}`; a `show_if` naming a missing setting hides its bullet for ever; a bullet
whose condition stopped holding simply disappears and the summary loses a line. None of that
errors, so these check that each meta file RESOLVES against the schema the scanner builds.
"""

from __future__ import annotations

import functools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as cfg  # noqa: E402
from models import Strategy  # noqa: E402
from services import lab_db, strategy_scanner  # noqa: E402
from services.stress_tester import _cond_holds, _reader_for  # noqa: E402

_ROOT = Path(cfg.MONOREPO_ROOT)
_STRATS = _ROOT / "strategies"
_TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

# The page is a summary: past seven bullets it is the parameter table again, and a bullet that
# wraps past one line on a laptop is a paragraph. Both are the complaint this section answers.
_MIN_BULLETS, _MAX_BULLETS = 3, 7
_MAX_CHARS = 150


@functools.lru_cache(maxsize=1)
def _rows() -> tuple:
    """Every strategy the scanner registers, parsed exactly the way the scanner parses it."""
    rows = []
    for cs in sorted(_STRATS.rglob("*.cs")):
        src = cs.read_text(encoding="utf-8", errors="replace")
        if re.search(r"public\s+class\s+\w+\s*:\s*Strategy\b", src):
            row = strategy_scanner._parse_file(cs, _ROOT, source=src)
            if row:
                rows.append(row)
    for mq5 in sorted(_STRATS.rglob("*.mq5")):
        src = mq5.read_text(encoding="utf-8", errors="replace")
        row = strategy_scanner._parse_mql5_file(mq5, _ROOT, source=src)
        if row:
            rows.append(row)
    for pkg in sorted((_STRATS / "python").iterdir()):
        if (pkg / "__init__.py").exists():
            row, err = strategy_scanner._parse_python_package(pkg, _ROOT)
            assert err is None, err
            if row:
                rows.append(row)
    return tuple(rows)


def _is_on_off(p: dict) -> bool:
    return p.get("type") == "bool" or p.get("widget") in ("toggle", "switch")


def test_the_scan_found_the_strategies_it_should():
    """The vacuity guard: every check below iterates this list, and an empty one passes them all."""
    ids = {r["id"] for r in _rows()}
    for sid in ("sos_fade", "extreme_leg", "orb", "londonbreakout"):
        assert sid in ids, f"the scan did not find {sid} — every check below would pass vacuously"


def test_every_strategy_has_a_tldr():
    """A strategy added without one opens on the four-step flow and the parameter table, which is
    what the owner could not read. Written for the NEXT strategy, as much as for these."""
    missing = [r["id"] for r in _rows() if not r.get("tldr")]
    assert not missing, f"no TL;DR in the meta file of: {missing}"
    for r in _rows():
        n = len(r["tldr"])
        assert _MIN_BULLETS <= n <= _MAX_BULLETS, f"{r['id']}: {n} bullets"


def test_every_bullet_is_one_short_line():
    for r in _rows():
        for b in r.get("tldr", []):
            text = b["text"]
            assert "\n" not in text, f"{r['id']}: a bullet is one line — {text!r}"
            assert len(text) <= _MAX_CHARS, f"{r['id']}: {len(text)} chars — {text!r}"


def test_every_token_names_a_real_NUMBER_or_CHOICE_setting():
    """A token naming nothing renders as the literal `{typo}` on the page. A token naming an
    on/off setting renders `true` — a gate belongs in `show_if`, never in the sentence."""
    checked = 0
    for r in _rows():
        by_name = {p["name"]: p for p in r["param_schema"]}
        for b in r.get("tldr", []):
            for name in _TOKEN.findall(b["text"]):
                checked += 1
                assert name in by_name, f"{r['id']}: {{{name}}} names no setting — {b['text']!r}"
                assert not _is_on_off(by_name[name]), (
                    f"{r['id']}: {{{name}}} is an on/off setting and would print true/false"
                )
    assert checked, "no bullet carries a token — this check compared nothing"


def test_every_show_if_names_a_real_setting():
    """A condition on a missing setting reads its value as nothing, which fails the condition —
    so the bullet is hidden for ever and nothing says why."""
    checked = 0
    for r in _rows():
        names = {p["name"] for p in r["param_schema"]}
        for b in r.get("tldr", []):
            for key in b.get("show_if", {}):
                checked += 1
                assert key in names, f"{r['id']}: show_if names no setting {key!r}"
    assert checked, "no bullet carries a show_if — this check compared nothing"


def test_every_bullet_is_SHOWN_at_the_defaults():
    """🔴 The durable one. The page hides a bullet whose `show_if` stopped holding, so it never
    states the old behaviour — but the summary then silently loses that line. This fails
    instead, when a default moves, so the TL;DR is rewritten rather than quietly shortened.

    Evaluated with the backend twin of the page's condition reader (`_reader_for` resolves a
    dropdown's Custom value exactly as `ParamEditor.readerFor` does)."""
    checked = 0
    for r in _rows():
        read = _reader_for(r["param_schema"], {})
        for b in r.get("tldr", []):
            cond = b.get("show_if")
            if cond:
                checked += 1
                assert _cond_holds(cond, read), (
                    f"{r['id']}: a default moved and this bullet no longer shows — {b['text']!r}"
                )
    assert checked, "no bullet carries a show_if — this check evaluated nothing"


def _overview(tmp_path: Path, meta: dict) -> dict:
    p = tmp_path / "x.meta.json"
    p.write_text(json.dumps(meta), encoding="utf-8")
    return strategy_scanner._read_strategy_overview(p)


def test_the_scanner_keeps_text_and_show_if_and_drops_the_rest(tmp_path):
    out = _overview(
        tmp_path,
        {
            "tldr": [
                {"text": "  Kept, trimmed.  ", "show_if": {"a": True}, "extra": 1},
                {"text": "   "},
                {"show_if": {"a": True}},
                "not a bullet",
                {"text": "No condition."},
            ]
        },
    )
    assert out["tldr"] == [
        {"text": "Kept, trimmed.", "show_if": {"a": True}},
        {"text": "No condition."},
    ]


def test_an_EMPTY_show_if_is_dropped_rather_than_hiding_the_bullet(tmp_path):
    """Both condition evaluators read `{}` as "holds nothing", so a kept `{}` hides the bullet on
    every page for ever. Dropping it makes it an ordinary unconditional bullet."""
    out = _overview(tmp_path, {"tldr": [{"text": "Always shown.", "show_if": {}}]})
    assert out["tldr"] == [{"text": "Always shown."}]


def test_a_meta_with_no_tldr_carries_none(tmp_path):
    assert "tldr" not in _overview(tmp_path, {"edge": "x"})
    assert "tldr" not in _overview(tmp_path, {"tldr": []})


def test_the_tldr_survives_the_database_and_a_NULL_reads_as_empty():
    """The column is JSON text. Stored and read back it must be the list again, and a row scanned
    before the column existed (NULL) must reach the page as `[]`, not fail validation."""
    bullets = [{"text": "Waits within {n} minutes.", "show_if": {"x": True}}]
    lab_db.upsert_strategy(
        {
            "id": "tldr_probe",
            "name": "TL;DR probe",
            "class_name": "TldrProbe",
            "source_path": "strategies/python/tldr_probe",
            "scanned_at": 1,
            "runner": "python",
            "tldr": bullets,
        }
    )
    assert lab_db.get_strategy("tldr_probe")["tldr"] == bullets

    with lab_db._connect() as conn:
        conn.execute("UPDATE strategies SET tldr = NULL WHERE id = 'tldr_probe'")
    row = lab_db.get_strategy("tldr_probe")
    assert row["tldr"] is None
    assert Strategy(**row).tldr == []
