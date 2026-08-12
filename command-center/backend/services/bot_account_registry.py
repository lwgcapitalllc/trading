"""The broker accounts a bot can be put ON — read and written from the Bots page.

**Why this exists at all.** `bot_accounts.py` DERIVES which bots share an account, and that
derivation is load-bearing: two bots naming one account are trading one balance whether or not
anybody grouped them, so there is no membership list to disagree with them. But the derivation has
one hole, and it is the hole that made 2026-08-12 a manual afternoon: **an account only existed
once some bot already named it.** So the very first bot on a new account could not be moved from
the page — `set_bot_account` had to refuse with *"no registered bot trades account N, so there is
no account here to join"* — and the only route was hand-editing an instance config on the VPS.

This registry closes exactly that hole and nothing else. It holds the facts about an ACCOUNT that
a bot has to adopt to trade it, and it holds no fact that a bot's own config already states.

**What is deliberately NOT here: the risk cap.** That is an account-level number stored per
instance because an instance config is the only file a bot reads, so the account's cap is whatever
its bots say it is — `bot_accounts.group_by_account` reports it and refuses when they disagree. A
copy here would be a second answer, and the one thing this whole subsystem is built to avoid is a
stored claim that can drift from what the bots actually do. **The registry says what an account
IS; the bots say what they are doing on it.**

Three-state fields, because this repo's oldest rule keeps applying:

  * `symbol_suffix` — a string is the suffix, `""` means this broker quotes bare symbols, and
    **`None` means nobody recorded it**. A move onto an account with `None` leaves the bot's
    symbol alone and SAYS so, rather than guessing a suffix onto a live instrument.
  * `mt5_path` — `""` means no terminal on this box is logged into the account, which makes it
    **unassignable**. That is a real state: the two tier-probe accounts were logged into MT5_Lab
    for minutes to read a spread, and MT5_Lab drives the backtest agent.

Pure: no HTTP, no SSH, no global paths. Every function takes the file path, so the rules can be
tested against a tmp file.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

__all__ = ["RegisteredAccount", "RegistryError", "registry_path", "load_accounts",
           "account_by_number", "upsert_account", "remove_account", "rebase_symbol"]

# Keys carrying prose rather than data. They are round-tripped untouched so a hand-written
# explanation in the file survives a write from the page — the same discipline every instance
# config here follows.
_PROSE = re.compile(r"^_")


class RegistryError(ValueError):
    """A registry the caller may not write, or an entry it may not store. Routers turn it into a
    400/409 — it is always a statement about the request, never about the machine."""


@dataclass
class RegisteredAccount:
    """One broker account, as far as putting a bot on it is concerned."""
    account: int
    label: str = ""
    broker: str = ""
    tier: str = ""                       # "ECN" / "Standard" / … — the broker's own word
    kind: str = "demo"                   # "demo" | "live"
    server: str = ""
    mt5_path: str = ""                   # "" = no terminal serves it ⇒ not assignable
    symbol_suffix: Optional[str] = None  # None = unrecorded; "" = bare symbols
    account_profile: str = ""            # a key of backtest.fills.PROFILES
    note: str = ""

    @property
    def assignable(self) -> bool:
        """Whether a bot can be put on this account at all.

        A terminal is not a nicety: the bot connects by attaching to a running terminal that is
        already logged into the account it claims to trade. Without one the move would be written,
        committed, pushed and pulled, and then fail at `connect()` with a message about
        credentials — pointing the reader at the password rather than at the missing terminal.
        """
        return bool(self.mt5_path)

    @property
    def unassignable_reason(self) -> str:
        if self.mt5_path:
            return ""
        return (f"account {self.account} has no terminal on the VPS logged into it, so a bot "
                f"assigned to it could not connect. Log a terminal into it and record that "
                f"terminal's path on the account first.")


def registry_path(monorepo_root: Path) -> Path:
    return Path(monorepo_root) / "algos" / "markets" / "fx" / "accounts.json"


def _read_raw(path: Path) -> dict:
    """The whole file, or an empty shell. **A MISSING file is empty; an UNREADABLE one raises.**

    Collapsing those is how a write turns a transient parse failure into a delete: the file is
    read, modified and written back whole, so answering `{}` for a file that exists and could not
    be parsed would drop every account in it and report success. Same shape as the `users.json`
    read-modify-write that could delete every Telegram user (2026-08-04).
    """
    if not path.exists():
        return {"accounts": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RegistryError(f"{path} exists and could not be parsed ({e}). Fix the file — "
                            f"writing over it would discard every account in it.")
    if not isinstance(raw, dict) or not isinstance(raw.get("accounts"), list):
        raise RegistryError(f"{path} is not an account registry (expected an object with an "
                            f"'accounts' list). Refusing to overwrite it.")
    return raw


def _entry(raw: dict) -> RegisteredAccount:
    """One stored row → a dataclass, dropping prose keys and unknown fields.

    ⚠ An unknown field is DROPPED rather than raising, and only here on the read: a registry
    written by a newer version of this app must not stop an older one from listing accounts. The
    WRITE path is strict, so nothing can be introduced from the page without being declared.
    """
    known = {f for f in RegisteredAccount.__dataclass_fields__}
    data = {k: v for k, v in raw.items() if k in known}
    if "account" not in data:
        raise RegistryError("a registry row has no account number")
    try:
        data["account"] = int(data["account"])
    except (TypeError, ValueError):
        raise RegistryError(f"a registry row has a non-numeric account: {raw.get('account')!r}")
    return RegisteredAccount(**data)


def load_accounts(path: Path) -> list[RegisteredAccount]:
    """Every registered account, lowest number first."""
    rows = [_entry(r) for r in _read_raw(path)["accounts"] if isinstance(r, dict)]
    return sorted(rows, key=lambda a: a.account)


def account_by_number(path: Path, account: int) -> Optional[RegisteredAccount]:
    return next((a for a in load_accounts(path) if a.account == account), None)


def _validate(entry: RegisteredAccount, known_profiles: Optional[set[str]]) -> None:
    if entry.account <= 0:
        raise RegistryError("an account number is a positive integer")
    if not entry.server.strip():
        raise RegistryError(
            f"account {entry.account} needs a server: an account number IS a login on a server, "
            f"and the pair is the identity. Half of it is a connection failure at startup with a "
            f"confusing message.")
    if entry.kind not in ("demo", "live"):
        raise RegistryError(f"kind must be 'demo' or 'live', not {entry.kind!r} — the page tints "
                            f"a live account and warns before every fleet action on one, so an "
                            f"unrecognised value would quietly drop both.")
    if entry.symbol_suffix is not None and not re.fullmatch(r"[.\-_A-Za-z0-9]*", entry.symbol_suffix):
        raise RegistryError(
            f"symbol_suffix {entry.symbol_suffix!r} is not a symbol suffix. It is appended to an "
            f"instrument name and sent to the broker; leave it null if it is not known.")
    # ⚠ `None` means the caller could not supply the roster, so the check is SKIPPED and that is
    # the caller's decision to state — never a silent pass. The router always supplies it.
    if known_profiles is not None and entry.account_profile:
        if entry.account_profile not in known_profiles:
            raise RegistryError(
                f"account_profile {entry.account_profile!r} is not a measured cost profile. "
                f"Known: {', '.join(sorted(known_profiles))}. A name nothing can price is a "
                f"backtest that refuses and a live config that claims a broker it cannot name.")


def _atomic_write(path: Path, raw: dict) -> None:
    """tmp + `os.replace`, so a reader never sees a half-written registry. `sort_keys=False` keeps
    the prose block at the top where somebody will read it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def upsert_account(path: Path, entry: RegisteredAccount,
                   known_profiles: Optional[set[str]]) -> tuple[RegisteredAccount, bool]:
    """Add an account, or replace the one with that number. Returns `(stored, created)`.

    ⚠ **It REPLACES the row rather than merging into it**, so a field cleared on the page is
    cleared on disk. A merge would make removing a symbol suffix impossible from the UI — the
    absent value and the unchanged value would be the same request.
    """
    _validate(entry, known_profiles)
    raw = _read_raw(path)
    rows: list[Any] = raw["accounts"]
    stored = asdict(entry)
    for i, row in enumerate(rows):
        if isinstance(row, dict) and str(row.get("account")) == str(entry.account):
            # Keep any prose key a human wrote on this row; the page cannot express them and a
            # write from it must not delete an explanation somebody left for the next reader.
            prose = {k: v for k, v in row.items() if _PROSE.match(k)}
            rows[i] = {**stored, **prose}
            _atomic_write(path, raw)
            return entry, False
    rows.append(stored)
    _atomic_write(path, raw)
    return entry, True


def remove_account(path: Path, account: int) -> bool:
    """Forget an account. Returns False when it was not registered.

    ⚠ It does NOT check whether a bot still names this account — that needs the instance configs,
    which this module deliberately cannot read. The router checks, and refuses: removing the
    registry row of an account a bot is trading would leave that bot running on an account the
    page can no longer describe.
    """
    raw = _read_raw(path)
    rows = raw["accounts"]
    keep = [r for r in rows if not (isinstance(r, dict) and str(r.get("account")) == str(account))]
    if len(keep) == len(rows):
        return False
    raw["accounts"] = keep
    _atomic_write(path, raw)
    return True


def rebase_symbol(symbol: str, suffix: Optional[str]) -> Optional[str]:
    """`XAUUSD.s` + `.p` → `XAUUSD.p`. `None` when it must not be touched.

    **The INSTRUMENT is the bot's and the SUFFIX is the account's**, which is why this is a rebase
    rather than a copy of a peer's symbol. Two bots on one account can legitimately trade gold and
    a currency pair; copying whichever symbol happened to be there would rewrite one of them onto
    the other's instrument — a bot that starts cleanly, connects cleanly and trades the wrong
    market.

    `None` is returned when the account records no suffix (`suffix is None`) or the symbol is
    empty, and the caller must report that rather than substitute: on 2026-08-12 the symbol did
    NOT move with the account and `XAUUSD.s` on an ECN book is a symbol the terminal does not
    quote — the bot connects, warms up, and sees no bars.
    """
    if suffix is None or not symbol:
        return None
    base = symbol.split(".", 1)[0]
    return base + suffix
