"""alert_policy.py — which HEALTH messages are sent now, held, or held to see if they clear.

**Why it exists (2026-09-26).** The health room carried ~800 messages in three weeks and ~30 needed
anybody to act. The cure is not fewer alerts in the code — each one was written for a reason — but
ONE place that knows which messages are repeats, which faults healed on their own before anybody
could act, and which are routine. See `notes/telegram-and-notifications.md` → *The health room's
noise*.

**The rule every line here answers to:** nothing important may become invisible. Every real problem
reaches the user at least once; anything held is written to the send log as `held` with its reason
(`notify_log`), and the daily summary counts it.

**Generic at the SEAM.** The policy is a table keyed by the alert's LABEL — the two words every
health message leads with (`alert_format.alert`). No strategy, no bot and no sender is named here, so
a bot written next year inherits all of it by using the house shape, and a new label is one row.

**What it can decide** (`decide`), for a HEALTH message only — trades and setups are never held:

    SEND   now, as always
    HOLD   not sent; logged `held` with the reason
    DEFER  written to the outbox with a deadline; sent then unless its recovery arrives first

The rules, in the order `decide` applies them:

1. **A recovery ends its fault.** A label listed in a fault's `recovered_by` looks up that fault's
   open episode. Still held (deferred) → both are held: it healed before anybody could act. Already
   sent → the recovery is sent, once. Held a moment ago → a follow-up recovery is held too (the
   watchdog's RESTARTED and then the bot's own ONLINE after one crash are one event).
2. **NEVER held**: every label in `NEVER_HOLD`, anything with HALT in it, and every REMINDER. They
   still update the memory (a STILL HALTED ends a held TRADING OFF).
3. **Routine**: a label held outright for a named subject (the chat bot's own nightly restart).
4. **Part of a Command Center action**: a bot's STOPPED while a deploy or restart it did not start
   is in flight — the action's own message already says it.
5. **Hold to see if it clears** (`defer_s`): OFFLINE, STALLED and NO MT5 LINK for 5 minutes, TRADING
   OFF for 15 and per ACCOUNT. ⚠ **Only while a deliverer is alive** (`notify_log.flusher_alive`) —
   a hold that waits on a process which is not running is a drop, so without one it sends at once.
6. **One alert per fault**: the same label, about the same bot, with the same body, is sent once;
   a repeat is held until the text changes, the fault is recovered, or 24 hours pass (`sticky`
   rules remember for ever — "once per strategy version").

⚠ **Cross-process by design.** Several bots, the watchdog and the reviewer all send, and each is its
own process, so the memory is a JSON file beside the send log, read and written under a lock file.
**Every failure answers SEND** — an unreadable state, a lock that cannot be taken, an exception
anywhere. A policy that can swallow an alert is worse than the noise it removes.

⚠ **NEVER raises**: it sits on the path of every health alert, some of them inside a trading loop.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify_log  # noqa: E402

SEND, HOLD, DEFER = "send", "hold", "defer"

#: How long an identical fault is remembered when nothing recovers it.
DEDUP_SECONDS = 24 * 3600
#: How long after a quick recovery a FOLLOW-UP recovery (the bot's own ONLINE after the watchdog's
#: RESTARTED) still counts as part of it.
QUIET_FOLLOW_UP_SECONDS = 5 * 60


@dataclass(frozen=True)
class Rule:
    """One row of the policy — see the module docstring for what each field does."""

    never_hold: bool = False
    dedup: bool = True
    defer_s: int = 0
    recovered_by: tuple = ()
    scope: str = "bot"  # "bot" or "account"
    sticky: bool = False
    hold_subjects: tuple = ()
    hold_during_action: bool = False
    needs_sent_fault: bool = False
    note: str = ""


#: Labels that are never held, whatever else is true. Anything with HALT in its label, and every
#: REMINDER, is added by `_never_hold` so a new halt message cannot be forgotten here.
NEVER_HOLD = frozenset(
    {
        "FLEET HALT",
        "ACCOUNT MISMATCH",
        "CLOSE FAILED",
        "SCALE-IN CLOSE FAILED",
        "ORDER REFUSED",
        "ORDER REJECTED",
        "NOT BACK ONLINE",
        "CANNOT SEE THE BOTS",
    }
)

#: A successful start clears every remembered fault of the bot that had no recovery of its own.
DEFAULT_RECOVERED_BY = ("ONLINE", "DEPLOYED")

RULES = {
    # ── hold to see whether it clears ────────────────────────────────────────────────────────
    "OFFLINE": Rule(
        defer_s=5 * 60,
        recovered_by=("BACK ONLINE", "RESTARTED", "ONLINE", "DEPLOYED"),
        note="held 5 minutes to see whether the watchdog's restart brings it back",
    ),
    "STALLED": Rule(
        defer_s=5 * 60,
        recovered_by=("RECOVERED",),
        note="held 5 minutes to see whether its heartbeat resumes",
    ),
    "NO MT5 LINK": Rule(
        defer_s=5 * 60,
        recovered_by=("RECONNECTED", "RECONNECTED — STILL HALTED"),
        note="held 5 minutes to see whether the terminal link comes back",
    ),
    "TRADING OFF": Rule(
        defer_s=15 * 60,
        scope="account",
        recovered_by=("TRADING BACK ON", "STILL HALTED"),
        note="held 15 minutes to see whether the account can trade again; one message for every "
        "bot on the account",
    ),
    "TRADING BACK ON": Rule(dedup=False, scope="account", needs_sent_fault=True),
    # ── one alert per fault, cleared by a real start ─────────────────────────────────────────
    "WILL NOT START": Rule(recovered_by=("ONLINE", "DEPLOYED", "BACK ONLINE")),
    # ── once per bot per strategy version: the version is in the body ────────────────────────
    "NO SETUP MESSAGES": Rule(sticky=True),
    # ── the chat bot's own routine restart ───────────────────────────────────────────────────
    "COMMANDS ONLINE": Rule(dedup=False, hold_subjects=("Telegram bot",)),
    "RESTARTED": Rule(dedup=False, hold_subjects=("Telegram bot",)),
    # ── a deliberate stop that a Command Center action already announced ─────────────────────
    "STOPPED": Rule(dedup=False, hold_during_action=True),
    # ── the reviewer keeps its own memory of what it has said ────────────────────────────────
    "REVIEW": Rule(dedup=False),
}

_SEVERE = ("⛔", "⚠️", "⚠")


def _never_hold(label: str) -> bool:
    return label in NEVER_HOLD or "HALT" in label or label.startswith("REMINDER")


def _rule(label: str, text: str) -> Rule:
    rule = RULES.get(label)
    if rule is not None:
        return rule
    # No row: a CRITICAL or WARNING is a fault and gets one-alert-per-fault; anything else (an OK,
    # an INFO, a message not in the house shape) is sent as it always was.
    head = str(text or "").lstrip()
    return Rule(dedup=head.startswith(_SEVERE), recovered_by=DEFAULT_RECOVERED_BY)


#: label -> the fault labels it recovers. Built from the table so it cannot disagree with it.
RECOVERS = {}
for _label, _r in RULES.items():
    for _rec in _r.recovered_by:
        RECOVERS.setdefault(_rec, []).append(_label)


@dataclass
class Decision:
    action: str = SEND
    reason: str = ""
    label: str = ""
    subject: str = ""
    episode: Optional[str] = None  # the open-episode key a DEFER opens, or a SEND closes
    until: Optional[float] = None
    suffix: str = ""
    covered: bool = False  # held because an identical alert already REACHED the room
    fault_key: Optional[str] = None
    body_hash: Optional[str] = None
    sticky: bool = False
    fault_scope: Optional[str] = None
    clears_on_start: bool = True
    extra: Optional[dict] = None  # facts for the send log: how long a fault lasted, what it ended


# ── the memory on disk ───────────────────────────────────────────────────────────────────────
def _state_path() -> Path:
    return notify_log.notify_dir() / "policy_state.json"


def _lock_path() -> Path:
    return notify_log.notify_dir() / "policy.lock"


@contextmanager
def _locked(wait: float = 2.0, stale: float = 10.0):
    """Hold the policy's lock file, or yield False when it cannot be had in `wait` seconds.

    ⚠ A lock older than `stale` belongs to a process that died holding it and is broken. The wait is
    short on purpose: this runs inside trading loops, and a caller that cannot have the lock SENDS.
    """
    path = _lock_path()
    got = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + wait
        while True:
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                got = True
                break
            except FileExistsError:
                try:
                    if time.time() - path.stat().st_mtime > stale:
                        os.remove(path)
                        continue
                except OSError:
                    pass
                if time.time() >= deadline:
                    break
                time.sleep(0.02)
    except Exception as e:  # noqa: BLE001
        print(f"alert_policy: could not take the lock ({e}) - sending")
    try:
        yield got
    finally:
        if got:
            try:
                os.remove(path)
            except OSError:
                pass


def _load() -> dict:
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except (OSError, ValueError):
        pass
    return {}


def _save(state: dict) -> None:
    path = _state_path()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _prune(state: dict, now: float) -> None:
    faults = state.get("faults", {})
    for k in [
        k for k, v in faults.items() if not v.get("sticky") and now - v.get("at", 0) > 7 * 86400
    ]:
        del faults[k]
    eps = state.get("episodes", {})
    for k in [k for k, v in eps.items() if now - v.get("at", 0) > 2 * 86400]:
        del eps[k]


def _hash(body: str) -> str:
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


def _scope(rule: Rule, bot, subject: str, account) -> str:
    if rule.scope == "account" and account is not None:
        return f"acct:{account}"
    return f"bot:{bot or subject}|{account}"


def _when(ts: float) -> str:
    try:
        from datetime import datetime, timezone

        from alert_format import when

        return when(datetime.fromtimestamp(ts, tz=timezone.utc))
    except Exception:  # noqa: BLE001
        return "earlier"


def _span(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds}s"
    return f"{round(seconds / 60)} min"


# ── is a Command Center action in flight for this bot? ───────────────────────────────────────
def action_in_progress(bot) -> Optional[str]:
    """The action (`promote`, `restart`, `start`) whose thread file is live for this bot, or None.

    The Command Center writes `<instance>/alert_thread.json` before it stops or starts a bot, and the
    bot consumes it once it is ONLINE (`runner.clear_alert_thread`). A file with no `action` is the
    older Command Center's, which always sent PROMOTED or RESTARTING ONTO DEPLOYED CODE — both a
    restart — so it counts as one. Expired or unreadable is None.
    """
    if not bot:
        return None
    try:
        from repo_paths import INSTANCES

        raw = json.loads((INSTANCES / str(bot) / "alert_thread.json").read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or float(raw.get("expires_at", 0)) < time.time():
            return None
        return str(raw.get("action") or "promote")
    except (OSError, ValueError, TypeError):
        return None


# ── the decision ─────────────────────────────────────────────────────────────────────────────
def decide(
    kind: str, text: str, *, account=None, bot=None, now: Optional[float] = None
) -> Decision:
    """What to do with this message. NEVER raises; any failure answers SEND."""
    try:
        return _decide(kind, text, account=account, bot=bot, now=now)
    except Exception as e:  # noqa: BLE001
        print(f"alert_policy: decision failed ({e}) - sending")
        return Decision(SEND, reason="policy failed")


def _decide(kind, text, *, account, bot, now) -> Decision:
    if kind != "health":
        return Decision(SEND)
    now = time.time() if now is None else now
    label, subject = notify_log.parse_header(text)
    rule = _rule(label, text)
    scope = _scope(rule, bot, subject, account)
    dec = Decision(SEND, label=label, subject=subject)
    never = _never_hold(label)

    with _locked() as got:
        if not got:
            dec.reason = "policy lock unavailable"
            return dec
        state = _load()
        _prune(state, now)
        faults = state.setdefault("faults", {})
        episodes = state.setdefault("episodes", {})
        changed = False

        # 1. a recovery ends its faults
        held_by_recovery = None
        fault_was_sent = False
        for fault_label in RECOVERS.get(label, []):
            frule = RULES[fault_label]
            fscope = _scope(frule, bot, subject, account)
            ekey = f"{fault_label}|{fscope}"
            for k in [k for k in faults if k.startswith(f"{fault_label}|{fscope}")]:
                del faults[k]
                changed = True
            ep = episodes.get(ekey)
            if not ep:
                continue
            if ep.get("state") == "pending":
                entry = _outbox_entry(ep.get("outbox"))
                if (
                    entry is not None
                    and entry.get("purpose") == notify_log.DEFERRED
                    and notify_log.cancel(ep.get("outbox"))
                ):
                    lasted = now - float(ep.get("at", now))
                    notify_log.record(
                        "health",
                        notify_log.HELD,
                        text=entry.get("text", ""),
                        account=entry.get("account"),
                        room=entry.get("chat", ""),
                        bot=entry.get("bot"),
                        reason=f"cleared after {_span(lasted)}, inside its hold - {label}",
                        duration_s=int(lasted),
                        now=now,
                    )
                    episodes[ekey] = {
                        "state": "cancelled",
                        "at": ep.get("at", now),
                        "cancelled_at": now,
                    }
                    held_by_recovery = (
                        f"its {fault_label} cleared after {_span(lasted)} and was never sent"
                    )
                    dec.extra = {"duration_s": int(lasted), "recovers": fault_label}
                else:
                    # Already claimed by the flusher, or turned into a retry: it went out (or is
                    # going), so the reader needs this recovery.
                    del episodes[ekey]
                    fault_was_sent = True
                changed = True
            elif ep.get("state") == "sent":
                lasted = now - float(ep.get("at", now))
                dec.extra = {"duration_s": int(lasted), "recovers": fault_label}
                del episodes[ekey]
                fault_was_sent = True
                changed = True
            elif ep.get("state") == "cancelled":
                if now - float(ep.get("cancelled_at", 0)) <= QUIET_FOLLOW_UP_SECONDS:
                    held_by_recovery = f"part of a {fault_label} that cleared on its own"
        if label in DEFAULT_RECOVERED_BY:
            for k in [
                k for k, v in faults.items() if v.get("scope") == scope and v.get("clears_on_start")
            ]:
                del faults[k]
                changed = True

        if never:
            dec.reason = "never held"
        elif held_by_recovery:
            dec.action, dec.reason = HOLD, held_by_recovery
        elif rule.needs_sent_fault and not fault_was_sent:
            dec.action = HOLD
            faults_of = " or ".join(f for f, r in RULES.items() if label in r.recovered_by)
            dec.reason = f"no {faults_of or 'fault'} was sent for this account"
        elif rule.hold_subjects and subject in rule.hold_subjects:
            dec.action, dec.reason = HOLD, f"routine for {subject}"
        elif rule.hold_during_action and action_in_progress(bot):
            dec.action = HOLD
            dec.reason = (
                f"part of a Command Center {action_in_progress(bot)} - its own message says it"
            )
        elif rule.defer_s:
            ekey = f"{label}|{scope}"
            ep = episodes.get(ekey)
            # "Pending" is the outbox file existing — or, for the few milliseconds between this
            # decision and `attach`, an episode opened a moment ago with no file named yet.
            waiting = (
                ep
                and ep.get("state") == "pending"
                and (
                    notify_log.pending(ep.get("outbox"))
                    or (not ep.get("outbox") and now - float(ep.get("at", 0)) < 10)
                )
            )
            if waiting:
                dec.action, dec.reason = (
                    HOLD,
                    f"one {label} is already waiting for this {rule.scope}",
                )
            elif (
                ep
                and ep.get("state") == "sent"
                and now - float(ep.get("sent_at", ep.get("at", 0))) < DEDUP_SECONDS
            ):
                # Sent and never recovered. ⚠ Only for a day: a bot restarted since has forgotten
                # it ever said the fault, so no recovery may ever come to close this.
                dec.action, dec.reason, dec.covered = (
                    HOLD,
                    f"{label} already sent at {_when(ep.get('sent_at', ep.get('at', now)))}",
                    True,
                )
            elif notify_log.flusher_alive(now):
                dec.action = DEFER
                dec.until = now + rule.defer_s
                dec.episode = ekey
                dec.reason = rule.note or f"held {_span(rule.defer_s)} to see whether it clears"
                dec.suffix = (
                    f"Held {_span(rule.defer_s)} to see whether it cleared on its own - it has not. "
                    f"First seen {_when(now)}."
                )
                if rule.scope == "account" and account is not None:
                    dec.suffix += f" Account {account}: one message for every bot on it."
                episodes[ekey] = {"state": "pending", "at": now}
                changed = True
            else:
                dec.reason = "sent at once - nothing is running that would deliver it later"
                dec.episode = ekey
        elif rule.dedup:
            body = notify_log.body_of(text)
            fkey = f"{label}|{scope}"
            prev = faults.get(fkey)
            h = _hash(body)
            if (
                prev
                and prev.get("body") == h
                and (rule.sticky or now - prev.get("at", 0) < DEDUP_SECONDS)
            ):
                dec.action, dec.covered = HOLD, True
                dec.reason = f"same {label} already sent at {_when(prev.get('at', now))}"
            else:
                dec.fault_key, dec.body_hash, dec.sticky = fkey, h, rule.sticky
                dec.fault_scope = scope
                # A start clears it unless it is `sticky` (once per VERSION — a restart on the
                # same code must not say it again).
                dec.clears_on_start = not rule.sticky and (
                    not rule.recovered_by
                    or bool(set(rule.recovered_by) & set(DEFAULT_RECOVERED_BY))
                )

        if changed:
            _save(state)
    return dec


def _outbox_entry(ident) -> Optional[dict]:
    if not ident:
        return None
    try:
        return json.loads((notify_log.outbox_dir() / f"{ident}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def attach(dec: Decision, outbox_id: str) -> None:
    """Record which outbox entry a DEFER wrote, so a recovery can cancel it. NEVER raises."""
    _update(
        lambda st: (
            st.setdefault("episodes", {}).setdefault(dec.episode, {}).update(outbox=outbox_id)
        )
    )


def note_outcome(dec: Optional[Decision], outcome: str, now: Optional[float] = None) -> None:
    """After a SEND: remember the fault (for one-alert-per-fault) and open the episode a recovery
    will close. Only a message that was sent or queued is remembered — a DROPPED one was never read,
    so its repeat must not be held as a duplicate of it. NEVER raises."""
    if dec is None or dec.action != SEND or outcome not in (notify_log.SENT, notify_log.QUEUED):
        return
    if not dec.fault_key and not dec.episode:
        return
    now = time.time() if now is None else now

    def _apply(st):
        if dec.fault_key:
            st.setdefault("faults", {})[dec.fault_key] = {
                "body": dec.body_hash,
                "at": now,
                "sticky": dec.sticky,
                "scope": dec.fault_scope,
                "clears_on_start": dec.clears_on_start,
            }
        if dec.episode:
            st.setdefault("episodes", {})[dec.episode] = {
                "state": "sent",
                "at": now,
                "sent_at": now,
            }

    _update(_apply)


def delivered(entry: dict, now: Optional[float] = None) -> None:
    """The flusher delivered a DEFERRED entry: its episode is now SENT. NEVER raises."""
    key = entry.get("policy_key")
    if not key:
        return
    now = time.time() if now is None else now

    def _apply(st):
        ep = st.setdefault("episodes", {}).get(key)
        if ep is not None and ep.get("outbox") in (None, entry.get("id")):
            ep.update(state="sent", sent_at=now)

    _update(_apply)


def _update(fn) -> None:
    try:
        with _locked() as got:
            if not got:
                return
            state = _load()
            fn(state)
            _save(state)
    except Exception as e:  # noqa: BLE001
        print(f"alert_policy: could not update its memory ({e})")
