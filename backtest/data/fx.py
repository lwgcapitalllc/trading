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
from typing import Callable, Optional, Sequence

__all__ = ["RateSeries", "constant_rate", "FxRateUnavailable"]


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
    ) -> "RateSeries":
        """Build from a bar frame as `backtest.data.BarSource` returns one.

        The index is UTC bar-OPEN timestamps (this repo's convention, matching MT5), so the value
        a bar contributes is in force from its open onwards — which is what `at()`'s
        last-bar-at-or-before lookup gives.
        """
        if close_col not in df.columns:
            raise ValueError(f"frame has no {close_col!r} column; got {list(df.columns)}")
        times = [int(ts.value // 1_000_000) for ts in df.index]
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
    return RateSeries.from_frame(df, invert=invert, label=label or symbol)
