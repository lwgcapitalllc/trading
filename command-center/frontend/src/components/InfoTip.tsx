import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Info } from 'lucide-react'

// Shared "ⓘ" hover tooltip for KPI/metric card labels.
//
// Portalled to <body> with fixed positioning so a card's overflow-hidden (needed for
// collapse/height clipping) can't crop it, and CLAMPED to the viewport on both axes:
// anchoring straight to the icon's own rect put a right-edge card's tooltip (Calmar,
// last column) partly off-screen, and a top-row card's tooltip above the fold.
//
// Width is fixed here rather than left to the content so the clamp math is exact —
// keep TIP_W and the w-[208px] class in sync.
const TIP_W = 208
const MARGIN = 8

export default function InfoTip({ text }: { text: string }) {
  const iconRef = useRef<HTMLSpanElement>(null)
  const tipRef = useRef<HTMLSpanElement>(null)
  const [anchor, setAnchor] = useState<DOMRect | null>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  // Measure the rendered tooltip before painting it: its height depends on the text,
  // so "does it fit above?" can't be answered until it exists.
  useLayoutEffect(() => {
    if (!anchor || !tipRef.current) { setPos(null); return }
    const h = tipRef.current.offsetHeight
    const left = Math.min(Math.max(MARGIN, anchor.left), window.innerWidth - TIP_W - MARGIN)
    const above = anchor.top - MARGIN - h
    const top = above >= MARGIN
      ? above
      : Math.min(anchor.bottom + MARGIN, window.innerHeight - h - MARGIN)
    setPos({ top: Math.max(MARGIN, top), left })
  }, [anchor, text])

  return (
    <span
      ref={iconRef}
      onMouseEnter={() => setAnchor(iconRef.current?.getBoundingClientRect() ?? null)}
      onMouseLeave={() => setAnchor(null)}
      className="relative inline-flex items-center ml-[5px] cursor-help flex-shrink-0"
    >
      <Info size={9} className="text-text-tertiary/50 hover:text-accent transition-colors" />
      {anchor && createPortal(
        <span
          ref={tipRef}
          style={{
            position: 'fixed',
            top: pos?.top ?? 0,
            left: pos?.left ?? 0,
            visibility: pos ? 'visible' : 'hidden',
          }}
          className="z-[100] w-[208px] rounded-lg bg-bg-base border border-border-default px-3 py-2.5 text-[11px] text-text-secondary shadow-2xl pointer-events-none leading-relaxed normal-case tracking-normal font-normal"
        >
          {text}
        </span>,
        document.body,
      )}
    </span>
  )
}
