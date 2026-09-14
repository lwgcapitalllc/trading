# Notes — Claude's own configuration — commands, hooks and guards

The slash commands, the editor guard that watches doc growth and sensitive paths, the bypass refusal, and the skills shipped with the repo. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### .claude/
Repo-shipped Claude configuration — available to every clone, unlike `~/.claude/` which is per machine. Three folders.

**`commands/` — the slash commands.** Two kinds, and the split is the point. The **audit** commands look BACKWARDS at code already written: `/audit-engines`, `/audit-strategy`, `/doc-audit`, `/dead-code-audit`, `/prop-firm-rules-audit`, `/quant-review`, `/regenerate-snapshots`, `/session-start`. The **build-time** commands (added 2026-08-12) run BEFORE and DURING the work, and each one exists because a specific class of defect kept reaching the audits: `/spec` (write down what I think you asked for, before code — catches right-code-wrong-question), `/wire-check` (trace every label, config field and registry to the line that consumes it), `/prove` (watch every new test go red, or kill it by mutation), `/measure` (no number without the command that produced it), `/live-safety` (the 22-question checklist before anything touches the live path), `/port` (drive a strategy through `docs/STRATEGY_WORKFLOW.md` and refuse to skip the parity gate), `/run-audit` (take a run id and answer both halves — is this run TRUE, and was this configuration WORTH IT — recomputing every number from the trade list and measuring the feature against a matched control rather than against a run with a different basis). ⚠ **They are prompts, not enforcement** — nothing makes anyone type them. The two things that ARE enforced are the commit hook and the editor guard below, and the commands exist so that when the hook asks "what did you check", there is a repeatable answer.

**`hooks/guard_sensitive_paths.py` — the editor guard.** A `PreToolUse` hook on Edit/Write. A `deployed/` snapshot **asks first**, because a live bot imports from it and an edit there changes what a running bot trades immediately, with no promote and no restart. `engines/`, `strategies/`, `algos/live/`, `algos/shared/`, `backtest/` and `*.pine` attach a one-paragraph reminder of the rule that path keeps breaking, at the moment of the edit rather than 40,000 words away. **Since 2026-08-12 it also watches the CLAUDE.md files themselves** — a file over **40 KB** gets a reminder to move the story out and keep the rule. 🔴 **Since 2026-08-13 it fires on GROWTH, not on size, and that correction matters more than the feature did.** Warning on size alone meant **ten files tripped it on every single edit**, including the ones that are legitimately large — `ChartPanel/CLAUDE.md` is 122 KB and only ~3% of it is movable narrative; the rest is dense engineering reference with measured reasons attached. **A guard that fires on work it should not be criticising is a guard people learn to dismiss, and a dismissed guard is worth LESS than none, because the next reader takes silence for checked.** So a trim now passes in silence and only an edit that ADDS bytes to an already-oversized file has to justify itself. The delta is computed from the tool call itself (`content` for Write, `old_string`/`new_string` for Edit, multiplied out when `replace_all` is set). 🔴 **The reason it lives HERE and not in the commit hook is the whole point: a commit-time warning arrives when the work is already finished, and nobody stops to refactor a doc at that moment — you type the message and move on.** The edit is when the file is open and the context is loaded, so it is the only moment the reminder can change what happens. ⚠ **The 40 KB is MEASURED, not picked** — all 28 files fall into two clumps with an empty gap between them (everything sane lands at 27 KB or below; the next file up is 63 KB), so 40 KB is the middle of that gap and no file is close enough for a paragraph to flip it. At the ceiling's landing, **11 files tripped and 17 passed.** ⚠ **It FAILS OPEN by design** — any error allows the edit, because a broken guard must never stop the work. ⚠ **Which also means its silence proves nothing** — and now that a trim is DELIBERATELY silent, silence is its most common answer. Run **`python3 .claude/hooks/check_guard.py`** — **twenty-one** cases since 2026-08-21, and it is **step 6 of `scripts/run_all_tests.sh`**, because a check nobody runs is not a check. Each asserts a specific verdict, so a guard that always warned and a guard that never warned both fail it. Watched RED by mutation, and **the map in that file's docstring was RUN rather than reasoned** — three entries first written from inspection were wrong, each claiming a mutation was more surgical than it is.

🔴 **STEP 6 WENT RED ON `main` ON 2026-09-04 AND THE GUARD WAS WORKING PERFECTLY — THE CASE HAD
AN EXPIRY DATE NOBODY WROTE DOWN.** One case wrote a hardcoded **400,000 bytes** over
`command-center/backend/CLAUDE.md` to prove the guard warns on growth. That doc reached **400,570
bytes**, so the "grow" quietly became a SHRINK, the guard correctly said nothing, and the failure
pointed at the guard. The comment naming the fixture still said *282 KB*. **A case whose premise is
a typed number about a file that GROWS is a case that rots on a schedule**, and it is the same
shape as the case pinned to a path that moved on 2026-09-02 — a fixture describing a repo you no
longer have. ✅ Every size there is now DERIVED from the file (`_size(BIG) + 50_000`), and two
PREMISE assertions refuse to run the file at all if the big fixture stops being oversized or the
small one stops being under — because trimming that doc would otherwise leave the oversized cases
passing while testing the quiet path. Both watched red. ✅ **The premise fired for real on 2026-09-13, when the docs were split, and the big fixture is now a GENERATED temp file** — a real doc as a fixture ties the guard's test to that doc never being fixed.

🔴 **The guard had a HOLE for as long as it existed, and it was found by the guard firing on
NOTHING while two files grew (2026-08-21).** The check above reads its byte delta out of the
TOOL CALL, so it can only see an edit made through Edit or Write. An edit made through Bash is
invisible to it — a heredoc, an in-place rewrite, a three-line script. On 2026-08-21
`algos/CLAUDE.md` grew 103,804 → 106,667 bytes and `strategies/python/loss_recovery/CLAUDE.md`
grew to 41,391, both already over the ceiling, and the guard said nothing, because neither edit
went through a tool it watches. **This is the worst failure shape a guard has, and this file
already names it: a dismissed guard is worth LESS than none, because the next reader takes
silence for checked. Here the silence was not even a decision — the guard never ran.**

✅ **Closed by a second hook on `PostToolUse` (matcher `*`, same script) that measures the FILE,
not the tool call**: current bytes on disk against `git cat-file -s HEAD:<path>`, for every
CLAUDE.md git knows about. ⚠ **It was deliberately NOT fixed by pattern-matching Bash for
redirections, in-place edits or python one-liners.** That is a deny-list against an infinite
space of ways to write a file: it is wrong quietly, and it goes stale the first time somebody
reaches for a tool it has not heard of — which is exactly how the browser guard's deny-list is
already known to be its weak half. **A measurement of the file cannot be fooled by HOW the edit
was made, and that is the entire point.** First live confirmation: it fired on this very
paragraph, which grew an already-oversized file.

⚠ **It is a BACKSTOP, never a replacement, and the older half stays exactly as it was.** That
one fires BEFORE the edit, while the file is open and the context is loaded, and the paragraph
above says plainly that the timing is the only reason it changes what happens. This one arrives
after the fact, which is worth less — but it is the only thing that can see what the other is
blind to.

⚠ **It says each file ONCE per session** (a marker under the temp dir, keyed on the session).
It runs after *every* tool call, so the naive version repeats itself forty times before the file
is committed, which is nagging with extra steps — the same mistake the growth rule fixed in
2026-08-13. The first time is the one that can change anything. ⚠ **A trim still passes in
silence**: growth against HEAD, never size alone. ⚠ **It FAILS OPEN in every direction** — not
a git repo, git missing, no HEAD, a timeout, an unwritable marker: all of them allow the action
with nothing printed.

⚠ **A CLAUDE.md with no HEAD version counts as 0 bytes, so a brand-new one born over the ceiling
WARNS — that is a decision, not a fallthrough.** A doc costs the next reader the same context
whether it has been bloated for months or arrived that way this morning, and "it is new" is not
a reason for it to land at 50 KB unremarked. The alternative — stay quiet until its first commit
— puts the warning at the one moment this repo has already measured to be useless, when the work
is finished and nobody stops to refactor a doc.

⚠ **It costs ~0.16s per tool call** — MEASURED on an idle machine, three passes of 20 runs over 33 CLAUDE.md files, of which ~0.06s is python interpreter startup that any hook here pays —
one `rev-parse`, one `ls-files`, and ONE batched `cat-file --batch-check` for the whole set
rather than one call per file. The per-file fan-out is the shape that made a version endpoint
slower every time either of us pushed, and it was avoided here on purpose.

🔴 **THE AUDIT THAT FOLLOWED FOUND A SECOND HOLE, BIGGER THAN THE FIRST (2026-08-21).** Nothing
ever "got around" this check — it has never blocked anything, it only prints. The real finding
is when it speaks. **It reads the file's size BEFORE the edit, so on the edit that takes a doc
OVER the ceiling the doc is still under it, and the check says nothing. It only ever starts
complaining about files that are already a problem — the moment it can do least good.** MEASURED
over the full history of all 33 docs: **every one of the 11 currently oversized files crossed
from below, and not one of them was warned at the crossing.** Two of those crossings happened
with the guard live and silent — `strategies/tradingview/CLAUDE.md` (then
`indicators/strategies/CLAUDE.md`) went 38,766 → 69,605 bytes in
one commit on 2026-08-16, and `strategies/python/loss_recovery/CLAUDE.md` went 26,745 → 41,391
on 2026-08-21. ✅ **The after-the-fact check closes this too, because it measures the file once
the edit has landed** — proven on a fixture that crosses in one go, and it is a case in
`check_guard.py`. ✅ **And the before-the-edit half now judges the size the file is ABOUT TO BE rather than the
size it is** (Aaron's call, 2026-08-21), so the crossing is caught at the one moment it can
still be prevented. It costs no extra nagging — a doc well under the ceiling has to be handed
an edit big enough to cross before it hears anything. ⚠ **A file that does not exist yet counts
as 0 bytes rather than being skipped**, so creating an oversized CLAUDE.md warns too; that
deliberately matches what the after-the-fact half does with a doc that has no committed
version, because the two halves disagreeing about what a new file means is how somebody ends
up trusting the quieter one.

⚠ **THE 40 KB'S ORIGINAL JUSTIFICATION HAS ERODED, and that is worth saying rather than leaving
the paragraph above to read as still-true.** The number was picked as the middle of an empty gap
**36,050 bytes wide** (largest sane file 27,116; next one up 63,166). Re-measured 2026-08-21:
that gap is now **7,823 bytes** — `indicators/engines/CLAUDE.md` sits at 33,568 just under, and
`strategies/python/loss_recovery/CLAUDE.md` at 41,391 just over. **So "no file is close enough
for a paragraph to flip it either way" is no longer true**, and 40 KB is now a judgement rather
than a measurement. ✅ **KEPT at 40 KB anyway (Aaron's call, 2026-08-21).** ⚠ **Chasing the
distribution upward is how a limit stops meaning anything** — the honest reading is that the
repo grew into the number, not that the number is wrong. **Re-measure this gap before ever
moving it, and record the new width here; do not move it because a file is sitting near it.**

⚠ **The direction of travel is good and the audit should say so.** Since the ceiling landed,
seven of the eleven oversized docs have SHRUNK, several by a lot — `command-center/backend`
−83 KB, `command-center/frontend` −75 KB, `indicators` −166 KB, `command-center` −117 KB, and
`strategies/python/sos_fade` −102 KB (307 → 205 KB, 2026-08-27). The reminder is working on
the files it can reach.


⚠ **MEASURED there, and it bounds what a doc migration can ever achieve: moving EVERY explanation
out — prose, tables and run numbers — still left 205 KB, because ~70% of that file is rules WITH
their justification, which must stay next to the code. Past that point, reaching the ceiling is a
decision to compress or DROP rules, not a migration. Say which is being asked for.**

🔴 **A subsystem fragment is ANCHORED at the repo root (2026-08-13, `subsystem_matches`)** — a fragment starting with `/` matches only paths actually under that top-level dir, while `.pine` is about what the file IS and still matches anywhere. It was a plain substring test until `indicators/engines/` was created and a Pine file was about to be told it is a canonical Python engine. **The standing lesson: a directory RENAME can silently re-aim a guard** — nothing fails and no test goes red; the only symptom is correct-looking advice about the wrong file. Story: `HISTORY.md`.

🔴 **IT HAPPENED AGAIN ON 2026-09-02, IN THE OPPOSITE DIRECTION, AND THE CHECK THAT WAS SUPPOSED TO CATCH IT STAYED GREEN.** The Pine `strategy()` files moved to `strategies/tradingview/`, so for the first time they sit under the top-level `strategies/` and collect its reminder as well as the Pine one. `check_guard.py` had a case asserting they do NOT — and it passed anyway, because the case names a path as a STRING and nothing asks whether that path still exists. **A case pinned to a path that has been moved out from under it is not testing anything; it is describing a repo you no longer have, in green.** It went red the moment it was pointed at the real path.

✅ **The second reminder was KEPT rather than special-cased away** — a Pine strategy is half of a parity gate, so *"if a default moves, every documented baseline needs pinning or re-measuring"* is true of it. Excluding the new folder from the fragment would have preserved 2026-08-13's behaviour exactly and left a special case behind, and a special case is the half that goes stale. ⚠ **The generalisation is worth more than either decision: a guard case that hardcodes a path needs re-aiming by hand whenever that path moves, and nothing will tell you.**

⚠ **The bloat it is guarding against was measured the same day and the root file was the worst case: 36 KB of its 69 KB — 53% — was `## System Summaries`, a paragraph per subsystem restating what that subsystem's own CLAUDE.md already said.** That section loads on EVERY session whether or not you go near the code it describes. **The duplication is also what makes the drift**: the 2026-08-12 doc audit found three files claiming there were no live bots, and the subsystem file was the one that was right. Hence the standing rule the guard's message repeats — **a fact lives in exactly ONE CLAUDE.md, the one next to the code. Parents ROUTE, children EXPLAIN.**

🔴 **`hooks/block_hook_bypass.py` — the bypass refusal (2026-09-07), and it exists because a git hook CANNOT enforce this one.** *Never bypass the commit hook* has been a rule here since 2026-08-04 and nothing enforced it: the flag tells git to skip its hooks, so the refusal that would object never runs — unreachable by construction. This one is a `PreToolUse` hook on Bash and refuses BEFORE git is invoked at all. It catches the long flag on commit, push, merge, cherry-pick, rebase and am; the short form, which need not lead its cluster (`-an` is that flag plus another, and reads as a typo rather than a decision); and pointing git at a different hooks folder for one command, which runs nothing while looking innocent in the shell history. ⚠ **The repo's own documented pre-push skip is deliberately ALLOWED** — it prints a loud line and has no silent form, and the objection is to skipping WITHOUT A TRACE, never to skipping. ⚠ **It FAILS OPEN and says so out loud when it does**: this one BLOCKS rather than advises, so a silent failure would make *checked* and *never ran* look identical, which is the mistake already paid for twice here. ⚠ **The wrapper in `settings.json` must NOT end `|| true`** like the two advisory hooks do — that swallows the refusal and leaves a hook that reads as protection while providing none. 🔴 **Its mutation map carries the sharpest lesson in this section, and it is one past step 11's: SIX of eleven entries written from inspection were wrong, and one mutation survived the entire file in GREEN.** Two defences sat over the same rule — the shell tokenizer makes a quoted commit message one word, so the case meant to cover the value-swallowing branch passed with that branch deleted. **Two defences over one rule can leave one of them uncovered while everything stays green, and only running the mutation shows which.** Ported from `block-no-verify.js` in `github.com/affaan-m/ecc` (MIT), rewritten on the standard library's shell tokenizer — Python because the other hooks here are, and a hook is a bad place to acquire a second runtime. Proof: **`python3 .claude/hooks/check_no_verify.py`**, 29 cases, **step 13 of `scripts/run_all_tests.sh`**.

**`skills/` — `learn/` (2026-08-11)**: `/learn <video-url> [focus]` watches a video and files a durable note to **`education/learned/`** (dated markdown, source link, what it covers with timestamps, what is worth acting on). It drives the third-party `watch` skill for the watching — captions first, `ffmpeg` frames second, Whisper API only when a video has no captions — and adds the note. ⚠ **The note is the deliverable and the chat reply is deliberately short**: a note that lists the TOPICS a video mentioned is worthless, so it records what the thing actually IS. ⚠ **The notes are COMMITTED and the videos are not re-watched** — a note already on disk for a URL is read rather than regenerated, because the frames are the whole token cost. ⚠ **No speech-to-text key is configured** (`~/.config/watch/.env`, per machine, git-ignored by living outside the repo): captions cover most of YouTube, and a caption-less source — a Loom, a TikTok, your own screen recording — comes back frames-only and says so. A free Groq key retires that.
