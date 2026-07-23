import { toast } from 'sonner'

// Copy a Recharts (SVG) chart to the clipboard as a PNG, so it can be pasted straight into a
// message. The klinecharts price panel has its own snapshot path (it renders a canvas, not SVG —
// see ChartPanel/index.tsx `copyChartImage`); this is the equivalent for every Recharts chart.
//
// An SVG has no background of its own, so it would paste as a black-on-black smear — we paint the
// page background in first, then rasterise at 2× for a crisp image.
export async function copyChartAsPng(container: HTMLElement | null): Promise<boolean> {
  const svg = container?.querySelector('svg')
  if (!svg) {
    toast.error('No chart to copy')
    return false
  }
  try {
    const { width, height } = svg.getBoundingClientRect()
    const clone = svg.cloneNode(true) as SVGSVGElement
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    clone.setAttribute('width', String(width))
    clone.setAttribute('height', String(height))
    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
    bg.setAttribute('width', '100%')
    bg.setAttribute('height', '100%')
    bg.setAttribute('fill', getComputedStyle(document.body).backgroundColor || '#0b0f1a')
    clone.insertBefore(bg, clone.firstChild)

    const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(clone))}`
    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('render failed'))
      img.src = url
    })

    const scale = 2
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('no canvas context')
    ctx.scale(scale, scale)
    ctx.drawImage(img, 0, 0)

    const blob = await new Promise<Blob | null>(res => canvas.toBlob(res, 'image/png'))
    if (!blob) throw new Error('encode failed')

    const canClipboard = typeof ClipboardItem !== 'undefined' && !!navigator.clipboard?.write
    if (canClipboard) {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      toast.success('Chart copied — paste it into the chat')
      return true
    }
    // Clipboard image writes blocked (or unsupported) — hand over a file instead of failing.
    const href = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = href
    a.download = 'chart.png'
    a.click()
    URL.revokeObjectURL(href)
    toast.message('Clipboard blocked — image downloaded instead')
    return true
  } catch {
    toast.error('Could not copy the chart')
    return false
  }
}
