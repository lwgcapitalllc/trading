# Instruction: Always Keep Documentation Up To Date

Any time a code change is made — no matter how small — ensure all relevant
documentation is updated in the same commit.

## What counts as "relevant documentation"

- **README.md** (root) — always check this first. Update repo structure,
  workflow descriptions, backup notes, or any section touched by the change.
- **SETUP.md** — update if the change affects how a fresh VPS is set up or
  restored (new files, new steps, changed paths, new dependencies).
- **CONTEXT.md** — update if the change affects architecture, infrastructure,
  bot behavior, or the "current phase" section.
- **Specific guide files** (`BOT_*_GUIDE.md`, `SCHEDULER_GUIDE.md`,
  `NOTIFICATIONS_GUIDE.md`) — update the relevant guide when changing the
  corresponding bot or subsystem.

## Rules

1. Never commit code without checking whether any doc describes the thing
   you just changed.
2. If a doc describes behavior that no longer exists, remove or correct it —
   stale docs are worse than no docs.
3. Keep the README repo structure tree in sync with the actual directory layout.
4. The SETUP.md restore steps must always reflect the current backup strategy
   so a fresh VPS rebuild works from reading that file alone.
