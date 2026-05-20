# Claude Code Setup & Workflow Guide
## LWG Capital Algo Trading Suite

---

## Step 1 — Install Claude Code on Mac

Open Terminal (Cmd + Space → type Terminal → Enter) and run:

```bash
curl -fsSL https://claude.ai/install.sh | sh
```

That's the official native installer — no Node.js needed, auto-updates in background.

Verify it worked:
```bash
claude --version
claude doctor
```

Then authenticate — it will open your browser and log you into your Claude account (same account as claude.ai).

---

## Step 2 — Navigate to Your Project

```bash
cd ~/path/to/your/algos
```

Tip: In Finder, drag your algos folder into Terminal — it pastes the full path automatically.

---

## Step 3 — Add CONTEXT.md to Your Repo

Copy the CONTEXT.md file (provided separately) into the root of your algos repo:

```
algos/
├── CONTEXT.md     ← add this
├── algo.py
├── README.md
...
```

Commit and push it:
```bash
git add CONTEXT.md
git commit -m "Add Claude context file"
git push
```

Claude Code reads all files in your repo automatically. CONTEXT.md gives it instant project understanding every session.

---

## Step 4 — Start Claude Code

```bash
cd ~/path/to/algos
claude
```

That's it. Claude Code reads your entire codebase and is ready to work.

---

## Daily Workflow

### When coding (use Claude Code in terminal):

```
cd ~/path/to/algos
claude
```

Then just talk to it naturally:
- "Add a trailing stop to bot_scalper.py that kicks in after 1R profit"
- "The dead zone logic in bot_smc_trend.py isn't closing losing trades — fix it"
- "Refactor the Calmar calculation in shared_calmar.py to use a 90-day window"

Claude Code edits the files directly. No downloading, no copy-paste.

When done, push as normal from VS Code or Terminal:
```bash
git add .
git commit -m "your message"
git push
```

### When designing / discussing ideas (use Claude.ai chat):

Use Claude.ai chat (here) for:
- Thinking through a new strategy
- Deciding between two approaches
- Understanding a trading concept
- Reviewing performance and deciding what to change

**At the end of every design chat, ask:**
> "Summarize what we decided, the key reasoning, and the exact changes needed for Claude Code to implement."

Copy that summary. Start a fresh chat or go to Claude Code and paste it.

---

## Chat Hygiene (fixes your CPU problem)

Long chats = massive context = slow responses + high CPU.

Rules:
1. **One chat per topic.** Don't continue a 2-week chat. Start fresh.
2. **End each chat with a summary.** Ask Claude: *"Summarize our decisions and what needs to be built."* Save it.
3. **Start new chats with just the context you need.** Paste CONTEXT.md + the summary from last session. That's all Claude needs.
4. **Delete old chats freely.** The context is in CONTEXT.md and your summaries — not in the chat history.

---

## Useful Claude Code Commands

| Command | What it does |
|---------|-------------|
| `claude` | Start a session in current directory |
| `claude --continue` | Resume your last session |
| `claude --resume` | Pick from recent past sessions |
| `claude doctor` | Check health of installation |
| `/help` | Show in-session commands |
| `/exit` | Exit Claude Code |
| Shift + Tab | Toggle Plan Mode (Claude plans before acting) |

**Plan Mode tip:** Use Shift+Tab before big changes. Claude tells you what it's going to do before touching any files. Good habit for anything touching shared components.

---

## The Two-Tool System

```
Claude.ai Chat                    Claude Code (Terminal)
─────────────────                 ──────────────────────
• Strategy discussion             • Writing new bot logic
• Design decisions                • Editing existing files
• Reviewing Calmar data           • Debugging
• Thinking out loud               • Refactoring
• "Should I add X to Bot FFT?"    • Running/testing code
        │                                  │
        └──── paste summary ───────────────┘
                  (one-time handoff)
```

---

## Project Knowledge in Claude.ai (optional upgrade)

If you want Claude.ai chats to know your project without pasting context each time:

1. Go to your Project in Claude.ai
2. Add Project Knowledge: paste the contents of CONTEXT.md
3. Update it when major things change (new bot, new risk rules, etc.)

Every chat inside that Project will start with full context — no re-explaining.

---

## Keeping CONTEXT.md Fresh

Update the bottom section of CONTEXT.md regularly:

```markdown
## What I Am Working On (Update This Section Each Session)
- Last completed: Added partial close logic to SMC Trend
- Currently working on: FFT signal confidence tuning  
- Next up: Calmar reporting improvements
- Open questions: Should FFT use H4 or H1 as primary trend filter?
```

Commit it with your code changes. This is your project memory.
