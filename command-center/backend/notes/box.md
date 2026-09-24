# Notes — The trading box, agents and test safety

Tunnel and agent supervision, SSH limits, readiness checks, keeping tests off the live box. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The agent supervisor — and the two indicators that were lying

**Added 2026-08-02. `services/agent_supervisor.py`.** Replaces `main._auto_start_agents`, a one-shot
thread that ran 8 seconds after boot and never again: it worked on a cold start and did nothing for
every case after it, which is why the MT5 agent had to be started by hand after every laptop sleep.
There is no separate startup path now — the first pass is the same pass as every later one, so
"it works on launch" and "it recovers from sleep" cannot diverge.

**Two probes, because `ssh -L` binds the local port ITSELF.** A TCP connect to 127.0.0.1:8766
succeeds for as long as the ssh process holds the forward, whether or not anything is alive at the
far end. That gives two independent signals, and the pair is what tells the failures apart:

| ports bound | agents answering | diagnosis | action |
|---|---|---|---|
| neither | — | the tunnel is dead (laptop slept) | rebuild it |
| both | **neither** | stale tunnel forwarding into nothing, **or** both agents really down | rebuild, then fire both tasks |
| both | one | the tunnel is fine | fire that agent's task only |

🔴 **The old health check answered neither question.** `_check_ssh` ran `ssh forexvps "echo ok"` — a
BRAND NEW connection that has nothing to do with the forwards — and that is what the sidebar's "SSH"
dot reported. So after a sleep the dot sat green beside two red agent dots, which sends you to the
VPS when the problem is on the laptop. `SystemHealth.ssh_tunnel` now measures the forwards;
`vps_reachable` is a new field carrying the old question, and it is what separates a dead tunnel
from a dead network. (The agent-start endpoints already rebuilt the tunnel before firing a schtask —
the workaround was in the code, the indicator just could not say so.)

🔴 **`/health` on the MT5 agent is not a statement about MT5.** It returns `ok` if Flask is alive,
which it is whether or not the terminal is running or logged in — so an MT5_Lab that had dropped its
broker connection showed a green dot and every python run needing uncached bars failed at fetch time
instead. `mt5_agent_client.status()` wraps the agent's `/status` and health now carries
`mt5_connected` / `mt5_server` / `mt5_account`. **`mt5_connected` is `Optional[bool]` and `None`
means the agent could not be asked** — an unanswered question is not a disconnected terminal, and
rendering it as one invents a measurement. The terminal is not probed at all when the agent is down.

**The guard is the point, not the loop.** Every action is skipped when the scope it would disturb
has a job running (`lab_db.get_running_job`), and a **python run counts as MT5 traffic** — the local
runner pulls its bars through port 8766 (`backtest/data/mt5_agent.py`), so restarting the tunnel
mid-fetch kills a run that never touched the VPS directly. `busy_scopes()` returns **all three
scopes** when the DB cannot be read: doing nothing is always safe, and the wrong guess in the other
direction kills a live run.

**One deliberate asymmetry, and it is not an oversight.** An **unbound** port is rebuilt even under a
running job — nothing can connect, so every call that job makes is already failing and rebuilding is
its only route back. A merely **stale** tunnel (ports bound, agents silent) is not, because that
reading has a real false positive: an agent driving a heavy backtest stops answering `/health` while
working perfectly. The NT8 agent does exactly this under pywinauto.

### A merge commit named no tree, and the fix that was BACKED OUT is the useful half (2026-08-21)

`git log --name-only` prints **no file list for a merge commit**, so a merge in range reached the
change list with `areas == []`. That field is what separates *this bot's own rules changed* from
*a shared engine moved underneath it*, and an empty one reads as the second. It surfaced as an
intermittent suite failure rather than a report, because whether it fires depends on a merge
happening to sit inside the 50-commit window — it entered on 2026-08-20 and would have left on
its own.

🔴 **The first fix was `--no-merges`, and it was WRONG in a way nothing in this service could
show.** Excluding merges from the change list made the list disagree with the headline count, so
`version_at` needed the same flag — and that is where it stops being a tidy-up.
**`algos/tools/promote.py` stamps `strategy_version` into a live bot's frozen `deployed.json`
using the same `rev-list --count`.** Changing what counts as a version HERE and not THERE would
have put two different numbers for "the version" into the product, one of them baked onto a
running bot. MEASURED across the live bot's trees: 516 commits, 512 excluding merges.

⚠ **The standing lesson is about where a definition lives.** This module's own docstring already
warned that `trees_for` mirrors `promote.py::repo_trees` and the two must not drift — the
counting RULE is the same kind of shared definition and had no such warning. A change that looks
local because it is one line in one file is not local when another program computes the same
number from the same git history.

**What shipped instead:** the record carries `merge: true`, derived from `%p` in the log format.
Merges stay in the list, so the count and the list still agree; the one row allowed to name no
tree now says why, rather than leaving a reader to infer it from an empty field. The test asserts
a flagged merge names NO tree and that at least one non-merge is in range — so it cannot be
satisfied by flagging everything, and still catches the widened-pathspec bug it was written for.
Watched RED by mutation: forcing the flag false reddens exactly the original assertion.

### The phantom daily loss cap, second half (2026-08-21)

Six FUNDED prop rows carried a daily loss limit their firm does not impose. **It was never typed
in.** An early migration ran `SET daily_loss_cap = max_loss_eod WHERE daily_loss_cap IS NULL`,
turning *this firm has no daily loss limit* into *its limit equals its entire drawdown* on every
row at once. A later migration recognised it — its own comment reads *"None of these firms has a
daily loss limit — clear the phantom cap that fed a false grading rule"* — cleared the six EVAL
rows, and stopped: *"funded/personal untouched"*. The funded half survived three more months.

🔴 **It graded in the direction that costs money.** A cap that does not exist fails days the firm
would have allowed, so a strategy is rejected for breaking a rule it cannot break.

⚠ **The signature is that each wrong value EQUALS that row's `max_loss_eod`.** Apex is the control:
its cap is a real, published number, DIFFERENT from its drawdown, and is deliberately untouched. A
blanket *"prop rows have no daily cap"* would have deleted a true rule.

Verified against each firm's own documentation (readable for the first time — see `CLAUDE.md` →
*The MCP servers*): Tradeify Select **Flex** publishes "Daily Loss Limit | None" across all sizes
— and these rows are the Flex product, so even the Daily policy's $1,000/$1,250 would be the wrong
number; FundedNext Futures Flex publishes "no daily loss limits, and no buffer rules"; LucidFlex
funded publishes **"Optional"**, chosen per account at purchase.

🔴 **That last one forced the fix to be GUARDED, and the guard is the part that could have cost a
real setting.** The clearing statement runs on every startup. Lucid's limit being optional means a
trader may genuinely set one — and an unguarded `SET daily_loss_cap = NULL WHERE id IN (…)` would
wipe it on the next restart, silently. So it keys on the phantom's signature,
`AND daily_loss_cap = max_loss_eod`. A deliberate cap differs from the drawdown and survives.

**Also landed:** both LucidFlex funded rows gained the published 90/10 profit split — the field had
never been populated, which reads as *unknown* rather than *wrong* everywhere downstream. And the
LucidFlex daily-loss TODO open since 2026-05-31 is closed: the eval article says there is no such
limit, the funded article says it is optional. ⚠ The related *60%-of-highest-EOD-profit LucidScale*
claim is on NEITHER article and stays unverified.

⚠ **Both the SEED and a MIGRATION were changed, and one test each — because they fail differently.**
The migration repairs an existing database; the seed is what a fresh clone inserts. 🔴 **The
fresh-build test cannot see a bad seed**: `init_db()` clears the phantom before any test observes
it, so restoring `"daily_loss_cap": 2000` to the seed left the whole file GREEN. MEASURED, not
reasoned. `test_the_seed_itself_carries_no_phantom_cap` therefore reads the seed CONSTANT via
`inspect.getsource` rather than the database. Both watched RED by mutation.

⚠ **The notes update is PARAMETERISED rather than inlined in the migration list**, because the old
and new text both contain apostrophes and quoted citations. Hand-escaping them into a literal SQL
string is not hypothetical: an unescaped quote in that very note took the backend down while it was
being written.

⚠ **`PATCH /rulesets/{id}` refuses prop rows** ("Firm rules — not editable"), which is correct and
was confirmed the hard way. A migration is the only channel for a correction like this.

### An ARMED watchdog stopped reporting itself as STOPPED (2026-08-21)

`schtasks` answers **`Ready`** for a task that is enabled and waiting for its next trigger — the
state a once-a-minute watchdog is in for 59 seconds out of every 60. The snapshot's status chain
handled `Running` and `Disabled` by name and swept **everything else into `STOPPED`**, so
`GET /bots/snapshot` reported the dead-man switch as STOPPED. MEASURED the same day, the box said
`Status: Ready, Scheduled Task State: Enabled, Last Run 5 min ago, Last Result: 0`.

⚠ **Nothing a person looked at was wrong, and that is the part worth being precise about.** Both
`STOPPED` and any other unrecognised value fell to the same gold *"waiting for next trigger"* dot
in `JobDot` and `JobPill`, with the correct tooltip. **The API was the only thing saying it** — and
the API is what the tooling, the tests and anyone with `curl` reads. This was first written down as
*"the Bots page shows the watchdog as STOPPED"*, which was false; *what the page shows* and *what
the endpoint returns* had been read as one claim.

🔴 **The defect was the SHARED VALUE, not the word.** While a healthy armed task and a genuinely odd
one both answered `STOPPED`, no reader could tell them apart — this repo's oldest failure shape,
one step down from *never let "no" and "cannot ask" be the same value*. `Ready` now maps to its own
`ARMED`, and `STOPPED` means something unrecognised and worth a look.

⚠ **Every visual is deliberately UNCHANGED.** `ARMED` falls through the same branch `STOPPED` did,
onto the same gold dot; `allJobsOk` still counts only `RUNNING`, so the tile reads exactly as it did
yesterday. This was a correctness fix to the payload, and rendering it differently is a separate
decision nobody has made.

Pinned by `tests/test_bots_snapshot_parse.py::test_an_armed_watchdog_is_not_reported_as_stopped`,
which asserts all five states map apart AND reads the branch out of the router's own source — so it
goes red if the mapping moves rather than passing against a copy of itself. Watched RED by mutation:
deleting the `Ready` branch fails it on that assertion alone.

**Also corrected that day:** two docstrings on `POST /bots/{bot_name}/stop` still described the
`wmic` hard kill it stopped performing on 2026-08-07. `_kill_bot` asks via `stop.request` and
escalates only for a bot that ignored it — the docstrings said otherwise for two weeks, and a reader
would reasonably have avoided the route in favour of the graceful path it already was.

**`schtasks /run` is not evidence.** It reports SUCCESS for a task Windows refuses to launch (see
`algos/CLAUDE.md` → the stored-password trap), so every fire is followed by a re-probe and the
outcome is logged either way — `nt8-started` or `nt8-fired-but-still-down`. Silence after a fire
used to read as success.

⚠ **It will not rescue an agent whose death left a job marked `running`.** "Dead" and "busy driving
my job and too loaded to answer" are indistinguishable from here, and the wrong guess kills a live
run — so the skip NAMES the deadlock (`nt8-DOWN-with-a-job-running (lock held by nt8 — Stop it or
restart the backend)`) rather than retrying silently forever. Observed live on 2026-08-02: the NT8
agent died on a backtest submission, the run row stayed `running`, and the loop correctly refused to
touch it. Clear the lock and the next pass restarts the agent by itself.

⚠ **The supervisor is DISABLED under pytest** — `CC_DISABLE_SUPERVISOR=1`, set at module scope in
`tests/conftest.py` (a fixture runs too late; `main` is imported at collection). Every endpoint test
builds a `TestClient`, which fires the startup hook, so without the guard a plain `pytest tests/` on
a laptop whose tunnel happened to be down would rebuild the tunnel and fire two scheduled tasks on
the live VPS. Same class of hazard as `tests/test_integration.py`, and refused by default for the
same reason.

🔴 **And a task that CANNOT start is not the same as a task that failed — that gap left the NT8
agent dead for two days (fixed 2026-08-06).** An agent process can be **alive with its socket
dead**: the PID is in the list, nothing is listening on its port. Windows then refuses to launch a
second instance of a task whose first one is still running (`0x800710E0`, *the operator or
administrator has refused the request*), so **every fire is a guaranteed no-op** and the loop
logged `nt8-fired-but-still-down` once a minute, indefinitely, while reporting a real action each
time. **Measured on the live box: PID 13396 alive since 2026-08-04 02:59 UTC with nothing bound to
8765.** The sidebar's Start button fires the same task and was equally unable to recover it — so
this was not a supervisor gap, it was the *only* recovery path in the app being a no-op against
this failure mode. The loop now kills the corpse and re-fires once: `nt8-wedged-process-killed` →
`nt8-restarted-after-kill`, or `nt8-still-down-after-kill` when the second fire is honest about
failing too.

⚠ **`kill_agent_process` is the two-clause `wmic` match and both clauses are load-bearing** — the
same rule `routers/bots.py::_kill_bot` documents, and the reason `taskkill /f /im python.exe` is
banned repo-wide. `name='python.exe'` alone would kill every python process on the box **including
the live trading bot**; the `commandline like '%nt8_agent.py%'` clause alone matches the `cmd.exe`
/ `wmic.exe` hosting the very command being issued, whose own commandline contains the script name
— i.e. the kill terminates the process running it. Verified against the live box on 2026-08-06:
the match resolved to one PID while the trading bot (9620), the MT5 agent (5392) and both Telegram
processes were untouched.

⚠ **wmic's exit code is not evidence, the OUTPUT is.** It prints `Method execution successful` per
matched process and `No Instance(s) Available.` when nothing matched, and neither reaches the exit
code — so `kill_agent_process` returns True only on the success string. **Nothing to kill is a
DIFFERENT diagnosis and is logged as one** (`fired-but-still-down (no process to clear)`): it means
the task genuinely never started, which is the stored-password trap or a missing interactive
session, and a second fire would not fix that either.

⚠ **The kill is safe here and would not be one branch earlier.** It sits after the busy-scope guard
has already returned, so no job is running in that agent's scope. Killing an agent that is merely
*too loaded to answer* is precisely the repair-at-the-wrong-moment this module exists to refuse.

**Tests:** `tests/test_agent_supervisor.py` (25) + `tests/test_system_health.py` (12). Most of them
are about what the supervisor REFUSES to do — the dangerous failure of a supervisor is not a missed
repair, it is a repair at the wrong moment. The six added with the wedged-agent path are that shape
too: three are about what the kill must NOT reach.

### A SLOW agent is not a DEAD agent — `_agent_state` (2026-09-10)

🔴 **An agent that answered late was reported DOWN, and down is a BUTTON.** Each agent's `/health`
gets 5s; anything short of an answer inside it — refused, errored or merely slow — set the dot red,
and a red agent dot says "click to start", which restarts the SSH tunnel and cuts every request in
flight through it, a running backtest's bar fetch included. MEASURED that day, polling each second:
**22/22 answers with nothing else running**, misses while the box was busy with a VPS scan AND
during the Bots page's own 60s fleet refresh — and the agent's terminal link never dropped once.
A timeout is what a busy healthy agent returns too, which is rule 2 exactly.

**The rule**: a REFUSED or errored call is `down` at once — only a dead or broken agent refuses. A
TIMEOUT is `slow` while the agent answered ok within `_AGENT_GRACE_S` (90s, three sidebar polls),
and `down` after it, so a genuinely HUNG agent still goes red, just not on its first late reply. An
agent that ANSWERS "not ok" is down with no grace — that is a measurement, not a gap. Served as
`{nt8,mt5}_agent_state` beside the booleans, which keep meaning "answered ok on this check".

⚠ **Grace, never a longer timeout** — a longer limit makes every check wait longer for a dead agent
too, and still cannot tell a hung agent from a busy one. ⚠ **`socket.timeout` is not a
`TimeoutError` on Python 3.9**, so `_is_timeout` names both and walks the `from exc` chain the two
agent clients wrap every failure in. ⚠ **The detection is proven against a REAL silent socket and a
REAL closed port** through the client's genuine `_get`, loaded as a private copy because
`_no_live_vps` rightly swaps the shared one out — a hand-built exception would prove only a guess
about the shape. Never point that copy at the VPS.

### NinjaTrader switched off on purpose — `services/nt8_switch.py` (2026-09-11)

🔴 **NinjaTrader shut down deliberately and NinjaTrader crashed looked identical**, so the app
complained about the first as though it were the second (Aaron shut it down to save memory). The
intent now lives ON THE BOX: the `NT8Agent` task disabled (or absent) = off. ⚠ **Never a setting
here** — one laptop's opinion about the VPS would disagree with the other clone, and disabling the
task is also what actually stops Windows and the supervisor starting the agent.

- **Asked only by the supervisor's loop** (`nt8_switched_off`, one SSH call per ~2 min); health,
  the NT8 client and the job lock read the remembered answer — no SSH in a request handler.
- ⚠ **Three states and only `True` acts.** `None` (not asked yet) behaves exactly as before;
  any value but `Disabled` is ON, so an unfamiliar word cannot silence a real outage. **A failed
  read KEEPS the last answer** — a crowded box must not flip an off NT8 back to red.
- 🔴 **It reads `Scheduled Task State`, never `Status` — MEASURED on the box:** disabling the task
  with its agent alive left `Status: Running`. Match that label exactly — `Idle Time: Disabled` and
  `Delete Task If Not Rescheduled: Disabled` sit in the same output.
- **Off:** the supervisor neither fires nor kills NT8 and logs nothing; `SystemHealth` carries
  `nt8_switched_off` + `nt8_off_reason`; `POST /system/nt8-agent/start` is 409 (it would rebuild
  the tunnel for nothing); `_locks.ensure_platform_idle` refuses NT8 jobs with a 503 before a run
  row exists; `runner_dispatch._agent_error` leads every failed NT8 call with the reason.
- ⚠ **With NT8 off the supervisor has ONE witness**, so an MT5 outage reads as a stale tunnel and
  rebuilds it first — still skipped under a running job.

Tests: `tests/test_nt8_switch.py` (19) + 14 across the supervisor, health and lock files; 15
mutations run on the final code, 15 killed.

## The box refuses SSH when it is crowded — `services/vps_ssh.py` (2026-09-11)

🔴 **A third of new SSH connections to the trading box were turned away before login.** MEASURED:
3 of 8 single, one-at-a-time connections refused within a second with
`kex_exchange_identification: read: Connection reset by peer`. The box's SSH server runs on its
defaults (`MaxStartups 10:30:100`: past 10 connections still logging in, it drops 30% of new ones,
rising to all at 100). One internet address (106.13.170.216) was holding 19 open, which works out
to ≈37%. Every Bots-page load reads one version per bot, so each load lost a bot or two to a 500
and a toast. **More bots means more reads per load, which is why it surfaced the day two demo
copies were registered.** The bots themselves were never touched.

- **Every ssh call goes through `vps_ssh.run`**: `_ssh`, the credentials write, the terminal scan
  and the alert-thread write here, and the supervisor's three calls. Only the tunnel's `Popen` is
  exempt, because the supervisor rebuilds it every pass. `test_NO_call_to_the_box_bypasses_the_retry`
  holds that. ⚠ It reads SOURCE, so an in-memory mutation cannot reach it (MEASURED: survived); a
  positive control beside it is what proves it can see a bypass.
- ⚠ **Only the refusal BEFORE LOGIN is retried, because it alone proves nothing ran** — the
  identification exchange is the protocol's first step, before any login and any command. That is
  what makes a retry safe for a WRITE. `Connection closed by <host> port 22` on its own (seen the same
  day) can come later in the handshake and is NOT retried. A timeout is never retried.
- ⚠ Waits of 0.5 / 1 / 2 / 3 s, 6.5s at worst; four refusals in a row at 37% is 1.9%.
- 🔴 **A box that could not be asked is a 502 (or 504 for a timeout) from EVERY endpoint** —
  `main.py` handles `VpsUnreachable` and `TimeoutExpired` once. `/bots/{bot}/version` sent a 500
  and a traceback, which says this backend is broken when the box did not answer. An endpoint that
  catches either itself keeps its own answer.
- ⚠ **This is a patch, not a fix. The box's SSH is on its defaults: password logins ON, a
  2-minute login grace, and `MaxStartups 10:30:100`, while an internet address guesses at it.**
  Hardening it (keys only, a short grace, a higher start limit, or a firewall to known addresses)
  needs admin rights and an SSH restart on the live box, and a bad config locks SSH out. So it is
  Aaron's call, and RDP must be confirmed working first.

Tests: `tests/test_vps_ssh.py` (16). 12 mutations were run: 11 were killed in memory, and the 12th
(the source scan) is covered by the positive control.

## The calendar's polarity list was written for the wrong provider

🔴 **Fixed 2026-08-05.** `calendar_service._LOWER_IS_BETTER` decides which way a released `actual`
is coloured — green when a LOWER print is the good one (inflation, unemployment), red otherwise. It
was a flat lowercase-substring list, and **it had been written against Forex Factory's naming while
this tab reads TradingView.**

**MEASURED against the live feed, 811 distinct real titles over ~275 days: six of its eleven keys
matched ZERO of them** — `initial claims`, `continuing claims`, `crude oil inventories`,
`gasoline inventories`, `natural gas storage`, `producer prices`. TradingView calls those
*Initial Jobless Claims*, *EIA Crude Oil Stocks Change*, *EIA Natural Gas Stocks Change* and *PPI*.

⚠ **A dead key costs nothing visible, and that is what makes it dangerous — the damage is what it
leaves UNCOVERED.** The worst case was **`Core PCE Price Index MoM` — HIGH impact, USD, the Fed's
own preferred gauge** — which matched nothing and fell through to the default higher-is-better. So
a 0.4% actual against a 0.3% forecast printed **green "beat" on PCE and red "miss" on CPI**, rows
apart in one table, answering one question. Pinned now by
`test_the_two_inflation_prints_agree_with_each_other`.

**The fix that matters is not the added keys, it is the guard.** `tests/test_calendar.py`
parametrises over `_LOWER_IS_BETTER` and **fails the build on any key that matches nothing** in
`tests/fixtures/tradingview_titles.txt` (the harvested corpus). The list is a CLAIM about one
provider's vocabulary, and a claim nothing checks is this repo's most-repeated defect — here in its
quietest form, because a wrong polarity renders a confident colour rather than an error. ⚠ **If
that test fails, the feed renamed an event: find what it calls it now, do not delete the key.**

⚠ **Keys are matched at a word boundary on the LEFT and openly on the RIGHT.** The left boundary
stops `ppi` matching *Shipping* / *Shopping* (theory rather than a live bug — zero real titles hit
it — but the next key added may not be so lucky). The open right end is what lets one key cover a
family: `inflation` alone covers *Inflation Rate*, *Core Inflation Rate*, *Michigan Inflation
Expectations*, *Food Inflation* and *TD-MI Inflation Gauge*.

⚠ **Every key in the shipped list matches real titles today** — candidates that read well but match
nothing (`unemployment change`, `bankruptcies`, `foreclosure`) were written, measured, and removed
rather than left in as aspiration. That is what keeps the dead-key test meaningful.

Two smaller fixes in the same pass:

- **Upstream failures are classified at one seam** (`_fetch`, blanket `except Exception` →
  `RuntimeError` → the router's 502). The source only converts `HTTPError`/`URLError`, so a non-JSON
  body raised **`json.JSONDecodeError` — a subclass of ValueError — which the router maps to 400**,
  reporting somebody else's outage as a malformed request; and a read timeout raised `TimeoutError`
  (an OSError, not a URLError), which escaped both handlers and became a bare 500. Neither is
  visible to the reader, which is why both survived. **`ValueError` out of this module must mean
  "the caller asked for something impossible", and nothing upstream can be that.**
- **The cache is bounded (64) and locked.** The key is the exact `(from, to, countries)` triple, so
  every week a reader pages to minted an entry nothing ever removed; and two readers landing on one
  uncached week each hit TradingView, since the endpoint runs in FastAPI's threadpool.

✅ `_MAX_SPAN_MS` (60 days) was checked rather than assumed: a 60-day window returns ~1,495 events,
inside the provider's ~2,000 cap, so no window the router accepts can be silently truncated. (105
days returns exactly 2,000 — truncated — which is what the guard is for.)

**And the chip roster is served rather than restated (`GET /calendar/currencies`, same day).** The
page's currency chips were a hardcoded nine sitting beside a comment saying they mirrored the
backend — a second statement of the same claim, which is the disease this whole audit is about, in
its mildest form: **the two are not even the same namespace.** TradingView is QUERIED by bloc code
(`US`, `EU`, `GB`) and ANSWERS with an ISO currency (`USD`, `EUR`, `GBP`), so the frontend could
never have derived it, and a tenth bloc added to `DEFAULT_COUNTRIES` would simply never have got a
chip — a currency present in the data and absent from the filter, which reads as a quiet week.
`calendar_service._COUNTRY_CURRENCY` is the one place the two namespaces meet. ⚠ **An unmapped code
falls back to itself** (a chip matching no event — visibly odd rather than silently absent), and the
build fails first: `test_every_queried_country_maps_to_a_currency` plus
`test_the_roster_is_the_currencies_the_feed_actually_returns`, which checks the roster **against the
811-title corpus in both directions** — no currency in the corpus without a chip, no chip for a
currency the feed never returns. Same guard shape as the dead polarity key, for the same reason.

## Readiness — the checks whose failure mode is silence

`services/readiness.py`, reported once at boot and served at `GET /system/readiness`. The supervisor
above watches things that announce themselves; this covers the opposite class — dependencies whose
absence produces no error anywhere, just a feature that quietly does nothing:

- **An un-backfilled news calendar makes the News & Holiday filter INERT.** The engine reports
  `has_coverage=False` outside the fetched range and tags nothing, so a correctly-wired filter over
  an unbackfilled period is indistinguishable from a broken one. The cache is git-ignored, so a
  fresh clone starts empty and every machine backfills its own. A cache that STOPS partway is the
  nastier case and is reported with the date it ends — recent trades come back *untagged, not
  unaffected*.
- **Missing `algos/credentials.json` makes every Telegram send a no-op.** Deliberate (a notifier
  must never be able to stop a trading loop) and it means a bot can be stopped, restarted or
  deployed with nobody told.

It **reports and does not act** — neither is repairable from here, and neither is worth refusing to
boot over. `_news_calendar()` catches everything: it runs inside the startup hook, and an exception
there would stop the backend booting over a git-ignored cache file.

## A unit test may not reach the VPS, and now it cannot

**2026-08-05.** `tests/conftest.py`'s `client` fixture has said *"all outbound VPS calls
stubbed"* since it was written, and it was not true: `list_strategy_files` was unstubbed on
both agents, so `GET /strategy-files/sync-status` really did call the NT8 agent over the live
SSH tunnel. **The test around it passed whenever the box happened to be up** and 502'd
otherwise — green on the machine with the tunnel open, red on a fresh clone or after a laptop
sleep, and pointing at the wrong thing either way.

`_no_live_vps` (autouse) covers **both channels the backend can reach the box on**, and a
test that legitimately needs one stubs the specific function above it, whose patch wins.

**HTTP** — `_get`/`_post` on both agent clients raise a message naming the fix. Those four
are the whole surface; every agent call funnels through them.

**SSH** — there is no funnel. `routers/bots.py::_ssh` is one, `services/agent_supervisor.py`
shells out three more times on its own (`restart_tunnel`, `schtasks_run`, `vps_reachable`),
and the next module to need the box will shell out again. So the guard sits on
`subprocess.run`/`Popen` themselves and decides **per-argv** — refuse when the program is
`ssh`/`scp`/`sftp`, or when `cfg.SSH_ALIAS` appears anywhere in it. That second clause is not
redundant: `restart_tunnel` opens with `pkill -f "ssh -N.*forexvps"`, whose program is not
ssh, and which would **kill the developer's own tunnel from inside a unit test**. ⚠ Everything
else runs for real — `_git_commit_push` really does shell out to git, and a blanket ban on
`subprocess` would be easier to write and would test nothing about the VPS. ⚠ Tests marked
`integration` are exempt; driving the live box is their whole job.

🔴 **The guard raises `LiveVpsCall(BaseException)`, and that is the load-bearing detail.**
Every probe on this path catches `Exception` and reads the failure as *the box is down* —
`vps_reachable`, `_agent_ok`, `schtasks_run`, and six bare `except Exception: pass` blocks in
`routers/system.py::_build_health`. **An `AssertionError` guard is swallowed by exactly the
code it is meant to police**: the call is still made, the caller reports "unreachable", the
suite stays green. ✅ **Measured rather than argued** — with the vps_reachable stub removed
from `test_system_health.py`, an `Exception`-based guard left **11 of 12 tests passing while
every one of them opened a real ssh connection**; the `BaseException` version fails 6 of them
by name, printing the exact argv. **This is the repo's own probe rule arriving in the test
harness: a check that cannot fail where the failure happens is not a check.**

⚠ **The interlock is autouse, so its failure mode is silence — a guard that never fires and a
guard that was never installed look identical from a green suite.** `tests/test_vps_interlock.py`
(13 tests) drives it directly: the classifier both ways, the four real call sites, that a stub
still wins, and that `LiveVpsCall` is **not** an `Exception` — pinned on its own so a future
tidy-up fails there instead of quietly disarming the whole suite.

🔴 **IT COULD NOT FOLLOW A TEST INTO A PROCESS THE TEST STARTED, AND ONE DID (2026-09-10).** A
fixture lives in one process; the stack-sensitivity pool starts real workers, and each asked the
box's terminal which broker was attached before failing — through `backtest/data/mt5_agent.py`,
a third HTTP door this fixture never covered. So: `_arm_child_guard` loads the repo's
`scripts/testing/vps_guard.py` into every process a test starts (same two doors, same
`BaseException`, registered under one module name so a worker's refusal survives the pickle
back), and `_no_live_vps` stubs that client — `status()` gives the tunnel-down `{}`, a fetch
refuses. **21 tests had passed only because the tunnel happened to be up.** Both pinned in
`test_vps_interlock.py`, the child case from a real child. And `portfolio_runner._build_and_run`
now resolves every leg's strategy BEFORE loading bars, so a bad name fails without reaching out.

⚠ **Three more conftest rules from the same pass**: the schema is built ONCE per worker and COPIED
per test (`_template_db`, sqlite `backup()`, never a file copy — the build leaves write-ahead
files); `lab_progress.json` is per test (`_private_progress_file` — a test was writing the file
the running app reads, which is where the 2026-08-06 audit's stale `"j2"` came from); and the
test client stubs the readiness REPORT, which re-read the 5.5 MB news cache on every client start
(~51 of 332 test-seconds). `GET /system/readiness` calls `check()`, so its own tests still read it.

🔴 **The private database is AUTOUSE since 2026-09-11 (`_private_lab_db`)** — before, only a test
that asked for `fresh_db` got one, and one that forgot wrote the live app's `data/lab.db` (a stack
test left two runs and a stack there). MEASURED by pointing every test at a path nobody had made:
ONE test touched it, reading a `sos_fade` row only this machine's lab held — red on a fresh clone.
⚠ **Its file is `private_lab.db`, never `lab.db`**, so a test building a fresh clone's schema at
`tmp_path / "lab.db"` still starts from nothing. ⚠ This process only; a started worker still sees
the real path, and none touches the database today. Proof: `tests/test_private_lab_db.py`.

**Same pass, the stale roster:** `EXPECTED_CLASS_NAMES` in `tests/test_strategies.py` still
listed `BosStrategy`, three tests deep, after `1946f8b` deleted the unfinished port. That
commit's message says "and its roster line with it" and means `backtest/tools/run_report.py`,
which it correctly called "the ONLY live reference" — this is a SECOND roster, in another
subsystem, and it went unnoticed for a day. ⚠ **A roster stated once per file is still stated
N times across the repo: when you delete a strategy, grep the CLASS NAME, not the package
path.**

🔴 **It went stale a THIRD time on 2026-08-14, and grepping the class name would NOT have caught
this one.** `strategies/python/realign` landed 2026-08-13 (`e87c304`) without its roster line,
and **`RealignStrategy` SUBCLASSES `SosFadeStrategy`** — so a grep for the base class finds
the file and tells you nothing. **Grep for `LAB_STRATEGY`, which is what the scanner actually
reads.** Same three tests red, same single cause.

## Three tests that were red on main, and none of them was wrong about the code (2026-08-14)

Found by the formatting/linting pass, which needed a green baseline before it could gate anything.
Two are the same defect in different files — **a measured number COPIED into a second place** — and
the third is worse than a stale value.

- **`test_python_runner.py` hardcoded a spread of `0.33`.** The owner of that number is
  `backtest/fills.py`, `b03aacd` re-measured PU Prime Standard to **0.32** over 1,893,438 ticks on
  2026-08-10, and this copy had been red since. It now READS `PROFILES["puprime_standard"].spread`
  and asserts the picked broker differs from the default — the half that can still go red for a real
  reason (a `broker_profile` nothing consumes). The identical stale `0.33` was also in
  `services/python_runner.py`'s own docstring and went with it.
- 🔴 **`test_deploy_commit_gate.py` depended on whether the developer happened to have files
  staged.** `_run_hook` ran the real `commit-msg` against the AMBIENT index, and that hook exits 0
  at `[ -z "$STAGED" ] && exit 0` **before** reaching the DOCS parser — so with a clean index the
  "the hook must refuse a short reason" test got exit 0 for a reason unrelated to its subject, and
  with real code staged the sibling test would fail on the PAIRING rule instead. ⚠ **Its docstring
  positively asserted the opposite** (*"it exercises the DOCS-line parser rather than the pairing
  rule"*) — a claim about another program's control flow that nothing checked, which is this
  backend's most-repeated defect wearing test clothes.

  **The probe now builds a SCRATCH index** — `GIT_INDEX_FILE` + `read-tree HEAD` + `update-index
  --force-remove` one instance config — so the staged set is exactly one path, the real index is
  never touched, and **no git object is written** (`--force-remove` stages a deletion; staging a
  modification would need a blob in `.git/objects` for a test that claims to commit nothing).
  ⚠ **The instance config is chosen deliberately**: `needs_proof` does not match it, so the hook
  reaches the DOCS parser rather than stopping one branch earlier on the money-path evidence rule.
  ⚠ **`_seed_probe_index` is shared by the helper AND its non-vacuity test.** The first version gave
  each its own copy of the two git calls, so the guard restated the thing it guarded and could not
  fail when it broke — dropping `--force-remove` now turns both red together, which was run and
  watched.

## Every SSH call rides ONE shared login — `services/vps_ssh.py` (2026-09-24)

Aaron: *"the bots page takes so dam long to load."* Each call to the box opened its own
connection, and the login alone cost **2.2s** (MEASURED, `echo hi`, three runs). The Bots page makes
a dozen calls per load. `vps_ssh.run` now adds ssh's own connection sharing to every COMMAND run:
the first call logs in and keeps the connection for 5 minutes, and each call after it opens a
channel on it — **0.45s** for the same `echo hi`.

- **Past 10 at once, ssh logs in fresh ON ITS OWN.** The box allows 10 channels per connection;
  MEASURED with 14 at once: 10 shared, 4 fell back, all 14 answered. Nothing here handles it.
- **A tunnel (`-N`/`-L`/`-R`/`-D`) is never shared.** A forward made through the shared login would
  live and die with it, not with the `ssh -N` that `start.sh` kills by name.
- **The shared login clears the ssh config's forwards** (`ClearAllForwardings`), or it would sit on
  the tunnel's port 8765 for as long as it lives.
- **A dead link ends it within ~15s** (keep-alives every 5s, three missed), so a laptop sleep does
  not leave later calls hanging on a dead connection.
- **The reachability probe is still honest**: `echo ok` still runs ON THE BOX; only the login is
  reused.

TESTED: `tests/test_vps_ssh.py`, the shared-login block; three mutations run in memory, each red.
