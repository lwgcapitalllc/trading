import { ReactNode, useEffect, useRef, useState } from 'react'

// Tracks whether the page's scroll container (the app shell's <main>) has scrolled past a small
// threshold. Used to condense sticky page banners once the user scrolls. The ref must be attached
// to an element rendered inside <main> so we can find the scroller via closest().
export function usePageScrolled(threshold = 6) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const scroller = ref.current?.closest('main')
    if (!scroller) return
    const onScroll = () => setScrolled(scroller.scrollTop > threshold)
    onScroll()
    scroller.addEventListener('scroll', onScroll, { passive: true })
    return () => scroller.removeEventListener('scroll', onScroll)
  }, [threshold])

  return { ref, scrolled }
}

// Variant for the full-bleed detail pages (BacktestDetail / TuningWorkbench) that hand-roll their
// own sticky banner because it coexists with a full-height sticky side panel. Returns `scrolled`
// (to condense the banner) plus the live measured banner `height` so the side panel can offset its
// own sticky `top` and `max-height` below the pinned banner instead of being hidden behind it.
//
// Hysteresis is the point of the two thresholds. Condensing the banner makes it shorter, which both
// shifts the content and shrinks the measured `height`. With a single flip point the scroll
// position lands right on that boundary and the banner oscillates full↔condensed (the "glitchy"
// transition). So we only condense after scrolling clearly past the banner (`condenseAt`) and only
// re-expand once scrolled back near the very top (`expandAt`); the dead zone between them absorbs
// the height change so it can never bounce the state back.
export function useStickyBanner(condenseAt = 72, expandAt = 8) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [scrolled, setScrolled] = useState(false)
  const [height, setHeight] = useState(0)
  const [fullHeight, setFullHeight] = useState(0)

  useEffect(() => {
    const el = ref.current
    const scroller = el?.closest('main')
    if (!el || !scroller) return
    const onScroll = () =>
      setScrolled(prev => (prev ? scroller.scrollTop > expandAt : scroller.scrollTop > condenseAt))
    onScroll()
    scroller.addEventListener('scroll', onScroll, { passive: true })
    const ro = new ResizeObserver(() => setHeight(el.offsetHeight))
    ro.observe(el)
    setHeight(el.offsetHeight)
    return () => {
      scroller.removeEventListener('scroll', onScroll)
      ro.disconnect()
    }
  }, [condenseAt, expandAt])

  // Remember the expanded height so the page can hold the document height constant while condensed.
  // Condensing shaves ~85px off the banner, which shrinks the scrollable area; on a short page that
  // makes the browser clamp scrollTop, which drops below `expandAt` and re-expands — a feedback loop
  // that reads as a flicker. The page absorbs `collapse` as an invisible bottom spacer so total
  // scroll height never changes and the clamp (hence the oscillation) can't happen.
  useEffect(() => {
    if (!scrolled) setFullHeight(height)
  }, [scrolled, height])
  const collapse = scrolled ? Math.max(0, fullHeight - height) : 0

  return { ref, scrolled, height, collapse }
}

// Sticky page banner. Pins to the top of the scrolling <main> and lets the page content scroll
// behind it. Full-bleeds across <main>'s 22px padding so the background covers edge-to-edge, and
// drops a subtle shadow once scrolled. `flow-root` contains child margins so the painted background
// always reaches the content boundary (no transparent gap where scrolling rows would peek through).
//
// Children is a render prop receiving `scrolled`. These list/index pages no longer condense their
// banner — the minimize behaviour earned its keep only on the two full-bleed detail pages
// (BacktestDetail / TuningWorkbench, which hand-roll their own banner via useStickyBanner). Here we
// keep the banner sticky and drop a subtle scroll shadow, but always render the full header by
// passing `false` to the render prop, so no page jumps between a full and a condensed layout.
export default function StickyHeader({
  children,
  threshold,
}: {
  children: (scrolled: boolean) => ReactNode
  threshold?: number
}) {
  const { ref, scrolled } = usePageScrolled(threshold)
  return (
    <div
      ref={ref}
      className={`sticky -top-[22px] z-30 flow-root -mx-[22px] -mt-[22px] px-[22px] pt-[22px] bg-bg-base transition-shadow duration-200 ${
        scrolled ? 'shadow-[0_10px_18px_-14px_rgba(0,0,0,0.8)]' : ''
      }`}
    >
      {children(false)}
    </div>
  )
}
