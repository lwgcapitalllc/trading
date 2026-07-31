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
from typing import Any, Dict, Optional

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
    bot_key: str                      # unique per bot; the process is found by this string
    display_name: str                 # what Telegram and the Bots page call it

    # ── which MT5 ───────────────────────────────────────────────────────────
    mt5_path: str                     # FULL path to terminal64.exe — this is "which instance"
    account: int                      # login number; BotMT5.connect refuses a mismatch
    server: str
    symbol: str                       # the BROKER's symbol string (XAUUSD, XAUUSD.s, …)
    magic: int                        # separates this bot's orders from every other order
    timeframe: str = "M15"

    # ── which strategy, and which version of it ─────────────────────────────
    strategy_package: str = "mpc_sos_fade"     # dir under strategies/python/
    strategy_class: str = "MpcSosFadeStrategy"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    strategy_source_hash: str = ""             # "" = UNPINNED (allowed, logged loudly)
    promoted_commit: str = ""
    promoted_at: str = ""
    strategy_version: int = 0                  # the lab's monotonic per-strategy version

    # ── where this bot reports ──────────────────────────────────────────────
    # Both optional, both empty = the shared default from algos/credentials.json. They exist
    # because bots are not interchangeable: a gold bot on a demo account and an FX bot on a
    # funded one are different conversations, and one Telegram group for both means the
    # message that matters is the one you scroll past.
    #   telegram_chat_id  — the destination. Not a secret (a chat id is useless without a
    #                       token), so it lives here rather than in the credentials file.
    #   telegram_token_key— NAMES a key in algos/credentials.json ("telegram_token_bleg"),
    #                       never the token itself. Set it only to give this bot its own
    #                       Telegram identity; leave empty to send as the default bot.
    telegram_chat_id: str = ""
    telegram_token_key: str = ""

    # ── runtime ─────────────────────────────────────────────────────────────
    warmup_bars: int = 5000           # history replayed to warm the engines before acting
    poll_seconds: int = 10            # how often to check for a newly closed bar
    initial_capital: float = 0.0      # 0 = read the live account balance at startup

    # ── broker clock ────────────────────────────────────────────────────────
    # "std,dst" hours ahead of UTC. MEASURED with backtest/tools/compare_feeds.py against THIS
    # terminal — never assumed. The default matches the Vantage lab terminal; a different broker
    # can differ, and a wrong value shifts every session boundary the strategy trades off.
    broker_tz_offsets: str = "2,3"

    @property
    def instance_dir(self) -> Path:
        return _INSTANCES / self.bot_key

    @property
    def strategy_dir(self) -> Path:
        return _REPO_ROOT / "strategies" / "python" / self.strategy_package

    @property
    def repo_root(self) -> Path:
        return _REPO_ROOT


def config_path(bot_key: str) -> Path:
    return _INSTANCES / bot_key / "config.json"


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
            f"Unknown key(s) in {p}: {', '.join(unknown)}. "
            f"Valid keys: {', '.join(sorted(known))}"
        )
    missing = [k for k in ("bot_key", "mt5_path", "account", "server", "symbol", "magic")
               if k not in raw]
    if missing:
        raise ValueError(f"{p} is missing required key(s): {', '.join(missing)}")
    raw.setdefault("display_name", raw["bot_key"])
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
    return {"login": int(account),
            "password": entry.get("password", ""),
            "server": entry.get("server", "")}
