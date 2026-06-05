# Snapshot Regeneration Prompt
## Run on Claude Code to refresh the project state and roadmap docs

> Run this on Claude Code (in the repo root) whenever you want to refresh
> the two handoff documents that you hand to new Claude.ai chats. Should
> be run after each milestone or pass ships, before starting a new chat
> session, or any time the project state has drifted.

---

## Your role

You are regenerating two portable documents from the current state of the
LWG Capital monorepo:

1. **`LWG_Project_State_Snapshot.md`** — what's currently built, the state
   of the platform, the architectural principles, and infrastructure.
2. **`LWG_Roadmap_And_Open_Questions.md`** — what's planned next, future
   milestones, open questions, and parallel tracks.

These two documents will be pasted into new Claude.ai chats so they can be
oriented in 30 seconds without re-explaining the foundation.

You are NOT changing any code or any other docs. You are reading existing
CLAUDE.md files, the design doc, and the actual filesystem to produce two
clean Markdown files.

---

## Source material

Read these in order:

1. **Repo root README.md and CLAUDE.md** — overall map and standing rules
2. **`docs/Command_Center_Backtest_Engine_Design.md`** — the architecture
   doc with M-milestone retrospectives
3. **`command-center/CLAUDE.md`** — top-level command center status
4. **`command-center/backend/CLAUDE.md`** — backend services, tables,
   endpoints, what's built
5. **`command-center/frontend/CLAUDE.md`** — frontend pages, components,
   what's built
6. **`algos/CLAUDE.md`** — forex bots and shared utilities (live MT5 side)
7. **`regime/CLAUDE.md`** and **`regime/REGIME_CLASSIFIER.md`** — the
   shared classifier
8. **`strategies/CLAUDE.md`** if it exists — the generic strategies
   subsystem (created in Pass 2.5)

Also look at:
- The actual `strategies/` directory structure to confirm what runners and
  strategies exist
- The actual database schema in `lab.db` (via `sqlite3` or via querying
  the backend) for current ruleset count and types
- Any in-flight spec files in the repo (`Pass*_Build_Spec.md`,
  `M*_Build_Spec.md`) that have not yet been deleted post-shipping

---

## Document 1: LWG_Project_State_Snapshot.md

Produce a snapshot with these sections, in this order:

### What this project is
One paragraph describing LWG Capital: personal algorithmic trading
operation, near-term goal (pass LucidFlex evals), long-term goal (30-50
funded accounts), S.Y.S.T.E.M. methodology, futures + prop focus today
with forex/MT5 planned but not built.

### Stack and infrastructure
List: Mac dev environment (FastAPI, Vite/React, SQLite, VS Code, Claude
Code, Claude.ai chat), Windows VPS (NT8, nt8_agent.py, pywinauto, MT5
forex bots), GitHub repo locations.

### Monorepo structure
A clean directory tree (2 levels) showing all peer subsystems. Comment
each line with its purpose in one phrase.

### What's shipped (chronological)
List all platform milestones (M1 through whatever the current latest is)
and all foundational passes (Pre-M4 unification, Pass 1, Pass 2, Pass 2.5,
etc.) in chronological order. For each, a 2-3 sentence summary of what
got built.

For each milestone, mark status as: ✅ shipped / 🚧 in flight / 📋 specified.

### Current state of strategies
List each strategy that exists, what file it lives at, what its grade is
(if known), and key facts about its performance. Include the M4 regime
breakdown for any strategy that's been analyzed.

### Current state of rulesets
Count of seeded rulesets, breakdown by type (prop_eval / prop_funded /
personal / demo). Note any parallel work being done on prop firm seeding.

### Architectural principles locked in
List the principles in numbered form. Include at minimum:
- One backtest, N verdicts
- Generic strategies + ruleset-injected config
- Categorized parameters (Strategy Logic vs Foundational)
- One shared regime classifier
- NT8 is the backtest + execution engine
- Observability is mandatory
- CLAUDE.md updates in same session as approved changes
- Strict build order with stop-and-report checkpoints

### Communication rules with Claude Code
List the non-negotiable rules: plain English, one clear question with
options, stop after each numbered step, update CLAUDE.md in same session,
smallest viable change first.

### What's NOT done
A pointer to the roadmap document for the forward plan.

---

## Document 2: LWG_Roadmap_And_Open_Questions.md

Produce a roadmap with these sections, in this order:

### Immediate next work (priority order)
Numbered list of the next 3-5 things to do, in actual sequence. Include
whether each is a platform task or a strategy task.

### Future platform milestones (in order, not yet started)
Each upcoming M-milestone with a paragraph describing what it builds and
why. Note any prerequisites (e.g. "M5 needs 2+ strategies grading B+").

### Smaller items raised but deferred
Bullet list of things that have come up in conversation but are not
actively planned. Each one short with brief context.

### Parallel tracks Aaron is running separately
Things happening in other dedicated chat sessions. Today this includes
the prop firm research workshop. Don't list things that are part of the
main work plan — only genuinely parallel uncorrelated tracks.

### Open architectural questions
Discussions that have happened but aren't fully resolved. Include enough
context that a new chat can pick them up if they become relevant, but
note that they shouldn't be proactively re-litigated.

### Communication rules for new chats
Same rules from the snapshot, repeated here so a chat that only got the
roadmap document still gets the rules.

---

## Hard rules

- **Read first, write second.** Do not invent facts. If a status is unclear
  from the source docs, mark it as "TODO: verify" and list the gap in your
  report back to the user.
- **Source from the repo, not from memory.** Even if you remember something
  from a prior session, verify it against the current state of the repo.
- **No secrets.** Don't include API keys, passwords, account IDs, or any
  other credentials in either document.
- **Chronological ordering** for shipped milestones. Newest at the bottom
  of "what's shipped" so reading top-to-bottom tells the project's story.
- **Keep both documents under ~10 pages each.** A new chat should be able
  to absorb both quickly.
- **Plain English throughout.** No code blocks. Inline code for file paths
  and identifiers is fine.

---

## Output

Write both documents to `/mnt/user-data/outputs/`:

- `LWG_Project_State_Snapshot.md`
- `LWG_Roadmap_And_Open_Questions.md`

After writing, report back in plain English:

- What you read to generate the documents
- Any TODO placeholders that need verification
- Anything in the repo that surprised you (stale CLAUDE.md content,
  references to files that don't exist, etc.) — flag as a separate
  issue, don't fix it in this pass

Do NOT make any other changes to the repo. This is a pure read +
generate task.

---

## When to run this prompt

- After each milestone (M4, M5, etc.) ships
- After each foundational pass (Pass 1, Pass 2, Pass 2.5, etc.) ships
- Before starting any new Claude.ai chat
- Whenever the project has drifted noticeably from the last snapshot
- On a fixed cadence (e.g. end of each week of active work)

The audit prompt (`DOC_AUDIT_PROMPT.md`) cleans the source-of-truth docs
in the repo. This prompt produces portable handoff documents from those
cleaned docs. Run the audit first if the repo docs are stale, then run
this regeneration.

---

*End of regeneration prompt.*
