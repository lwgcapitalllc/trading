"""bot_versions.py — a real VERSION NUMBER for a bot's code, and what sits between two of them.

🔴 **The number on the Configure tab was `v0`, and nothing had ever written it.**
`deployed.json` carries a `strategy_version` int that `live_config.LiveConfig` defaults to 0;
no code path in this repo assigns it. So the card read `v0` before a promote and `v0` after
one, and the single question that tab exists to answer — *am I behind, and by how much* — had
no answer anywhere on the page. Aaron put it plainly on 2026-08-07: *"I just wanna know what
is the version that I have compiled in my backtester versus the version that is deployed."*

**Why not the lab's own `strategy_versions` registry.** It exists, it is content-addressed and
monotonic per strategy, and it is the WRONG SCOPE. It hashes the strategy PACKAGE, while a bot
runs that package plus `engines/` and `backtest/` — which is where most of the logic actually
lives, and is precisely why `algos/live/version.py::deployment_hash` spans all three. A version
off the lab registry would sit unchanged while the engines beneath it moved: the bot would
report the version it was promoted at and trade different rules. That is the exact failure the
deployment pin was built to prevent, re-introduced one layer up as a label.

**Why not just show the hash.** A hash answers *are these the same* and structurally cannot
answer *how far apart*. "Behind by 21" is the whole ask.

So a version is **the number of commits in this repo's history that have touched any of the
bot's trees**, counted at a given commit. Three properties fall out of that, and the page needs
all three:

* it moves when — and only when — the code this bot runs moves;
* it is DERIVED FROM THE GIT HISTORY, so this machine and Aaron's brother's compute the same
  number for the same commit, with no registry to keep in sync and nothing to migrate;
* subtracting two of them is not an estimate of how much is waiting to go out, it IS it.

⚠ **`trees_for` mirrors `algos/tools/promote.py::repo_trees`, and the two must not drift.**
That function decides what is COPIED into a snapshot; this one decides what is COUNTED. A tree
that is promoted but not counted is a change that deploys while this page says you are up to
date — silent, and wrong in the reassuring direction. The subsystem rule forbids importing
across into `algos/`, so the agreement is pinned by a test that READS that file instead
(`tests/test_bot_versions.py`), the same arrangement `test_notification_routing.py` uses for
the Telegram routing table.

⚠ **Every function here answers `None` rather than a number it cannot stand behind.** A missing
commit (never fetched), an unreadable git, a bot with no strategy package: the page renders "we
could not work this out" and no button. `0` would mean *up to date*, which is the most
reassuring answer available and the one most likely to be wrong — the same rule `mt5_link` and
`grid_sensitivity_score` already follow.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import config as cfg

# Mirrors algos/tools/promote.py::repo_trees. See the module docstring.
_SHARED_TREES = ("engines", "backtest")

_GIT_TIMEOUT = 20

# A field default this parser will not guess at. See `_dataclass_defaults`.
_UNPARSED = object()


def trees_for(strategy_package: str) -> list[str]:
    """The repo-relative trees whose history IS this bot's version.

    Empty for a bot with no strategy package — an unpromoted or misconfigured bot, where the
    honest answer is that there is nothing to count.
    """
    if not strategy_package:
        return []
    return [f"strategies/python/{strategy_package}", *_SHARED_TREES]


def _git(*args: str) -> str | None:
    """Run git in the monorepo, or None.

    None on a non-zero exit as well as on a raised error: `rev-list` against a commit this
    clone has never fetched exits 128, and treating that as an empty result would report
    version 0 for a deployment that is simply not describable from here.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(cfg.MONOREPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def has_commit(commit: str) -> bool:
    """Whether this clone holds the commit at all.

    The deployed commit is read off the VPS, so a clone that has not fetched it can compare
    nothing. That is a real state (a fresh clone, a laptop that has not pulled) and it must
    read as *cannot answer*, never as *no changes*.
    """
    if not commit:
        return False
    return _git("cat-file", "-e", f"{commit}^{{commit}}") is not None


def version_at(commit: str, trees: list[str]) -> int | None:
    """How many commits up to `commit` have touched any of `trees`."""
    if not commit or not trees:
        return None
    out = _git("rev-list", "--count", commit, "--", *trees)
    if out is None:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


def uncommitted_edits(trees: list[str]) -> list[str]:
    """Files in `trees` with uncommitted changes.

    The backtester runs the WORKING TREE, not HEAD, so an edited-but-uncommitted strategy is
    genuinely running code that no version number describes. The page says so rather than
    quietly attributing those edits to the HEAD version — a promote from a dirty tree is
    refused by `promote.py` anyway, so this is also the explanation for that refusal.
    """
    if not trees:
        return []
    out = _git("status", "--porcelain", "--", *trees)
    if not out:
        return []
    return [ln[3:].strip() for ln in out.splitlines() if ln.strip()]


def unpushed_commits(trees: list[str]) -> list[str] | None:
    """Commits touching `trees` that exist HERE and not on the branch the VPS pulls from.

    🔴 **A promote pulls on the VPS and deploys from ITS working tree, so the ceiling on what
    can be deployed is the UPSTREAM — never this laptop's HEAD.** A local commit the remote has
    never seen is code the VPS cannot fetch, so the promote runs, reports success, restarts the
    bot, and leaves it behind by exactly those commits. Every number on the page is then
    correct and the reader is left with a Deploy button that appears to have done nothing.

    MEASURED 2026-08-14: a deploy of `mpc_sos_fade_demo` landed **v164** while the backtester
    read **v165**, because the single commit between them was sitting unpushed on this machine.
    The banner said "1 version behind" straight after a successful deploy and nothing on it
    said why. This is the same shape as `uncommitted_edits` one step further out — the working
    tree is not HEAD, and HEAD is not what the VPS can reach.

    `None` when there is no upstream to measure against (a detached HEAD, a branch tracking
    nothing). Never `[]`, which is the claim *everything is pushed*.
    """
    if not trees:
        return None
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not upstream or not upstream.strip():
        return None
    out = _git("log", "--format=%h %s", f"{upstream.strip()}..HEAD", "--", *trees)
    if out is None:
        return None
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def changes_between(from_commit: str, to_commit: str, trees: list[str]) -> list[dict] | None:
    """Every commit touching `trees` in `(from_commit, to_commit]`, newest first.

    `area` is which of the bot's trees a commit touched, so the page can separate *the
    strategy's own rules changed* from *a shared engine moved underneath it*. ⚠ It is NOT a
    claim about whether trades move: `backtest/` holds both the fill model the bot runs on and
    the lab's cache, and no path can tell those apart. Naming the area is derived; naming the
    effect would be a guess wearing a label.
    """
    if not from_commit or not to_commit or not trees:
        return None
    # ONE git call for the whole range, files included.
    #
    # 🔴 It was `git log` for the commit list plus a `git show --name-only` PER COMMIT, and the
    # cost is not the git work — it is 1,080 PROCESS LAUNCHES at ~40ms each. MEASURED on the
    # `tests/test_bot_version.py` suite: 1,080 subprocesses, 51.8s of a 53.7s run, i.e. the whole
    # file. ⚠ **It grew with the repo**: the fan-out is one process per commit in the range, so
    # every commit anybody makes made this endpoint and that suite slower, for ever. Off a bot
    # deployed 89 commits back that is ~3.7s of the /version card's own latency.
    #
    # `--name-only` on the same `git log` gives every commit's file list in one stream, so the
    # range costs ONE process however far behind the bot is.
    #
    # ⚠ **`%x1e` (record separator) prefixes each record and the output is SPLIT on it, rather
    # than parsed line by line.** git puts a blank line between the format line and the file
    # list, so a line-oriented reader has to know that layout; a record separator does not care
    # what git puts between the fields. `%s` is the subject's FIRST LINE, so no record can
    # contain a stray separator.
    out = _git(
        "log",
        "--format=%x1e%h\x1f%s\x1f%cs",
        "--name-only",
        f"{from_commit}..{to_commit}",
        "--",
        *trees,
    )
    if out is None:
        return None

    changes: list[dict] = []
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        header, _, files = record.partition("\n")
        parts = header.split("\x1f")
        if len(parts) != 3:
            continue
        sha, subject, date = parts
        # ⚠ The `tree + "/"` test is KEPT even though the pathspec above already filters git's
        # output. A pathspec of `engines` also matches a top-level FILE named `engines`, which
        # this test excludes — dropping it would quietly widen what counts as touching a tree.
        areas = sorted(
            {
                tree
                for tree in trees
                if any(f.strip().startswith(tree + "/") for f in files.splitlines())
            }
        )
        changes.append(
            {
                "commit": sha,
                "subject": subject,
                "date": date,
                "areas": areas,
            }
        )
    return changes


# ── settings that would change WITHOUT anyone asking ────────────────────────────


def _dataclass_defaults(source: str) -> dict[str, object]:
    """Every dataclass field's literal default in a config module, by field name.

    **`ast`, never `import` or `exec`.** This parses source read out of an arbitrary historical
    commit; running it would execute code from that commit inside the backend.

    Two refusals rather than two guesses:

    * a default that is not a literal (a call, a name, an expression) is `_UNPARSED`, so it is
      reported as *changed, cannot say to what* instead of as unchanged;
    * a field declared in more than one class in the file with DIFFERENT defaults is also
      `_UNPARSED` — `mpc_bleg` subclasses `mpc_sos_fade`'s config and overrides fields, so
      picking one silently would describe the wrong bot.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    found: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                continue
            name = stmt.target.id
            if stmt.value is None:
                value: object = _UNPARSED
            else:
                try:
                    value = ast.literal_eval(stmt.value)
                except (ValueError, SyntaxError):
                    value = _UNPARSED
            if name in found and found[name] != value:
                found[name] = _UNPARSED
            else:
                found[name] = value
    return found


def _config_source_at(commit: str, package: str) -> str | None:
    return _git("show", f"{commit}:strategies/python/{package}/config.py")


def _param_meta(package: str) -> dict[str, dict]:
    """`name → {label, group, desc}` from the strategy's own meta file.

    The wording on the page is the STRATEGY's, copied — the same discipline the trade-fib
    layer follows. A mapping from parameter name to human sentence written here would be a
    second claim about what a setting does, and this repo has met that failure four times.
    """
    path = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / package / f"{package}.meta.json"
    try:
        params = json.loads(path.read_text(encoding="utf-8")).get("params") or []
    except (OSError, ValueError):
        return {}
    return {
        entry["name"]: {
            "label": entry.get("label") or entry["name"],
            "group": entry.get("group") or "",
            "desc": entry.get("desc") or "",
        }
        for entry in params
        if isinstance(entry, dict) and entry.get("name")
    }


def _render(value: object) -> str:
    if value is _UNPARSED:
        return "?"
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def setting_changes(
    package: str, from_commit: str, to_commit: str, stated_params: dict
) -> list[dict] | None:
    """Settings whose DEFAULT moved between the two commits.

    This is the part of a promote nobody asks for and everybody gets. The bot's instance
    config states a value for most settings and takes the code's default for the rest
    (`algos/live/live_config.py` — *"a value that is not in the file is a value this bot does
    not have an opinion about"*). So a default that changes in the repo changes what the bot
    trades on the next promote, with nothing in the request saying so. On the promote in front
    of Aaron today that is the 36-hour time stop.

    `stated` marks the ones the config PINS, which therefore will not move. They are returned
    rather than filtered out because *this changed in the repo and your bot is holding it
    still* is the reassuring half of the same question, and dropping it leaves the reader
    unable to tell "not affected" from "not checked".
    """
    if not package or not from_commit or not to_commit:
        return None
    before_src = _config_source_at(from_commit, package)
    after_src = _config_source_at(to_commit, package)
    if before_src is None or after_src is None:
        return None

    before = _dataclass_defaults(before_src)
    after = _dataclass_defaults(after_src)
    meta = _param_meta(package)

    changes: list[dict] = []
    for name, now in after.items():
        was = before.get(name, _UNPARSED)
        if name in before and was == now:
            continue
        info = meta.get(name, {})
        is_new = name not in before
        changes.append(
            {
                "name": name,
                "label": info.get("label") or name,
                "group": info.get("group") or "",
                "desc": info.get("desc") or "",
                # `was` is "" for a setting the deployed version did not HAVE, and `is_new` says
                # which. Rendering "(new)" here would put the page's wording in the service, and
                # "Off" would be a lie in the safe-looking direction — the old code had no such
                # lever at all, which is not the same as having it switched off.
                "is_new": is_new,
                "was": "" if is_new else _render(was),
                "now": _render(now),
                "stated": name in (stated_params or {}),
            }
        )
    changes.sort(key=lambda c: (c["stated"], c["label"]))
    return changes


def compare(strategy_package: str, deployed_commit: str, stated_params: dict) -> dict:
    """Everything the Configure tab needs to say how far behind a bot is.

    Always returns a dict. `comparable` False carries a `reason` in plain words, because the
    states that make this unanswerable (never promoted, commit not fetched, no git) are
    ordinary and each has a different fix.
    """
    trees = trees_for(strategy_package)
    local_version = version_at("HEAD", trees)
    dirty = uncommitted_edits(trees)
    unpushed = unpushed_commits(trees)
    base = {
        "deployed_version": None,
        "local_version": local_version,
        "versions_behind": None,
        "uncommitted_files": dirty,
        "unpushed_commits": unpushed,
        "comparable": False,
        "reason": "",
        "changes": [],
        "setting_changes": [],
    }

    if not trees:
        base["reason"] = (
            "This bot has no strategy package recorded, so there is nothing to compare."
        )
        return base
    if local_version is None:
        base["reason"] = "Could not read this repo's history."
        return base
    if not deployed_commit:
        base["reason"] = "This bot has never been promoted, so it has no deployed version yet."
        return base
    if not has_commit(deployed_commit):
        base["reason"] = (
            f"This machine has not fetched the commit the bot was deployed from "
            f"({deployed_commit}). Pull, then reload."
        )
        return base

    deployed_version = version_at(deployed_commit, trees)
    if deployed_version is None:
        base["reason"] = "Could not count the deployed version from this repo's history."
        return base

    changes = changes_between(deployed_commit, "HEAD", trees) or []
    settings = setting_changes(strategy_package, deployed_commit, "HEAD", stated_params) or []

    base.update(
        {
            "deployed_version": deployed_version,
            "versions_behind": max(0, local_version - deployed_version),
            "comparable": True,
            "changes": changes,
            "setting_changes": settings,
        }
    )
    return base
