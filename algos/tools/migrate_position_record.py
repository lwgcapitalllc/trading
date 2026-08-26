"""Bring a bot's open-position record up to the shape the DEPLOYED strategy expects.

A live bot writes a record of its open position so a restart can carry on managing it. The
restore refuses if the record is missing any field the strategy needs — deliberately, because a
record it cannot fully read means it does not know what it is holding.

🔴 **Written 2026-08-26, when that refusal halted a bot holding a real trade.** The bot was
promoted from v168 to v241 while a position was open; the newer strategy carries 13 more fields
(scale-in and reclaim state) and the record, written minutes earlier by the old version, had
none of them. The trade sat with only its broker stop and nothing ratcheting it.

**What this does, and the two rules it will not break:**

  1. It only ever ADDS missing fields. An existing value is never touched — the record is the
     only account of what the strategy believes it is holding, and overwriting one would make
     the bot manage a position that differs from the one on the book.
  2. Every value comes from CONSTRUCTING the deployed strategy and reading the field off a fresh
     instance. Nothing is hardcoded here. A default typed into this file would be a guess that
     goes stale the next time the strategy changes, and it would look exactly like a measurement.

⚠ **It refuses unless the broker actually holds the recorded ticket.** Migrating a record for a
position that is gone would hand the bot a phantom trade.

⚠ **It is not a general repair tool.** It fixes ONE shape of damage — fields that a newer
strategy added and an older one never wrote. A record that disagrees with the broker about
direction, size, entry or stop is a different problem and this will not touch it.

⚠ **The bot must be STOPPED.** A running bot rewrites this file whenever the stop moves, so an
edit underneath it is lost at best.

Read-only unless --write is given.
"""

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

try:  # the VPS console is cp1252; degrading one character beats losing the report
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[2]
INSTANCES = REPO / "algos" / "markets" / "fx" / "instances"


def load_cfg(bot: str) -> dict:
    p = INSTANCES / bot / "config.json"
    if not p.exists():
        raise SystemExit(f"no instance config at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def deployed_defaults(bot: str, cfg: dict) -> dict:
    """Every position field the DEPLOYED strategy persists, at its fresh-instance value.

    Runs in a clean subprocess given only the snapshot, the same way `promote.py::verify` does
    and for the same reason: this process has the repo on `sys.path`, so an in-process import
    could satisfy itself from the repo and answer for code the bot is not running. The subprocess
    then checks that what it imported really came from inside the snapshot - "it imported" and
    "it imported the deployment" are different claims and only the second one is worth anything.
    """
    root = INSTANCES / bot / "deployed"
    if not root.is_dir():
        raise SystemExit(f"no deployed snapshot at {root} - promote the bot first")
    params = dict(cfg["strategy_params"])
    params.setdefault("symbol", cfg["symbol"])
    paths = [str(root), str(root / "strategies" / "python")]
    code = textwrap.dedent(f"""
        import sys, json, pathlib, importlib
        sys.path[:0] = {paths!r}
        pkg = importlib.import_module({cfg["strategy_package"]!r})
        origin = getattr(pkg, "__file__", "") or ""
        root = pathlib.Path({str(root)!r}).resolve()
        assert root in pathlib.Path(origin).resolve().parents, (
            "imported from outside the snapshot: " + origin)
        lab = pkg.LAB_STRATEGY
        cls, cfg_cls = lab["strategy"], lab["config"]
        built = cls(cfg_cls(**json.loads({json.dumps(params)!r})), initial_capital=1000.0)
        # The field list lives on the EXECUTION object, not the strategy. Found by searching
        # rather than by naming one attribute: a guessed name that misses would fall through to
        # the strategy itself and report zero fields, which reads as "nothing to migrate" - a
        # silent wrong answer, and the worst outcome this tool has.
        ex, fields = None, None
        for holder in (built,) + tuple(
            getattr(built, n) for n in dir(built) if not n.startswith("__")
        ):
            if hasattr(holder, "_POSITION_FIELDS"):
                ex, fields = holder, holder._POSITION_FIELDS
                break
        assert fields, (
            "no object on the built strategy declares _POSITION_FIELDS - this tool cannot know "
            "what the record should contain, and guessing is the one thing it must not do")
        out = {{}}
        for name in fields:
            v = getattr(ex, name)
            try:
                json.dumps(v)
            except TypeError:
                v = None  # a non-JSON default is reported as absent rather than invented
            out[name] = v
        print("@@" + json.dumps(out))
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(root))
    if r.returncode != 0:
        raise SystemExit(
            f"could not build the deployed strategy:\n{(r.stderr or r.stdout).strip()}"
        )
    marker = [ln for ln in r.stdout.splitlines() if ln.startswith("@@")]
    if not marker:
        raise SystemExit("the deployed strategy reported no position fields")
    return json.loads(marker[0][2:])


def broker_holds(cfg: dict, ticket: int) -> bool:
    import MetaTrader5 as mt5

    if not mt5.initialize(path=cfg["mt5_path"]):
        raise SystemExit(f"could not attach to {cfg['mt5_path']}: {mt5.last_error()}")
    info = mt5.account_info()
    if info is None or int(info.login) != int(cfg["account"]):
        got = info.login if info else None
        mt5.shutdown()
        raise SystemExit(f"WRONG TERMINAL: account {got}, expected {cfg['account']}")
    pos = mt5.positions_get(symbol=cfg["symbol"])
    if pos is None:
        mt5.shutdown()
        raise SystemExit("positions_get returned None - the account could not be READ")
    held = any(p.ticket == ticket for p in pos)
    mt5.shutdown()
    return held


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bot", required=True)
    ap.add_argument("--write", action="store_true", help="apply it; without this, report only")
    ap.add_argument("--skip-broker-check", action="store_true", help="only when MT5 is unreachable")
    a = ap.parse_args()

    cfg = load_cfg(a.bot)
    rec_path = INSTANCES / a.bot / "position.json"
    if not rec_path.exists():
        raise SystemExit(f"no position record at {rec_path} - nothing to migrate")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    strat = rec.get("strategy") or {}
    ticket = rec.get("ticket")

    print(f"\nrecord   T{ticket}  written {rec.get('written')}")
    print(f"broker   {rec.get('broker')}")

    if not a.skip_broker_check:
        if not broker_holds(cfg, int(ticket)):
            raise SystemExit(
                f"\nREFUSING: the broker does not hold T{ticket}. Migrating a record for a "
                f"position that is gone would hand the bot a trade that does not exist."
            )
        print(f"broker holds T{ticket}: yes")

    defaults = deployed_defaults(a.bot, cfg)
    missing = [k for k in defaults if k not in strat]
    extra = [k for k in strat if k not in defaults]

    print(f"\ndeployed strategy persists {len(defaults)} field(s)")
    print(f"record has {len(strat)}; missing {len(missing)}, unknown-to-this-version {len(extra)}")
    if extra:
        # Not an error and NOT removed: a field this version does not read is inert, and
        # deleting it would make a rollback to the older version lossy.
        print(f"  left alone (a rollback would still want them): {', '.join(sorted(extra))}")
    if not missing:
        print("\nnothing to do - the record already has every field this version needs.")
        return

    print("\nwould add, each read off a freshly built deployed strategy:")
    for k in sorted(missing):
        print(f"  {k:<18} = {defaults[k]!r}")

    if not a.write:
        print("\nreport only. Re-run with --write to apply.")
        return

    backup = rec_path.with_name(
        f"position.{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.pre-migrate.json"
    )
    shutil.copy2(rec_path, backup)
    for k in missing:
        strat[k] = defaults[k]
    rec["strategy"] = strat
    rec["_migrated"] = (
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}: added "
        f"{len(missing)} field(s) the deployed strategy expects and the writing version did not "
        f"have. Values read off a freshly built deployed strategy, not typed in. Existing values "
        f"untouched. Previous file: {backup.name}"
    )
    rec_path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"\nwritten. Previous record kept as {backup.name}")
    print("Restart the bot; it will restore the position and manage it from the next bar.")


if __name__ == "__main__":
    main()
