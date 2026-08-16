/**
 * Native form-control styling that the theme cannot reach from a class on the element itself.
 *
 * There is exactly one entry today and it earns a file rather than a home in whichever component
 * needed it first: three separate trees render `<input type="date">` — `PeriodPicker`,
 * `BacktestDetail`'s period filter and `ChartPanel`'s Go-to-date — and a constant living in any one
 * of them either goes uncopied (which is what happened) or drags a cross-tree import behind it
 * (`ChartPanel` is strategy-agnostic and must not start importing page furniture).
 */

/**
 * Makes `<input type="date">`'s own calendar button VISIBLE on a dark surface.
 *
 * 🔴 Chrome ships the picker indicator as a near-black SVG. On this theme that is an invisible
 * glyph on an invisible button, so the input reads as plain text and there is no discoverable way
 * to a calendar at all. Reported off the screen (2026-08-16, on the period filter's popover):
 * *"can't see the calendar icon."*
 *
 * ⚠ **Every `type="date"` in the app must carry this.** It lived privately inside `PeriodPicker`
 * from the day that component was written, and the two date inputs added elsewhere since simply did
 * not have it — the shape this repo keeps meeting, where a fix lives where it was first needed
 * rather than where the rule belongs.
 *
 * ⚠ `invert`, never a colour. The indicator is a raster the browser owns, so inverting it follows
 * whatever a future theme swap does to the surface under it; a hardcoded white would go invisible
 * again the first time somebody builds a light theme.
 *
 * ⚠ It is a `::-webkit-` pseudo-element, so it is Chrome/Safari only. Firefox draws its own
 * indicator in the platform's colours and needs nothing — this is additive, and its absence there
 * is not a bug to chase.
 */
export const DATE_INDICATOR_CLS =
  '[&::-webkit-calendar-picker-indicator]:invert [&::-webkit-calendar-picker-indicator]:opacity-50 [&::-webkit-calendar-picker-indicator]:cursor-pointer'
