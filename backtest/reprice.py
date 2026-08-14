"""Re-price a COMPLETED run's stored trades at a different cost profile, without replaying it.

**Why this can exist at all**, and it is the whole reason the page toggle is honest rather than
indicative: for every cost this module charges, the cost expressed in **R is independent of
position size**. Take the spread. A trade risks `dist * qty` dollars and is charged `spread * qty`,
so

    cost_R = (spread * qty) / (dist * qty) = spread / dist

and `qty` cancels. Commission and swap cancel the same way. That matters because a charged run
compounds differently — every later trade is a different SIZE — and the naive worry is that you
cannot know the cost of a position you never sized. You do not need to: the R is fixed, and the
dollars follow from re-walking the balance.

**What it may NOT do.** `bid_ask_fills` moves the fills themselves, so it changes WHICH setups fill
and which get displaced — measured at 161 trades → 159, with four setups that never existed on the
free path. There is no arithmetic over a stored trade list that can produce a trade the list does
not contain, so that layer is refused here and stays a re-run. Returning a number for it would be
the same defect this repo keeps meeting from the other side: a figure on a page that no code
actually produced.

**Proven, not argued.** `tests/test_reprice.py` replays `mpc_sos_fade` over real cached bars twice
— free, and charged — then rebuilds the second from the first's stored curve and asserts equality
to the cent. The spread case reproduces 130.27R / $16,266,933.57 exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from .fills import AccountProfile

__all__ = [
    "REPRICEABLE_LAYERS",
    "EXACT_LAYERS",
    "APPROXIMATE_LAYERS",
    "RepriceError",
    "RepricedTrade",
    "RepricedRun",
    "reprice_curve",
    "rollovers_between",
]

# The cost layers a stored run can be re-priced at. Deliberately NOT the same roster as
# `python_runner.COST_LAYERS`: that one includes `bid_ask_fills`, which changes the trade list and
# therefore has to be replayed. `slippage` is absent for a different reason — it is charged on
# MARKET exits only, and which exits were market rather than limit is a property of the fill model
# at replay time, not something the stored curve records. Both are re-run-only, and the caller is
# expected to SAY so rather than silently drop them.
REPRICEABLE_LAYERS = ("spread", "commission", "swap")

#: Which of those reproduce a real replay to the cent, and which only approximately. A caller
#: showing a re-priced number is expected to caption the difference — a figure that looks exact and
#: is not is the same defect as a label claiming something the code does not do, which is the one
#: this repo keeps meeting. `spread` and `commission` are pure functions of size, price distance and
#: rung count, all stored. `swap` depends on which BARS existed (see `rollovers_between`), and the
#: stored curve records trades rather than the bar stream.
EXACT_LAYERS = ("spread", "commission")
APPROXIMATE_LAYERS = ("swap",)

_NY = ZoneInfo("America/New_York")


class RepriceError(ValueError):
    """A run that cannot be re-priced from storage. Always names the missing thing.

    This refuses rather than degrades on purpose. Every alternative — assuming a default risk %,
    treating an absent stop as zero, skipping a trade whose record is short a field — produces a
    complete-looking equity curve that is quietly about a different run, which is exactly the class
    of failure the layered-cost work was built to end.
    """


@dataclass(frozen=True)
class RepricedTrade:
    index: int
    r: float  # R after the charge
    r_before: float  # R as the stored run measured it
    cost_r: float  # what the layers took off, in R
    cost_usd: float  # ...and in dollars on the RE-PRICED equity path
    profit: float  # the trade's own dollars on that path
    equity: float  # balance after it closed


@dataclass(frozen=True)
class RepricedRun:
    trades: list[RepricedTrade]
    layers: tuple[str, ...]
    initial_capital: float
    #: True when ANY trade's R or risk had to be recovered from rounded stored prices instead of
    #: read off the record — i.e. the run predates `r`/`risk_usd` (2026-08-03). Such a run is
    #: accurate to ~0.02% of final equity rather than exact, and that has to reach the reader.
    derived_basis: bool = False

    @property
    def final_equity(self) -> float:
        return self.trades[-1].equity if self.trades else self.initial_capital

    @property
    def sum_r(self) -> float:
        return sum(t.r for t in self.trades)

    @property
    def total_cost_usd(self) -> float:
        """The FEES — what the layers actually took out of the account, in dollars.

        ⚠ **This is NOT how much smaller the run finished, and the two are not close.** The balance
        impact is `<stored final equity> - final_equity`, and it is larger by however much the fees
        would have compounded into: on the 161-trade reference run these are **$332,371 of fees
        against $18,200,741 of balance**, a factor of 55. Both are real, they answer different
        questions, and a caller showing one under a name that suggests the other has told the reader
        the feature is broken — which is exactly what the lab's Costs pill did until 2026-08-03,
        printing this figure captioned "after compounding". Name it "fees" and derive the balance
        impact separately, or show R, which is the size of the charge and cannot be confused for
        either.
        """
        return sum(t.cost_usd for t in self.trades)

    @property
    def is_exact(self) -> bool:
        """True when every chosen layer reproduces a real replay to the cent.

        Exposed so a caller cannot forget to ask: a UI showing an approximate figure without
        saying so is indistinguishable from one showing an exact figure, which is how a number
        nobody measured comes to be trusted.
        """
        return all(l in EXACT_LAYERS for l in self.layers) and not self.derived_basis

    @property
    def approximate_layers(self) -> tuple[str, ...]:
        return tuple(l for l in self.layers if l not in EXACT_LAYERS)

    @property
    def total_cost_r(self) -> float:
        """What the layers took off, in R.

        **This is the additive unit and dollars are not.** Charging a layer changes the balance,
        which changes every later position's SIZE, so one layer's dollar cost depends on which
        others are also on — three per-layer dollar figures would not sum to the total and the UI
        would look broken while every number in it was right. In R the size cancels (see the module
        docstring), so per-layer R figures add up exactly. Show R per layer, dollars for the total.
        """
        return sum(t.cost_r for t in self.trades)


#: Rollovers on these weekdays book nothing. Saturday because the market is shut outright, and
#: FRIDAY because gold closes at the rollover instant itself — the weekend is carried by the
#: triple-swap weekday (Wednesday on both broker profiles here) rather than by Friday and Saturday
#: nights. Getting this pair wrong is not a rounding error: charging Friday too books 8 nights a
#: week instead of 7 and cost 0.74R over a 161-trade run, ~20x the residual documented below.
_SHUT_WEEKDAYS = frozenset({4, 5})


def rollovers_between(entry_ms: int, exit_ms: int, close_hour_ny: int) -> list[date]:
    """Every daily rollover a position open over `(entry_ms, exit_ms]` was charged for.

    The rollover is the broker's day boundary — the same `close_hour_ny` instant the daily close
    uses. Half-open at the entry end (`roll_ms <= entry_ms` books nothing) because a rollover at or
    before the fill predates the position: the replay's own guard, and the reason a trade opened
    just after the boundary is not charged for the night it did not hold.

    ⚠ **This reproduces what the replay EFFECTIVELY charges, which is not what its code literally
    says.** `mpc_sos_fade._charge_swap` fires on the first BAR at or after a rollover and latches
    once, so any rollover inside a stretch with no bars is silently SUPERSEDED by the last one in
    that stretch. Its own `_last_rollover_before` skips Saturday only; Friday is skipped in practice
    because no bar lands between Friday's close and Sunday's. Mirroring the source line-for-line
    would therefore be the wrong answer — measured at 0.74R too expensive over 161 trades.

    ⚠ **Accurate, not exact, and the gap is HOLIDAY closures.** The same supersede rule applies to
    Christmas, New Year and the like, which no weekday rule can know about — the stored curve
    records trades, never the bar stream, so a re-price cannot see that the market was shut. Over
    the 161-trade 2020→2026 reference run the residual is **0.038R on 129.57R (0.03%), and 0.32% on
    final equity**. That is inside the noise of the spread measurement itself, but it is a real
    difference and callers must label swap as such rather than present it as exact. The exact fix
    is to have the replay RECORD the nights it charged, which is a re-run — see this module's
    CLAUDE.md entry.
    """
    if exit_ms <= entry_ms:
        return []
    start = datetime.fromtimestamp(entry_ms / 1000.0, tz=timezone.utc).astimezone(_NY).date()
    end = datetime.fromtimestamp(exit_ms / 1000.0, tz=timezone.utc).astimezone(_NY).date()
    out: list[date] = []
    day = start - timedelta(days=1)  # a position can span the boundary on its entry day
    while day <= end:
        if day.weekday() not in _SHUT_WEEKDAYS:
            roll_ms = int(datetime.combine(day, time(close_hour_ny), tzinfo=_NY).timestamp() * 1000)
            if entry_ms < roll_ms <= exit_ms:
                out.append(day)
        day += timedelta(days=1)
    return out


def _qty_open_at(row: dict, when_ms: int) -> float:
    """How much of the position was still open at `when_ms`.

    A runner banks in RUNGS, so a trade held over three nights may have carried a full position
    into the first and a third of it into the last. `legs` records each rung's fill time and size,
    which is the only way to know that after the fact — falling back to the entry size would
    overcharge every scale-out, and falling back to the final size would undercharge it.
    """
    qty = float(row.get("size") or 0.0)
    for leg in row.get("legs") or []:
        leg_ms = int(leg.get("ms") or 0)
        if leg_ms and leg_ms <= when_ms:
            qty -= float(leg.get("qty") or 0.0)
    return max(qty, 0.0)


def _cost_r(
    row: dict, *, profile: AccountProfile, layers: Sequence[str], dist: float, close_hour_ny: int
) -> float:
    """What the chosen layers charge this trade, as a fraction of its own 1R.

    Everything here is computed **per unit of size and then divided by the trade's 1R**, so the
    result is invariant to the equity path — see the module docstring. `qty` appears in numerator
    and denominator of every term and cancels; it is kept explicit rather than algebraically
    removed so each line still reads as the charge it mirrors in `execution.py`.
    """
    qty = float(row.get("size") or 0.0)
    risk_usd = dist * qty
    if risk_usd <= 0:
        raise RepriceError(
            f"trade #{row.get('index')} risked nothing measurable "
            f"(size {qty}, stop distance {dist})"
        )
    cost = 0.0

    if "spread" in layers:
        # Half on the entry, half across the exit rungs. The rungs sum to the entry size, so a
        # round turn is exactly one spread on the position — matching `_charge_spread`, which
        # charges `(spread/2) * qty` at `_open_position` and again over `_exit_portion`.
        cost += float(getattr(profile, "spread", 0.0)) * qty

    if "commission" in layers:
        # Per LOT per SIDE. `profile.commission` already converts size to lots, so this cannot
        # drift from the replay the way a local `qty / contract_size` would.
        legs = row.get("legs") or []
        exit_qty = [float(lg.get("qty") or 0.0) for lg in legs] or [qty]
        cost += profile.commission(qty) + sum(profile.commission(q) for q in exit_qty)

    if "swap" in layers and getattr(profile, "swap", None) is not None:
        entry_ms, exit_ms = int(row.get("entry_ms") or 0), int(row.get("exit_ms") or 0)
        if not entry_ms or not exit_ms:
            raise RepriceError(
                f"trade #{row.get('index')} has no entry/exit time, so the nights "
                f"it was held cannot be counted"
            )
        direction = 1 if str(row.get("direction", "")).lower().startswith("l") else -1
        for roll_date in rollovers_between(entry_ms, exit_ms, close_hour_ny):
            roll_ms = int(
                datetime.combine(roll_date, time(close_hour_ny), tzinfo=_NY).timestamp() * 1000
            )
            held = _qty_open_at(row, roll_ms)
            if held > 0:
                # NEGATIVE for a charge, positive for a credit (a short's gold swap is a credit),
                # and `cost` here is "what was taken off", so the sign flips.
                cost -= profile.swap_charge(direction, held, roll_date)

    return cost / risk_usd


def reprice_curve(
    curve: Sequence[dict],
    *,
    profile: AccountProfile,
    layers: Iterable[str],
    initial_capital: float,
    close_hour_ny: int = 17,
) -> RepricedRun:
    """Rebuild a stored equity curve with `layers` charged, exactly.

    `curve` is `equity_curve.json` as `backtest/output.py` writes it. Two things are READ off each
    row rather than assumed, and both matter:

    * **the trade's own R**, from its stored dollars over its own 1R — never re-derived from prices;
    * **the fraction of the balance it risked**, which is NOT the strategy's configured risk %. Six
      of one 161-trade run's trades sized at 5.9%–9.8% instead of 10%, because a resting limit is
      SIZED WHEN IT IS PLACED and the balance can move before it fills. Substituting the config
      value re-sizes those trades and the error compounds through every trade after them. The
      fraction is measured to be identical between a free replay and a charged one, so it is a
      property of the trade, not of the cost layer.

    Raises `RepriceError` on an un-repriceable layer or an incomplete record. It never returns a
    partial curve: half a cost model produces a plausible number about no particular run.
    """
    layers = tuple(dict.fromkeys(layers))
    bad = [l for l in layers if l not in REPRICEABLE_LAYERS]
    if bad:
        raise RepriceError(
            f"{', '.join(bad)} cannot be re-priced from a stored run — it changes which trades "
            f"fill, so it needs a re-run. Re-priceable: {', '.join(REPRICEABLE_LAYERS)}"
        )

    free_equity = equity = float(initial_capital)
    derived = False
    out: list[RepricedTrade] = []
    for i, row in enumerate(curve, start=1):
        entry = float(row.get("entry_price") or 0.0)
        stop = float(row.get("stop_price") or 0.0)
        qty = float(row.get("size") or 0.0)
        if not entry or not stop or qty <= 0:
            raise RepriceError(
                f"trade #{row.get('index', i)} is missing the entry price, stop price or size that "
                f"pricing a cost needs — it predates those fields, so this run needs a re-run"
            )
        dist = abs(entry - stop)
        # Prefer the two numbers the STRATEGY measured over recovering them from stored prices.
        # Recovery is correct but lossy — `profit` is rounded to cents and `stop_price` to 5dp —
        # and the error compounds through the balance re-walk to ~0.02% of final equity. Runs
        # written before these fields (2026-08-03) fall back and are ACCURATE, NOT EXACT; callers
        # must caption that, which is what `used_stored_r` is for.
        stored_r, stored_risk = row.get("r"), row.get("risk_usd")
        exact = isinstance(stored_r, (int, float)) and isinstance(stored_risk, (int, float))
        risk_usd = float(stored_risk) if exact else dist * qty  # the 1R it risked, stored path
        r_before = (
            float(stored_r)
            if isinstance(stored_r, (int, float))
            else float(row.get("profit") or 0.0) / risk_usd
        )
        derived = derived or not exact
        k = risk_usd / free_equity  # ...as a fraction of the balance it had then
        cost_r = (
            _cost_r(row, profile=profile, layers=layers, dist=dist, close_hour_ny=close_hour_ny)
            if layers
            else 0.0
        )
        r = r_before - cost_r

        free_equity += r_before * risk_usd  # walk the stored path in parallel, to keep `k` honest
        risk_now = k * equity  # what the same trade risks on the re-priced path
        equity += r * risk_now
        out.append(
            RepricedTrade(
                index=int(row.get("index", i)),
                r=r,
                r_before=r_before,
                cost_r=cost_r,
                cost_usd=cost_r * risk_now,
                profit=r * risk_now,
                equity=equity,
            )
        )

    return RepricedRun(
        trades=out, layers=layers, initial_capital=float(initial_capital), derived_basis=derived
    )
