# CLAUDE.md — tools/token-usage

**Purpose:** answer "where did this machine's Claude Code tokens go?" from the local session logs.
**Scope:** read-only. It changes nothing and sends nothing anywhere.

```
python3 tools/token-usage/usage_report.py            # last 7 days
python3 tools/token-usage/usage_report.py --days 30
```

- ⚠ **It only sees THIS machine.** Claude Code keeps session logs per machine
  (`~/.claude/projects/<repo folder>/`), so each person runs it on their own laptop. Two people
  sharing one subscription need both reports to see the whole bill.
- ⚠ **"Input processed" is the figure that explodes, and why.** Every turn re-reads the whole
  conversation, so the total is roughly conversation size x turns. A session open for days with
  hundreds of turns at 500k+ context dominates everything else.
- ⚠ **Byte counts are not token counts** — roughly 4 bytes per token for English text.
- ⚠ **Only the Read tool pulls a folder's CLAUDE.md into context**; a shell search does not. The
  "docs loaded automatically" table counts those loads.

Built 2026-09-13 from the audit that found 5.6 billion input tokens in one week, 58% of it in
three sessions left open for days, and the backend doc (574 KB) loaded 249 times.
