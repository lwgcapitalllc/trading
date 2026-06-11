// Shared regime visualization constants. Data-driven colors (not Tailwind theme
// tokens) applied via inline style. Mirrors the 5 labels + UNKNOWN from
// regime/classifier.py. Used by BacktestDetail and the tuning workbench.

export const REGIME_COLORS: Record<string, string> = {
  TRENDING:        '#06b6d4',
  TRANSITIONING:   '#8b5cf6',
  RANGING:         '#f59e0b',
  HIGH_VOLATILITY: '#ef4444',
  LOW_VOLATILITY:  '#64748b',
  UNKNOWN:         '#6b7280',
}

export const REGIME_LABEL: Record<string, string> = {
  TRENDING: 'Trending', RANGING: 'Ranging', HIGH_VOLATILITY: 'High Volatility',
  LOW_VOLATILITY: 'Low Volatility', TRANSITIONING: 'Transitioning', UNKNOWN: 'Unknown',
}

export const REGIME_ORDER = ['TRENDING', 'TRANSITIONING', 'RANGING', 'HIGH_VOLATILITY', 'LOW_VOLATILITY']
