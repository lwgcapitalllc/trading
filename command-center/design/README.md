# LWG Capital Command Center — Design

Visual reference for the Command Center app. Lets the design be discussed,
versioned, and refined over time — with zero translation gap between design and
code, because the design *is* code.

## Files

| File | What it is |
|---|---|
| `prototype.html` | Interactive clickable prototype. Open in any browser. |
| `README.md` | This file. |

## How to use it

Double-click `prototype.html`. No build step, no account, no install. Click
through the sidebar and the Smart Money sub-tabs — it is genuinely interactive,
including the Config form's live weight-sum validation.

## Theme — "Refined", electric cyan accent

Indigo-black dark: purple-tinted surfaces (`bg-base #080810`, `bg-sunken #0d0d1a`),
soft corners, roomy spacing, crisp type, monospace for numbers only. Chosen for a
tool kept open for hours — the least fatiguing of the directions reviewed.

- **Accent:** electric cyan `#00e5ff` — interactive elements, primary charts.
- **Secondary:** gold `#d9a441` — shortlist markers, highlights, an XAUUSD nod.
- **Semantic, reserved:** green `#00ff7f` = profit / running / pass, red `#ff3b5c` = loss / error /
  fail, amber `#ffb300` = warning / yellow-flag. Never decorative.

Theme is defined in `tailwind.config.js` in the React app. The prototype uses inline styles that reflect the same palette.

## Screens

Fully built:
- **App shell** — sidebar, top bar, six routes, VPS/API status dots, brand wordmark.
- **Overview** — stat row + Bots card + Smart Money card; cards navigate to sub-pages.
- **Smart Money** — Pool overview, Rankings, Candidate profile, Disqualified Log, Config,
  Scanner Terminal, Clear Cache, run lock-down UI.
- **Bots** — live monitoring table, scheduled jobs, control actions (global + per-bot),
  Configure tab (4-card risk cap editor with full deploy pipeline).

Scaffolded (real routes, empty states):
- **Backtests, Stress Tests, Settings.**

## What the prototype is NOT

- Not pixel-final — proportions, layout, color, hierarchy are intentional; exact
  spacing is refined in the build.
- Not real data — all numbers are representative fixtures.
- Not real charts — funnel, sparklines, donut are CSS/SVG placeholders. The
  React build replaces them with Recharts. The *shape* of each chart (what it
  plots, the 80% line) is the spec.

## How this feeds the build

The build spec defines *what* to build — structure, data contracts, behavior.
This folder defines *how it looks*. The prototype shows the target layout for
screens not yet built (Backtests, Stress Tests, Settings).

Keep this prototype updated as the vision evolves — it is the living design doc.
