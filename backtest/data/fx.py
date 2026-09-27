"""fx.py — the quote-currency conversion, sourced from broker bars rather than assumed.

**The question this answers.** A strategy computes money from a PRICE, and a price is in the
symbol's QUOTE currency. XAUUSD is quoted in dollars against a dollar account, so for the whole
life of this repo the two have been the same thing and nothing converted. GBPJPY is quoted in yen.
Without a conversion the backtest overstates its overnight cost by ~156x and mis-sizes every trade
by the same factor — silently, because the numbers are the right shape.

**Why a SERIES and not a number.** A rate is not a constant. USDJPY ran roughly 100 to 160 across
a window these strategies replay, so pricing six years of trades at one reading is wrong by up to
60% at the ends of it — in sizing, which divides by the rate, and in every cost, which multiplies
by it. That error does not average out: it is largest exactly where the window is longest, which
is where a backtest is most believed.

**What it returns.** A `time_ms -> rate` callable, which is the shape
`Execution.set_rate_provider` takes. The rate is *account currency per one unit of quote
currency*: 1.0 when the two are the same, and 1/USDJPY for a yen-quoted symbol on a dollar
account.

⚠ **It REFUSES outside its data rather than reaching for the nearest number.** A request before
the first bar raises. The alternative — flat-extrapolating the earliest rate backwards — is
exactly the failure this module exists to end: a plausible number, no error, and a wrong one. The
caller's window must be inside the conversion pair's history, which is checkable before the run.

⚠ **It carries the rate FORWARD across a gap, and that is deliberate and different.** A weekend
has no bars and the rate genuinely did not move for anyone holding through it, so the last close
is the right answer rather than a guess. Backwards is extrapolation; forwards is persistence.
"""

from __future__ import annotations

import bisect
import datetime as _dt
import re
from typing import Callable, Optional, Sequence

__all__ = [
    "ACCOUNT_CURRENCY",
    "FxRateUnavailable",
    "QuoteConversion",
    "RateSeries",
    "UnknownQuoteCurrency",
    "constant_rate",
    "conversion_symbol",
    "fx_contract_size",
    "quote_currency",
    "rate_provider_for",
    "series_for",
]

#: The currency every lab account is denominated in. Every broker account this repo trades or
#: replays (PU Prime, Vantage) is a dollar account, and the run form's deposit is dollars. A
#: non-dollar account would need this to become a per-run fact, not a second constant.
ACCOUNT_CURRENCY = "USD"


class FxRateUnavailable(RuntimeError):
    """Asked for a rate outside the series. Never answered with a stand-in."""


def constant_rate(value: float) -> Callable[[int], float]:
    """A fixed rate, for a symbol whose quote currency IS the account currency.

    Exists so "this instrument needs no conversion" is a thing a caller SAYS rather than a thing it
    omits — the same reasoning as the cost sentinels in `backtest/fills.py`. A silent absence and a
    deliberate 1.0 read identically at the call site and mean very different things.
    """
    if value <= 0:
        raise ValueError(f"a conversion rate must be positive, got {value!r}")
    return lambda _time_ms: value


class RateSeries:
    """A conversion rate over time, built from the conversion pair's own bars.

    `times_ms` must be sorted ascending and the same length as `closes`. `invert` turns a quoted
    pair into the direction the caller needs: a dollar account pricing a yen-quoted symbol holds
    USDJPY bars and needs USD-per-JPY, so it inverts.
    """

    def __init__(
        self,
        times_ms: Sequence[int],
        closes: Sequence[float],
        *,
        invert: bool = False,
        label: str = "",
    ) -> None:
        if len(times_ms) != len(closes):
            raise ValueError(
                f"{len(times_ms)} timestamps against {len(closes)} closes — a rate series must "
                f"pair them exactly, and a mismatch means the frames were sliced apart."
            )
        if not times_ms:
            raise ValueError("a rate series needs at least one bar; an empty one can only guess")
        for a, b in zip(times_ms, times_ms[1:]):
            if b <= a:
                raise ValueError(
                    "timestamps must be strictly ascending — the lookup is a binary search and "
                    "would silently return the wrong bar otherwise"
                )
        for c in closes:
            if c <= 0:
                raise ValueError(
                    f"a non-positive close ({c!r}) cannot be a rate. Sizing divides by this, so "
                    f"passing it on would be an infinite position."
                )
        self._t = list(times_ms)
        self._c = list(closes)
        self._invert = bool(invert)
        self._label = label or "rate"

    @property
    def first_ms(self) -> int:
        return self._t[0]

    @property
    def last_ms(self) -> int:
        return self._t[-1]

    def __len__(self) -> int:
        return len(self._t)

    def at(self, time_ms: int) -> float:
        """The rate in force at `time_ms` — the last bar that had already CLOSED at or before it.

        ⚠ Before the first bar this RAISES. See the module docstring: a flat extrapolation
        backwards is a plausible wrong number, which is worse than a stopped run.
        """
        if time_ms < self._t[0]:
            raise FxRateUnavailable(
                f"{self._label}: asked for {time_ms}, which is before the series starts "
                f"({self._t[0]}). Widen the conversion pair's history or narrow the run — this "
                f"will not extrapolate backwards."
            )
        i = bisect.bisect_right(self._t, time_ms) - 1
        c = self._c[i]
        return (1.0 / c) if self._invert else c

    def provider(self) -> Callable[[int], float]:
        """The `time_ms -> rate` callable `Execution.set_rate_provider` takes."""
        return self.at

    @classmethod
    def from_frame(
        cls,
        df,
        *,
        invert: bool = False,
        label: str = "",
        close_col: str = "close",
        bar_minutes: Optional[int] = None,
    ) -> "RateSeries":
        """Build from a bar frame as `backtest.data.BarSource` returns one.

        The index is UTC bar-OPEN timestamps (this repo's convention, matching MT5). 🔴 **Each
        close is keyed at its bar's CLOSE, not its open** — open plus one bar. Keyed at the open,
        a bar's close was "in force" for the whole bar it had not finished yet: a daily USDJPY bar
        priced a 10:00 fill at that evening's close. That is lookahead, and it was how this built
        the series until 2026-09-27. `bar_minutes` is the frame's spacing; left out, it is read off
        the smallest gap, and a one-bar frame refuses because it has no gap to read.
        """
        if close_col not in df.columns:
            raise ValueError(f"frame has no {close_col!r} column; got {list(df.columns)}")
        opens = [int(ts.value // 1_000_000) for ts in df.index]
        if bar_minutes is None:
            gaps = [b - a for a, b in zip(opens, opens[1:]) if b > a]
            if not gaps:
                raise ValueError(
                    "cannot read the bar spacing off fewer than two bars — state bar_minutes, "
                    "because a close keyed at the wrong instant is lookahead"
                )
            span_ms = min(gaps)
        else:
            span_ms = int(bar_minutes) * 60_000
        times = [t + span_ms for t in opens]
        return cls(times, [float(v) for v in df[close_col]], invert=invert, label=label)


def series_for(
    source,
    symbol: str,
    timeframe,
    start_date: str,
    end_date: str,
    *,
    invert: bool,
    label: Optional[str] = None,
) -> RateSeries:
    """Pull the conversion pair's bars and wrap them.

    `source` is anything with `BarSource.load`'s signature, injected rather than constructed so
    tests run offline — the same pattern the rest of this package uses.
    """
    df = source.load(symbol, timeframe, start_date, end_date)
    if df is None or len(df) == 0:
        raise FxRateUnavailable(
            f"{symbol} returned no bars for {start_date}..{end_date}, so there is no rate to "
            f"convert with. This refuses rather than defaulting to 1.0, which would silently "
            f"price a foreign-quoted instrument as though it were the account's own currency."
        )
    from backtest.data.timeframes import to_minutes

    return RateSeries.from_frame(
        df, invert=invert, label=label or symbol, bar_minutes=to_minutes(timeframe)
    )


# ── which currency a symbol pays out in, and what converts it ────────────────


class UnknownQuoteCurrency(ValueError):
    """The symbol's name does not say what currency it is quoted in. Never assumed to be dollars."""


#: Quote currencies this can convert. A name ending in anything else refuses.
_KNOWN_QUOTES = frozenset(
    "USD JPY GBP EUR CHF CAD AUD NZD SGD HKD NOK SEK DKK ZAR MXN TRY PLN CNH".split()
)
#: The currencies the market quotes AGAINST the dollar (GBPUSD, not USDGBP). Every other one is
#: quoted as USDxxx. A market convention, not a broker setting.
_QUOTED_AGAINST_USD = frozenset({"EUR", "GBP", "AUD", "NZD"})
#: Six capitals at the front, not followed by a seventh — "GBPJPY.p" and "GBPJPYm" match, "US30",
#: "USTEC" and "MNQ 06-26" do not.
_PAIR = re.compile(r"^([A-Z]{3})([A-Z]{3})(?![A-Z])")


def quote_currency(symbol: str) -> str:
    """The currency a symbol's price, and so its P&L, is in: "GBPJPY.p" -> "JPY".

    ⚠ **REFUSES a name it cannot read**, never answers "USD". A dollar default is right for every
    symbol this repo traded before 2026-09 and silently 156x wrong on the first yen pair — the
    exact failure this module exists to end.
    """
    m = _PAIR.match(symbol or "")
    if not m or m.group(2) not in _KNOWN_QUOTES:
        raise UnknownQuoteCurrency(
            f"cannot tell what currency {symbol!r} is quoted in from its name, so its P&L cannot "
            f"be converted to {ACCOUNT_CURRENCY}. Add its quote currency to backtest/data/fx.py "
            f"rather than assuming it is {ACCOUNT_CURRENCY}."
        )
    return m.group(2)


#: Units in one standard lot of a currency pair. MEASURED 100,000 on PU Prime's GBPJPY.p and
#: GBPUSD.p (2026-09-17), and the market convention for every currency pair.
FX_CONTRACT_SIZE = 100_000.0


def fx_contract_size(symbol: str) -> Optional[float]:
    """100,000 for a currency pair ("GBPJPY.p"), None for anything else (gold, an index).

    None is "not a currency pair", never "100": gold's lot is 100 ounces and silver's 5,000, and
    this function has no business answering for either.
    """
    m = _PAIR.match(symbol or "")
    if m and m.group(1) in _KNOWN_QUOTES and m.group(2) in _KNOWN_QUOTES:
        return FX_CONTRACT_SIZE
    return None


def conversion_symbol(symbol: str) -> Optional[tuple]:
    """(pair, invert) that converts `symbol`'s quote currency into the account's, or None.

    None means the symbol is ALREADY in the account currency — XAUUSD, GBPUSD. The pair carries the
    traded symbol's own broker suffix, because the rate must come off the same feed: "GBPJPY.p"
    converts through "USDJPY.p", inverted, since a dollar account needs dollars per yen.
    """
    quote = quote_currency(symbol)
    if quote == ACCOUNT_CURRENCY:
        return None
    suffix = symbol[6:]
    if quote in _QUOTED_AGAINST_USD:
        return (f"{quote}{ACCOUNT_CURRENCY}{suffix}", False)
    return (f"{ACCOUNT_CURRENCY}{quote}{suffix}", True)


def rate_provider_for(
    source,
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    timeframe=60,
    lead_days: int = 14,
) -> Optional[Callable[[int], float]]:
    """The per-bar conversion a run on `symbol` needs, or None when it needs none.

    🔴 **THIS IS THE ONE PLACE A RUN DECIDES ITS CONVERSION.** Every replay path — the lab run, the
    optimizer, the stack — asks here and hands the answer to `backtest.replay.build_strategy`, so
    no two paths can price the same yen trade differently.

    None for a dollar-quoted symbol, and that None is what keeps every gold run byte-identical:
    nothing is installed, so the strategy reads its configured constant exactly as before.

    Hourly bars by default: the rate is read at each fill, and an hourly close is at most an hour
    stale where a daily one is up to a day. `lead_days` starts the conversion pair before the run
    so the run's first bar already has a closed rate behind it — without it the first fills of a
    run starting on a Monday would refuse.
    """
    pair = conversion_symbol(symbol)
    if pair is None:
        return None
    rate_symbol, invert = pair
    padded = (
        _dt.date.fromisoformat(str(start_date)[:10]) - _dt.timedelta(days=lead_days)
    ).isoformat()
    series = series_for(
        source, rate_symbol, timeframe, padded, end_date, invert=invert, label=rate_symbol
    )
    return series.provider()


class QuoteConversion:
    """A strategy's quote-to-account factor: its configured constant, or a rate installed per run.

    The piece each strategy's execution layer holds so it does not grow its own copy of this logic.
    `at(time_ms)` is read at the moment each money figure happens — sizing at the entry, P&L at
    the exit, swap at the rollover it is charged for — which is what a broker does.

    ⚠ **With nothing installed `at()` returns the constant and the strategy is byte-identical**,
    which is how this lands without moving a stored gold result. ⚠ **An installed rate that
    answers 0 or less RAISES.** Sizing divides by it, so a zero is an infinite position, and
    falling back to the constant would be a snapshot rate presented as a measured one.
    """

    def __init__(self, constant: float) -> None:
        self._constant = float(constant)
        self._provider: Optional[Callable[[int], float]] = None

    def install(self, fn: Optional[Callable[[int], float]]) -> None:
        """Install a `time_ms -> rate` callable, or None to go back to the constant."""
        self._provider = fn

    @property
    def installed(self) -> bool:
        return self._provider is not None

    def at(self, time_ms: Optional[int]) -> float:
        if self._provider is None:
            return self._constant
        if time_ms is None:
            raise FxRateUnavailable(
                "a conversion rate is installed but this figure did not say WHEN it happened, "
                "and a rate is only an answer at a moment"
            )
        v = self._provider(int(time_ms))
        if not (v > 0):
            raise FxRateUnavailable(
                f"the installed conversion rate answered {v!r} at {time_ms}; a rate must be "
                f"positive, and sizing divides by it"
            )
        return v
