/**
 * A broker cost profile's id in words: `puprime_ecn` → `PU Prime ECN`, `vantage_demo` →
 * `Vantage Demo`.
 *
 * The id is the backend's key into its measured cost profiles and it stays the value every request
 * sends — this changes only what a PAGE prints. Every form, caption and tooltip that names a
 * profile goes through here, so one account never reads two ways on two screens.
 * ⚠ An unknown brand is capitalised rather than refused: a profile added tomorrow still reads as
 * words, just without its brand's own spelling.
 */
const BRANDS: Record<string, string> = { puprime: 'PU Prime', vantage: 'Vantage' }
const WORDS: Record<string, string> = { ecn: 'ECN' }

const cap = (w: string) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w)

export function brokerName(id: string | null | undefined): string {
  if (!id) return ''
  const [brand, ...rest] = id.split('_')
  return [BRANDS[brand] ?? cap(brand), ...rest.map((w) => WORDS[w] ?? cap(w))].join(' ')
}
