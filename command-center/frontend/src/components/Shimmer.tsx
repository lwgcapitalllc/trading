/**
 * ONE loading placeholder for the whole app: a block shaped like the content it stands in for,
 * with a sheen sweeping across it, so a page waiting on data reads as *on its way* rather than
 * hung. Aaron, 2026-09-10: *"so that the UX looks clean and it doesn't look like the page is hung
 * or waiting on anything."*
 *
 * The rules this exists to hold are in `frontend/CLAUDE.md` → *Loading states — the shimmer
 * pattern*. The three that decide whether it is used correctly:
 *
 * 🔴 **A shimmer means "still asking". It is NEVER the answer to "could not ask".** A query that
 * has FAILED renders its words (`unknown`, `balance unread`, the error line); a query that
 * answered with nothing renders that. Shimmering over a dead link is the repo's rule 1 in a new
 * costume — a page that looks busy for ever while the thing behind it is down.
 *
 * ⚠ **Only the FIRST read shimmers.** A background refetch with data on hand keeps the data on
 * screen; blanking a 60s poll back to placeholders makes a live page flicker every minute.
 *
 * ⚠ **Same size, same place.** Give it the height and width of the thing that will land there,
 * so nothing on the page moves when the data arrives. A placeholder that jumps is worse than a
 * blank.
 *
 * ⚠ **Every block sweeps on the SAME clock** (one animation, one duration), so blocks that appear
 * together pulse together rather than each flashing on its own — the difference between
 * "loading" and "noise".
 *
 * 🔴 **The sweep is `animate-skeleton-sweep` in `src/index.css`, NEVER Tailwind's `animate-shimmer`.**
 * The config's `shimmer` keyframe SLIDES an element across the whole screen. The first build
 * redefined it there, but a running dev server reads the config only at startup, so every running
 * app kept the slide and drew each block flying over the page — reported off Aaron's screen as
 * *"a thing moving across the screen over the text"*. index.css hot-reloads, and a new name
 * cannot meet a stale definition, so nobody has to remember to restart anything.
 *
 * ⚠ **The block must be visible BETWEEN sweeps.** The first build used the raised-surface colour
 * as its base, which is 6 units off the card behind it — MEASURED invisible on screen, so the page
 * read as blank half the time. The base is the active-surface colour and the sweep is a soft light
 * band laid over it.
 *
 * ⚠ **Theme tokens only**, and it stops for anyone who has asked their OS for reduced motion (the
 * media query sits beside the animation in index.css).
 */
export function Shimmer({
  className = '',
  shape = 'line',
  children,
}: {
  /** Size it here — `h-[13px] w-[80px]` — to match the content it stands in for. */
  className?: string
  /** `line` a word or number · `pill` a chip · `dot` a status dot · `block` a card or section. */
  shape?: 'line' | 'pill' | 'dot' | 'block'
  /** GHOST CONTENT — a sample of what will land here (`$00,000.00`), rendered invisible, so the
   *  block takes that content's exact width, height and TEXT BASELINE. Use it wherever the real
   *  value sits in a row aligned on baseline: an empty block has no baseline, so it sits low and
   *  the row jumps when the value arrives (MEASURED: 3px on the Bots account heading). */
  children?: React.ReactNode
}) {
  const radius =
    shape === 'pill'
      ? 'rounded-pill'
      : shape === 'dot'
        ? 'rounded-full'
        : shape === 'block'
          ? 'rounded-lg'
          : 'rounded-[4px]'
  return (
    <span
      aria-hidden
      data-shimmer=""
      // ⚠ `align-middle` only when EMPTY — with ghost content the block must keep the text's
      // own baseline, which is the whole point of passing it.
      className={`inline-block ${children ? '' : 'align-middle'} shrink-0 ${radius} bg-bg-active
                  bg-no-repeat bg-[length:300%_100%] bg-gradient-to-r from-transparent from-40%
                  via-text-tertiary/20 via-50% to-transparent to-60% animate-skeleton-sweep
                  ${className}`}
    >
      {children && <span className="invisible">{children}</span>}
    </span>
  )
}
