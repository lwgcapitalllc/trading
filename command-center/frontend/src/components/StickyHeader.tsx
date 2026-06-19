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
export function useStickyBanner(threshold = 6) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [scrolled, setScrolled] = useState(false)
  const [height, setHeight] = useState(0)

  useEffect(() => {
    const el = ref.current
    const scroller = el?.closest('main')
    if (!el || !scroller) return
    const onScroll = () => setScrolled(scroller.scrollTop > threshold)
    onScroll()
    scroller.addEventListener('scroll', onScroll, { passive: true })
    const ro = new ResizeObserver(() => setHeight(el.offsetHeight))
    ro.observe(el)
    setHeight(el.offsetHeight)
    return () => {
      scroller.removeEventListener('scroll', onScroll)
      ro.disconnect()
    }
  }, [threshold])

  return { ref, scrolled, height }
}

// Sticky page banner. Pins to the top of the scrolling <main> and lets the page content scroll
// behind it. Full-bleeds across <main>'s 22px padding so the background covers edge-to-edge, and
// drops a subtle shadow once scrolled. `flow-root` contains child margins so the painted background
// always reaches the content boundary (no transparent gap where scrolling rows would peek through).
//
// Children is a render prop receiving `scrolled` — pages condense their banner (shrink the title,
// hide chip/description rows, force any score/grade legend collapsed) while keeping tabs, filters,
// actions and the legend's collapsed key in view.
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
      {children(scrolled)}
    </div>
  )
}
