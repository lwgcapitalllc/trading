// Feature flags — one switch per app area that can be hidden without deleting it.
//
// A flag here hides a whole AREA: its nav item, its route and every card that
// summarises it. Anything less leaves a page reachable with no way to reach it,
// or an Overview card pointing at a route that no longer exists.
//
// Flipping one back is the only change needed to restore the area — nothing is
// deleted, and no backend, hook, type or page is touched by turning one off.
// Typed as plain booleans rather than `as const`: with literal types every
// `FEATURES.x && <Card/>` in the app narrows to `false` and TypeScript starts
// reporting the switched-off branch as dead code that must be deleted, which is
// the one thing a flag exists to avoid.
export const FEATURES: Record<'smartMoney', boolean> = {
  // Smart Money — the copy-trading candidate scanner. OFF since 2026-08-04:
  // Aaron is leaning the command center down to what he actually uses, and this
  // is not on the list for a while. The `smart-money/` pipeline, the backend
  // router, the hooks and the pages are all untouched and still work.
  smartMoney: false,
}

export type FeatureKey = keyof typeof FEATURES
