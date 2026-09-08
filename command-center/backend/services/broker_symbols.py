"""The broker's own tradeable universe, grouped by asset class.

**The Run form used to suggest ten symbol names typed in by hand**, and they were Vantage's names
while the lab sat attached to PU Prime — a list describing a broker nobody was connected to. This
module replaces it with the terminal's own answer: on 2026-09-07 the attached PU Prime demo
returned **1,085 instruments in 0.34s**, across shares, ETFs, crypto, indices, forex, metals,
energy, softs and bonds.

Three rules shaped every decision in here.

🔴 **"Cannot ask" and "the broker offers nothing" must never take the same value** (rule 1). An
unreachable agent, a disconnected terminal and a terminal that answers with an error all come back
as `available=False` carrying a reason, and the symbol list is `None` rather than `[]`. A caller
that renders an empty list as "no instruments" would be describing a broker outage as a product
decision.

🔴 **The list belongs to the ATTACHED terminal, never to the broker you picked in the form**
(rule 3). Only one terminal is attached at a time, so the universe is whatever THAT one carries —
which is why every response names the server and account it was read from. A page showing PU
Prime's 1,085 names under a Vantage selection is the mixed-basis defect this lab keeps paying for,
one field over.

🔴 **The terminal is free to change accounts under a running lab** (rule 16), so the cache is keyed
on the identity read at fetch time and that identity is re-checked on every call. A cached list
served after the terminal moved is a list about a broker you are no longer talking to.

⚠ **The asset classes are derived from KEYWORDS in the broker's own grouping, never from a table of
PU Prime's folder names.** A table would be right on one broker and silently wrong on the next, and
this repo already owns a shelf of those. Anything the keywords do not recognise keeps the broker's
own label rather than being swept into an "Other" bucket — 155 of PU Prime's symbols land that way
(its 24-hour share CFDs and its tokenised names), and inventing a category for them would be a
claim nobody measured.
"""

from __future__ import annotations

import datetime
import re
import time
from typing import Optional

from services import mt5_agent_client

#: How long a fetched universe stays fresh. A broker adds instruments over months, not minutes,
#: and the fetch costs 0.34s — so this is about not hammering the terminal while somebody flicks
#: between categories, not about staleness being dangerous.
_TTL_SECONDS = 30 * 60

#: `(server, account) -> (fetched_at_monotonic, payload)`. Keyed on the terminal's IDENTITY, so a
#: terminal that switches accounts cannot be served the previous account's universe.
_cache: dict[tuple[str, Optional[int]], tuple[float, dict]] = {}

#: The identity of the most recent SUCCESSFUL read, so a blip on the identity probe can still be
#: answered from what we already hold. `None` until one has succeeded this process.
_last_key: Optional[tuple[str, Optional[int]]] = None


# ── Asset classes ──────────────────────────────────────────────────────────────

#: Ordered keyword rules, first match wins. Each entry is `(class label, patterns)` and the
#: patterns are matched against the broker's group name lowercased with its punctuation stripped.
#:
#: ⚠ **The ORDER carries meaning and must not be sorted.** Metals are checked before commodities
#: because a broker filing gold under "Precious Metals" and one filing it under "Commodities" are
#: both saying the same thing, and the more specific answer is the more useful one. Indices are
#: checked before shares because "Equity Indices" is an index group, not a share group.
_CLASS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Metals", ("gold", "silver", "xau", "xag", "platin", "pallad", "metal")),
    ("Energy", ("oil", "brent", "wti", "natgas", "energy")),
    ("Commodities", ("commodit", "agricult", "softs", "grain")),
    ("ETFs", ("etf",)),
    ("Crypto", ("crypto", "coin")),
    ("Indices", ("indic", "index", "indices")),
    ("Shares", ("equit", "share", "stock")),
    ("Bonds", ("bond", "treasur", "gilt", "euribor", "yield")),
    ("Forex", ("forex", "currenc", "majors", "minors", "exotics")),
]

#: Short keys that are too collision-prone for a substring test and are matched as whole words.
#: `fx` inside "fxpro" or "effects" is not a currency group.
_CLASS_TOKENS: list[tuple[str, tuple[str, ...]]] = [
    ("Forex", ("fx",)),
    ("Indices", ("idx",)),
]


def _clean_group(path: str) -> str:
    """The broker's own group name for a symbol, with its symbol-suffix noise trimmed.

    MT5 hands back a path like `Forex .p\\EURUSD.p`, so the group is everything before the first
    separator. Brokers spell the same group several ways on one terminal — PU Prime carries
    `Forex` and `Forex .p`, `Indices` and `Indices-JP.s` — and the trailing `.p` / `.s` is the
    account tier rather than a different asset, so it is dropped for the DISPLAY label only.

    🔴 **Only a one- or two-letter LOWERCASE tail is trimmed, and that narrowness was measured
    rather than chosen.** The first version stripped any trailing dotted word, which turned PU
    Prime's `US.24H` group — its 62 round-the-clock share CFDs — into a category called `US`. An
    over-eager trim does not fail; it produces a plausible label that tells the reader nothing,
    which is the worse half of getting it wrong.

    ⚠ **It is never dropped from the SYMBOL.** The suffix on a symbol is the name the terminal
    quotes, and trimming it there is how you hand MT5 a name it has never heard of.
    """
    head = (path or "").replace("/", "\\").split("\\")[0].strip()
    return re.sub(r"\s*\.[a-z]{1,2}$", "", head).strip() or "Ungrouped"


def classify(path: str) -> str:
    """The asset class for a broker group, or the broker's own label when nothing matches.

    ⚠ **The fallback is the broker's label, never "Other".** Two groups that fall through would
    otherwise merge into one meaningless bucket — PU Prime's 24-hour share CFDs and its tokenised
    names are 62 and 93 symbols and are not the same thing.
    """
    label = _clean_group(path)
    flat = re.sub(r"[^a-z0-9]+", " ", label.lower())
    for cls, patterns in _CLASS_RULES:
        if any(p in flat for p in patterns):
            return cls
    words = set(flat.split())
    for cls, tokens in _CLASS_TOKENS:
        if words & set(tokens):
            return cls
    return label


#: The order categories are offered in — the liquid, frequently-traded classes first, because the
#: reader is picking one instrument and 667 share names should not sit between them and gold.
#: Anything not named here (a broker group the keywords did not recognise) sorts after these,
#: alphabetically.
_CLASS_ORDER = [
    "Forex",
    "Metals",
    "Indices",
    "Energy",
    "Commodities",
    "Shares",
    "ETFs",
    "Crypto",
    "Bonds",
]


def _class_sort_key(label: str) -> tuple[int, str]:
    return (_CLASS_ORDER.index(label), "") if label in _CLASS_ORDER else (len(_CLASS_ORDER), label)


# ── The universe ───────────────────────────────────────────────────────────────

#: MT5's `trade_mode`: only this one lets the account OPEN a new position. Everything else —
#: disabled, close-only, long-only — is a real restriction the reader should see rather than a
#: reason to hide the instrument.
_TRADE_MODE_FULL = 4


def _shape(raw: dict) -> dict:
    """One agent symbol record, trimmed to what a picker and a run actually need."""
    path = raw.get("path") or ""
    mode = int(raw.get("trade_mode") or 0)
    return {
        "symbol": raw.get("symbol") or "",
        "description": raw.get("description") or "",
        "broker_group": _clean_group(path),
        "asset_class": classify(path),
        "tradable": mode == _TRADE_MODE_FULL,
        "trade_mode_label": raw.get("trade_mode_label") or "unknown",
        "digits": int(raw.get("digits") or 0),
        "contract_size": float(raw.get("contract_size") or 0.0),
        "volume_min": float(raw.get("volume_min") or 0.0),
        "volume_step": float(raw.get("volume_step") or 0.0),
        # The venue lot ceiling — part of what a run is measured on (rule 17), so it travels with
        # the symbol rather than being looked up again somewhere else.
        "volume_max": float(raw.get("volume_max") or 0.0),
    }


#: How many times the identity probe is asked before the terminal is called unreachable.
#: 🔴 **ONE ATTEMPT WAS NOT ENOUGH AND THE PICKER BLAMED THE BROKER FOR IT.** The tunnel drops a
#: single request now and then — the observed failure is an immediate *"Remote end closed
#: connection without response"*, not a timeout — and with no retry that blip is indistinguishable
#: from a dead terminal. Reported from the screen 2026-09-07 over a terminal that was connected the
#: whole time and answering 30 probes out of 30 a minute later.
_PROBE_ATTEMPTS = 2
_PROBE_BACKOFF_S = 0.4


def _attached() -> tuple[str, Optional[int]]:
    """The terminal the lab is attached to right now, or a raised RuntimeError.

    ⚠ **An unreachable agent RAISES rather than returning blanks.** A blank server would key the
    cache the same way for every outage, and the second caller would then be served the previous
    broker's universe under a terminal nobody can reach.

    ⚠ **Only a TRANSPORT failure is retried.** A terminal that answers and says it is not connected
    has given a real answer, and asking it twice would just be slower about believing it.
    """
    last: Exception = RuntimeError("the terminal was never asked")
    for attempt in range(_PROBE_ATTEMPTS):
        try:
            st = mt5_agent_client.status()
        except Exception as exc:  # noqa: BLE001 - a transport failure is worth one more ask
            last = exc
            if attempt + 1 < _PROBE_ATTEMPTS:
                time.sleep(_PROBE_BACKOFF_S)
            continue
        if st.get("mt5_connected") is not True:
            raise RuntimeError(st.get("error") or "the terminal is not connected to a broker")
        server = str(st.get("server") or "")
        if not server:
            raise RuntimeError("the terminal did not say which server it is on")
        account = st.get("account")
        return server, (int(account) if account is not None else None)
    raise RuntimeError(str(last))


def universe(refresh: bool = False) -> dict:
    """Every instrument the attached terminal carries, grouped by asset class.

    Always returns a payload; never raises. `available` is False with a plain-English `reason` and
    a `symbols` of `None` when the terminal could not be asked — the caller renders that as "cannot
    tell", which is a different sentence from "this broker offers nothing".
    """
    try:
        server, account = _attached()
    except Exception as exc:  # noqa: BLE001 - every failure here means "cannot ask"
        # 🔴 **A LIST WE ALREADY HOLD BEATS A BLANK PANEL, and serving nothing here was the defect.**
        # The identity check runs before the cache is consulted (it has to — rule 16, the terminal
        # can switch accounts underneath us) and the first version RETURNED at this point, so one
        # dropped request threw away 1,085 instruments read seconds earlier and told the reader the
        # broker could not be reached. On a terminal that was connected the entire time.
        # ⚠ **It is served STALE, never as a fresh answer**: the payload keeps the server and
        # account it was actually read from and carries the time, so the page says which terminal
        # it describes and when. That is the honest form of the rule-16 hazard — the terminal MAY
        # have moved during the blip, and a reader who can see the account it came from can tell.
        # ⚠ **This is the pattern the rest of this app already uses** for a failed refetch (the bot
        # snapshot and the calendar both keep their last good rows and date them).
        stale = _last_good()
        if stale is not None:
            return {**stale, "stale": True, "reason": str(exc)}
        return _unavailable(str(exc))

    key = (server, account)
    hit = _cache.get(key)
    if hit and not refresh and (time.monotonic() - hit[0]) < _TTL_SECONDS:
        return hit[1]

    try:
        data = mt5_agent_client.symbols()
    except Exception as exc:  # noqa: BLE001 - same three-state rule as above
        return _unavailable(str(exc), server=server, account=account)

    raw = data.get("symbols")
    if raw is None:
        return _unavailable("the terminal returned no symbol list", server=server, account=account)

    symbols = sorted(
        (_shape(s) for s in raw if s.get("symbol")),
        key=lambda s: (_class_sort_key(s["asset_class"]), s["symbol"]),
    )
    classes = {}
    for s in symbols:
        c = classes.setdefault(s["asset_class"], {"label": s["asset_class"], "count": 0})
        c["count"] += 1

    payload = {
        "available": True,
        "stale": False,
        "reason": None,
        "server": server,
        "account": account,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        # What CAME BACK, never what was asked for (rule 3). The agent reports its own total
        # separately, so a filtered or truncated answer cannot read as a complete one.
        "count": len(symbols),
        "total_on_terminal": int(data.get("total_on_terminal") or len(symbols)),
        "classes": sorted(classes.values(), key=lambda c: _class_sort_key(c["label"])),
        "symbols": symbols,
    }
    _cache[key] = (time.monotonic(), payload)
    global _last_key
    _last_key = key
    return payload


def _unavailable(reason: str, server: str = "", account: Optional[int] = None) -> dict:
    """The shape returned whenever the terminal could not answer.

    ⚠ **`symbols` is `None`, never `[]`.** That is the whole point of this function existing.
    """
    return {
        "available": False,
        "stale": False,
        "reason": reason,
        "server": server,
        "account": account,
        "fetched_at": None,
        "count": None,
        "total_on_terminal": None,
        "classes": [],
        "symbols": None,
    }


def _last_good() -> Optional[dict]:
    """The most recent successfully-read universe, or None if there has never been one.

    ⚠ **No TTL is applied here on purpose.** This path is only reached when the terminal cannot be
    asked at all, and at that moment a list from an hour ago is strictly more useful than nothing —
    a broker's instruments change over months. The staleness is REPORTED rather than enforced, so
    the decision about whether it is too old belongs to the person reading the timestamp.
    """
    if _last_key is None:
        return None
    hit = _cache.get(_last_key)
    return hit[1] if hit else None


def clear_cache() -> None:
    """Drop every cached universe. Used by the tests, and by an explicit refresh."""
    global _last_key
    _cache.clear()
    _last_key = None
