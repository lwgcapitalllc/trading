/** Display names for the cost layers a python run can charge. ONE map, read by the run page, the
 *  tuning page and the optimize form — the first two each carried a copy and the third printed the
 *  raw ids. An unknown layer prints its own id rather than vanishing. */
export const COST_LAYER_LABEL: Record<string, string> = {
  spread: 'spread',
  swap: 'overnight swap',
  commission: 'commission',
  slippage: 'slippage',
  bid_ask_fills: 'bid/ask fills',
}
