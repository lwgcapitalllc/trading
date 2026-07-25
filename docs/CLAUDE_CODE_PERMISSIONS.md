# Claude Code Permissions — Reference

**Purpose:** How permission prompts work in this repo, and how to change them.
**File that controls it:** `.claude/settings.json` (repo root, checked into git).
**Last reviewed:** 2026-07-25

---

## Why this exists

Claude Code asks before running most commands. Left alone, it blocks on a
confirmation prompt and does nothing until you come back — you lose the whole
time you were away. This config auto-approves the routine stuff and only stops
for things that can lose work.

---

## The three lists

`.claude/settings.json` has a `permissions` block with three arrays. They are
checked in this order:

1. **`deny`** — blocked outright. Claude cannot run it, and cannot ask.
2. **`ask`** — always prompts, even if something in `allow` also matches.
3. **`allow`** — runs silently, no prompt.

**`deny` beats `ask` beats `allow`.** That ordering is the whole design. It lets
`allow` be broad (`Bash(ssh forexvps *)`) while `ask` carves destructive
exceptions back out of it.

There is also `defaultMode`, set to `acceptEdits`. That means edits to files
apply without prompting. The reasoning: an edit is always recoverable from git,
whereas `rm` and `git reset` are not. If you want to approve every file edit,
delete that line.

---

## What is currently auto-allowed

| Group | Covers |
|---|---|
| Navigation & reads | `cd`, `ls`, `cat`, `head`, `tail`, `grep`, `rg`, `find`, `tree`, `wc`, `stat`, `diff`, `jq`, `awk`, `sort`, `uniq` |
| Safe writes | `mkdir`, `touch`, `cp` |
| Git (non-destructive) | `status`, `diff`, `log`, `show`, `blame`, `branch`, `add`, `commit`, `fetch`, `pull`, `push`, `ls-files`, `rev-parse` |
| GitHub CLI (read) | `gh pr view/list`, `gh issue view/list`, `gh run list/view` |
| Python | `python`, `python3`, both venv interpreters, `pytest`, `pip list/show/freeze` |
| Node | `npm run`, `npm ls`, `npm test`, `npx tsc`, `npx vitest`, `npx eslint`, `node` |
| Data & local services | `sqlite3`, `curl` to localhost / 127.0.0.1, `lsof`, `ps` |
| VPS (read) | `ssh forexvps` with `netstat`, `schtasks /query`, `tasklist`, `dir`, `type`, `wmic`, `curl -s` |
| VPS (deploy) | `git push`, `ssh forexvps "cd C:\trading && git pull*"`, the `mt5_connect.lock` delete, `taskkill`, `schtasks /run` |
| Web | `WebFetch` on github.com, raw.githubusercontent.com, docs.claude.com |

The full VPS deploy sequence from the root `CLAUDE.md` now runs start to finish
without a single prompt.

---

## What still stops and asks

Anything with no undo:

- `rm`, `rmdir`, `mv`, `sed -i`, `chmod`, `sudo`
- `kill`, `pkill`, `killall` (local)
- `git reset`, `git checkout`, `git restore`, `git clean`, `git rebase`, `git merge`, `git filter-branch`
- `gh pr merge`, `gh release`
- `pip install`, `npm install`, `npm uninstall`, `brew`
- On the VPS: `del` (other than the lock file), `rmdir`, `format`, `schtasks /delete`

---

## What is blocked outright

- `git push --force` / `git push -f`
- `rm -rf /`
- Reading **or** writing `.env`, `credentials.json`, `users.json` anywhere in the repo

The secrets denials back up the "Never Do" list in the root `CLAUDE.md` — that
rule is now enforced by the harness, not just documented.

---

## How to change it

### Rule syntax

```
Bash(<command prefix>:*)
```

The `:*` means "this prefix plus anything after it". Examples:

- `Bash(pytest:*)` — any pytest invocation
- `Bash(git push:*)` — any git push
- `Bash(npx tsc --noEmit)` — that exact command only, no wildcard

Older entries in this repo use a space instead of a colon (`Bash(npx tsc *)`).
Both work. Use the colon form for anything new — it is the current documented
syntax.

Non-Bash tools use the same shape: `Read(...)`, `Edit(...)`, `Write(...)`,
`WebFetch(domain:example.com)`.

### Compound commands

Claude splits on `&&` and checks **each part separately**. So:

```
cd /Users/alwg/trading && git add file.tsx
```

needs *both* `Bash(cd:*)` and `Bash(git add:*)` allowed. This is the single most
common reason a rule "doesn't work" — the rule matches the interesting half of
the command but not the `cd` in front of it. `Bash(cd:*)` is in `allow` for
exactly this reason.

### To stop a recurring prompt

Copy the command from the prompt, cut it back to its stable prefix, add `:*`,
and put it in `allow`. Then restart Claude Code.

You can also run `/permissions` inside Claude Code to view and edit the lists
interactively, or `/fewer-permission-prompts` to have it scan recent transcripts
and propose an allowlist.

---

## Where settings live

Claude Code merges several files. Later ones win.

| File | Scope | In git? |
|---|---|---|
| `~/.claude/settings.json` | All your projects | No |
| `.claude/settings.json` | This repo, everyone | **Yes** |
| `.claude/settings.local.json` | This repo, just you | No (git-ignored) |

Put team-wide rules in `.claude/settings.json` so your brother gets them on
clone. Put anything personal or machine-specific in `.claude/settings.local.json`.

Note: `~/.claude/settings.json` still holds around 25 one-off entries from before
this config existed (`Bash(git commit -m ' *)`, specific compare-script
invocations, etc.). They are redundant now but harmless. Safe to delete when
convenient.

---

## The nuclear options

If you ever want zero prompts for one session:

- **Shift+Tab** cycles permission modes live — normal → accept-edits → plan → bypass.
- `claude --dangerously-skip-permissions` starts in bypass mode.

Bypass mode ignores all three lists. It will run `rm -rf`, force-push, and
destructive VPS commands without asking. Do not use it on this repo — the whole
point of the config above is that you do not have to.

---

## Related

- Root `CLAUDE.md` — VPS deploy workflow, "Never Do" list
- `scripts/README.md` — VPS bootstrap run order
