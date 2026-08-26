/**
 * The two decisions the trade overlay used to make from an ASSUMPTION instead of from the trade.
 *
 * Pure arithmetic, no imports, no klinecharts — which is the point. Everything else in
 * `overlays.ts` is painted into a canvas and has no element to assert on, so the only checks that
 * layer can carry are pixel measurements through a live browser. These two rules are numeric, so
 * they live where `scripts/check_trade_geometry.mjs` can drive them directly and
 * `scripts/run_all_tests.sh` can run that without the app up.
 */

/** +1 on a long, −1 on a short. Favourable ⇔ `(price − entry) * sign > 0`. */
export type Sign = 1 | -1

/** A float-equality guard, NOT a "near enough" band — two prices that name the same level come
 *  from the same field and either match exactly or belong to different things. */
const EPS = 1e-9

/** Did the STOP close this trade? Read off the PRICES, never the exit reason: the reason string
 *  is the BRACKET that closed, so a trade that lost its full risk at the stop routinely reports
 *  the name of a profit target. */
export function stoppedOut(
  exitPrice: number | undefined,
  stopPrice: number | undefined,
  sign: Sign
): boolean {
  if (typeof exitPrice !== 'number' || typeof stopPrice !== 'number') return false
  return (exitPrice - stopPrice) * sign <= EPS
}

/**
 * How far the adverse (red) band reaches — the WORST PRICE THIS TRADE ACTUALLY TRADED, and the
 * stop only when the stop actually filled. `null` when it never went against its entry.
 *
 * 🔴 It used to run entry→STOP for any trade whose net P&L was negative, without asking where
 * price went. The premise was "a loser lost at its stop", and it is false for the commonest
 * small loser this strategy makes: one that comes off at its staged breakeven stop a few ticks
 * ABOVE the entry and goes negative on COSTS alone. MEASURED on the long of 2020-10-13 (entry
 * 1901.71, exit 1902.01, stop 1879.72): price bottomed at 1882.36, and the chart painted 2.64
 * further to the stop — a level it never traded — so the band contradicted the `DD` marker
 * printed inside it. Aaron's call, 2026-08-25.
 *
 * ⚠ The floor is clamped to the stop even when the stop did NOT close the trade. A recorded worst
 * price beyond an unhit stop is a defect, not a measurement — the live strategy widened the
 * hold's worst price with the whole of the closing bar before working out that bar's exits — and
 * nothing backfills a stored run. Clamping is what makes every run stored before that fix read
 * right.
 */
export function adverseFloor(o: {
  entryPrice: number
  stopPrice?: number
  maePrice?: number
  exitPrice?: number
  sign: Sign
}): number | null {
  const { entryPrice, stopPrice, maePrice, exitPrice, sign } = o
  if (typeof entryPrice !== 'number') return null
  const adverse = (p: number) => (p - entryPrice) * sign < -EPS
  // The stop took it, so the stop IS the drawdown — nothing adverse is drawn beyond it.
  if (stoppedOut(exitPrice, stopPrice, sign)) {
    return typeof stopPrice === 'number' && adverse(stopPrice) ? stopPrice : null
  }
  if (typeof maePrice !== 'number') return null
  const floor =
    typeof stopPrice === 'number' && (maePrice - stopPrice) * sign < -EPS ? stopPrice : maePrice
  return adverse(floor) ? floor : null
}

/**
 * What to do about the EXIT marker. Every trade must show where it came off — that is a fact about
 * the trade, not a reward for making money (Aaron's call, 2026-08-25) — but the honest way to show
 * it is the trade's FILLS.
 *
 * 🔴 `exitPrice` IS NOT A FILL. It is the size-weighted AVERAGE of the trade's fills. On a
 * one-fill exit that average IS the fill and drawing it is right; on a two-fill exit it is a price
 * nothing ever traded at, sitting between two lines that are already drawn. MEASURED on the
 * re-entry short of 2020-11-04 (run `6b18811e25d5`): half came off at 1895.40058, the runner at
 * 1895.72498, and the average 1895.56278 was drawn as a third line between them — 32 cents of
 * chart holding three chips, which pushed the two REAL ones off their own levels.
 *
 * 🔴 It used to draw only when the exit BANKED, which is the opposite failure. A rung had to clear
 * a tenth of the entry risk to reach the chart at all, so a trade that came off at its staged
 * breakeven stop had no exit anywhere on it. **That is fixed where it belongs — `chart_spec.py`
 * now emits every fill and flags which banked — so this function's job shrank to the one case the
 * fills cannot cover.**
 *
 *   `'leg'`  — the trade's fills are known and drawn. The average is not one of them: skip it.
 *   `'stop'` — no fills recorded and the exit is at the stop; the caller renames that chip
 *              `SL / Exit` rather than stacking a second red line on the same pixel row.
 *   `'draw'` — no fills recorded, so the average is the only price there is. Draw it.
 *   `'none'` — the trade carries no exit price.
 */
export function exitMarker(o: {
  exitPrice?: number
  legPrices: number[]
  stopPrice?: number
}): 'leg' | 'stop' | 'draw' | 'none' {
  const { exitPrice, legPrices, stopPrice } = o
  if (typeof exitPrice !== 'number') return 'none'
  if (legPrices.length) return 'leg'
  if (typeof stopPrice === 'number' && Math.abs(stopPrice - exitPrice) < EPS) return 'stop'
  return 'draw'
}

/**
 * Which way the exit closed against its own entry — PRICE only, never P&L.
 *
 * ⚠ The two disagree, and that disagreement is the whole reason this trade type was invisible: a
 * breakeven-stop exit sits favourably above a long's entry and still nets a loss once costs come
 * out. Colouring the line by P&L would paint a level price cleared as if price had not.
 */
export function exitSide(
  entryPrice: number,
  exitPrice: number,
  sign: Sign
): 'favourable' | 'adverse' | 'flat' {
  const d = (exitPrice - entryPrice) * sign
  if (d > EPS) return 'favourable'
  if (d < -EPS) return 'adverse'
  return 'flat'
}
