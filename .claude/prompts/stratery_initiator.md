I'm building an algorithmic trading strategy for LWG Capital. I've attached two files — read them first: the Strategy Framework (how I build: layers, buckets, methodology, rulesets, data fidelity) and my Project State Snapshot (what's built, where things stand). Don't re-derive any of it; build within it.
The non-negotiables, summarized so we're aligned:

Intraday only, flat by session end. Bar-close logic at M5/M15.
Built on gold (XAUUSD) — its wide intraday range is the opportunity, its ~18% spread is the constraint, so targets must be big enough that spread still leaves a real edge. Favor breakout/momentum over small-target scalps. Always check net edge after spread+slippage, never gross.
One instrument, proven first. Get a real edge on gold before asking whether it generalizes to a pool (USDJPY, etc.). The pool is the graduation of a proven single-instrument edge, not the starting point — starting with a pool hides noise as edge.
MT5 first (faster optimization), port winners to NinjaScript later.

How we work: this chat = strategy design and decisions; I paste execution prompts into Claude Code (it has the repo). Build idea-first — pressure-test the hypothesis before any code, build the simplest honest version (entry + basic exit), run once before optimizing, sweep only to see the shape, pick from the robust middle, then stress-test. "Trades every day" is not an edge. Give me brief reasoning, one question at a time when you need input, and a clean Claude Code seed prompt when we're ready to build.
The strategy for this chat:
[STRATEGY — e.g. "Opening Range Breakout on gold: the first 30-min range after a session open; trade a bar-close break in the break direction with a target sized to beat spread, flat by session end."]
Start by pressure-testing the idea with me before any code: does it have a plausible edge on gold specifically, what's the simplest honest version, and what would make me abandon it.