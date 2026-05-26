# LWG Capital Command Center — Design

Visual reference for the Command Center app. Lets the design be discussed,
versioned, and refined over time — with zero translation gap between design and
code, because the design *is* code.

## Files

| File | What it is |
|---|---|
| `prototype.html` | Interactive clickable prototype. Open in any browser. |
| `tokens.css` | Design tokens — the theme. Colors, type, spacing, radius. |
| `*.png` | Reference screenshots. |
| `README.md` | This file. |

## How to use it

Double-click `prototype.html`. No build step, no account, no install. Click
through the sidebar and the Smart Money sub-tabs — it is genuinely interactive,
including the Config form's live weight-sum validation.

## Theme — "Refined", teal accent

Refined dark: soft 12px corners, calm charcoal surfaces, roomy spacing, crisp
type, monospace for numbers only. Chosen for a tool kept open for hours — the
least fatiguing of the directions reviewed.

- **Accent:** teal `#2dd4bf` — interactive elements, primary charts.
- **Secondary:** gold `#d9a441` — shortlist markers, highlights, an XAUUSD nod.
- **Semantic, reserved:** green = profit / running / pass, red = loss / error /
  fail, amber = warning / yellow-flag. Never decorative.

Everything lives in `tokens.css`. The React app's Tailwind config should be
generated from this file so design and code never drift.

## Screens

Fully built and clickable:
- **App shell** — sidebar, top bar, six routes, VPS/API status.
- **Smart Money** — Pool overview, Rankings, Candidate profile, Disqualified,
  Config.
- **Bots** — live monitoring table, scheduled jobs; control actions shown
  disabled (the deliberate v1 safety split).

Scaffolded (real routes, empty states):
- **Overview, Backtests, Stress Tests, Settings.**

### Smart Money — Pool overview
![Smart Money overview](sm.png)

### Smart Money — Rankings
![Rankings table](rankings.png)

### Smart Money — Candidate profile
![Candidate profile](profile.png)

### Smart Money — Config
Form editor for the pipeline config file. Number inputs for thresholds, sliders
for the five scoring weights.
![Config editor](config.png)

### Smart Money — Config validation
When the scoring weights do not sum to 100, the bar turns red and Save is
disabled. Server-side validation enforces the same rule. Saving writes the file
locally only — it never commits or pushes.
![Config validation](config-validation.png)

### Bots — monitoring
![Bots monitoring](bots.png)

## What the prototype is NOT

- Not pixel-final — proportions, layout, color, hierarchy are intentional; exact
  spacing is refined in the build.
- Not real data — all numbers are representative fixtures.
- Not real charts — funnel, sparklines, donut are CSS/SVG placeholders. The
  React build replaces them with Recharts. The *shape* of each chart (what it
  plots, the 80% line) is the spec.

## How this feeds the build

The build spec defines *what* to build — structure, data contracts, behavior.
This folder defines *how it looks*. Claude Code uses both. Build-order step 3
(frontend skeleton) generates the Tailwind theme directly from `tokens.css`.

Keep this prototype updated as the vision evolves — it is the living design doc.
