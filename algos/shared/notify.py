"""
notify.py — Telegram notification helper for VPS-side components.

Single source of truth for sending Telegram messages from bots, the live runner, monitor,
and any other VPS process. Every message declares its KIND (`TRADE`, `HEALTH` or `SIGNAL`) and
the kind picks the room — see the routing block below. A message also carries the ACCOUNT it is
about, and that account's own rooms win: two people own two live accounts on this box, and
neither may read the other's fills.

Credentials come from `credentials.py` (env var, else the git-ignored `algos/credentials.json`)
— never from a literal in this file. The previous token was committed here and in five other
files; it was revoked 2026-07-30 and the constants were replaced by this lookup.

Usage:
    from notify import send_telegram, TRADE, HEALTH
    send_telegram("🟢 *Bot online*", HEALTH)
"""

import json
import sys
from pathlib import Path

try:
    import requests as _requests
except ImportError:
    _requests = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credentials import get as _cred  # noqa: E402
from credentials import telegram_credentials
from repo_paths import ALGOS_ROOT  # noqa: E402

# ── Where a message goes is decided by WHAT IT IS ────────────────────────────────────────────
#
# Two rooms, because they are read at different times and by a different reflex. A fill is the
# account moving and it is read the moment it arrives; a re-warm after a link blip is a fact
# about the machinery, worth having and worth scrolling past. Mixing them costs the trade alert
# its meaning — a chat that pings nine times a day for routine chatter is one you learn to
# ignore, and the day you mute it you mute your fills with it. The dead-man's switch already
# makes the same call one level out by using EMAIL.
#
# `kind` is a REQUIRED argument on every sender here, deliberately. A default would route
# silently, and "the wrong room, quietly" is precisely the failure this exists to end — the
# same reasoning that makes the ledger's stream routing a table rather than a guess. A new call
# site that states nothing fails at the call, and `test_notification_routing.py` greps every
# call site in the repo so it fails in the SUITE first.
#
# SIGNAL is the third room, added 2026-08-13. A pre-trade setup alert is a third reflex again:
# read when you have time rather than the moment it arrives, and MEASURED at roughly five times
# the volume of fills (11/month against 2/month on `sos_fade` over 6.5 years — see
# `docs/LIVE_SETUP_ALERTS.md` §3). Putting that in the trades chat would bury the fills under
# setups that mostly do not become trades, which is the exact failure the split already exists to
# prevent, arriving from a new direction.
TRADE = "trade"
HEALTH = "health"
SIGNAL = "signal"

#: kind -> the credential key naming its chat. HEALTH and SIGNAL fall back to the TRADE chat (see
#: `chat_for`); a message in the wrong room beats a message nobody sends.
CHAT_KEYS = {
    TRADE: "telegram_chat_id",
    HEALTH: "telegram_health_chat",
    SIGNAL: "telegram_signal_chat",
}

_warned = False
_warned_keys: set = set()
_warned_kinds: set = set()
_warned_no_room: set = set()
_warned_unreadable: set = set()

# ── EVERY ACCOUNT NAMES ITS OWN ROOMS (2026-09-13) ───────────────────────────────────────────
#
# Aaron's call, the day a second person's live account joined the box: two owners, two lots of
# real money, and neither may read the other's fills. So a room is a property of the ACCOUNT —
# three fields on its row in `markets/fx/accounts.json` — and a message is routed by the account
# it is ABOUT, never by a setting on the bot. A bot moved onto another account reports into that
# account's rooms with no edit, which is the same reason no bot's NAME says demo or live.
#
# 🔴 **A LIVE ACCOUNT NEVER BORROWS A ROOM.** A trade or a signal for a live account that names no
# room of its own is NOT SENT, and says so once. That is the opposite call from every other
# fallback in this file, and the asymmetry is the point: a message in the wrong room is normally a
# nuisance you can see and fix, while a live fill in a room the wrong person reads is somebody
# else's money on somebody's screen and cannot be taken back. The runner REFUSES TO START a live
# bot whose account names no trade and no signal room, so this is a configuration that changed
# under a running bot rather than an ordinary state.
#
# ⚠ **HEALTH is optional and falls through to the shared room, live accounts included.** Most of
# it is about the one box every account shares, and every message names its account in its
# subject. An account that names a health room gets it, with no code change.
#
# ⚠ **A DEMO account may name rooms too and they are honoured.** None does today; demo accounts
# keep the shared rooms in `credentials.json`, exactly as they always have.
#
# ⚠ **Committed, not in `credentials.json`**: a chat id is not a secret (nothing can post without
# the token, which stays in the credentials file), so a room reaches the box with a pull and
# survives a rebuild — the per-bot rooms in the instance configs are committed the same way. Read
# per message, so an edit reaches a running bot with no restart.
#
# ⚠ **`shared/telegram_rooms.json` was retired 2026-09-13 and DELETED 2026-09-14**, once both
# live bots had restarted onto this code. Only the older code read it, and only for a live account.
LIVE = "live"

#: kind -> the field on an account's registry row naming that kind's room.
ACCOUNT_ROOM_KEYS = {
    TRADE: "telegram_trade_chat",
    HEALTH: "telegram_health_chat",
    SIGNAL: "telegram_signal_chat",
}

#: The rooms a LIVE account must name before a bot on it may trade. HEALTH is deliberately not one
#: of them — see the block above. `live/runner.py` refuses to start without these.
REQUIRED_LIVE_KINDS = (TRADE, SIGNAL)

# ── A SECOND ROOM MAY GET A COPY OF THE SETUPS, AND ONLY THE SETUPS (2026-09-23) ─────────────
#
# The ask (the user, 2026-09-23): the setup messages about one owner's account also arrive in the
# OTHER owner's signals room, so both read the same setups while each account's fills stay where
# they are. Nothing about the primary room changes — this adds a destination, it never moves one.
#
# 🔴 **SIGNAL ONLY, and that asymmetry is the whole design.** A setup is an opinion about where
# price is; a fill is somebody's money, and the one-room rule above exists precisely so a live
# fill never reaches a room the wrong person reads. So `kind` is checked at the copy: TRADE and
# HEALTH never copy, whatever this file says. A copy of a fill is the one thing here that could
# not be taken back.
#
# ⚠ **The copy is FLAT — never threaded.** A `reply_to` id belongs to the chat it was posted in,
# so replaying it in another room is either refused by Telegram or files the follow-up under a
# stranger's message. The copy room gets each message loose; the thread stays in the room the
# bot's own account owns.
#
# ⚠ **Its own file, NOT a field on the account's registry row, and that is deliberate.** The
# Command Center REPLACES a row when somebody edits that account on the page — it keeps only the
# `_`-prefixed prose keys (`bot_account_registry.upsert_account`) — so a field the page does not
# know about would be dropped the next time anyone touched the account: silently, and discovered
# months later by a room that quietly stopped receiving. This file is written by a person and
# read here, and nothing else touches it.
#
# ⚠ **Read through `repo_paths`, per message, exactly like the registry**, so an edit reaches a
# running bot with no restart and a bot running from its frozen snapshot still reads the repo's
# copy. 🔴 **The CODE here IS frozen into that snapshot** (`algos/shared` is in
# `live_config.ORDER_PATH_ROOTS`), so a bot promoted before this change sends no copies until its
# next promote — the data arriving on a pull is not enough on its own.
SIGNAL_COPIES = ALGOS_ROOT / "markets" / "fx" / "signal_copies.json"

#: Which copy problems have already been printed. Same reason as `_warned_kinds`: a bot sends on
#: a bar loop, so a broken copy destination must say so once rather than on every setup.
_warned_copies: set = set()


def signal_copy_chats(account) -> tuple:
    """The extra rooms a COPY of this account's SETUP messages goes to. `()` when there are none.

    ⚠ **The three states collapse to two here, unlike `account_rooms`, and on purpose.** A file
    naming nobody and a file that cannot be read both mean NO COPY: the message itself has already
    gone to the room that owns it, so there is nothing a caller could do differently with the
    distinction. It is SAID once per cause instead of returned.

    NEVER raises.
    """
    if account is None:
        return ()
    try:
        raw = json.loads(SIGNAL_COPIES.read_text(encoding="utf-8"))
        rooms = (raw.get("copies") or {}).get(str(account)) or ()
    except FileNotFoundError:
        return ()  # nobody on this box has asked for a copy — the ordinary state, said nothing about
    except (OSError, ValueError, AttributeError) as e:
        if "unreadable" not in _warned_copies:
            _warned_copies.add("unreadable")
            print(
                f"notify: {SIGNAL_COPIES} could not be read, so NO setup copies are being sent "
                f"({e}). Every message still reaches its own room."
            )
        return ()
    if isinstance(rooms, str):  # one room may be written as a bare string
        rooms = (rooms,)
    # `dict.fromkeys`: a room listed twice is one room, and the order stays the one a person wrote.
    return tuple(dict.fromkeys(str(c).strip() for c in rooms if str(c).strip()))


def _copy_signal(text: str, account, primary: str, token: str, mode) -> None:
    """Post `text` to every extra room this account names for setups. Never raises.

    ⚠ Called only AFTER the message's own room has taken it, so a copy can never stand in for the
    real one, and a failure here leaves the primary's message id — the thread everything replies
    to — untouched.

    `mode` is the parse mode that actually DELIVERED the primary, not the one asked for: a message
    whose Markdown Telegram rejected was resent as plain text, and a copy that asked for parsing
    again would fail in the copy room alone.
    """
    if _requests is None:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat in signal_copy_chats(account):
        if chat == primary:
            continue  # the copy room IS the room it has already gone to
        body = {"chat_id": chat, "text": text}
        if mode:
            body["parse_mode"] = mode
        try:
            resp = _requests.post(url, json=body, timeout=5)
            if resp.status_code != 200 and chat not in _warned_copies:
                _warned_copies.add(chat)
                print(
                    f"notify: the setup copy to {chat} returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
        except Exception as e:  # noqa: BLE001 — a courtesy copy may never break a send
            if chat not in _warned_copies:
                _warned_copies.add(chat)
                print(f"notify: the setup copy to {chat} failed: {e}")


def _account_row(account):
    """The account's registry row, `{}` when it names none, `None` when it could not be read.

    ⚠ **`bot_state` is imported HERE rather than at module scope**, for two reasons and both
    matter. It discovers every instance folder at import, so a process whose only job is to send
    one message would pay for a directory scan it has no use for; and this module is imported by
    `algos/live/`, where an import added at module scope is one more thing that can go wrong
    before a bot has a logger. Any failure answers *could not read*, which is what this function's
    third state is for.
    """
    try:
        import bot_state as _bot_state

        return _bot_state.account_row(account)
    except Exception:
        return None


def account_rooms(account):
    """`{kind: chat id}` for the rooms this ACCOUNT names. `{}` when it names none, and **`None`
    when the registry could not be read at all** — three states, never two.

    An empty room field and an unreadable registry mean different things to a live account: the
    first is a room nobody has entered yet, the second is a question that could not be asked.

    NEVER raises.
    """
    row = _account_row(account)
    if row is None:
        return None
    return {
        kind: str(row.get(field) or "").strip()
        for kind, field in ACCOUNT_ROOM_KEYS.items()
        if str(row.get(field) or "").strip()
    }


def missing_rooms(account):
    """Which of `REQUIRED_LIVE_KINDS` this account does not name: `()` when it names both, and
    **`None` when the registry could not be read**.

    The runner's startup gate reads this for a bot on a LIVE account. It does not ask whether the
    account IS live — that is the caller's question, and this one answer serves the gate, the
    Command Center's refusal and any later reader.
    """
    rooms = account_rooms(account)
    if rooms is None:
        return None
    return tuple(kind for kind in REQUIRED_LIVE_KINDS if not rooms.get(kind))


def chat_for(kind: str, override: str = "", account=None):
    """`(chat_id, is_dedicated)` for a message of this `kind`. An EMPTY chat id means DO NOT SEND.

    `override` is the bot's own instance-config value and wins outright — that is what lets one
    bot report somewhere of its own. ⚠ It is a per-BOT choice, so it stays with the bot when the
    bot moves; the account's rooms follow the ACCOUNT.

    `account` is the broker login the message is about, or `None`. Its row in the account registry
    names the rooms — see the block above, and note that a LIVE account's trade or signal room is
    the one destination in this file with NO fallback.

    HEALTH and SIGNAL fall back to the TRADE chat when their own shared key is unset, and SAY SO
    once. That is the opposite call from `deadman_url`, where unset means the check cannot work at
    all: here the message is still worth delivering, just not where you wanted it. The fallback is
    a nuisance you can see, never a silent drop.

    ⚠ **The fallback stays asymmetric: TRADE never borrows another kind's room.** Health or
    signals landing among the fills is a nuisance you can see and fix; a fill buried in setup
    chatter is the thing being prevented.
    """
    if kind not in CHAT_KEYS:
        raise ValueError(
            f"unknown notification kind {kind!r} - expected one of {sorted(CHAT_KEYS)}"
        )
    if override:
        return override, True
    row = _account_row(account)
    if row is None:
        # The registry has never been readable in this process — so whether this account is live
        # cannot be established, and a room cannot be looked up. The message still goes to the
        # shared room, because the alternative is dropping every message on a box whose account
        # file is broken, and it is LOUD about it: this is the one path here that could put a live
        # fill in the shared room.
        if account is not None and account not in _warned_unreadable:
            _warned_unreadable.add(account)
            print(
                f"notify: the account registry could not be read, so account {account} cannot be "
                f"classified - its messages are going to the shared rooms. Check "
                f"markets/fx/accounts.json."
            )
    own = (account_rooms(account) or {}).get(kind, "")
    if own:
        return own, True
    if (row or {}).get("kind") == LIVE and kind in REQUIRED_LIVE_KINDS:
        if (account, kind) not in _warned_no_room:
            _warned_no_room.add((account, kind))
            print(
                f"notify: LIVE account {account} names no {kind} channel, so its {kind} messages "
                f"are NOT BEING SENT. A live account never borrows another account's room - set "
                f"it on Bots -> Accounts."
            )
        return "", False
    dest = _cred(CHAT_KEYS[kind])
    if dest:
        return dest, True
    if kind != TRADE:
        fallback = _cred(CHAT_KEYS[TRADE])
        if fallback and kind not in _warned_kinds:
            _warned_kinds.add(kind)
            print(
                f"notify: {CHAT_KEYS[kind]} is not set - {kind} messages are going to the "
                f"main group. Set it in algos/credentials.json to split them out."
            )
        return fallback, False
    return "", False


def send_telegram(
    text: str,
    kind: str,
    chat_id: str = "",
    token_key: str = "",
    reply_to=None,
    markdown=True,
    *,
    account=None,
) -> bool:
    """Send `text` to the chat this `kind` routes to. Returns True on success.

    `kind` is `TRADE`, `HEALTH` or `SIGNAL` and is required — see the routing block above.
    `account` is the broker login the message is about, and its registry row names the room. ⚠ A
    trade or signal for a LIVE account with no room of its own is NOT SENT and returns False —
    that is the one destination here with no fallback.

    Use `send_telegram_id` instead when the message id is needed — this wrapper exists so the
    many callers that only care whether it went keep reading cleanly.

    `chat_id` and `token_key` are what make notifications PER BOT. A deployment sets them in its
    own instance config, so two bots on two accounts can report into two different groups, and
    can do it as two different Telegram bots. `token_key` names a key in `algos/credentials.json`
    (e.g. `telegram_token_bleg`) rather than carrying the token itself — the secret never enters
    an instance config, which is a normal committed-ish JSON file.

    A named token that is missing falls back to the default one and WARNS, rather than dropping
    the message: the wrong sender identity is recoverable, a silently missing trade alert is not.
    (It will usually still fail at Telegram — a bot can only post to a chat it belongs to — but
    it fails loudly, with the reason printed.)

    NEVER raises. A notifier that can take down a trading loop is worse than a missed message,
    so every failure path — no requests, no credentials, a dead network, a 4xx from Telegram —
    prints and returns False. Credentials are read per call rather than at import so a bot that
    starts before the file is written picks it up on the next message instead of staying mute
    for its whole session.
    """
    return (
        send_telegram_id(text, kind, chat_id, token_key, reply_to, markdown, account=account)
        is not None
    )


def send_telegram_id(
    text: str,
    kind: str,
    chat_id: str = "",
    token_key: str = "",
    reply_to=None,
    markdown=True,
    *,
    account=None,
):
    """Same send, but returns Telegram's `message_id` (or None on failure).

    The id is what lets a later message REPLY to this one — the trade exit replies to the trade
    entry, so both halves of a trade sit in one thread and an outcome is never read apart from
    the setup it came from.

    `reply_to` is best-effort by design: if the message being replied to has been deleted,
    Telegram refuses the send outright. A missing thread link is not a reason to lose a trade
    alert, so that case retries as a standalone message.
    """
    global _warned
    token, _group, _admin = telegram_credentials()
    if token_key:
        named = _cred(token_key)
        if named:
            token = named
        elif token_key not in _warned_keys:
            _warned_keys.add(token_key)
            print(
                f"notify: credential {token_key!r} is not set - falling back to the default "
                f"Telegram bot. Add it to algos/credentials.json, or clear telegram_token_key "
                f"in this bot's instance config."
            )
    dest, _dedicated = chat_for(kind, chat_id, account)
    if not token or not dest:
        if not _warned:
            _warned = True
            print(
                "notify: Telegram is not configured (see algos/credentials.template.json) - "
                "messages will be dropped for the rest of this run"
            )
        return None
    if _requests is None:
        print(f"notify: requests not installed, dropping message: {text}")
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _post(parse_mode, reply):
        body = {"chat_id": dest, "text": text}
        if parse_mode:
            body["parse_mode"] = parse_mode
        if reply:
            body["reply_to_message_id"] = reply
        return _requests.post(url, json=body, timeout=5)

    # 🔴 `markdown=False` is DELIVERY-CRITICAL, not cosmetic, and the rescue below cannot stand
    # in for it. The rescue only fires on a Telegram 400, i.e. only when the entity is UNBALANCED.
    # A name carrying an EVEN number of underscores parses "successfully" and Telegram silently
    # eats them: `sos_fade_demo` renders as `sos` + italic(`fade`) + `demo`, underscores gone,
    # HTTP 200, nothing logged. The old `mpc_sos_fade_demo` had three underscores — odd, so it
    # was rejected and the rescue delivered it intact, which is why this was never seen.
    # **The rename to a two-underscore key is what turned a loud failure into a silent one**
    # (2026-09-03). Every message `algos/live/alerts.py` builds is plain text by design — see its
    # "Plain text, no Markdown, ever" rule — so that path asks for no parsing at all and cannot
    # be corrupted by whatever a bot is named next.
    mode = "Markdown" if markdown else None
    try:
        r = _post(mode, reply_to)
        if reply_to and r.status_code == 400 and "replied" in r.text:
            # The entry message was deleted. Losing the thread link is a cosmetic loss; losing
            # the trade alert is not.
            print("notify: reply target is gone, sending standalone")
            reply_to = None
            r = _post(mode, None)
        if markdown and r.status_code == 400 and "parse entities" in r.text:
            # Markdown is a nicety; DELIVERY is the point. An underscore in a bot key, a symbol
            # or a file path inside an exception opens an italic that never closes, and Telegram
            # rejects the WHOLE message — so the alert that never arrives is the one reporting a
            # crash, whose text is a traceback full of paths. Measured on the first real send:
            # "MT5_FFT" alone was enough. Retry unformatted rather than lose it.
            print(f"notify: Markdown rejected, resending as plain text - {r.text[:160]}")
            # Reassigned, not passed inline: this is now the mode that DELIVERED, and the setups
            # copy below reuses it rather than repeating a request Telegram has just refused.
            mode = None
            r = _post(mode, reply_to)
        if r.status_code != 200:
            print(f"notify: Telegram returned {r.status_code}: {r.text[:200]}")
            return None
        if kind == SIGNAL:
            # A second room may read the setups — see the copies block above. Deliberately after
            # the primary has succeeded, and it cannot change what this returns.
            _copy_signal(text, account, dest, token, mode)
        return (r.json().get("result") or {}).get("message_id")
    except Exception as e:
        print(f"notify: send failed: {e}")
        return None
