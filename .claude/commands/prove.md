Prove the new tests actually catch the bug — by watching them go RED, or by mutation.

**Why this exists:** a green test that has never seen the bug tells you nothing, and this repo
has written at least eight of them. Each one passed against the exact defect it was written for.

- A cancel test whose two obvious assertions stayed true under its own mutation.
- Three browser checks that silently read the LIVE lab, because every route mock keyed on
  `localhost:8000` while the app fetches through the Vite proxy at `/api`.
- `page.locator('svg').first()` — the sidebar logo.
- "A table is absent" — also satisfied while the whole panel is absent.
- A test asserting the death BAR, where the divergence only begins on the next one.
- A concurrency test with 5 writers × 40k rows that finished too fast to ever collide.
- A pixel count on an empty viewport, identical to a layer that does not draw.
- A splice test that passed against the broken code.

---

## The rule

**Every new test is watched RED for the RIGHT REASON, or it is proven by mutation and says so
in its own docstring.** There is no third option.

## Do this

### 1. Sort the new tests into two piles

- **Can go red at HEAD** — it tests behaviour the fix introduced or changed.
- **Cannot go red at HEAD** — it pins a rule that was already correct, or covers a brand-new
  module where there is no "before".

Say which pile each test is in. Do not guess — if unsure, try it.

### 2. For the first pile — watch it red

```
git stash
pytest <the new test file> -x
git stash pop
```

Report the actual failure message for each test. **Read it.** A test that fails for a
different reason than the defect (an import error, a missing fixture, a renamed field) has not
been watched red — it has been watched broken. Those are not the same and only one of them
counts.

⚠ Do not `git stash` if a second session may be working the tree. It has swept up in-flight
edits before. Use `git worktree` or check with the user.

### 3. For the second pile — mutate the code

Break the rule the test claims to pin, in the smallest way that is still a real break. Run the
test. It must fail. Put the code back.

Then answer: **which test caught it?** If a DIFFERENT test caught your mutation than the one
whose docstring claims it, fix the docstring — do not pick a new mutation. It is not enough to
know the suite catches a shortcut; you have to know which test does.

Record the mutation in the test's docstring, so the next reader does not have to rediscover it.

### 4. Check for the vacuous shapes

Before reporting green, ask of each new test:

- **Does the locator match something that was never in question?** (a logo, a header's own
  button, a label that exists three times)
- **Is it asserting an ABSENCE that is also true when the whole container is missing?** Assert
  the container is present first.
- **Does it mock a URL the app never calls?** Check the real fetch path, including proxies.
- **Is the fixture more capable than production?** If the test double answers something the
  real object cannot, you are testing a system you do not have. Fix the FIXTURE, never add a
  `getattr(x, 'field', None)` to production — that permanently erases the difference between
  *no value* and *wrong object passed*.
- **Does the race actually race?** If it finishes too fast to collide, it proves nothing. Scale
  it until it fails against the broken code.
- **Is the viewport empty?** A pixel count on nothing is identical to a layer that does not draw.
- **Does the grep assert it MATCHED something?** A grep test that finds nothing passes forever.

### 5. Report

One line per test: **watched red** (with the failure message) or **proven by mutation** (with
the mutation). Anything you could not prove either way gets called out by name and labelled
**vacuous — kept deliberately** or **needs work**. Never let it pass silently.
