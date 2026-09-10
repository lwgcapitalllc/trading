"""Bring the account list into line with what the VPS is logged into — by rule, on request.

Aaron, 2026-09-10: *"When I do a scan, it's not just to say what the difference is. I want you to
resync the command center to the VPS... I didn't want to manually have to push a button and say
add this, add that."* And on when it runs: *"sync is 100% manually triggered by me only."*

`terminal_scan` still reads and judges; it writes nothing and must stay that way. This module takes
its judgement and decides what the list may be CHANGED to, then applies that through the same
registry writer a typed-in account goes through. The split is the whole design:

🔴 **An account a bot trades is NEVER changed.** A terminal's login can change under a running bot
— the live runner halts precisely because of it (2026-08-12: a terminal switched accounts under a
running bot and it sized off a stranger's balance for two hours). A sync that agreed with the
terminal would turn that halt into a quiet approval. Anything wrong on such an account comes back
as ATTENTION, in words, and nothing is written for it.

🔴 **A terminal is only ever CLEARED, never SET.** Clearing a claim the box has just contradicted
makes the account unassignable, which is the safe direction. Setting one is a statement of INTENT —
*bots may trade this account through that terminal* — and the box cannot know intent: the two tier
probes were logged into the lab's own terminal for minutes and deliberately left with none, because
a bot pointed there would trade through the terminal the backtests run on. So an added account
arrives with no terminal, and an empty terminal is never filled.

⚠ **Nothing is ever removed.** An account the scan could not see is UNVERIFIED — its terminal is
stopped, or nobody could ask — and deleting on the absence of evidence is this repo's oldest
mistake with a delete attached.

⚠ **Only what the box MEASURED is written**: server, demo-or-live, the symbol ending. The label,
tier, cost profile and note are a person's, and a guessed cost profile would price every backtest
on that account (see `terminal_scan.suggested_registration`).

⚠ **A bot's settings file that cannot be read BLOCKS the whole sync.** Without it there is no way
to tell which accounts a bot trades, and guessing "none" is the one answer that lets the rule above
be broken. Rule 1: *could not ask* never buys the permissive answer.

⚠ **"Demo or live" is written only as `demo` or `live`.** A broker that says `contest`, or nothing,
is ATTENTION — guessing demo for an account that is real is how a bot gets pointed at somebody's
money.

🔴 **The page SHOWS the plan before anything is written, and Sync applies only that plan** (Aaron,
2026-09-10: *"it doesn't show me what it is going to do before I do it"*). `plan_id` is the
fingerprint of what the preview listed. The write re-scans, re-plans and REFUSES if the fingerprint
moved — a terminal that switched account while the reader was looking must not be written on the
strength of an answer they never saw. Re-scanning rather than replaying a cached plan is the point:
a cached plan was judged against bot configs that may have changed since, and "an account a bot
trades is never changed" is only true if it is checked at the moment of the write.

Pure planning over the reconciliation; `apply_sync` is the one function that touches a file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from services import bot_account_registry as registry
from services import terminal_scan

__all__ = [
    "SyncChange",
    "SyncAttention",
    "SyncPlan",
    "plan_sync",
    "plan_id",
    "shown_diffs",
    "apply_sync",
    "commit_message",
]

_KINDS = ("demo", "live")

# What each written field is called on the page. A field with no entry here is shown by its own
# name, which is a bug to fix here rather than a thing to tidy in the browser.
_WORDS = {
    "mt5_path": "Terminal",
    "server": "Server",
    "kind": "Demo or live",
    "symbol_suffix": "Instrument ending",
    "broker": "Broker",
}


@dataclass
class _Diff:
    field: str
    value: Any  # what the list will say
    was: Any  # what the list says now (None on an add — there is no row yet)
    # The evidence, in words. True before AND after the write, so the preview and the receipt say
    # the same sentence — one tense-free fact rather than a "will" and a "did" that can drift.
    why: str
    found: str  # what the page says when it was NOT written


@dataclass
class SyncChange:
    """One write sync will make. `fields` is what changes; an ADD carries the whole new row."""

    account: int
    action: str  # "add" | "update"
    label: str
    fields: dict
    said: list  # what follows from the change, for a person — never a field name
    live: bool = False  # this change made it (or added it as) real money; said in words
    # Field by field: what the list says now, what it will say, and the evidence. This is what
    # the preview lists and what `plan_id` fingerprints — so what was shown IS what is approved.
    diffs: list = field(default_factory=list)


@dataclass
class SyncAttention:
    """Something sync found and deliberately did NOT change. `account` is None only when the
    finding is about a terminal rather than about an account."""

    account: Optional[int]
    label: str
    said: list


@dataclass
class SyncPlan:
    changes: list = field(default_factory=list)
    attention: list = field(default_factory=list)
    blocked: Optional[str] = None  # set ⇒ nothing may be written this time, and why


def _ending(suffix: Optional[str]) -> str:
    if suffix is None:
        return "(not recorded)"
    return suffix or "(nothing)"


def _broker_facts(readings: list) -> tuple[dict, list]:
    """Server, demo-or-live and symbol ending, from terminals the SCAN asked.

    ⚠ **Bot-reported readings carry none of these** — a bot reports only the account number — so
    they are skipped rather than read as "unknown", which would look like a disagreement.
    ⚠ **Two terminals on one account that disagree resolve to NOTHING, with a sentence**: one login
    has one server, so a disagreement means one reading is stale and picking between them is a guess.
    """
    asked = [r for r in readings if r.account_source == "terminal"]
    facts: dict = {}
    trouble: list = []
    for name, what in (("server", "servers"), ("kind", "account types"), ("symbol_suffix", None)):
        values = {getattr(r, name) for r in asked if getattr(r, name) is not None}
        if len(values) == 1:
            facts[name] = values.pop()
        elif len(values) > 1:
            where = ", ".join(sorted(terminal_scan._short(r.install) for r in asked))
            shown = ", ".join(sorted(_ending(v) if name == "symbol_suffix" else v for v in values))
            trouble.append(
                f"It's open on {where} and they report different "
                f"{what or 'instrument endings'} ({shown}), so sync didn't pick one."
            )
    return facts, trouble


def _fact_diffs(row: Any, facts: dict, where: str) -> tuple[list, list]:
    """How the list differs from the box on this account's broker facts."""
    diffs: list = []
    trouble: list = []

    server = facts.get("server")
    if server and server != (row.server or ""):
        diffs.append(
            _Diff(
                "server",
                server,
                row.server,
                f"Read off {where}.",
                f"Your list says server {row.server or '(none)'}; the VPS says {server}.",
            )
        )

    kind = facts.get("kind")
    if kind and kind != (row.kind or ""):
        if kind in _KINDS:
            diffs.append(
                _Diff(
                    "kind",
                    kind,
                    row.kind,
                    f"The broker says this is a {kind.upper() if kind == 'live' else kind} "
                    f"account, read off {where}.",
                    f"Your list says it's a {row.kind or '(none)'} account; the broker says it's "
                    f"{kind.upper() if kind == 'live' else kind}.",
                )
            )
        else:
            trouble.append(
                f"The broker says it's a {kind} account, and your list can only record demo or "
                f"live, so sync left it as {row.kind or '(none)'}."
            )

    if "symbol_suffix" in facts:
        suffix = facts["symbol_suffix"]
        if suffix != row.symbol_suffix:
            diffs.append(
                _Diff(
                    "symbol_suffix",
                    suffix,
                    row.symbol_suffix,
                    f"Measured on {where}.",
                    f"Your list says instruments end {_ending(row.symbol_suffix)}; the VPS "
                    f"quotes {_ending(suffix)}.",
                )
            )
    return diffs, trouble


def plan_sync(
    found: Any,
    rows: list,
    bot_accounts: Optional[dict],
    bot_names: dict,
    today: str,
) -> SyncPlan:
    """Decide what sync may change. Writes nothing.

    `found` is a `terminal_scan.Reconciliation`; `rows` the registered accounts; `bot_accounts`
    maps every registered bot to the account its config names (`None` = benched), and is itself
    `None` when any bot's config could not be read.
    """
    plan = SyncPlan()
    if not found.asked:
        plan.blocked = found.reason or "The VPS refused the scan, so there was nothing to sync."
        return plan
    if bot_accounts is None:
        plan.blocked = (
            "A bot's settings file couldn't be read, so sync couldn't tell which accounts your "
            "bots trade. It changed nothing — fix that file, then sync again."
        )

    bots_on: dict = {}
    for key, account in (bot_accounts or {}).items():
        if account is not None:
            bots_on.setdefault(int(account), []).append(key)

    def names(keys: list) -> str:
        shown = sorted(bot_names.get(k, k) for k in keys)
        return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]

    by_key = {t.key: t for t in found.terminals}
    seen: dict = {}
    for t in found.terminals:
        if t.account is not None:
            seen.setdefault(int(t.account), []).append(t)
    labels = {int(r.account): str(r.label or "") for r in rows}

    # 1 — a bots' terminal logged into an account those bots are not set to trade. The live halt
    # already fires; this is the page saying so. Keyed on the bots' OWN account, so the row check
    # below does not report the same event a second time.
    alarm_terminals: set = set()
    for t in found.terminals:
        if t.state != "owned_by_bot" or t.account is None:
            continue
        wrong: dict = {}
        for bot in t.owned_by_bots or []:
            want = (bot_accounts or {}).get(bot)
            if want is not None and int(want) != int(t.account):
                wrong.setdefault(int(want), []).append(bot)
        for want, keys in sorted(wrong.items()):
            alarm_terminals.add(t.key)
            short = terminal_scan._short(t.install)
            plan.attention.append(
                SyncAttention(
                    want,
                    labels.get(want, ""),
                    [
                        f"{short} is logged into #{t.account}, but {names(keys)} "
                        f"{'is' if len(keys) == 1 else 'are'} set to trade #{want}. A bot stops "
                        f"itself when this happens — log {short} back into #{want}. Sync changed "
                        f"nothing here."
                    ],
                )
            )

    # 2 — every row of the list.
    for row in rows:
        account = int(row.account)
        readings = seen.get(account, [])
        where = ", ".join(
            sorted(
                terminal_scan._short(r.install) for r in readings if r.account_source == "terminal"
            )
        )
        diffs: list = []
        trouble: list = []

        claimed = str(row.mt5_path or "")
        if claimed:
            key = terminal_scan._install_key(claimed)
            t = by_key.get(key)
            if t is not None and t.account is not None and int(t.account) != account:
                short = terminal_scan._short(claimed)
                via = " (reported by the bot there)" if t.account_source == "bot" else ""
                if not (bots_on.get(account) and key in alarm_terminals):
                    diffs.append(
                        _Diff(
                            "mt5_path",
                            "",
                            claimed,
                            f"{short} is logged into #{t.account}{via}, not this account.",
                            f"Your list says it's on {short}, but {short} is logged into "
                            f"#{t.account}{via}.",
                        )
                    )

        facts, fact_trouble = _broker_facts(readings)
        trouble += fact_trouble
        more, kind_trouble = _fact_diffs(row, facts, where)
        diffs += more
        trouble += kind_trouble

        keys = bots_on.get(account)
        if keys and diffs:
            plan.attention.append(
                SyncAttention(
                    account,
                    labels[account],
                    [
                        f"{names(keys)} trade{'s' if len(keys) == 1 else ''} this account, so sync "
                        f"left it alone."
                    ]
                    + [d.found for d in diffs],
                )
            )
        elif diffs and plan.blocked:
            plan.attention.append(SyncAttention(account, labels[account], [d.found for d in diffs]))
        elif diffs:
            after = {d.field: d.value for d in diffs}
            plan.changes.append(
                SyncChange(
                    account,
                    "update",
                    labels[account],
                    after,
                    (
                        ["No bot can be put on this account until you give it a terminal again."]
                        if "mt5_path" in after
                        else []
                    ),
                    # Only when THIS change is what made it real money — every later sync of a
                    # live account saying so again is how the word stops being read.
                    live=(after.get("kind") == "live"),
                    diffs=diffs,
                )
            )
        if trouble:
            plan.attention.append(SyncAttention(account, labels[account], trouble))

    # 3 — accounts logged in on the box that the list has never heard of.
    registered = set(labels)
    for account, readings in sorted(seen.items()):
        if account in registered:
            continue
        keys = bots_on.get(account)
        asked = [r for r in readings if r.account_source == "terminal"]
        if keys:
            plan.attention.append(
                SyncAttention(
                    account,
                    "",
                    [
                        f"{names(keys)} trade{'s' if len(keys) == 1 else ''} #{account}, but it "
                        f"isn't in your list. Sync doesn't add an account your bots trade — add it "
                        f"by hand."
                    ],
                )
            )
            continue
        if not asked:
            # Only a bot has reported it. Step 1 already raised it if those bots are set to
            # trade something else; a bot reports no server or type, so nothing can be added.
            continue
        where = ", ".join(sorted(terminal_scan._short(r.install) for r in asked))
        facts, trouble = _broker_facts(readings)
        kind = facts.get("kind")
        if not trouble and kind not in _KINDS:
            trouble.append(
                f"The broker says it's a {kind} account, and your list can only record demo or "
                f"live, so sync didn't add it."
                if kind
                else "The broker didn't say whether it's demo or live, so sync didn't add it — "
                "guessing demo for real money is the mistake to avoid. Add it by hand once you "
                "know."
            )
        if not trouble and not facts.get("server"):
            trouble.append("The VPS didn't report its server, so sync couldn't add it.")
        if trouble:
            plan.attention.append(
                SyncAttention(
                    account,
                    "",
                    [f"#{account} is logged in on {where}, not in your list."] + trouble,
                )
            )
            continue
        if plan.blocked:
            plan.attention.append(
                SyncAttention(
                    account, "", [f"#{account} is logged in on {where}, not in your list."]
                )
            )
            continue
        company = next((r.company for r in asked if r.company), "") or ""
        suffix = facts.get("symbol_suffix")
        # What the new row will say, as the page lists it. `note` is deliberately not one of them:
        # it carries today's date, and a fingerprint that moved at midnight would refuse a sync
        # whose every fact was unchanged.
        shown = [
            _Diff("server", facts["server"], None, f"Read off {where}.", ""),
            _Diff("kind", kind, None, f"Read off {where}.", ""),
            _Diff("symbol_suffix", suffix, None, f"Measured on {where}.", ""),
        ]
        if company:
            shown.append(_Diff("broker", company, None, f"Read off {where}.", ""))
        plan.changes.append(
            SyncChange(
                account,
                "add",
                "",
                {
                    "account": account,
                    "label": "",
                    "broker": company,
                    "tier": "",
                    "kind": kind,
                    "server": facts["server"],
                    "mt5_path": "",
                    "symbol_suffix": suffix,
                    "account_profile": "",
                    "note": f"Added by Sync VPS on {today}: found logged in on {where}.",
                },
                [
                    f"Logged in on {where} and not in your list. It arrives with no terminal or "
                    f"password, so no bot can use it until you add both."
                ],
                live=(kind == "live"),
                diffs=shown,
            )
        )
    return plan


def plan_id(plan: SyncPlan) -> str:
    """The fingerprint of what a preview listed — the thing a person approves by pressing Sync.

    It covers each change's account, action and every field's before AND after, and nothing else.
    ⚠ **Not the attention list**: nothing there is written, so a finding that appeared since the
    preview does not change what the press does. ⚠ **Not the words**: rewording a sentence is not
    a different plan, and a fingerprint over prose would refuse a sync on a copy edit.
    """
    rows = sorted(
        ([c.account, c.action, [[d.field, d.was, d.value] for d in c.diffs]] for c in plan.changes),
        key=lambda r: (r[0], r[1]),
    )
    blob = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _shown(name: str, value: Any) -> str:
    if name == "mt5_path":
        return terminal_scan._short(value) if value else "none"
    if name == "symbol_suffix":
        # Three states, and they read differently: unmeasured, bare symbols, a real ending.
        return "not recorded" if value is None else (value or "none")
    return str(value) if value else "not set"


def shown_diffs(change: SyncChange) -> list[dict]:
    """A change's diffs as the page prints them — words, never a field name or a path.

    `before` is `None` on an ADD, which the page renders as a new row rather than as a value that
    was empty: *not in your list* and *in your list, blank* are different facts.
    """
    return [
        {
            "what": _WORDS.get(d.field, d.field),
            "before": None if change.action == "add" else _shown(d.field, d.was),
            "after": _shown(d.field, d.value),
            "why": d.why,
        }
        for d in change.diffs
    ]


def apply_sync(path: Any, plan: SyncPlan, known_profiles: Optional[set]) -> tuple[list, list]:
    """Write the plan's changes. Returns `(applied, failed)`; `failed` holds `(change, reason)`.

    ⚠ **Each change is applied onto the row as it is ON DISK NOW**, not the row the plan was built
    from. The scan takes minutes, and an edit a person saved in that window would otherwise be
    overwritten by a stale copy — so an update only ever sets the fields it names, and an add is
    skipped if somebody added the account meanwhile.
    """
    applied: list = []
    failed: list = []
    if plan.blocked:
        return applied, failed
    for change in plan.changes:
        try:
            current = registry.account_by_number(path, change.account)
            if change.action == "add":
                if current is not None:
                    failed.append(
                        (change, "It was added by hand while the sync ran — left as written.")
                    )
                    continue
                entry = registry.RegisteredAccount(**change.fields)
            else:
                if current is None:
                    failed.append((change, "It was removed from your list while the sync ran."))
                    continue
                entry = replace(current, **change.fields)
            registry.upsert_account(path, entry, known_profiles)
            applied.append(change)
        except registry.RegistryError as e:
            failed.append((change, str(e)))
    return applied, failed


def commit_message(applied: list) -> str:
    """One line naming what changed — the only record of it in the history."""
    parts = []
    for c in applied:
        what = "added" if c.action == "add" else "updated " + ", ".join(sorted(c.fields))
        parts.append(f"{c.account} {what}")
    return f"accounts: synced with the VPS - {'; '.join(parts)} [command center]"
