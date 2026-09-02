"""promote.py — deploy a version of the code to one bot, deliberately.

    python algos/tools/promote.py --bot mpc_sos_fade_demo
    python algos/tools/promote.py --bot mpc_sos_fade_demo --dry-run
    python algos/tools/promote.py --bot mpc_sos_fade_demo --show     # what is deployed now

**What promoting means, and why it is a copy.** Until 2026-08-03 a deployed bot imported its
strategy straight out of `strategies/python/<pkg>` in the repo working tree. So the repo and the
deployment were the same thing: a `git pull` on the VPS — for a lab fix, an agent update,
anything — rewrote the code under a running bot, and the version pin then refused to restart it.
Backtesting a new version could brick the deployed one. The live bot sat dead for three days on
exactly that.

Aaron's rule, and it is the right one: **a bot runs what you last deployed until you deploy
something else.** So promoting COPIES the code into `instances/<bot>/deployed/`, and the runner
imports from there. After that the repo is free — pull it, refactor it, backtest a new version,
break it — and the deployment does not move until this script is run again.

**Three trees are copied, not one.** The strategy package is a thin layer; it imports
`engines.*` (market structure, fibs, FVG, RSI divergence, sessions, liquidity) and
`backtest.replay` / `backtest.fills`, which is where the logic actually lives. Freezing only the
strategy would leave the engines free to change under a green pin — the bot would start, report
the version it was promoted at, and trade different rules.

**Only `.py` is copied**, because only `.py` executes. That also keeps the git-ignored data
directories (`backtest/cache/`, `engines/news/data/`) out of the snapshot for free. The
assumption is not taken on trust: `--verify` (on by default) imports the strategy out of the
finished snapshot in a clean subprocess and builds it with the promoted parameters, so a file
this rule wrongly excluded fails the promote instead of the next restart.

**A dirty tree is refused** unless `--allow-dirty`. The snapshot records the commit it came
from, and recording a commit that does not describe the files copied makes the whole audit
trail a guess.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
import time
import types
from datetime import date
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for _p in (str(_REPO / "algos" / "live"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_config  # noqa: E402
from bridge import (  # noqa: E402
    UnsupportedStrategyConfig,
    assert_secondary_wired,
    assert_supported,
)
from feed import fast_feed_timeframe  # noqa: E402
from live_config import deployed_record  # noqa: E402
from version import current_commit, deployment_hash  # noqa: E402

# Directory names never copied into a snapshot, at any depth.
SKIP_DIRS = {"tests", "__pycache__", ".pytest_cache", ".git"}

# Machine-readable "which versions did this move between", for a caller that has to report
# it. Kept out of the prose lines so rewording one cannot break the other.
_VERSION_MARK = "##VERSIONS"


def _tree_sources(root: Path):
    """Every `.py` under `root` that belongs in a snapshot, as (absolute, relative) pairs."""
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        if SKIP_DIRS & set(rel.parts):
            continue
        yield py, rel


def repo_trees(cfg) -> list[tuple[Path, Path]]:
    """(source in the repo, destination inside `deployed/`) for each tree, layout preserved.

    The destination mirrors the repo exactly, so an import resolves the same way against the
    snapshot as against the repo — the freeze changes which copy is loaded, never how it is
    spelled.
    """
    rel_strategy = Path("strategies") / "python" / cfg.strategy_package
    return [
        (_REPO / rel_strategy, rel_strategy),
        (_REPO / "engines", Path("engines")),
        (_REPO / "backtest", Path("backtest")),
    ]


def dirty_paths(trees) -> list[str]:
    """Tracked files with uncommitted edits inside the trees being promoted."""
    rels = [str(dest).replace("\\", "/") for _, dest in trees]
    out = subprocess.run(
        ["git", "-C", str(_REPO), "status", "--porcelain", "--", *rels],
        capture_output=True,
        text=True,
    )
    return [ln[3:].strip() for ln in out.stdout.splitlines() if ln.strip()]


def version_at(commit: str, trees) -> Optional[int]:
    """How many commits up to `commit` have touched the trees being promoted.

    🔴 **This is the number the bot reports, and until 2026-08-14 it reported `v0`.**
    `LiveConfig.strategy_version` was an int defaulting to 0 that NOTHING assigned — so the
    ONLINE banner read `v0 (e4137dbb)` on every bot, on every start, for ever. A field that is
    declared and never written is indistinguishable from a measurement, which is the defect
    this repo has now met in `running=False`, in `is_compiled`, and here.

    **A version is the count of commits touching THIS BOT'S TREES**, so it moves when — and
    only when — the code this bot runs moves, and subtracting two of them is the work between
    two deployments. It is derived from `repo_trees`, the same function that decides what is
    COPIED, so a tree that is promoted is a tree that is counted; a second roster here is how
    a change deploys while the number says nothing happened.

    ⚠ **`None`, never 0.** 0 is a real version (a tree with no history yet) and is also the
    value that has been lying on this field since it was declared. An unfetched commit, a
    checkout that is not a git repo, a `rev-list` that fails — every one of those is *cannot
    say*, and the bot renders it `v?`.

    ⚠ **`command-center/backend/services/bot_versions.version_at` runs the SAME command over
    the SAME trees**, so the two agree by construction rather than by being kept in step.
    They are one definition evaluated in two places, and the difference is WHEN: this one is
    stamped at the moment the promote is true, which is what lets the bot — with no git and no
    backend — state its own version.
    """
    if not commit or not trees:
        return None
    rels = [str(dest).replace("\\", "/") for _, dest in trees]
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO), "rev-list", "--count", commit, "--", *rels],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def vlabel(n: Optional[int]) -> str:
    """`v165`, or `v?` for a version nobody could count. Never `v0` for an unknown."""
    return "v?" if n is None else f"v{n}"


def stage(cfg, trees, dry_run: bool = False) -> tuple[Path, int]:
    """Build the new snapshot in `deployed.new/`, WITHOUT touching the live one.

    Staged rather than written in place because a promote can fail — the verify step below is
    there precisely to catch a snapshot that does not import. A failed promote must leave the
    previous deployment exactly as it was, still importable, still matching its pin. Writing
    into `deployed/` and then discovering the problem would take out a working bot in order to
    tell you the new version is broken.
    """
    staging = cfg.deployed_dir.with_name("deployed.new")
    files = [
        (src_file, dest_rel / rel)
        for src_tree, dest_rel in trees
        for src_file, rel in _tree_sources(src_tree)
    ]
    if dry_run:
        return staging, len(files)

    _remove_tree(staging)
    for src_file, rel in files:
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst)
    return staging, len(files)


def activate(cfg, staging: Path) -> None:
    """Swap the verified snapshot in. Last destructive step, and the only one.

    The old snapshot is REPLACED rather than merged over. Merging leaves a file that was deleted
    upstream sitting in the deployment, still importable, and the hash would then describe a
    tree that exists nowhere in git.

    🔴 **The old snapshot is MOVED ASIDE, never deleted first (fixed 2026-08-26).** This used to
    read `rmtree(dest)` and then `staging.rename(dest)`, which opens a window where the bot has
    NO deployed code at all — and on Windows that window can become permanent, because a rename
    fails outright if anything holds either directory (the running bot, an indexer, a virus
    scanner). **That is exactly what happened on 2026-08-26: the promote deleted the live
    snapshot, the rename failed, and the bot was left with no code to restart onto.** It kept
    running only because Python already had its modules in memory.

    ⚠ **`stage()`'s own docstring promised what this function then broke** — *"a failed promote
    must leave the previous deployment exactly as it was"*. It was true of staging and false of
    activation, and the two are three functions apart. **A safety property is only as strong as
    its LAST step; check the whole path, not the part that documents itself.**

    Order now: move `deployed` -> `deployed.old`, move the staged tree into place, and only then
    delete the backup. Any failure rolls the backup back, so the bot always has exactly one
    complete snapshot.
    """
    dest = cfg.deployed_dir
    backup = dest.with_name("deployed.old")
    _remove_tree(backup)

    moved = False
    if dest.exists():
        dest.rename(backup)
        moved = True
    try:
        staging.rename(dest)
    except Exception:
        # Put the working deployment back before re-raising. A promote that fails must cost
        # nothing; a promote that fails AND takes out the bot is worse than never running one.
        #
        # ⚠ The rollback is itself wrapped: if it fails too, the ORIGINAL error is the one worth
        # reading, and `recover_interrupted()` puts `deployed.old` back on the next run. A
        # rollback that can raise turns one diagnosable failure into a confusing one.
        if moved and not dest.exists():
            try:
                backup.rename(dest)
            except OSError:
                pass
        raise
    _remove_tree(backup)


def _remove_tree(path: Path, attempts: int = 5) -> None:
    """`shutil.rmtree` with Windows in mind.

    ⚠ **A file being deleted on Windows can be held briefly by something that is not the bot** —
    Defender scans a freshly-written tree, Explorer keeps a handle, the indexer wakes up. The
    failure is transient and a single attempt turns it into a stopped promote; on 2026-08-26 a
    leftover staging directory did exactly that. Retrying costs a second and removes a whole
    class of spurious failures.

    Never raises. Every caller here is either cleaning up a backup that no longer matters or
    clearing a stale staging tree, and neither is worth failing a promote over.
    """
    for i in range(attempts):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.2 * (i + 1))
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def open_position_gap(cfg, position_fields: list) -> Optional[dict]:
    """Is this bot holding a position whose record the NEW version could not restore?

    Returns `{ticket, missing}` when it is, `None` when there is nothing to worry about — no
    record, or a record that already carries every field.

    ⚠ **An unreadable record counts as a gap, not as "no position".** A record that will not
    parse is one the restore would refuse anyway, and reporting it as absent is the shape of
    error this whole file exists to stop.
    """
    if not position_fields:
        return None
    rec_path = cfg.deployed_dir.parent / "position.json"
    if not rec_path.exists():
        return None
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        strat = rec.get("strategy") or {}
        ticket = rec.get("ticket")
    except Exception:
        return {"ticket": "?", "missing": ["<the record could not be read at all>"]}
    missing = [f for f in position_fields if f not in strat]
    return {"ticket": ticket, "missing": missing} if missing else None


def recover_interrupted(cfg) -> str:
    """Put a deployment back if a previous promote died between the two renames.

    Returns a sentence describing what it did, or "" when there was nothing to do. Called at the
    START of every promote, because the one moment somebody is definitely looking at this tool is
    the moment they are running it again after it failed.

    ⚠ **It only ever restores; it never chooses between two candidates.** If both `deployed` and
    `deployed.old` exist, the live one has already been swapped in and the backup is just
    litter — removing it is safe, and preferring one over the other is a decision this function
    has no basis to make.
    """
    dest, backup = cfg.deployed_dir, cfg.deployed_dir.with_name("deployed.old")
    if dest.exists():
        if backup.exists():
            _remove_tree(backup)
            return "cleared a leftover deployed.old from an earlier promote"
        return ""
    if backup.exists():
        backup.rename(dest)
        return "RECOVERED: the previous promote died mid-swap and left no deployment; the "
    return ""


def startup_refusals(startup: dict, primary_timeframe: str) -> list:
    """Every reason a bot with this configuration would REFUSE TO START, as printable strings.

    🔴 **A PROMOTE'S "verified" LINE MEANS IMPORTS AND BUILDS, NEVER RUNS — AND THAT COST A BOT
    ON 2026-08-28.** The re-entry was switched on, `promote.py --dry-run` printed *"verified: the
    snapshot imports and builds with the promoted parameters"*, and the bot would not come back
    up: `bridge.assert_supported` refuses at RUNTIME, in the runner, which nothing before a
    restart reaches. The bot was down until the setting was reverted. **The fix for a sentence
    that overclaims is not a better sentence — it is making the preview ask the question the
    restart asks.**

    ⚠ **It answers off VALUES shipped from the verify subprocess, never off a live import.** The
    staged snapshot holds no `algos/` tree, so the subprocess cannot import these rules; and this
    parent must not import the STRATEGY, because doing so would satisfy itself from the repo
    rather than from the snapshot — which is the whole reason `verify` runs out of process.

    ⚠ **Returns a LIST rather than raising**, so the FEED problems are all named at once. ⚠ Each
    of the two bridge checks contributes at most ONE entry, because both raise on their first
    refusal exactly as the runner does — so a config with two problems inside one of them is
    reported, fixed, and reported again. That is deliberate (the list must describe the restart,
    and a restart stops at the first raise too), and it is written down here because "names every
    problem at once" is what the shape of the return value suggests and it is not true.

    ⚠ **A missing `startup` payload returns [] — and that is the honest answer, not a pass.** It
    means an older snapshot's verify step did not ship one, so the question was NOT ASKED. The
    caller says so; it must never print a clean bill of health on silence (rule 1).
    """
    if not startup:
        return []
    problems = []
    cfg_ns = types.SimpleNamespace(**(startup.get("settings") or {}))
    try:
        assert_supported(cfg_ns)
    except UnsupportedStrategyConfig as exc:
        problems.append(str(exc))
    minutes = startup.get("fast_feed_minutes")
    if startup.get("fast_feed_error"):
        # ⚠ **AND THE SEAM CHECK BELOW IS SKIPPED WHEN ASKING BLEW UP.** The subprocess reports
        # `fast_feed_minutes: None` after an exception, which is the same value a strategy with
        # no fill clock produces — so running the check here would print *"the strategy offers no
        # fill clock"* for a strategy that has one and raised. Rule 1, one layer up: the two
        # answers must not print the same sentence.
        problems.append(
            f"asking the strategy how fast a second feed it needs raised "
            f"{startup['fast_feed_error']}"
        )
    else:
        # 🔴 **THE SAME FUNCTION THE RUNNER CALLS, off shipped VALUES.** It used to be a
        # hand-written `has_make_dual_clock` branch here, which had a hole the runner's version
        # did not: it only ran `if minutes is not None`, so a strategy with the re-entry ON and
        # no fill clock at all passed the preview silently. That was invisible while
        # `assert_supported` refused the setting outright and became reachable the moment it
        # stopped. One rule, two callers — the reason `fast_feed_timeframe` exists.
        try:
            assert_secondary_wired(
                cfg_ns,
                fill_clock_minutes=minutes,
                has_merge=bool(startup.get("has_make_dual_clock")),
            )
        except UnsupportedStrategyConfig as exc:
            problems.append(str(exc))
    if minutes is not None:
        try:
            fast_feed_timeframe(minutes, primary_timeframe)
        except (ValueError, RuntimeError) as exc:
            problems.append(str(exc))
    return problems


def verify(cfg, root: Path) -> tuple[bool, str]:
    """Import the strategy out of `root` and build it with the promoted parameters.

    This is what makes "copy only `.py`" a checked assumption instead of a hopeful one: a file
    that rule wrongly excluded fails the promote here, rather than the next time the bot is
    restarted — which, on current evidence, is three days later and at the worst moment.

    Runs in a CLEAN subprocess on purpose. This process already has the repo on `sys.path`, so an
    in-process import could quietly satisfy itself from the repo and pass a snapshot that is
    missing a file. The subprocess is given only the snapshot, and then checks that the package
    it actually loaded came from inside it — a path check, because "it imported" and "it imported
    the copy I just made" are different claims and only the second one is worth anything here.
    """
    params = dict(cfg.strategy_params)
    params.setdefault("symbol", cfg.symbol)
    paths = [str(root), str(root / "strategies" / "python")]
    code = textwrap.dedent(f"""
        import sys, json, pathlib
        sys.path[:0] = {paths!r}
        import importlib
        pkg = importlib.import_module({cfg.strategy_package!r})
        origin = getattr(pkg, "__file__", "") or ""
        root = pathlib.Path({str(root)!r}).resolve()
        assert root in pathlib.Path(origin).resolve().parents, (
            "imported from outside the snapshot: " + origin)
        lab = getattr(pkg, "LAB_STRATEGY", None)
        assert lab, "package declares no LAB_STRATEGY"
        cls, cfg_cls = lab["strategy"], lab["config"]
        assert cls.__name__ == {cfg.strategy_class!r}, (
            "package provides " + cls.__name__ + ", config names " + {cfg.strategy_class!r})
        params = json.loads({json.dumps(params)!r})
        fields = cfg_cls.__dataclass_fields__
        unknown = sorted(set(params) - set(fields))
        assert not unknown, (
            "strategy_params names " + ", ".join(unknown) + " but this version of the strategy "
            "has no such setting. It would be ignored, so the bot would trade a configuration "
            "nobody chose. Remove it from config.json, or promote a version that has it.")
        built = cls(cfg_cls(**params), initial_capital=1000.0)
        # Which settings this deployment does NOT state, and will therefore take from the
        # strategy's own defaults. Not an error — but it is the quiet way a new version changes
        # behaviour, so the caller prints it rather than letting it pass unremarked.
        import dataclasses
        defaulted = {{
            name: repr(getattr(built.cfg if hasattr(built, "cfg") else cfg_cls(**params), name))
            for name in sorted(set(fields) - set(params))
        }}
        # Which fields this version needs in an open-position record. Searched for rather than
        # named: a guessed attribute that misses would report an empty list, and an empty list
        # reads as "nothing to worry about" - a silent wrong answer about a live position.
        pos_fields = []
        for holder in (built,) + tuple(
            getattr(built, n) for n in dir(built) if not n.startswith("__")
        ):
            if hasattr(holder, "_POSITION_FIELDS"):
                pos_fields = list(holder._POSITION_FIELDS)
                break
        # What a RESTART needs beyond importing. Shipped as VALUES, never as a verdict: the
        # rules live in algos/live/ and `repo_trees` copies no algos/ tree at all, so bridge.py
        # and feed.py do not exist inside this snapshot. The parent decides.
        # ⚠ EVERY field is sent, not the handful a check reads today. A capability rule that
        # grows a new field would otherwise take its `getattr` default here and pass on a value
        # this bot does not hold - a check that is wrong in the direction of saying yes.
        resolved = built.cfg if hasattr(built, "cfg") else cfg_cls(**params)
        settings, opaque = {{}}, []
        for name in sorted(fields):
            v = getattr(resolved, name, None)
            (settings.__setitem__(name, v) if v is None or isinstance(v, (bool, int, float, str))
             else opaque.append(name))
        try:
            ask = getattr(built, "fast_feed_minutes", None)
            fast_min, fast_err = (ask() if callable(ask) else None), None
        except Exception as exc:
            fast_min, fast_err = None, type(exc).__name__ + ": " + str(exc)
        startup = {{
            "settings": settings,
            "opaque": opaque,
            "fast_feed_minutes": fast_min,
            "fast_feed_error": fast_err,
            "has_make_dual_clock": callable(getattr(built, "make_dual_clock", None)),
        }}
        print("@@" + json.dumps({{"defaulted": defaulted, "position_fields": pos_fields,
                                 "startup": startup}}))
    """)
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=str(root)
    )
    if out.returncode != 0:
        return False, (out.stderr or out.stdout).strip()
    marker = [ln for ln in out.stdout.splitlines() if ln.startswith("@@")]
    return True, marker[0][2:] if marker else "{}"


def write_pin(
    cfg, hash_: str, commit: str, when: str, files: int, version: Optional[int] = None
) -> None:
    """Record what was deployed, in `deployed.json` beside the snapshot.

    **Not into `config.json`, and the reason is practical.** Promoting happens ON THE VPS,
    because the snapshot is built from whatever that machine has checked out. `config.json` is
    tracked in git, so writing the pin there would leave the VPS holding a modified tracked file
    and the next `git pull` would refuse — turning every deploy into a merge conflict. That is
    exactly the kind of friction that gets a safety mechanism switched off.

    So the split is: `config.json` is the INTENDED configuration — tracked, human-edited, and
    the source of `strategy_params`. `deployed.json` is what is ACTUALLY deployed on this
    machine right now — git-ignored, written only by this script, never by hand.

    Nothing is lost from the audit trail: `promoted_commit` plus the hash reconstruct the exact
    tree from git. And the Bots page gets ONE file that answers "what is running?" without
    having to assume the repo was untouched since — which is the assumption that just cost three
    days of downtime.

    The full parameter set is copied in too. `config.json` can be edited between promotes (the
    Bots page writes `exec_risk_pct` to it live), so the params a version was DEPLOYED with are
    not recoverable from it afterwards. Recording them here is what makes "show me the settings
    that version ran" answerable later.
    """
    (cfg.instance_dir / "deployed.json").write_text(
        json.dumps(
            {
                "strategy_source_hash": hash_,
                "promoted_commit": commit,
                "promoted_at": when,
                "strategy_package": cfg.strategy_package,
                "strategy_class": cfg.strategy_class,
                # MEASURED here, not carried from `config.json` — that copy is an int defaulting
                # to 0 that nothing has ever assigned, which is why every bot reported `v0`. See
                # `version_at`. `None` is written as JSON null and reads back as *cannot say*.
                "strategy_version": version,
                "strategy_params": cfg.strategy_params,
                "files": files,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def show(cfg) -> int:
    print(f"{cfg.bot_key} — {cfg.display_name}")
    print(f"  frozen   : {'yes' if cfg.is_frozen else 'NO — importing from the repo tree'}")
    print(f"  pinned   : {cfg.strategy_source_hash or '(unpinned)'}")
    print(f"  promoted : {cfg.promoted_commit or '?'} on {cfg.promoted_at or '?'}")
    print(f"  version  : {vlabel(cfg.strategy_version)}")
    if cfg.is_frozen:
        actual = deployment_hash(cfg.source_roots)
        match = actual == cfg.strategy_source_hash
        print(f"  on disk  : {actual} {'✓ matches' if match else '✗ SNAPSHOT MODIFIED'}")
    return 0


def main(argv=None) -> int:
    # A Windows console is cp1252 and cannot encode the arrows these messages are written with.
    # It does not degrade — it raises, mid-print, AFTER the snapshot has been staged, so the
    # promote dies somewhere in the middle with no pin written. Measured on the VPS the first
    # time this ran. Same fix, same reason, as `runner.py::_make_logger`.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Deploy a version of the code to one bot.")
    ap.add_argument("--bot", required=True)
    ap.add_argument("--dry-run", action="store_true", help="report, copy nothing")
    ap.add_argument("--show", action="store_true", help="print what is deployed and exit")
    ap.add_argument(
        "--allow-dirty",
        action="store_true",
        help="promote uncommitted edits (the recorded commit will not describe them)",
    )
    ap.add_argument(
        "--no-verify", action="store_true", help="skip the post-copy import check (not recommended)"
    )
    ap.add_argument(
        "--allow-open-position",
        action="store_true",
        help="promote even though the open position's record cannot be restored by this version",
    )
    args = ap.parse_args(argv)

    cfg = live_config.load(args.bot)
    if args.show:
        return show(cfg)

    trees = repo_trees(cfg)
    for src, _ in trees:
        if not src.is_dir():
            print(f"  ! missing source tree: {src}")
            return 1

    dirty = dirty_paths(trees)
    if dirty and not args.allow_dirty:
        print(f"Refusing to promote — {len(dirty)} uncommitted change(s) in the trees to deploy:")
        for d in dirty[:10]:
            print(f"    {d}")
        if len(dirty) > 10:
            print(f"    … and {len(dirty) - 10} more")
        print(
            "Commit them, or pass --allow-dirty and accept that promoted_commit will not "
            "describe what was copied."
        )
        return 1

    # Before anything else: did a PREVIOUS promote die between the two renames and leave this
    # bot with no deployment at all? That is the state 2026-08-26 produced, and the moment
    # somebody runs this tool again is the moment to say so.
    note = recover_interrupted(cfg)
    if note:
        print(f"  {note}previous snapshot has been put back.")

    commit = current_commit(_REPO)
    print(f"promote {cfg.bot_key} {'(dry run)' if args.dry_run else ''}".rstrip())
    print(f"  from commit {commit or '?'}{' [DIRTY]' if dirty else ''}")

    # A dry run STAGES AND VERIFIES like a real one — it just does not activate. Reporting a
    # file count and stopping would be a preview of nothing: the two things worth knowing
    # before you deploy are "does it import" and "which settings will change", and both need
    # the snapshot to actually exist. Nothing live is touched either way — staging writes to
    # `deployed.new`, and only `activate()` below swaps.
    staging, n = stage(cfg, trees)
    print(f"  staged {n} .py file(s) -> {cfg.deployed_dir}")
    was = deployed_record(cfg.bot_key)

    if not args.no_verify:
        ok, detail = verify(cfg, staging)
        if not ok:
            shutil.rmtree(staging, ignore_errors=True)
            print("  ! the staged snapshot does not import — nothing was deployed.")
            print("    The previous deployment is untouched and still running.")
            print(textwrap.indent(detail, "    "))
            return 1
        print("  verified: the snapshot imports and builds with the promoted parameters")
        report = json.loads(detail or "{}")
        defaulted = report.get("defaulted", {})
        startup = report.get("startup") or {}
        if not startup:
            # Rule 1: NOT ASKED and NOTHING WRONG must not print the same way.
            print(
                "  ! this snapshot's verify step shipped no startup facts, so whether the bot "
                "would START was NOT CHECKED (only that it imports and builds)."
            )
        else:
            if startup.get("opaque"):
                print(
                    f"  ! {len(startup['opaque'])} setting(s) are not plain values and were not "
                    f"carried into the startup check: {', '.join(startup['opaque'])}"
                )
            refusals = startup_refusals(startup, cfg.timeframe)
            if refusals:
                # 🔴 DELIBERATELY non-zero on a DRY RUN, unlike the open-position warning below.
                # A preview that renders green for a config which kills the bot is the exact
                # failure this check exists for, and the Command Center's verdict is the exit
                # code (`if errorlevel 1`), never the prose.
                print(
                    f"\n  !! THIS CONFIGURATION WOULD NOT START. {len(refusals)} refusal(s) "
                    f"the RESTART would hit, which importing and building cannot reach:"
                )
                for r in refusals:
                    print(textwrap.indent("- " + r, "     "))
                print(
                    "\n  ! nothing was deployed. Fix the configuration, or promote a version "
                    "that supports it."
                )
                shutil.rmtree(staging, ignore_errors=True)
                return 1
        gap = open_position_gap(cfg, report.get("position_fields") or [])
        if gap:
            # 🔴 2026-08-26: a bot was promoted v168 -> v241 while holding a real trade. The
            # newer strategy persists 13 more position fields, the record had none of them, the
            # restore refused, and the bot HALTED with the position unmanaged - no stop
            # ratcheting, no time exit. Nothing warned. This is the one question worth asking
            # before promoting a bot that is in the market, and it can only be asked here,
            # because only the staged snapshot knows what the new version needs.
            print(
                f"\n  !! THIS BOT IS HOLDING A POSITION (T{gap['ticket']}) AND THIS VERSION "
                f"CANNOT RESTORE IT."
            )
            print(f"     The record is missing {len(gap['missing'])} field(s) it needs:")
            print(f"       {', '.join(sorted(gap['missing']))}")
            print("     Restarting onto this version would HALT the bot and leave the position")
            print("     with only its broker stop - nothing ratcheting it, no time exit.")
            print("     Either wait until the position closes, or repair the record first:")
            print(f"       migrate_position_record.py --bot {cfg.bot_key} --write")
            if not args.dry_run and not args.allow_open_position:
                print("\n  ! nothing was deployed. Pass --allow-open-position to promote anyway.")
                shutil.rmtree(staging, ignore_errors=True)
                return 1
        if defaulted:
            # Settings this version has that the deployment does not state. They take the
            # strategy's own defaults, which is how a new version quietly changes behaviour —
            # so it is named here, at the moment you can still decide about it.
            print(
                f"  ! {len(defaulted)} setting(s) not stated in config.json, taking this "
                f"version's defaults:"
            )
            for name, val in sorted(defaulted.items()):
                print(f"      {name} = {val}")
            print("    Add them to strategy_params to state them deliberately.")

    new_hash = deployment_hash([staging / r for _, r in trees])
    old_hash = was.get("strategy_source_hash", "")
    if old_hash and old_hash == new_hash:
        print(f"  code is UNCHANGED from the running deployment ({old_hash[:12]})")
    elif old_hash:
        print(f"  code changes: {old_hash[:12]} -> {new_hash[:12]}")

    # The version this promote MOVES FROM and TO, printed on the dry run as well — it is one
    # of the two questions a preview exists to answer, and it is the one a reader can act on
    # without knowing what a commit hash means.
    #
    # ⚠ `was` is read from the PREVIOUS `deployed.json`, so the "from" is the commit that is
    # actually running, never `HEAD~1` or whatever the repo happens to hold. A bot three
    # deployments behind must not be described as one behind.
    from_version = version_at(was.get("promoted_commit", "") or "", trees)
    to_version = version_at(commit or "", trees)
    print(f"  version  : {vlabel(from_version)} -> {vlabel(to_version)}")
    # A machine-readable line for the caller that has to put those two numbers in a message.
    # Parsed and STRIPPED by `command-center/backend/routers/bots.py::_run_promote`, the same
    # way its OK/FAIL markers are — a caller scraping the prose line above would break the
    # first time somebody rewords it.
    print(
        f"{_VERSION_MARK} {from_version if from_version is not None else '?'} "
        f"{to_version if to_version is not None else '?'}"
    )

    if args.dry_run:
        shutil.rmtree(staging, ignore_errors=True)
        print("  dry run — nothing was deployed, the running bot is untouched.")
        return 0

    activate(cfg, staging)

    hash_ = deployment_hash(cfg.source_roots)
    when = date.today().isoformat()
    write_pin(cfg, hash_, commit, when, n, version=to_version)
    print(f"  pinned {hash_} ({commit or '?'}, {when}) as {vlabel(to_version)}")
    print("  restart the bot to run it — a promote never touches a running process.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
