"""live_config.py — one live bot's instance configuration.

(The `live_` prefix is deliberate. These modules are imported by BARE NAME because `runner.py`
is launched as a script, so a module called `config` here would shadow
`command-center/backend/config.py` and `strategies/python/*/config.py` for anything that ends up
with both directories on `sys.path` — which the test suite does, and which failed exactly that
way once already.)

Everything machine-, account- and version-specific about a deployment lives in ONE
git-ignored-ish JSON file per bot, under `algos/markets/fx/instances/<bot_key>/config.json`.
The bot reads it and nothing else: no defaults from the strategy's own `config.py`, no
environment guessing, no hardcoded terminal path.

**Why `strategy_params` is a full explicit dict and not "the defaults plus overrides".** A
partial override reads the rest from `strategies/python/<pkg>/config.py`, which is the file the
lab edits all day. That is precisely the leak this design exists to close — see `version.py`.
So the promoted parameter set is written out in full, and a value that is not in the file is a
value this bot does not have an opinion about (it takes the dataclass default, which is then
part of the pinned code hash anyway).

Credentials never appear here. The MT5 login/password/server come from
`algos/credentials.json` via `shared/credentials.py`, keyed by account number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INSTANCES = _REPO_ROOT / "algos" / "markets" / "fx" / "instances"

# ── what may change under a RUNNING bot ─────────────────────────────────────────
# Strategy params that the runner will pick up from a rewritten instance config without a
# restart. Everything else needs one, deliberately: these are the knobs that change HOW
# MUCH the bot risks, never WHICH trades it takes, so applying one leaves the running bot
# still comparable to the backtest that justified it. Change which trades it takes and the
# `strategy_source_hash` pin stops meaning anything.
#
# ⚠ MIRRORED in command-center/backend/services/bot_params.py::RUNTIME_EDITABLE, which is
# what the Bots page will let you edit. The two cannot import each other (the subsystems
# are independent by rule), so the command center pins the agreement with a test that
# READS this file — see tests/test_bot_params_agreement.py. Change one, change both.
RUNTIME_RELOADABLE = frozenset({"exec_risk_pct"})


@dataclass
class LiveConfig:
    # ── identity ────────────────────────────────────────────────────────────
    bot_key: str  # unique per bot; the process is found by this string
    display_name: str  # what Telegram and the Bots page call it

    # ── which MT5 ───────────────────────────────────────────────────────────
    mt5_path: str  # FULL path to terminal64.exe — this is "which instance"
    # The login this bot trades. `BotMT5.connect` refuses a mismatch.
    #
    # ⚠ **`None` means ON THE BENCH: registered, configured, and deliberately not on any
    # account.** It is what "remove this bot from the account" writes, and it has to be a real
    # state rather than a deletion — a bot's magic, its params and its promoted version are all
    # facts worth keeping while it is not trading, and re-adding it later must give back the same
    # bot rather than a new one that happens to share a name. The KEY is still required in the
    # file (see `load`), so *deliberately unassigned* and *somebody forgot the account* stay
    # different things.
    #
    # ⚠ **An unassigned bot cannot START, and three separate places enforce it** rather than one:
    # `runner.run()` refuses, `startup_coordinator` skips it in the full boot sequence and refuses
    # in single-bot mode. Two of those are recovery paths that re-issue a start on their own, so a
    # guard in the runner alone would leave the bench meaning "until the watchdog notices".
    account: Optional[int]
    server: str
    symbol: str  # the BROKER's symbol string (XAUUSD, XAUUSD.s, …)
    magic: int  # separates this bot's orders from every other order
    timeframe: str = "M15"

    # ── which strategy, and which version of it ─────────────────────────────
    strategy_package: str = "mpc_sos_fade"  # dir under strategies/python/
    strategy_class: str = "MpcSosFadeStrategy"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    strategy_source_hash: str = ""  # "" = UNPINNED (allowed, logged loudly)
    promoted_commit: str = ""
    promoted_at: str = ""
    # 🔴 This was `int = 0` and NOTHING assigned it, so every bot's ONLINE banner read `v0`
    # from the day it was written. `algos/tools/promote.py::version_at` measures it now (the
    # count of commits touching this bot's trees) and stamps it into `deployed.json`, which
    # overrides this field below. `None` means *nobody could count it* — a bot promoted before
    # 2026-08-14, or a checkout `rev-list` could not read — and renders `v?`, never `v0`.
    strategy_version: Optional[int] = None

    # ── where this bot reports ──────────────────────────────────────────────
    # Both optional, both empty = the shared default from algos/credentials.json. They exist
    # because bots are not interchangeable: a gold bot on a demo account and an FX bot on a
    # funded one are different conversations, and one Telegram group for both means the
    # message that matters is the one you scroll past.
    #   telegram_chat_id  — where its TRADES go (entry and exit). Not a secret (a chat id is
    #                       useless without a token), so it lives here rather than in the
    #                       credentials file.
    #   telegram_health_chat— where its HEALTH messages go (link lost, re-warmed, halted,
    #                       stopped, config refused). Separate because the two are read with a
    #                       different reflex, and a room that pings all day for machinery is one
    #                       you learn to ignore. Empty = the shared `telegram_health_chat`.
    #   telegram_token_key— NAMES a key in algos/credentials.json ("telegram_token_bleg"),
    #                       never the token itself. Set it only to give this bot its own
    #                       Telegram identity; leave empty to send as the default bot.
    #   telegram_signal_chat— where its PRE-TRADE SETUP alerts go: a setup forming, its entry
    #                       zone going live, a rule blocking it, and what became of it. A third
    #                       room because it is a third reflex — read when you have time, not the
    #                       moment it arrives — and MEASURED at ~5x the volume of fills (11/month
    #                       against 2/month over 6.5 years). Empty = the shared
    #                       `telegram_signal_chat`. See `docs/LIVE_SETUP_ALERTS.md`.
    #   setup_alert_categories— which of those four to send. Empty list = none; ABSENT = all four
    #                       (`setup_alerts.DEFAULT_CATEGORIES`). The two are deliberately
    #                       different: "I switched them all off" is a choice, "I said nothing" is
    #                       not, and collapsing them would make a config typo look deliberate.
    telegram_chat_id: str = ""
    telegram_health_chat: str = ""
    telegram_signal_chat: str = ""
    telegram_token_key: str = ""
    setup_alert_categories: Optional[List[str]] = None

    # ── runtime ─────────────────────────────────────────────────────────────
    warmup_bars: int = 5000  # history replayed to warm the engines before acting
    poll_seconds: int = 10  # how often to check for a newly closed bar
    initial_capital: float = 0.0  # 0 = read the live account balance at startup
    # The most of the account's FREE margin ONE order may consume. An order needing more is
    # REFUSED, never shrunk to fit — see `algos/shared/order_sizing.py`. 50 leaves room for the
    # position to move against us before the broker starts closing things, and for a second bot
    # sharing the login. 100 would let one setup commit the whole account, which is how the
    # 2026-08-07 order got as far as the broker deleting it at the fill.
    margin_safety_pct: float = 50.0
    # ── the ACCOUNT-level risk cap (G10) ────────────────────────────────────
    # The most open risk EVERY bot on this account may hold at once, as a % of the live balance,
    # measured to each position's CURRENT broker-side stop — so a stop moved to breakeven frees
    # its room, exactly as it does in `backtest/portfolio/`. It is the layer above
    # `exec_risk_pct`, which is per-TRADE and has never had anything above it: two bots at 10%
    # put 20% on from a state neither can see.
    #
    # ⚠ `None` = UNCAPPED, and that is a supported, honest state rather than an oversight. A
    # one-bot account needs no cap, every result this repo has measured was taken without one,
    # and inventing a default here would change a live bot's behaviour with no measurement behind
    # it. The runner LOGS which state it is in at startup so "no cap" is a reported fact — the
    # same call `deadman_url` makes, for the same reason: an absent guard must not be silent.
    #
    # ⚠ It is NOT runtime-reloadable. `RUNTIME_RELOADABLE` covers `exec_risk_pct` alone because
    # that one is applied only while flat by rebuilding the strategy; the cap is read by the
    # bridge, which holds live order state, so changing it means a restart.
    account_risk_cap_pct: Optional[float] = None

    # ── the balance the strategy may size against ───────────────────────────
    #
    # ADDED to the broker's balance before anything sizes off it, so an amount to EXCLUDE is
    # written NEGATIVE. Zero or absent means "size off exactly what the broker reports", which is
    # the only sane default and the behaviour every bot had before 2026-08-26.
    #
    # 🔴 It exists because a defect can put money in the account. Five copies of one order filled
    # on 2026-08-25 and left $3,344.80 the strategy did not earn; the very next trade went out at
    # 0.53 lots where the risk percentage called for 0.40. **Labelling the trades in the record
    # was not enough — the balance they left behind keeps sizing every trade that follows.**
    #
    # ⚠ It REFUSES rather than clamping: an adjustment that leaves nothing to trade on makes the
    # basis unreadable, and every caller already treats that as "cannot size".
    # ⚠ NOT runtime-reloadable. It is read at startup and at every flat-moment re-anchor, so a
    # change needs a restart - the same rule as the account cap above.
    # ⚠ It is a CLAIM, and it goes stale. State the reason and the date beside it in
    # `config.json`, and revisit it when the account is next reconciled.
    sizing_basis_adjustment: float = 0.0

    # ── broker clock ────────────────────────────────────────────────────────
    # "std,dst" hours ahead of UTC. MEASURED with backtest/tools/compare_feeds.py against THIS
    # terminal — never assumed. The default matches the Vantage lab terminal; a different broker
    # can differ, and a wrong value shifts every session boundary the strategy trades off.
    broker_tz_offsets: str = "2,3"

    @property
    def instance_dir(self) -> Path:
        return _INSTANCES / self.bot_key

    # ── the deployed snapshot ───────────────────────────────────────────────
    # A promoted bot runs a FROZEN COPY of its code, held here, and the repo working tree
    # becomes irrelevant to it. That is the whole point, and it is the half of the version
    # isolation that was missing until 2026-08-03: `strategy_params` was frozen in this file
    # from the start, but `strategy_dir` pointed straight at `strategies/python/<pkg>` in the
    # repo. So a `git pull` on the VPS — for a lab fix, an agent update, anything — rewrote the
    # code under a running bot, and the pin then refused to restart it. Backtesting a new
    # version could brick the deployed one. Aaron's rule, and it is the right one: a bot runs
    # what you last DEPLOYED until you deploy something else.
    #
    # Three trees, not one, because all three decide what the bot trades:
    #   strategies/python/<pkg>   the strategy itself
    #   engines/                  market structure, fibs, FVG, divergence, sessions, liquidity
    #   backtest/                 replay + the fill model the live bridge mirrors
    # Hashing only the first (which is all the pin used to do) leaves the engines free to move
    # under a green pin — the bot starts happily and trades different logic. See version.py.
    @property
    def deployed_dir(self) -> Path:
        return self.instance_dir / "deployed"

    @property
    def version_label(self) -> str:
        """`v165`, or `v?` when nobody could count it. **Never `v0` for an unknown.**

        One rendering, read by the log banner, the ONLINE alert, the ledger's startup record
        and `bot_state.json` — four places that would otherwise each decide what to print for
        `None`, and `f"v{None}"` renders `vNone` in every one of them.
        """
        return "v?" if self.strategy_version is None else f"v{self.strategy_version}"

    @property
    def is_frozen(self) -> bool:
        """True once this bot has been promoted — i.e. it has its own copy of the code."""
        return (self.deployed_dir / "strategies" / "python" / self.strategy_package).is_dir()

    @property
    def code_root(self) -> Path:
        """The tree this bot's imports resolve against: its snapshot, or the repo if unpromoted.

        An UNPROMOTED bot falling back to the repo is deliberate — it is the state you pass
        through while building a new bot, and refusing to run at all would make the first
        promotion impossible. `runner.py` says loudly which of the two it is using.
        """
        return self.deployed_dir if self.is_frozen else _REPO_ROOT

    @property
    def strategy_dir(self) -> Path:
        return self.code_root / "strategies" / "python" / self.strategy_package

    @property
    def import_paths(self) -> list[Path]:
        """What to put at the FRONT of `sys.path` so every import resolves inside `code_root`.

        Mirrors the repo layout exactly, so a snapshot import and a repo import find the same
        module by the same name — the freeze changes WHICH copy is loaded, never how it is
        spelled.
        """
        return [self.code_root, self.code_root / "strategies" / "python"]

    @property
    def source_roots(self) -> list[Path]:
        """Every tree the version pin must hash, in a fixed order (the hash depends on it)."""
        return [self.strategy_dir, self.code_root / "engines", self.code_root / "backtest"]

    @property
    def repo_root(self) -> Path:
        return _REPO_ROOT


def config_path(bot_key: str) -> Path:
    return _INSTANCES / bot_key / "config.json"


def deployed_path(bot_key: str) -> Path:
    """The deployment record written by `algos/tools/promote.py`. Git-ignored, machine-local."""
    return _INSTANCES / bot_key / "deployed.json"


def deployed_record(bot_key: str) -> Dict[str, Any]:
    """What is actually deployed on THIS machine, or `{}` if the bot was never promoted.

    Separate from `config.json` because promoting happens on the VPS and `config.json` is tracked
    in git — writing the pin there would make every deploy collide with the next `git pull`. See
    `promote.write_pin`.
    """
    p = deployed_path(bot_key)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A corrupt record must not stop a bot that is otherwise fine — the snapshot itself is
        # still hash-checked, which is the guarantee that matters. Reported as unpromoted.
        return {}


def _assert_magic_is_unique(bot_key: str, account, magic) -> None:
    """No two bots on ONE ACCOUNT may share a magic number.

    The magic is what separates one bot's orders from every other order on the terminal: every
    read in `mt5_ops.py` filters on it, and `bridge.adopt_broker_state` HALTS on a position under
    this bot's magic that it has no record of. Two bots sharing one would therefore each read the
    OTHER's position as its own — cancel its orders, ratchet its stop, and report its fill as a
    trade of its own — which is precisely the doubled-book failure the duplicate-process guards
    exist to prevent, arriving through configuration instead of through a second process.

    ⚠ **It is per ACCOUNT, not global.** Two bots on two different accounts may share a magic
    quite safely — the terminal scopes orders by login — and refusing that would be a rule nobody
    could satisfy once there are more accounts than sensible magic numbers.

    ⚠ **An unreadable sibling config is SKIPPED, not fatal.** A half-written instance directory
    must not stop a healthy bot from starting; the cost of skipping is that a clash hiding inside
    a broken file is missed, and a broken file fails loudly on its own next start anyway.

    ⚠ **A bot on the BENCH (`account is None`) is exempt, and so is a benched sibling.** The rule
    is about two bots reading one terminal's order book, and a bot on no account reads nothing. It
    is not a technicality: `None == None`, so without this the guard would fire between two
    unassigned bots — refusing to load a bot that is not trading, because of another bot that is
    not trading either. It re-arms the moment either is assigned, which is the moment it matters.

    Checked at LOAD rather than in a linter, because the file is edited by hand and by the Bots
    page, and the only moment that reliably precedes trading is this one.
    """
    if account is None:
        return
    for other in sorted(_INSTANCES.glob("*/config.json")):
        try:
            raw = json.loads(other.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if raw.get("bot_key") == bot_key:
            continue
        if raw.get("account") == account and raw.get("magic") == magic:
            raise ValueError(
                f"magic {magic} is already used by bot {raw.get('bot_key')!r} on account "
                f"{account}. Two bots sharing one magic on one account each read the OTHER's "
                f"orders as their own — cancelling them, moving their stops and booking their "
                f"fills — so give {bot_key!r} a magic of its own before starting it."
            )


def _assert_account_cap_agrees(bot_key: str, account, cap) -> None:
    """Every bot on ONE ACCOUNT must state the SAME `account_risk_cap_pct`.

    The cap is an ACCOUNT-level fact — *the most open risk this account may ever hold* — and it is
    stored per instance, because an instance config is the only file a bot reads. Those two facts
    together are the hazard: two bots on one account can state different numbers, and then the
    budget is not one budget. `bridge._account_cap_check` reads the CALLER's own setting, so which
    number binds depends on which bot happens to ask, and the account's real ceiling becomes the
    LARGEST of them — the least protective one, chosen by nothing.

    ⚠ **A missing cap is a DISAGREEMENT, not a neutral value, and this is the case worth stating.**
    `null` means uncapped, so one capped bot beside one uncapped bot is the worst of the shapes:
    the uncapped bot fills the account freely while the capped one is refused, so the guard is
    doing nothing except handicapping whichever bot was configured correctly. Reading `null` as
    "no opinion, inherit the sibling's" would be this repo's own *no* vs *cannot ask* defect — the
    absent value would silently acquire a meaning nobody wrote down.

    ⚠ **It REFUSES rather than warning, and that is a deliberate cost.** An incoherent cap takes
    every bot on the account off the box at its next start, which is loud and recoverable; a
    warning leaves an account trading under a ceiling that is not enforced and reads on screen as
    though it is. The Bots page writes the number to every bot on the account in one action, so
    this should only ever fire on a hand edit or a half-finished one.

    ⚠ **Per ACCOUNT, like the magic guard**, and an unreadable sibling is SKIPPED for the same
    reason: a half-written instance directory must not stop a healthy bot from starting.

    ⚠ **A bot on the BENCH (`account is None`) is exempt, for the magic guard's reason and one
    more of its own.** There is no budget to disagree about — but also, `null` is the natural cap
    for a bot nobody has decided about yet, so without this exemption two benched bots with
    different caps would refuse to load, and assigning a benched bot to a capped account would be
    blocked by whichever OTHER benched bot happened to sort first. The Bots page adopts the
    account's cap as part of the assignment precisely so the guard is satisfied on arrival.
    """
    if account is None:
        return
    for other in sorted(_INSTANCES.glob("*/config.json")):
        try:
            raw = json.loads(other.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if raw.get("bot_key") == bot_key or raw.get("account") != account:
            continue
        theirs = raw.get("account_risk_cap_pct")
        if theirs == cap:
            continue
        mine_s = "no cap" if cap is None else f"{cap}%"
        theirs_s = "no cap" if theirs is None else f"{theirs}%"
        raise ValueError(
            f"account risk cap disagreement on account {account}: {bot_key!r} states {mine_s} "
            f"and {raw.get('bot_key')!r} states {theirs_s}. The cap is a ceiling on the WHOLE "
            f"account, so two values mean the real ceiling is whichever bot asks — and a bot "
            f"with no cap fills the account freely while the capped one is refused. Set "
            f"account_risk_cap_pct to the same value in every instance on this account (or to "
            f"null in all of them to run uncapped)."
        )


def load(bot_key: str) -> LiveConfig:
    """Read one bot's config. Raises with an actionable message if it is missing or malformed —
    a live bot must never start on a guessed configuration."""
    p = config_path(bot_key)
    if not p.exists():
        raise FileNotFoundError(
            f"No live config for bot {bot_key!r} at {p}. Copy "
            f"algos/live/instance.template.json there and fill it in."
        )
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw.pop("_README", None)
    known = {f for f in LiveConfig.__dataclass_fields__}
    unknown = sorted(k for k in raw if k not in known and not k.startswith("_"))
    if unknown:
        # Loud, not silent: a typo'd key is a setting that reads as applied and is not.
        raise ValueError(
            f"Unknown key(s) in {p}: {', '.join(unknown)}. Valid keys: {', '.join(sorted(known))}"
        )
    missing = [
        k for k in ("bot_key", "mt5_path", "account", "server", "symbol", "magic") if k not in raw
    ]
    if missing:
        raise ValueError(f"{p} is missing required key(s): {', '.join(missing)}")
    raw.setdefault("display_name", raw["bot_key"])
    _assert_magic_is_unique(raw["bot_key"], raw["account"], raw["magic"])
    _assert_account_cap_agrees(raw["bot_key"], raw["account"], raw.get("account_risk_cap_pct"))

    # The DEPLOYMENT record wins on the version fields. `config.json` states the intent; only a
    # promote can state what is actually on disk, and only the machine that ran it knows. Left
    # alone, `config.json`'s copy of these would go stale the moment the repo moved and the bot
    # would report a version it is not running — the exact confusion this whole mechanism exists
    # to remove.
    #
    # `strategy_params` is deliberately NOT overridden: it stays live-editable in `config.json`
    # so the Bots page can change `exec_risk_pct` on a running bot (see RUNTIME_RELOADABLE). The
    # promoted set is recorded in `deployed.json` anyway, so the two can be compared and any
    # drift shown rather than hidden.
    deployed = deployed_record(raw["bot_key"])
    for key in ("strategy_source_hash", "promoted_commit", "promoted_at", "strategy_version"):
        if key in deployed:
            raw[key] = deployed[key]

    return LiveConfig(**{k: v for k, v in raw.items() if not k.startswith("_")})


def account_credentials(account: int) -> Optional[dict]:
    """`{login, password, server}` for an MT5 account, from `algos/credentials.json`
    (`mt5_accounts` keyed by the account number as a string). Returns None when absent — the
    caller reports that as "not configured", never as a crash."""
    import sys

    sys.path.insert(0, str(_REPO_ROOT / "algos" / "shared"))
    from credentials import _load  # noqa

    accounts = _load().get("mt5_accounts") or {}
    entry = accounts.get(str(account))
    if not entry:
        return None
    return {
        "login": int(account),
        "password": entry.get("password", ""),
        "server": entry.get("server", ""),
    }
