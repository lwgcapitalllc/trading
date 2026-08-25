import { test, expect } from '@playwright/test'
import { balTick, balanceTicks } from '../src/lib/chartAxis'

/**
 * Pure-function checks for the dollar axis. No browser, no backend — they import the module
 * directly, which is why they live here rather than needing the app running.
 *
 * ⚠ Every one was watched RED by mutating the function under it, not by deleting the feature:
 *  - stepping the ticks FROM the starting balance again reddens "round ticks" and "collision";
 *  - dropping the inserted anchor reddens "break-even is always labelled";
 *  - capping the suffix at "k" again reddens "suffix ladder" and the drawdown case.
 */

test('round ticks — a huge run does not carry the opening balance into every label', () => {
  // The reported case: $10,000 opening balance, curve into nine figures.
  const ticks = balanceTicks(10_000, 9_000, 180_000_000)
  expect(ticks).toEqual([10_000, 50_000_000, 100_000_000, 150_000_000])
  expect(ticks.map(balTick)).toEqual(['$10k', '$50M', '$100M', '$150M'])
})

test('break-even is always labelled, even when it is not a round number', () => {
  const ticks = balanceTicks(2_500, 2_000, 9_000)
  expect(ticks).toContain(2_500)
})

test('collision — a round tick beside break-even is dropped, break-even wins', () => {
  const ticks = balanceTicks(3_900, 0, 10_000)
  expect(ticks).toContain(3_900)
  expect(ticks).not.toContain(4_000)
  // and the rest of the ladder is untouched
  expect(ticks).toEqual([0, 2_000, 3_900, 6_000, 8_000, 10_000])
})

test('a zero-anchored axis (drawdown in dollars) is round and ends on $0', () => {
  const ticks = balanceTicks(0, -49_600_000, 0)
  expect(ticks).toEqual([-40_000_000, -30_000_000, -20_000_000, -10_000_000, 0])
  expect(ticks.map(balTick)).toEqual(['-$40M', '-$30M', '-$20M', '-$10M', '$0'])
})

test('suffix ladder — k, M, B, and a signed drawdown', () => {
  expect(balTick(999)).toBe('$999')
  expect(balTick(0)).toBe('$0')
  expect(balTick(10_000)).toBe('$10k')
  expect(balTick(1_500_000)).toBe('$1.5M')
  expect(balTick(150_000_000)).toBe('$150M')
  expect(balTick(2_000_000_000)).toBe('$2B')
  expect(balTick(-4_200)).toBe('-$4.2k')
  // the exact string the bug produced
  expect(balTick(150_010_000)).not.toBe('$150010k')
})
