# Notes — Standalone scripts, tools and the course material

The VPS bootstrap and recovery scripts and their scheduled tasks, the hand-run tools that belong to no subsystem, and how course notes are filed. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### scripts/
Cross-subsystem VPS bootstrap and full-recovery scripts (`bootstrap_vps.ps1` for the MT5/algos side, `bootstrap_ninjatrader.ps1` for the NT8 side). Idempotent, run on a wiped or new VPS. Full run order in `scripts/README.md`. ⚠ **`bootstrap_vps.ps1`'s task list gained `SYS_LEDGERSYNC` on 2026-08-24** — the box commits and
pushes its own decision record hourly, so the backup no longer waits for a Mac to wake up. It is the
one task there that needs a SECRET a rebuild does not restore (`github_token` in the git-ignored
`algos/credentials.json`): without it the task runs, commits, and silently never pushes.

⚠ **And `SYS_REENTRYWATCH` on 2026-09-03** — hourly, grades each live re-entry against the strategy
and reports on Telegram. It needs no secret. 🔴 **It is the SECOND task here whose normal state is
silence**, alongside the dead-man's switch, so it carries the same hazard: a missing watcher and a
quiet month look identical. That is why it announces its own failure and writes a health record on
every run — **a task list that registers an alarm nobody can tell is dead is the 2026-08-05 failure
with a different name.** Rules: `algos/CLAUDE.md` → *The re-entry can be switched on*.

⚠ **And `SYS_BROKERCOSTS` on 2026-09-03** — daily at 06:40 UTC, it reads the broker's overnight
financing off the live terminal and reports when the broker MOVES it. That rate was caught drifting
four times in seven weeks and every one was found by a person who happened to look. It needs no
secret and it CHANGES nothing — re-pricing the lab's constant re-bases every charged figure in the
repo and stays a deliberate job. 🔴 **THIRD task here whose normal state is silence**, so same
hazard and same answer: it announces its own failure and writes a health record carrying the
reading on every run. Rules: `algos/CLAUDE.md` → *`SYS_BROKERCOSTS`*.

⚠ **And `SYS_GETSCREENRESTART` on 2026-09-13** — every Saturday it restarts the VPS host's
Getscreen.me remote-access agent, which leaked 2.1 GB of kernel memory in four months on this 4 GB
box. 🔴 **FOURTH task here whose normal state is silence**, and nothing on the box alarms on low
memory — by decision, not a gap. Rules: `algos/CLAUDE.md` → *`SYS_GETSCREENRESTART`*.
🔴 `install_ledger_sync.sh` **no longer installs anything and refuses if you ask** — its Mac agent
was a SECOND WRITER of an append-only file, and two appends to one file end cannot be merged at any
content (eight hours of hourly conflicts, 2026-08-28). **`--no-push` did not save it: on a shared
branch a local commit is a push with a delay.** The rule is enforced in `ledger_sync.py`, which
refuses to commit records the running machine did not write. Rules live in `algos/CLAUDE.md`; do
not restate them here.

**`setup_learning_mode.sh` (2026-08-11) is the odd one out — it targets a DEV MACHINE, not the VPS**, and is the one-time install behind `/learn <video-url>`: it puts `ffmpeg`/`yt-dlp` on the PATH and clones the third-party `watch` skill (MIT, `bradautomates/claude-video`) to `~/.claude/vendor/`, symlinked into `~/.claude/skills/watch`. ⚠ **The watch skill is deliberately NOT vendored into this repo**, so a clone alone does not make `/learn` work — the skill checks for the install and names the script rather than shelling out to `yt-dlp` itself. **Re-running the script is also how it UPDATES**, which is the part that bites: `yt-dlp` breaks whenever a video site changes its markup, and a stale copy fails on real URLs while looking perfectly installed.

### tools/
Standalone utilities that belong to no subsystem and are run by hand. Two today. `tools/token-usage/` answers where this machine's Claude Code tokens went, read-only, off the local session logs — see *Token use* in the root CLAUDE.md. And `tools/skool-transcript/` — rips course video transcripts and indexes them into `education/`. It has its own CLAUDE.md. ⚠ **Nothing imports it and nothing schedules it**, which is the point — it is a dev-machine tool, not part of any deployable, so it is out of scope for the commit hook's money-path rule and for every parity gate.

### education/
The course material the engines were extracted FROM, plus notes. Two halves and they are different things. `education/smc/` is the source library — transcripts, summaries and visual playbooks for the SMC course, with its own CLAUDE.md; it is reference material a human reads, and no code reads any of it. `education/learned/` is where `/learn <video-url>` files a dated note per video (source link, what it covers with timestamps, what is worth acting on). ⚠ **The notes are COMMITTED and videos are never re-watched** — a note already on disk for a URL is read rather than regenerated, because the extracted frames are the whole token cost.
