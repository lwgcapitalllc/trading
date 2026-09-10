"""What the VPS is ACTUALLY logged into, checked against the account list somebody typed.

The account list (`algos/markets/fx/accounts.json`) is a stored claim, and until this module
existed nothing ever compared it with the machine. On 2026-09-10 it named a terminal for account
700107749 that is not logged into it, and `C:\\MT5_Scalper` had been sitting on a **live** account
for a day with no part of the Command Center able to see it.

**The split this module is built around, and it is the whole design:**

  * the BOX is the authority on what is logged in where — account, server, demo-or-live, which
    terminal, what suffix the broker quotes
  * the REPO stays the authority on intent — which account a bot should trade, what it is called,
    which measured cost profile prices it, and any note a human left

🔴 **This module never merges them.** `services/account_sync.py` applies its findings BY RULE when
a person presses Sync (2026-09-10) — and never to an account a bot trades, because the
account-mismatch halt in `algos/live/runner.py` exists precisely because a terminal's login is free
to change under a running bot. A write that agreed with the terminal there would be resolving that
alarm by agreeing with it.

⚠ **Nothing here writes.** Reconciling produces findings; the sync applies them through the
registry writer, which validates them the same way a typed-in account is validated. The one write
seam stays the one write seam.

🔴 **Three states at the top, and they must not collapse into two.** `asked=False` means the scan
could not run — the box was unreachable, the script refused, or it printed something unreadable —
and it is NOT "no terminals found". A caller that renders a refusal as an empty list has converted
"cannot ask" into "nothing there", which is this repo's oldest and most expensive mistake.

Pure: no HTTP, no SSH, no global paths. The router supplies the raw scan payload and the registry
rows, so every rule below is testable against a dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "ScanUnavailable",
    "TerminalReading",
    "RegistryCheck",
    "Reconciliation",
    "parse_scan",
    "reconcile",
    "suggested_registration",
]

# The registry fields the BOX is allowed to have an opinion about. Everything else on a
# `RegisteredAccount` is a judgement a person made and the box cannot know: the label, the broker's
# marketing tier, which measured cost profile prices it, and any note. Keeping this list explicit
# is what stops a later "just sync everything" from quietly overwriting somebody's typing.
MACHINE_FIELDS = ("server", "kind", "mt5_path", "symbol_suffix")


class ScanUnavailable(RuntimeError):
    """The scan did not produce a reading. Always about the CHANNEL, never about a terminal."""


@dataclass
class TerminalReading:
    """One terminal on the box, and how it lines up with the account list."""

    key: str  # normalised install dir - the join key
    install: str  # as the box spells it, for a person to read
    state: str  # "probed" | "not_running" | "owned_by_bot"
    running: bool = False
    owned_by_bots: list = field(default_factory=list)
    account: Optional[int] = None
    server: Optional[str] = None
    kind: Optional[str] = None  # "demo" | "live" | "contest" | None = not established
    company: Optional[str] = None
    currency: Optional[str] = None
    leverage: Optional[int] = None
    symbol_suffix: Optional[str] = None
    symbol_suffix_how: Optional[str] = None
    reason: Optional[str] = None  # why it was not probed
    error: Optional[str] = None  # why a probe failed
    # WHERE the account number came from. "terminal" = this tool attached and asked; "bot" = the
    # bot trading through it reported what IT observes; None = nobody could say. The provenance is
    # kept because the two are different strengths of evidence and a reader deserves to know which.
    account_source: Optional[str] = None
    verdict: str = "unasked"  # "new" | "known" | "conflict" | "unasked"
    conflicts: list = field(default_factory=list)

    @property
    def is_live(self) -> bool:
        """Real money. `None` is NOT live and is not demo either — it is unestablished."""
        return self.kind == "live"

    @property
    def actionable(self) -> bool:
        """Whether there is an account here a person could add to the list."""
        return self.verdict == "new" and self.account is not None


@dataclass
class RegistryCheck:
    """One row of the account list, and whether the box backs it up."""

    account: int
    label: str
    verdict: str  # "confirmed" | "contradicted" | "unverified"
    detail: str
    conflicts: list = field(default_factory=list)
    seen_on: Optional[str] = None  # the install where the box actually found this account


@dataclass
class Reconciliation:
    asked: bool
    scanned_at: Optional[str] = None
    reason: Optional[str] = None  # set when asked is False, and only then
    terminals: list = field(default_factory=list)
    registry: list = field(default_factory=list)

    @property
    def new_accounts(self) -> list:
        return [t for t in self.terminals if t.actionable]

    @property
    def contradicted(self) -> list:
        return [r for r in self.registry if r.verdict == "contradicted"]


def parse_scan(payload: Any) -> Reconciliation:
    """Turn the box script's JSON into a reading, or raise.

    ⚠ **A payload that is not a dict, or that lacks `asked`, RAISES rather than defaulting.**
    Defaulting `asked` to True would make a truncated pipe, an SSH banner or a Windows error page
    read as a successful scan of zero terminals — which is the exact shape that turns "cannot ask"
    into "nothing there".
    """
    if not isinstance(payload, dict) or "asked" not in payload:
        raise ScanUnavailable(
            "the scan did not return a readable result, so what the box is logged into is "
            "UNKNOWN - this is not a statement that no terminals were found"
        )
    if not payload.get("asked"):
        return Reconciliation(
            asked=False,
            scanned_at=payload.get("scanned_at"),
            reason=str(payload.get("reason") or "the box refused the scan and gave no reason"),
        )
    return Reconciliation(asked=True, scanned_at=payload.get("scanned_at"))


def _reading(raw: dict) -> TerminalReading:
    known = {f for f in TerminalReading.__dataclass_fields__ if f not in ("verdict", "conflicts")}
    return TerminalReading(**{k: v for k, v in raw.items() if k in known})


def _norm_suffix(value: Any) -> Optional[str]:
    """`None` stays `None`. Everything else becomes a string, so `""` survives as a real answer."""
    return None if value is None else str(value)


def _compare(reading: TerminalReading, row: Any) -> list:
    """Where the account list and the box disagree about ONE account.

    ⚠ **A registry field that is unset is NOT a conflict.** An empty suffix claim means nobody
    recorded one, and reporting that as a contradiction would bury the real disagreements under
    rows that are merely incomplete. Only a field that is SET and DIFFERENT counts.
    """
    out = []
    server = str(getattr(row, "server", "") or "")
    if server and reading.server and server != reading.server:
        out.append(f"Your list says server {server}; the VPS says {reading.server}")

    kind = str(getattr(row, "kind", "") or "")
    if kind and reading.kind and kind != reading.kind:
        # Worth its own sentence: this is the one that decides whether real money is involved.
        out.append(
            f"Your list says it's a {kind} account; the broker says it's {reading.kind.upper()}"
        )

    suffix = _norm_suffix(getattr(row, "symbol_suffix", None))
    if suffix is not None and reading.symbol_suffix is not None and suffix != reading.symbol_suffix:
        out.append(
            f"Your list says instruments end {suffix or '(nothing)'}; the VPS quotes "
            f"{reading.symbol_suffix or '(nothing)'}"
        )
    return out


def _account_from_bots(raw: dict, observed_by_bot: dict) -> tuple:
    """What the bots trading through a terminal say they are ACTUALLY on.

    🔴 **This is the only way a terminal a bot owns can be checked at all.** The scan deliberately
    never attaches there, so before the live runner reported its observed account every row
    pointing at the bots' terminal came back UNVERIFIED — which is exactly where a stale claim had
    been sitting for weeks.

    ⚠ **It uses the OBSERVED account, never the configured one.** A bot's configured account comes
    from a file in the same repo as the account list, so checking one against the other proves
    nothing. The observed number is the terminal's own answer, read off `account_info()`.

    ⚠ **A bot that could not ask contributes NOTHING**, rather than a zero or its configured
    number. ⚠ **Bots that disagree resolve to unknown**: one terminal holds one login, so a
    disagreement means somebody is reporting stale state and guessing between them would be
    inventing a fact.
    """
    seen = set()
    for bot in raw.get("owned_by_bots") or []:
        value = observed_by_bot.get(bot)
        if value is not None:
            seen.add(int(value))
    if len(seen) != 1:
        return None, None
    return seen.pop(), "bot"


def reconcile(payload: Any, registered: Any, observed_by_bot: Any = None) -> Reconciliation:
    """Join what the box reports against the account list. Writes nothing.

    `registered` is the list of `RegisteredAccount` rows. Only their attributes are read, so this
    module never imports the registry and stays testable against any object with those fields.
    """
    result = parse_scan(payload)
    if not result.asked:
        return result

    rows = list(registered or [])
    by_account = {int(r.account): r for r in rows}

    seen_accounts = {}
    # What each bot says, from the SAME answer as the terminals: the box script reads every bot's own
    # heartbeat and attaches it to the terminal it owns, so one scan is one trip taken at one moment.
    # An explicit `observed_by_bot` still wins, which is how the tests drive the judgement directly.
    by_bot: dict = {}
    for raw_t in payload.get("terminals") or []:
        for bot, seen in (raw_t.get("reported_by_bots") or {}).items():
            by_bot[bot] = seen
    by_bot.update(observed_by_bot or {})
    for raw in payload.get("terminals") or []:
        reading = _reading(raw)
        if reading.account is not None:
            reading.account_source = "terminal"
        elif raw.get("state") == "owned_by_bot":
            found, source = _account_from_bots(raw, by_bot)
            if found is not None:
                reading.account, reading.account_source = found, source
                reading.reason = (
                    f"Your bots use this terminal; they report it is on account {found}"
                )
        if reading.account is None:
            # Not probed, or probed and unreadable. Either way there is no account to judge, and
            # the record already carries WHY in `reason`/`error`.
            reading.verdict = "unasked"
            result.terminals.append(reading)
            continue
        seen_accounts[int(reading.account)] = reading
        row = by_account.get(int(reading.account))
        if row is None:
            reading.verdict = "new"
        else:
            # 🔴 **Only BROKER facts are compared here — never which terminal it was seen on.**
            # An account can be logged in on several terminals at once, and on this box that is
            # the NORMAL state: the demo account is open in the bots' terminal and in the lab's
            # at the same time. Treating "found somewhere else too" as a contradiction reported
            # the one correct row in the list as wrong, on the very first live run.
            reading.conflicts = _compare(reading, row)
            reading.verdict = "conflict" if reading.conflicts else "known"
        result.terminals.append(reading)

    # Keyed on the RESOLVED readings rather than the raw payload, so a terminal whose account
    # came from the bot trading through it is visible here too. Passing the payload meant the one
    # terminal this tool cannot attach to was also the one no row could ever be checked against.
    by_key = {r.key: r for r in result.terminals}
    for row in rows:
        result.registry.append(_check_row(row, seen_accounts, by_key))
    return result


def _check_row(row: Any, seen: dict, by_key: dict) -> RegistryCheck:
    """Whether the box backs up one row of the account list.

    🔴 **An account can be logged in on MORE THAN ONE terminal, and this function was written as
    if it could not be.** On this box the demo account is open in the bots' terminal and in the
    lab's simultaneously, which is normal and intended — so "I found this account somewhere other
    than the row claims" is not evidence against the row. The row's terminal claim is checked by
    looking up THAT terminal and asking what IT is logged into; nothing else can contradict it.
    The first live run reported the one entirely correct row in the list as wrong.

    🔴 **"Not seen" is UNVERIFIED, never "wrong".** A terminal that is switched off, or one a bot
    trades through and is therefore deliberately not attached to, produces no reading — and
    calling that a contradiction would fill the page with false alarms and teach everyone to
    ignore the real ones.
    """
    account = int(row.account)
    label = str(getattr(row, "label", "") or "")

    # Broker facts — server, demo-or-live, the suffix. These belong to the ACCOUNT, so a reading
    # from any terminal logged into it is evidence about them.
    reading = seen.get(account)
    conflicts = list(reading.conflicts) if reading is not None else []

    claimed = str(getattr(row, "mt5_path", "") or "")
    if not claimed:
        detail = "No terminal is recorded for it, so there's nothing to check it against."
        if conflicts:
            return RegistryCheck(
                account,
                label,
                "contradicted",
                detail,
                conflicts,
                reading.install if reading else None,
            )
        return RegistryCheck(account, label, "unverified", detail)

    key = _install_key(claimed)
    terminal = by_key.get(key)

    if terminal is None:
        detail = f"The VPS has no terminal installed at {_short(claimed)}."
    elif terminal.account is None and terminal.state == "owned_by_bot":
        detail = (
            f"{_short(claimed)} is your bots' terminal, and no bot on it has reported which "
            f"account it is on yet."
        )
    elif terminal.account is None:
        detail = f"{_short(claimed)} is not running, so it couldn't be checked."
    elif terminal.account == account:
        # The claimed terminal was ASKED — by this tool, or by the bot trading through it — and
        # it is on this account. That is the row confirmed, whatever else the account is open in.
        also = sorted(
            _short(t.install) for t in by_key.values() if t.account == account and t.key != key
        )
        how = " (reported by the bot there)" if terminal.account_source == "bot" else ""
        detail = f"Logged in on {_short(terminal.install)}{how}."
        if also:
            detail += f" Also open on {', '.join(also)}."
        verdict = "contradicted" if conflicts else "confirmed"
        return RegistryCheck(account, label, verdict, detail, conflicts, terminal.install)
    else:
        # Asked, and on something else. A measurement, not a gap.
        name = _short(claimed)
        via = " (reported by the bot there)" if terminal.account_source == "bot" else ""
        said = f"Your list says it's on {name}, but {name} is logged into #{terminal.account}{via}."
        conflicts = conflicts + [said]
        return RegistryCheck(account, label, "contradicted", said, conflicts, terminal.install)

    # The claimed terminal could not be asked. Broker-fact conflicts still stand on their own.
    if conflicts:
        return RegistryCheck(
            account, label, "contradicted", detail, conflicts, reading.install if reading else None
        )
    return RegistryCheck(account, label, "unverified", detail)


def _short(path: str) -> str:
    r"""`C:\MT5_FFT\terminal64.exe` or `C:\MT5_FFT` → `MT5_FFT`, in the box's own casing.

    ⚠ **Every sentence here is read by a person, not parsed by a program** (2026-09-10: *"I don't
    know what I'm looking at"*). A full Windows path in a sentence is noise; the folder name is
    the name the terminal goes by on the box. Parsing is split on backslash by hand, as in
    `_install_key`, because this runs on a Mac and the paths are always the box's.
    """
    p = str(path or "").strip().rstrip("\\/")
    if p.lower().endswith("terminal64.exe"):
        p = p[: -len("terminal64.exe")].rstrip("\\/")
    return p.replace("/", "\\").rsplit("\\", 1)[-1] or str(path or "")


def _install_key(path: str) -> str:
    """The join key for a hand-typed terminal path.

    It mirrors the box script's own normalisation - lowercased, exe stripped, no trailing slash -
    because the two sides must agree on what counts as the same terminal. Windows semantics are
    hardcoded rather than taken from `os.path`: this runs on a Mac and the paths are always the
    box's.
    """
    p = str(path or "").strip().rstrip("\\/")
    if p.lower().endswith("terminal64.exe"):
        p = p.rsplit("\\", 1)[0] if "\\" in p else p.rsplit("/", 1)[0]
    return p.lower().rstrip("\\/")


def suggested_registration(reading: TerminalReading) -> dict:
    """The fields a discovered account would arrive with, for the page to pre-fill.

    ⚠ **It fills ONLY what the box measured**, and deliberately leaves the label, tier, cost
    profile and note empty for a person. A guessed cost profile is the dangerous one: it prices
    every backtest against that account, and this repo refuses an unmeasured cost rather than
    borrowing a sibling's number.

    ⚠ **There is no password here and there cannot be** — the terminal encrypts it at rest. The
    account arrives unusable by a bot until somebody stores one, which is the honest state rather
    than a surprise at connect time.
    """
    return {
        "account": reading.account,
        "server": reading.server or "",
        "kind": reading.kind or "",
        "mt5_path": _exe_for(reading),
        "symbol_suffix": reading.symbol_suffix,
        "broker": reading.company or "",
        "label": "",
        "tier": "",
        "account_profile": "",
        "note": "",
    }


def _exe_for(reading: TerminalReading) -> str:
    """The registry stores the exe, and the scan's display path is the folder."""
    install = str(reading.install or "").rstrip("\\/")
    if not install:
        return ""
    if install.lower().endswith("terminal64.exe"):
        return install
    return install + "\\terminal64.exe"
