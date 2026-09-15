"""A fresh, unassigned, never-promoted copy of an existing bot.

**Why this exists.** A bot is one folder, one account, one running process — that part is not
negotiable, `algos/CLAUDE.md` calls it "a bot IS its folder" and the live runner enforces it at
startup. So "put SOS Fade on a third account" has never been possible by pointing an EXISTING bot
at a new login: both of its copies are already trading somewhere, and moving either one just
pulls it off the account it is on. The only way to get a strategy onto a new account is a fresh
folder, and until now that meant a person hand-editing one.

**Which bot to clone is picked on the frontend**, from data the Bots page already has —
`frontend/src/lib/botTemplates.ts` reads the same "live copy over demo, demo over bench" rule
this module's docstring used to implement server-side, off `useBotAccounts` and
`useRegisteredAccounts`, both fetched already. That is why `POST /{bot_name}/clone` needs no
"template" concept of its own here: it clones exactly the bot it is called on, and this module's
whole job is what a fresh copy of ONE bot looks like.

Pure: no HTTP, no SSH, no filesystem. The router owns discovery and disk writes; this module owns
the rules for what a fresh key, a fresh order tag, and a fresh copy of a config carry.
"""

from __future__ import annotations

import re

__all__ = ["next_key", "next_magic", "clone_config"]

# The same alphabet `algos/shared/bot_registry` and this router's own `_KEY_PATTERN` hold every
# bot key to — restated because the two subsystems may not import each other.
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# The magic numbers in use today start at 770115; this just has to stay clear of them and of
# whatever a human types by hand in the low 770000s.
_MAGIC_FLOOR = 770100

# Facts about THIS bot's account, its deployment state, or its own order tag — never carried from
# the bot a clone is sourced from, because every one of them would misdescribe an account this
# fresh file has never traded and code it has never run. Deliberately a CLOSED list of what gets
# RESET, not an allowlist of what gets kept: a strategy field this module has never heard of (today
# or added later) is copied through by `clone_config` unchanged, because the failure direction that
# matters is a strategy setting silently dropped off a clone, not one carried forward.
_RESET_FIELDS: dict[str, object] = {
    "mt5_path": "",
    "account": None,
    "server": "",
    "strategy_source_hash": "",
    "promoted_commit": "",
    "promoted_at": "",
    "strategy_version": 0,
    "telegram_chat_id": "",
    "telegram_token_key": "",
    "account_risk_cap_pct": None,
    "sizing_basis_adjustment": 0.0,
    "initial_capital": 0,
}


def next_key(existing_keys: set, strategy_package: str) -> str:
    """The next unused `<strategy>_<n>` key for a fresh copy of this strategy.

    ⚠ Never reuses a hand-picked suffix like `_demo` — that names something about when or where a
    bot was first set up, which a copy minted here knows nothing about. A plain rising number says
    only "another one of these," which is all a fresh copy ever is.
    """
    n = 1
    while True:
        candidate = f"{strategy_package}_{n}"
        if candidate not in existing_keys and _KEY_PATTERN.match(candidate):
            return candidate
        n += 1


def next_magic(existing_magics: set) -> int:
    """The smallest order-tag number no bot on any account is already using.

    `live_config._assert_magic_is_unique` only refuses a clash on ONE account, so a global search
    is stricter than the runtime requires — deliberately, so a fresh copy's first start never
    needs anyone to first reason about which existing bot trades which account.
    """
    used = {int(m) for m in existing_magics if m}
    m = _MAGIC_FLOOR
    while m in used:
        m += 1
    return m


def clone_config(source: dict, new_key: str, magic: int, created_at: str) -> dict:
    """A fresh, unstarted, unassigned copy of `source`'s strategy identity and trading-logic
    settings — never its account, its deployment record, or the history written for the account
    it has actually been running on.

    **Every underscore-prefixed key is prose, and prose is dropped, not copied.** Those notes are
    a diary of what was measured and decided FOR THE BOT THEY ARE WRITTEN ON — a broker's spread,
    an account's balance, a promote that landed for that account's own snapshot. Carrying them onto
    a bot they were never true for is exactly the repo's own rule about a guessed number: a
    plausible-looking claim nobody has checked for this file. One new note replaces the lot and
    points back at the source for the real history — it is never asked to restate it.

    **Everything else is copied through unchanged, including a field this function has never seen**
    — a strategy's own settings (`strategy_params`, `symbol`, `timeframe`, `warmup_bars`, and
    anything a future strategy adds) are the bot's identity and belong on every copy of it.
    `_RESET_FIELDS` is the opposite kind of list on purpose: a short, closed set of facts about
    THIS bot's account and deployment, which a fresh copy starts with none of.
    """
    cloned = {k: v for k, v in source.items() if not k.startswith("_")}
    cloned.update(_RESET_FIELDS)
    cloned["bot_key"] = new_key
    cloned["magic"] = magic
    if isinstance(source.get("strategy_params"), dict):
        cloned["strategy_params"] = dict(source["strategy_params"])

    source_key = source.get("bot_key") or "its source bot"
    cloned["_cloned_from"] = (
        f"Created {created_at} as a fresh copy of {source_key}'s trading-logic settings, copied "
        f"byte-for-byte as of that date. Not yet on any account, not yet promoted, not yet "
        f"started. Every measurement and every broker fact behind these settings lives on "
        f"{source_key}'s own config — this file states none of it, because none of it has been "
        f"checked for this account."
    )
    return cloned
