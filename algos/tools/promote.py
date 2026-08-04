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
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for _p in (str(_REPO / "algos" / "live"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_config  # noqa: E402
from live_config import deployed_record  # noqa: E402
from version import deployment_hash, current_commit  # noqa: E402

# Directory names never copied into a snapshot, at any depth.
SKIP_DIRS = {"tests", "__pycache__", ".pytest_cache", ".git"}


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
    out = subprocess.run(["git", "-C", str(_REPO), "status", "--porcelain", "--", *rels],
                         capture_output=True, text=True)
    return [ln[3:].strip() for ln in out.stdout.splitlines() if ln.strip()]


def stage(cfg, trees, dry_run: bool = False) -> tuple[Path, int]:
    """Build the new snapshot in `deployed.new/`, WITHOUT touching the live one.

    Staged rather than written in place because a promote can fail — the verify step below is
    there precisely to catch a snapshot that does not import. A failed promote must leave the
    previous deployment exactly as it was, still importable, still matching its pin. Writing
    into `deployed/` and then discovering the problem would take out a working bot in order to
    tell you the new version is broken.
    """
    staging = cfg.deployed_dir.with_name("deployed.new")
    files = [(src_file, dest_rel / rel)
             for src_tree, dest_rel in trees
             for src_file, rel in _tree_sources(src_tree)]
    if dry_run:
        return staging, len(files)

    if staging.exists():
        shutil.rmtree(staging)
    for src_file, rel in files:
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst)
    return staging, len(files)


def activate(cfg, staging: Path) -> None:
    """Swap the verified snapshot in. Last destructive step, and the only one.

    The old snapshot is REMOVED rather than merged over. Merging leaves a file that was deleted
    upstream sitting in the deployment, still importable, and the hash would then describe a
    tree that exists nowhere in git.
    """
    dest = cfg.deployed_dir
    if dest.exists():
        shutil.rmtree(dest)
    staging.rename(dest)


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
        print("@@" + json.dumps(defaulted))
    """)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(root))
    if out.returncode != 0:
        return False, (out.stderr or out.stdout).strip()
    marker = [ln for ln in out.stdout.splitlines() if ln.startswith("@@")]
    return True, marker[0][2:] if marker else "{}"


def write_pin(cfg, hash_: str, commit: str, when: str, files: int) -> None:
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
        json.dumps({
            "strategy_source_hash": hash_,
            "promoted_commit": commit,
            "promoted_at": when,
            "strategy_package": cfg.strategy_package,
            "strategy_class": cfg.strategy_class,
            "strategy_version": cfg.strategy_version,
            "strategy_params": cfg.strategy_params,
            "files": files,
        }, indent=2) + "\n", encoding="utf-8")


def show(cfg) -> int:
    print(f"{cfg.bot_key} — {cfg.display_name}")
    print(f"  frozen   : {'yes' if cfg.is_frozen else 'NO — importing from the repo tree'}")
    print(f"  pinned   : {cfg.strategy_source_hash or '(unpinned)'}")
    print(f"  promoted : {cfg.promoted_commit or '?'} on {cfg.promoted_at or '?'}")
    print(f"  version  : v{cfg.strategy_version}")
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
    ap.add_argument("--allow-dirty", action="store_true",
                    help="promote uncommitted edits (the recorded commit will not describe them)")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the post-copy import check (not recommended)")
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
        print("Commit them, or pass --allow-dirty and accept that promoted_commit will not "
              "describe what was copied.")
        return 1

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
        defaulted = json.loads(detail or "{}")
        if defaulted:
            # Settings this version has that the deployment does not state. They take the
            # strategy's own defaults, which is how a new version quietly changes behaviour —
            # so it is named here, at the moment you can still decide about it.
            print(f"  ! {len(defaulted)} setting(s) not stated in config.json, taking this "
                  f"version's defaults:")
            for name, val in sorted(defaulted.items()):
                print(f"      {name} = {val}")
            print("    Add them to strategy_params to state them deliberately.")

    new_hash = deployment_hash([staging / r for _, r in trees])
    old_hash = was.get("strategy_source_hash", "")
    if old_hash and old_hash == new_hash:
        print(f"  code is UNCHANGED from the running deployment ({old_hash[:12]})")
    elif old_hash:
        print(f"  code changes: {old_hash[:12]} -> {new_hash[:12]}")

    if args.dry_run:
        shutil.rmtree(staging, ignore_errors=True)
        print("  dry run — nothing was deployed, the running bot is untouched.")
        return 0

    activate(cfg, staging)

    hash_ = deployment_hash(cfg.source_roots)
    when = date.today().isoformat()
    write_pin(cfg, hash_, commit, when, n)
    print(f"  pinned {hash_} ({commit or '?'}, {when})")
    print("  restart the bot to run it — a promote never touches a running process.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
