"""bot_params.py — what a LIVE bot is actually configured with, and what may be changed.

The problem this solves: the only way to know what a running bot is trading was to SSH in
and read a JSON file. That is how a bot ends up running something nobody remembers
approving. This turns the instance config into a readable view, borrowing the LAB's param
schema for labels/groups/descriptions so the two surfaces cannot develop separate
vocabularies for the same knob.

**The editable/read-only split is the whole point of this module, so it is stated once
here and everything else reads it.** Two kinds of parameter live in an instance config:

  *How much* — `exec_risk_pct`. Changing it does not change WHICH trades the bot takes.
  Same signals, same sequence, different size. It stays comparable to the lab (just
  scaled), and "this is sizing bigger than I am comfortable with" is a real thing to feel
  at 2am. Editable.

  *Which trades* — fib levels, the SOS window, the FVG rules. Change one and the bot is no
  longer the bot that was backtested, and you find out months later when live does not
  match the lab and you cannot tell whether it was the market or the edit. The
  `strategy_source_hash` pin exists precisely to stop that; an edit box beside it would
  make the pin theatre. Read-only here — those go lab → backtest → promote.

Arming (dry run → live) is deliberately NOT in this set. It is reported, never written:
`algos/live/runner.py` defaults to dry run and requires `--live` to be typed, and a web
button that quietly arms a bot is a different decision from resizing one.

Pure: no DB writes, no SSH, no network. The router owns the git/VPS side effects.
"""

from __future__ import annotations

from typing import Any, Optional

# The ONE list. Anything not named here is read-only — see the module docstring.
RUNTIME_EDITABLE: set[str] = {"exec_risk_pct"}

# Bounds for the editable fields. A risk % is a per-trade fraction of the account, and
# both ends matter: 0 silently stops the bot trading (every size rounds to below the
# broker minimum) while looking like a running bot, and there is no number here big
# enough to be a typo-proof ceiling, so the cap is set where a single stop-out would
# take a third of the account and the UI is expected to argue before it gets there.
RUNTIME_BOUNDS: dict[str, tuple[float, float]] = {
    "exec_risk_pct": (0.1, 35.0),
}

# Keys of the instance config that are identity/plumbing rather than strategy params.
_IDENTITY = ("account", "server", "symbol", "timeframe", "mt5_path", "magic")
_VERSION = (
    "strategy_package",
    "strategy_class",
    "strategy_version",
    "strategy_source_hash",
    "promoted_commit",
    "promoted_at",
)


def _schema_index(param_schema: Optional[list[dict]]) -> dict[str, dict]:
    """name → the lab's scanned schema entry (label, group, desc, unit, widget, …)."""
    return {p["name"]: p for p in (param_schema or []) if p.get("name")}


def _notes(config: dict) -> dict[str, str]:
    """The `_`-prefixed prose in an instance config, keyed by the field it explains.

    `_exec_risk_pct` documents `exec_risk_pct`. These are the reasons a value is what it
    is — the single most useful thing on the page when deciding whether to change it — and
    they are written at the moment the decision is made, which is the only time they are
    accurate.
    """
    return {k.lstrip("_"): v for k, v in config.items() if k.startswith("_") and isinstance(v, str)}


def _row(name: str, value: Any, schema: dict, note: Optional[str]) -> dict:
    meta = schema.get(name, {})
    return {
        "name": name,
        "value": value,
        "label": meta.get("label") or meta.get("display_name") or name.replace("_", " "),
        "group": meta.get("group") or "Other",
        "desc": meta.get("desc"),
        "unit": meta.get("unit"),
        "type": meta.get("type") or _infer_type(value),
        "options": meta.get("options"),
        "choices": meta.get("choices"),
        "core": bool(meta.get("core", False)),
        "editable": name in RUNTIME_EDITABLE,
        "min": RUNTIME_BOUNDS.get(name, (None, None))[0],
        "max": RUNTIME_BOUNDS.get(name, (None, None))[1],
        "note": note,
    }


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    return "string"


def build_view(
    bot_key: str,
    config: dict,
    param_schema: Optional[list[dict]] = None,
    section: str = "strategy_params",
) -> dict:
    """Turn an instance config.json into the Bots page's parameter view.

    `param_schema` is the lab's scanned schema for the same strategy (labels, groups,
    descriptions). It is OPTIONAL and purely cosmetic — a bot whose strategy has never
    been scanned still renders every parameter, just under its raw field name. Never let
    a missing schema hide a value: the point of the page is that nothing about a running
    bot is invisible.
    """
    schema = _schema_index(param_schema)
    notes = _notes(config)
    params = config.get(section, {}) or {}

    runtime, strategy = [], []
    for name, value in params.items():
        row = _row(name, value, schema, notes.get(name))
        (runtime if row["editable"] else strategy).append(row)

    # Schema order first (the lab's curated order), unschema'd params after, alphabetical
    # — so the list reads the same here as it does in the Run modal.
    order = {p["name"]: i for i, p in enumerate(param_schema or [])}
    strategy.sort(key=lambda r: (order.get(r["name"], 10_000), r["name"]))

    return {
        "bot_key": bot_key,
        "display_name": config.get("display_name") or bot_key,
        "identity": {k: config.get(k) for k in _IDENTITY},
        "version": {k: config.get(k) for k in _VERSION},
        "runtime": runtime,
        "strategy": strategy,
        "notes": notes,
        "readme": config.get("_README"),
    }


class RuntimeUpdateError(ValueError):
    """A rejected runtime edit. The router turns this into a 400."""


def validate_runtime(updates: dict[str, Any]) -> dict[str, Any]:
    """Check a proposed runtime change and return the values to write.

    Rejects rather than clamps. A silently clamped risk % is the worst outcome available:
    the user believes they set 50 and the bot trades 35, and nothing on screen disagrees.
    """
    if not updates:
        raise RuntimeUpdateError("No changes were sent.")

    illegal = sorted(set(updates) - RUNTIME_EDITABLE)
    if illegal:
        raise RuntimeUpdateError(
            f"Not editable at runtime: {', '.join(illegal)}. "
            f"Only {', '.join(sorted(RUNTIME_EDITABLE))} can be changed on a running bot — "
            f"anything that changes WHICH trades are taken has to go through "
            f"lab → backtest → promote so the version pin stays meaningful."
        )

    clean: dict[str, Any] = {}
    for name, value in updates.items():
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise RuntimeUpdateError(f"{name} must be a number, got {value!r}.")
        if num != num or num in (float("inf"), float("-inf")):
            raise RuntimeUpdateError(f"{name} must be a real number, got {value!r}.")
        lo, hi = RUNTIME_BOUNDS[name]
        if not (lo <= num <= hi):
            raise RuntimeUpdateError(f"{name} must be between {lo} and {hi} — got {num}.")
        clean[name] = num
    return clean
