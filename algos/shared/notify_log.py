"""notify_log.py — the SEND LOG and the OUTBOX: what every Telegram message did, and a second chance.

**Why it exists (2026-09-26).** A hand count of the health room over 4–25 Sep 2026 found about
800 messages, of which about 30 needed anybody to act. Cutting that down means HOLDING messages,
and a held message is only safe if it is written down somewhere a person can still read — so
this file is the precondition for every hold in `alert_policy.py`, not an add-on to it. The
second half is the opposite failure: on 19 Sep every TRADING OFF from five bots on two accounts
was lost while the TRADING BACK ON a minute later arrived (ledger: 20 `trading_disabled`, 20
`trading_restored`, zero OFF messages in the room). A send that fails for a reason that goes away
by itself was simply dropped.

**The send log.** One JSON line per outcome, in `algos/logs/notify/<UTC date>.jsonl` (git-ignored,
one folder per machine): time, kind, account, room, label, subject, bot, outcome and — when sent —
Telegram's message id. `outcome` is one of:

    sent     Telegram took it (an in-place edit counts, and says `edit_of`)
    queued   written to the outbox: a TRANSIENT failure to retry, or a deliberate deferral
    held     the policy decided not to send it — `reason` says why, and the daily summary counts it
    dropped  it will never be sent — no room, a permanent refusal, or the outbox gave up after 24h

⚠ **Rule 1 applies to this log too.** A missing file is "nothing was written", which is not the
same as "nothing happened" — the daily summary says which it can prove.

**The outbox.** One JSON file per message in `<log dir>/outbox/`, written atomically. Two kinds
of entry share it because they share every property that matters — a message that must still go
out, owned by nobody once the process that wrote it has moved on:

* `retry` — a TRANSIENT failure (network error, timeout, HTTP 429, HTTP 5xx). Re-sent every minute
  by the monitor with a visible *(delayed, first tried HH:MM)* line, given up after 24 hours.
* `deferred` — a message the policy is holding to see whether it clears by itself (TRADING OFF,
  OFFLINE, STALLED, NO MT5 LINK). Sent when `not_before` passes; CANCELLED by deleting the file.
  **The file's existence is the one source of truth for "still pending"**, so a recovery and the
  flusher cannot both win: whoever renames or deletes it first owns it.

⚠ **NEVER raises, never blocks for long.** Every public function here is on the path of an alert,
and some of those run inside a live trading loop. A failure to log costs a log line; it may never
cost the message or the loop.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_paths import ALGOS_ROOT  # noqa: E402

#: Overrides the folder, for tests and for a machine that keeps logs elsewhere. Read PER CALL so a
#: test's monkeypatched environment reaches a module imported long before it.
ENV_DIR = "LWG_NOTIFY_DIR"

SENT, QUEUED, HELD, DROPPED = "sent", "queued", "held", "dropped"
OUTCOMES = (SENT, QUEUED, HELD, DROPPED)

RETRY, DEFERRED = "retry", "deferred"

#: A transient failure is retried for this long, then counted as given up.
GIVE_UP_SECONDS = 24 * 3600

#: How long a flusher heartbeat stays believable. The monitor runs every minute; five missed runs
#: means nothing is delivering deferred messages, and the policy stops deferring (see `flusher_alive`).
FLUSHER_FRESH_SECONDS = 5 * 60

#: A claimed outbox entry older than this was claimed by a flusher that died mid-send; it is put back.
CLAIM_STALE_SECONDS = 10 * 60


def notify_dir() -> Path:
    override = os.environ.get(ENV_DIR, "").strip()
    return Path(override) if override else ALGOS_ROOT / "logs" / "notify"


def outbox_dir() -> Path:
    return notify_dir() / "outbox"


# ── reading a message's header ───────────────────────────────────────────────────────────────
def parse_header(text: str) -> tuple[str, str]:
    """`(LABEL, subject)` off the first line of an `alert_format.alert()` message.

    The shape is `<icon> <LABEL> · <subject>` and the SUBJECT may itself hold ` · ` (`SOS Fade ·
    LIVE`), so the split is on the FIRST separator only. A message not in the house shape (a
    Telegram command reply, a hand-written notice) returns its first line as the label and no
    subject, which is still a key a person can read in the log.
    """
    try:
        first = str(text or "").strip().splitlines()[0].strip()
    except IndexError:
        return "", ""
    parts = first.split(" ", 1)
    # The icon is one token when there is one. ⚠ ASCII letters only decide it: `ℹ` (the INFO icon)
    # is a Unicode LETTER, so `isalnum` alone reads it as the start of a label.
    if len(parts) == 2 and not any(ch.isascii() and ch.isalnum() for ch in parts[0]):
        first = parts[1].strip()
    label, _, subject = first.partition(" · ")
    return label.strip(), subject.strip()


def body_of(text: str) -> str:
    """Everything after the header line — the FAULT text two copies of one alert share."""
    lines = str(text or "").strip().splitlines()
    return "\n".join(line.strip() for line in lines[1:]).strip()


# ── the send log ─────────────────────────────────────────────────────────────────────────────
def _now_iso(now: Optional[float] = None) -> str:
    ts = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc)
    return ts.isoformat(timespec="seconds")


def record(
    kind: str,
    outcome: str,
    *,
    text: str = "",
    account=None,
    room: str = "",
    bot: Optional[str] = None,
    message_id=None,
    reason: Optional[str] = None,
    now: Optional[float] = None,
    **extra,
) -> None:
    """Append one line to today's send log. NEVER raises.

    ⚠ **One `write()` of one line**, so concurrent appenders (several bots, the monitor, the
    reviewer) interleave whole lines rather than characters on every platform this runs on — the
    same property the bots' own ledger relies on.
    """
    try:
        label, subject = parse_header(text)
        row = {
            "ts": _now_iso(now),
            "kind": kind,
            "outcome": outcome,
            "label": label,
            "subject": subject,
            "bot": bot,
            "account": account,
            "room": str(room or ""),
        }
        if message_id is not None:
            row["message_id"] = message_id
        if reason:
            row["reason"] = reason
        for k, v in extra.items():
            if v is not None:
                row[k] = v
        day = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc)
        folder = notify_dir()
        folder.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with open(folder / f"{day:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as e:  # noqa: BLE001 — a log line may never cost the message
        print(f"notify_log: could not write the send log ({e})")


def read_window(start: datetime, end: datetime) -> tuple[list, Optional[str], int]:
    """Every send-log row with `start <= ts < end`, plus a reason it could not be read, plus how
    many daily files were found.

    ⚠ **Three answers, never two** (rule 1): rows and no problem is a log that was read; a problem
    is a log that could NOT be read; zero files found is neither — nothing was written, which a
    caller must not report as "nothing happened".
    """
    rows: list = []
    found = 0
    day = (start - timedelta(days=1)).date()
    while day <= end.date():
        path = notify_dir() / f"{day:%Y-%m-%d}.jsonl"
        day += timedelta(days=1)
        if not path.exists():
            continue
        found += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            return rows, f"could not read {path.name}: {e}", found
        for line in lines:
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(str(row.get("ts")))
            except (ValueError, TypeError):
                continue  # a torn last line is ordinary; the file is written live
            if start <= ts < end:
                rows.append(row)
    return rows, None, found


# ── transient or permanent ───────────────────────────────────────────────────────────────────
def is_transient(status_code: Optional[int] = None, exc: Optional[BaseException] = None) -> bool:
    """Would the same request succeed if it were simply sent again later?

    A network error or a timeout (an exception with no HTTP answer), HTTP 429 (Telegram's rate
    limit) and any 5xx are TRANSIENT. Every other 4xx is PERMANENT — the chat does not exist, the
    bot was removed from it — and re-sending it for a day would only fill the log.
    """
    if exc is not None:
        return True
    if status_code is None:
        return True
    return status_code == 429 or status_code >= 500


# ── the outbox ───────────────────────────────────────────────────────────────────────────────
def _write_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def enqueue(
    *,
    purpose: str,
    kind: str,
    chat: str,
    text: str,
    account=None,
    bot: Optional[str] = None,
    token_key: str = "",
    reply_to=None,
    markdown: bool = False,
    not_before: Optional[float] = None,
    policy_key: Optional[str] = None,
    reason: Optional[str] = None,
    suffix: str = "",
    now: Optional[float] = None,
) -> Optional[str]:
    """Write one outbox entry and return its id, or `None` if it could not be written. NEVER raises.

    ⚠ **The token itself is never written** — only the NAME of the credential that holds it
    (`token_key`), resolved again at delivery, so this git-ignored folder never holds a secret.
    """
    try:
        now = time.time() if now is None else now
        ident = f"{int(now * 1000):015d}-{uuid.uuid4().hex[:8]}"
        folder = outbox_dir()
        folder.mkdir(parents=True, exist_ok=True)
        _write_atomic(
            folder / f"{ident}.json",
            {
                "id": ident,
                "purpose": purpose,
                "kind": kind,
                "chat": str(chat or ""),
                "text": text,
                "account": account,
                "bot": bot,
                "token_key": token_key or "",
                "reply_to": reply_to,
                "markdown": bool(markdown),
                "created": now,
                "not_before": not_before if not_before is not None else now,
                "policy_key": policy_key,
                "attempts": 0,
                "reason": reason,
                "suffix": suffix,
            },
        )
        return ident
    except Exception as e:  # noqa: BLE001
        print(f"notify_log: could not write to the outbox ({e}) — this message is lost")
        return None


def cancel(ident: Optional[str]) -> bool:
    """Delete a PENDING outbox entry. True only if THIS call removed it — False means it had
    already been claimed by a flusher (so it is being, or has been, sent) or never existed."""
    if not ident:
        return False
    try:
        os.remove(outbox_dir() / f"{ident}.json")
        return True
    except OSError:
        return False


def pending(ident: Optional[str]) -> bool:
    return bool(ident) and (outbox_dir() / f"{ident}.json").exists()


def entries() -> list:
    """Every unclaimed outbox entry, oldest first. Unreadable files are skipped, never deleted."""
    out = []
    try:
        paths = sorted(outbox_dir().glob("*.json"))
    except OSError:
        return out
    for path in paths:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _unclaim_stale(now: float) -> None:
    try:
        for path in outbox_dir().glob("*.claimed"):
            try:
                if now - path.stat().st_mtime > CLAIM_STALE_SECONDS:
                    os.replace(path, path.with_suffix(".json"))
            except OSError:
                continue
    except OSError:
        pass


def delayed_marker(first_tried: float, tz: str = "America/Chicago") -> str:
    """`(delayed, first tried 3:04 PM CDT)` — in the box's clock with the zone named, because the
    reader's Telegram stamp says when it ARRIVED and the whole point of this line is that the two
    differ."""
    try:
        from alert_format import when

        return f"(delayed, first tried {when(datetime.fromtimestamp(first_tried, tz=timezone.utc), tz)})"
    except Exception:  # noqa: BLE001
        return "(delayed)"


def flush(
    deliver: Callable[[dict, str], tuple],
    *,
    now: Optional[float] = None,
    on_delivered: Optional[Callable[[dict, object], None]] = None,
    limit: int = 20,
) -> dict:
    """Deliver every outbox entry that is due. Returns counts by what happened. NEVER raises.

    `deliver(entry, text)` performs the send and returns `(message_id, failure)` where `failure`
    is `None` on success, `"transient"` or `"permanent"`. `on_delivered` is told about every
    successful send (the policy marks a deferred fault as SENT there).

    ⚠ **An entry is CLAIMED by renaming it before it is sent**, so two monitor passes that overlap
    cannot both deliver it, and a recovery that arrives mid-send finds it gone and treats the
    fault as sent — which is the true state by then.
    """
    counts = {"sent": 0, "retry": 0, "dropped": 0, "waiting": 0}
    try:
        now = time.time() if now is None else now
        _unclaim_stale(now)
        done = 0
        for entry in entries():
            if done >= limit:
                break
            ident = entry.get("id")
            if not ident:
                continue
            if float(entry.get("not_before") or 0) > now:
                counts["waiting"] += 1
                continue
            src = outbox_dir() / f"{ident}.json"
            claimed = src.with_suffix(".claimed")
            try:
                os.replace(src, claimed)
            except OSError:
                continue  # cancelled or claimed by somebody else between the listing and here
            done += 1
            purpose = entry.get("purpose")
            first = float(entry.get("first_tried") or entry.get("created") or now)
            if purpose == RETRY and now - first > GIVE_UP_SECONDS:
                record(
                    entry.get("kind", ""),
                    DROPPED,
                    text=entry.get("text", ""),
                    account=entry.get("account"),
                    room=entry.get("chat", ""),
                    bot=entry.get("bot"),
                    reason="gave up after 24 hours of failed re-sends",
                    gave_up=True,
                    attempts=entry.get("attempts"),
                    now=now,
                )
                _remove(claimed)
                counts["dropped"] += 1
                continue
            text = entry.get("text", "")
            if purpose == RETRY:
                text = f"{text}\n{delayed_marker(first)}"
            elif entry.get("suffix"):
                text = f"{text}\n{entry['suffix']}"
            try:
                message_id, failure = deliver(entry, text)
            except Exception as e:  # noqa: BLE001
                message_id, failure = None, "transient"
                print(f"notify_log: delivery raised ({e})")
            if failure is None:
                record(
                    entry.get("kind", ""),
                    SENT,
                    text=text,
                    account=entry.get("account"),
                    room=entry.get("chat", ""),
                    bot=entry.get("bot"),
                    message_id=message_id,
                    delayed=True if purpose == RETRY else None,
                    deferred=True if purpose == DEFERRED else None,
                    first_tried=_now_iso(first) if purpose == RETRY else None,
                    now=now,
                )
                _remove(claimed)
                counts["sent"] += 1
                if on_delivered is not None:
                    try:
                        on_delivered(entry, message_id)
                    except Exception as e:  # noqa: BLE001
                        print(f"notify_log: after-delivery hook failed ({e})")
                continue
            if failure == "transient":
                # A deferred message that then fails keeps the line saying why it was held.
                entry["text"] = text if purpose == DEFERRED else entry.get("text", "")
                entry["purpose"] = RETRY
                entry["first_tried"] = first
                entry["attempts"] = int(entry.get("attempts") or 0) + 1
                try:
                    _write_atomic(src, entry)
                    _remove(claimed)
                except OSError:
                    try:
                        os.replace(claimed, src)
                    except OSError:
                        pass
                counts["retry"] += 1
                continue
            record(
                entry.get("kind", ""),
                DROPPED,
                text=entry.get("text", ""),
                account=entry.get("account"),
                room=entry.get("chat", ""),
                bot=entry.get("bot"),
                reason="Telegram refused it permanently on re-send",
                now=now,
            )
            _remove(claimed)
            counts["dropped"] += 1
    except Exception as e:  # noqa: BLE001
        print(f"notify_log: the outbox flush failed ({e})")
    return counts


def _remove(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ── is anybody delivering deferred messages? ─────────────────────────────────────────────────
def _flusher_file() -> Path:
    return notify_dir() / "flusher.json"


def mark_flusher_alive(now: Optional[float] = None) -> None:
    """Stamped by the monitor on every pass. NEVER raises."""
    try:
        notify_dir().mkdir(parents=True, exist_ok=True)
        _write_atomic(_flusher_file(), {"at": time.time() if now is None else now})
    except Exception as e:  # noqa: BLE001
        print(f"notify_log: could not stamp the flusher heartbeat ({e})")


def flusher_alive(now: Optional[float] = None) -> bool:
    """Whether a process that delivers deferred messages has run in the last five minutes.

    🔴 **A hold that waits on a process which is not running is a DROP.** So the policy only
    defers while this is True. If the monitor is dead, or is old code that has never heard of the
    outbox (the mixed state of a rollout), a fault is sent at once, exactly as before this existed.
    """
    try:
        at = float(json.loads(_flusher_file().read_text(encoding="utf-8")).get("at") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    now = time.time() if now is None else now
    return 0 <= now - at <= FLUSHER_FRESH_SECONDS
