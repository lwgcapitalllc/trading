Trace every setting, label and registry in the change to the line that actually CONSUMES it — before calling anything done.

**Why this exists:** this is the repo's number-one defect class, and it has worn four
costumes. Every one shipped green and rendered no error.

- **A label claiming what no code does.** The Run modal collected commission and slippage the
  runner never read. The Optimize modal showed params the grid builder never read. The SSH dot
  named a tunnel it never probed. A table captioned "ranked by profit factor" was sorted newest-first.
- **An empty registry answering confidently.** `BOTS = {}` for six weeks — `/restart` asked you
  to confirm, acted on nothing, and reported SUCCESS. Two "disabled" jobs could not have worked
  if switched on.
- **A declared field nobody assigns.** `RunningJobStatus` declared `python` and the constructor
  never set it, so a Pydantic default told every python backtest its platform was free.
- **A value written and never served.** `exec_secondary` sat on the child run's own row from
  day one; nothing handed it to the reader, so the page could not state it and a rerun did not
  carry it.

---

## Run this over the current diff

### 1. List the claims

Every one of these in the changed code is a claim:

- a string a user reads — label, caption, tooltip, chip, heading, toast
- a config field, form input, or API request field
- a registry, map, or lookup table (`BOTS`, `TASK_NAMES`, `COST_LAYERS`, `_LOWER_IS_BETTER`, …)
- a model field, dataclass field, or column
- a status, badge, or boolean the UI branches on

### 2. For each one, find the consumer

Grep for it. Name the file and line that READS it and does something with it. Not the line
that sets it — the line that acts on it.

Report each as one row:

| Claim | Where it is stated | Where it is consumed | Verdict |
|---|---|---|---|

Verdicts: **wired** (consumer found, does what the label says) · **dead** (no consumer) ·
**mismatched** (consumer exists, does something else) · **unserved** (stored but nothing
hands it to the reader).

### 3. The four questions that catch the costumes

Ask these explicitly and answer them:

1. **Does any lookup here resolve through a map?** If yes, print the map's actual contents at
   runtime, do not read the literal. A map populated elsewhere can be empty.
2. **Does any model declare a field the constructor might not assign?** A default is
   indistinguishable from a measurement. Check the constructor, not the class.
3. **Does any list of magic strings get matched against another system's vocabulary?**
   (provider names, event titles, symbol suffixes, retcodes). Measure how many real values each
   key matches. A key matching nothing fails silently and leaves the gap uncovered — that is how
   the Fed's own inflation gauge got coloured backwards.
4. **Is anything computed and stored that nothing renders or returns?** Grep the field name
   across the whole repo. A measurement summarised down to the number you wanted to compare is
   one you can no longer display.

### 4. If this change compares two runs

Rule 11. List every field that decides what a run is MEASURED on — window, `cost_layers`,
`broker_profile`, `sizing_mode`, per-leg params — and confirm each is carried forward. This
app has broken that rule four times.

### 5. Report

Lead with anything **dead**, **mismatched** or **unserved**. If everything is wired, say so in
one line and name how many claims you checked. Do not pad it.
