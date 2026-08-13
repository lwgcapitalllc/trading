Write a one-page spec BEFORE any code, so we find out early that I understood the wrong thing.

**Use this for anything non-trivial.** Skip it for a typo or a one-line fix.

**Why this exists:** the most expensive mistakes in this repo were not bugs. They were
correct code answering a question nobody asked. The drawdown-zone layer measured a region in
TIME when Aaron meant the red box on his screen — a region in PRICE. Every version of it was
self-consistent, easy to test, and wrong. It took two rounds of complaints to find. Reading a
spec costs a minute.

---

## Do not write code yet

Read whatever you need to understand the request. Then write the spec below and STOP. Wait
for a yes.

## The spec — keep it to one page

**1. What I think you asked for.**
Restate the request in your own words, in plain English. If the user said it in their own
vocabulary ("in the drawdown", "dancing around by this hour"), restate that phrase as a
RULE, and name what kind of thing it is — a region in price, a region in time, a count, a
milestone. That translation is where this goes wrong.

**2. What it changes.**
The files. The behaviour a reader would notice. Whether any stored number moves.

**3. What decides whether it worked.**
Name the measurement, not a feeling. "The chart draws N marks, zero past any exit" beats
"the marks look right". If the answer is a backtest, name the baseline it is compared
against and where that baseline is written down.

**4. What would prove it wrong.**
The result that would make us abandon this. If you cannot name one, the spec is not finished
— you have described an intention, not a test.

**5. The alternative I am NOT doing, and why.**
One sentence. This is where the reader catches you optimising the wrong lever. The time-stop
pass asked for an HOUR; the hour turned out to sit on a 16-hour plateau while the MILESTONE
it was gated on moved the result by a third of the strategy.

**6. What I am assuming.**
Anything you could not check. For each one, say what it would cost to check it — and if that
is one command, go and run it instead of assuming (rule 4). An assumption survives because
no command exists to test it, not because it is safe.

**7. Scope I am NOT touching.**
Especially: does this reach `algos/live/`, a canonical `engines/` module, or any stored
baseline? Say so plainly.

---

## Then stop

End with: *"Say go, or tell me what I got wrong."*

Do not start work on a yes-but — if the reply changes the shape, rewrite the spec first.
