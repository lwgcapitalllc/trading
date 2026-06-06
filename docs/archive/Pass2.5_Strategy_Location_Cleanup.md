# Pass 2.5 — Strategy Location + Deploy Button Cleanup
## Build Spec

**For Claude Code.** Small cleanup pass between Pass 2 and the strategy
improvement work. Moves strategy files to a generic top-level location,
adds per-strategy Deploy buttons, and renames the Files tab to reflect
its real purpose.

Read `backend/CLAUDE.md`, `frontend/CLAUDE.md`, and the existing Pass 1
and Pass 2 docs first.

---

## 0. Communication rules (same as always)

- Plain English replies. No code blocks unless I ask.
- One clear question with concrete options when you need input.
- Update CLAUDE.md in the same session as approved changes.
- This is "Pass 2.5 — Strategy Location Cleanup" — not a numbered milestone.

---

## 1. What Pass 2.5 delivers

- [ ] New top-level `strategies/` directory at the monorepo root, organized
  by runner platform
- [ ] The three generic strategies moved from `algos/markets/futures/lucid_flex/`
  to `strategies/ninjatrader/`
- [ ] Old `algos/markets/futures/lucid_flex/` directory removed (or emptied
  if other things live there too — check first)
- [ ] `strategies` table gains a `source_path` field tracking each strategy's
  canonical location in the repo
- [ ] Strategy scanner reads from the new path and populates `source_path`
- [ ] Strategies tab gets a "Deploy" button per strategy (prominent when
  status is "Needs deploy", less prominent when "In sync")
- [ ] Clicking Deploy reads the file from `source_path`, uploads it to the
  VPS NT8 strategy folder, refreshes sync status
- [ ] "Files" tab renamed to "Deployed" everywhere
- [ ] `strategies/CLAUDE.md` created as a subsystem doc
- [ ] Top-level README and monorepo `CLAUDE.md` updated to reflect the new
  subsystem
- [ ] All references to the old path (`algos/markets/futures/lucid_flex/`)
  searched and updated or removed across the repo

---

## 2. Folder structure

### Target layout

```
trading/                               (monorepo root)
├── strategies/                         ← NEW top-level subsystem
│   ├── CLAUDE.md
│   ├── README.md                       ← brief: what this is, how to add a strategy
│   ├── ninjatrader/
│   │   ├── ORB.cs
│   │   ├── VWAP_MR.cs
│   │   └── Momentum.cs
│   ├── mt5/                            ← empty for now, exists as placeholder
│   │   └── .gitkeep
│   └── tradovate/                      ← optional, omit if you prefer
│       └── .gitkeep
├── algos/                              ← existing, untouched
├── command-center/                     ← existing, untouched
├── regime/                             ← existing peer subsystem
└── ...
```

### Why this structure

- **Top-level peer subsystem.** Strategies are cross-cutting — used by the
  command center backtest lab and (eventually) live deployment. Same pattern
  as `regime/`.
- **Organized by runner platform, not market.** A `.cs` file always belongs
  to NT8 regardless of whether it trades futures, stocks, or options. The
  `runner` field on the strategies table already names platforms — folder
  structure matches.
- **Empty placeholder folders are fine.** `mt5/` and `tradovate/` show the
  intended expansion path. Easy to spot where forex strategies will live.

### Move the existing files

The three generic strategies currently live at
`algos/markets/futures/lucid_flex/` (or wherever Pass 1 left them — check
first). Move them to `strategies/ninjatrader/`:

```
algos/markets/futures/lucid_flex/ORB.cs        → strategies/ninjatrader/ORB.cs
algos/markets/futures/lucid_flex/VWAP_MR.cs    → strategies/ninjatrader/VWAP_MR.cs
algos/markets/futures/lucid_flex/Momentum.cs   → strategies/ninjatrader/Momentum.cs
```

After the move, check if `algos/markets/futures/lucid_flex/` is now empty.
If yes → remove the empty directory. If no → leave it (something else lives
there). Either way, document what you found in `backend/CLAUDE.md`.

---

## 3. Backend changes

### Database schema

Add a `source_path` field to the `strategies` table:

```sql
ALTER TABLE strategies ADD COLUMN source_path TEXT;
```

Backfill for the three existing strategies:

```sql
UPDATE strategies SET source_path = 'strategies/ninjatrader/ORB.cs' WHERE id = 'orb';
UPDATE strategies SET source_path = 'strategies/ninjatrader/VWAP_MR.cs' WHERE id = 'vwap_mr';
UPDATE strategies SET source_path = 'strategies/ninjatrader/Momentum.cs' WHERE id = 'momentum';
```

`source_path` is relative to the monorepo root. Backend code joining it with
the repo root gets the absolute path.

### Strategy scanner update

The scanner currently reads from the old path. Update it to read from
`strategies/ninjatrader/`. When discovering a strategy, populate the
`source_path` field with its canonical relative path.

If the scanner discovers a `.cs` file that isn't in the database yet, it
inserts a new row with `source_path` set. If it finds a database row whose
`source_path` no longer exists on disk, it flags it (don't auto-delete —
just surface a warning in the scanner's report).

### New endpoint: Deploy from source

```
POST /strategies/{strategy_id}/deploy
Response: 202 Accepted
Body: { "deploy_job_id": "...", "status": "started" }

GET /strategies/{strategy_id}/deploy/{deploy_job_id}
Response: {
  "status": "running" | "complete" | "failed",
  "filename": "ORB.cs",
  "uploaded_size_bytes": 8421,
  "vps_path": "C:\\Users\\Administrator\\Documents\\NinjaTrader 8\\...",
  "error": null | "..."
}
```

Implementation: read the file from `<repo_root>/<source_path>`, then call
the existing VPS agent upload endpoint with the file contents. Reuse the
existing upload logic — don't duplicate it. The Deploy endpoint is just a
convenience layer that knows where to find the file.

Edge cases to handle:
- `source_path` is null → return 400 "Strategy has no source_path. Set it
  first or use the Deployed tab to upload manually."
- File at `source_path` doesn't exist on disk → return 404 with a clear
  error message
- File on VPS is locked → propagate the 423 error from the upload endpoint

After a successful deploy, the strategy's sync-status should update to "in
sync" on the next sync-status fetch.

---

## 4. Frontend changes

### Strategies tab — add Deploy button

Each strategy row in the main Strategies list currently shows a sync-status
badge (from Pass 2). Add a Deploy button to the action area:

**When status is "Needs deploy" or "Missing":**
- Deploy button is prominent (filled, primary color)
- Click → calls the deploy endpoint, shows progress, refreshes sync status

**When status is "In sync":**
- Deploy button is less prominent (outlined, secondary) or even hidden
  behind a "..." menu
- Still clickable for redeploy (overwriting)
- A "Redeploy" tooltip clarifies the action

### Rename "Files" tab to "Deployed"

Everywhere in the frontend code, rename:
- Tab label: "Files" → "Deployed"
- Page title: "Strategy Files on VPS" → "Deployed Strategies on VPS"
- Any component file like `FilesTab.tsx` → `DeployedTab.tsx`
- Routes like `/strategies/files` → `/strategies/deployed`
- Type names referencing "files" can stay (they describe the data, not the
  UI label) — but if any component is literally called `FilesTab` rename it

The Deployed tab's functionality stays exactly the same. Drag/drop upload,
file list, delete, Compile All — all unchanged. Only the name changes to
reflect that the user's mental model is "what's deployed on the VPS," not
"manage some files."

---

## 5. New `strategies/CLAUDE.md`

Create `strategies/CLAUDE.md` following the canonical subsystem template:

```markdown
# CLAUDE.md — Strategies

**Purpose:** Generic trading strategy implementations, organized by runner platform.
**Scope:** This holds strategy source files (`.cs` for NT8, `.mq5` for MT5).
  It does NOT cover: backtest infrastructure (see command-center/), live bot
  runtime logic (see algos/), or regime classification (see regime/).
**Status:** Production. NinjaTrader strategies are live; MT5 is placeholder.
**Last reviewed:** [today's date]

## Key paths

- `ninjatrader/` — NT8 strategies (.cs files, C#)
- `mt5/` — MT5 expert advisors (.mq5 files, MQL5) — placeholder, no
  strategies yet
- `tradovate/` — placeholder for future Tradovate strategies

## Standing instructions

**Do**
- Keep strategy logic generic — no firm-specific defaults baked in
- All foundational parameters (account size, daily loss, hours, etc.)
  come from the active ruleset at runtime, not from file defaults
- Use the [Category] attribute on every NinjaScriptProperty to tag
  whether the parameter is "Strategy Logic" (tunable by optimizer) or
  "Foundational" (injected from ruleset)
- New strategies go in the appropriate runner subfolder

**Never do**
- Hardcode firm-specific values (account size, max daily loss,
  commission, etc.) as defaults
- Add a strategy file with the firm name in its filename
  (e.g. `ORB_LucidFlex.cs` is wrong — `ORB.cs` is right)
- Mix strategy logic with risk-management mechanics that should be
  foundational

## Adding a new NinjaTrader strategy

1. Create `<StrategyName>.cs` in `strategies/ninjatrader/`
2. Follow the Pass 1 categorization model — strategy logic params get
   `[Category("Strategy Logic")]`, foundational params get
   `[Category("Foundational")]`
3. Run the strategy scanner from the command center (`POST /strategies/scan`)
   to register it in the database
4. Set the strategy's `source_path` to its repo-relative location
5. From the Strategies tab in the command center, click Deploy

## Guides & references

- Pass 1 spec (in repo history) — foundational config rules
- Pass 2 + Pass 2.5 (this file) — deployment manager
- `backend/CLAUDE.md` — backend-side details
```

Plus a small `strategies/README.md` with a one-paragraph overview pointing
people at the CLAUDE.md.

---

## 6. Cross-repo cleanup

Search for stale references and update or remove each:

- Any reference to `algos/markets/futures/lucid_flex/` in any `.md`, `.py`,
  `.tsx`, or config file
- Any reference to `_LucidFlex` strategy class names that survived Pass 1
- Old paths in `algos/CLAUDE.md`, root `CLAUDE.md`, or `README.md` pointing
  at the lucid_flex directory

For each match, either:
- Update the path to point at `strategies/ninjatrader/`
- Or delete the reference if it's now obsolete

Report what was found and what was changed.

---

## 7. Build order

Strict. Stop and report after each:

1. **Move files + update paths.** Move the three `.cs` files. Update the
   strategy scanner to read from the new location. Add the `source_path`
   column and backfill. Verify scanner discovers all three strategies at
   the new path. **Don't touch frontend yet** — verify backend works first.

2. **Deploy endpoint.** Add the new `POST /strategies/{id}/deploy` and
   GET status endpoint. Smoke test: deploy ORB via curl. Verify it appears
   on the VPS at the right path.

3. **Strategies tab — Deploy button.** Add the per-strategy Deploy action.
   Verify clicking it triggers the deploy endpoint and refreshes sync status.

4. **Rename Files → Deployed.** Tab label, component names, routes. Verify
   the tab still works exactly the same after rename.

5. **Cross-repo cleanup.** Grep for stale references, update or remove.
   Bring back the list of what was found and changed.

6. **New subsystem docs.** Create `strategies/CLAUDE.md` and `strategies/README.md`.
   Update root `CLAUDE.md` and `README.md` to list the new subsystem.

7. **End-to-end test:** From a freshly-loaded UI, click Deploy on each of
   the three strategies. Click Compile All. Run a backtest with each.
   Verify all three work end-to-end via the new flow.

8. **Update existing CLAUDE.md files** (backend, frontend, command-center).
   Note the new structure, the source_path field, the Deploy button, the
   tab rename.

---

## 8. What NOT to do in Pass 2.5

- Don't change strategy code. The .cs files are moved, not modified.
- Don't add new compile logic — Pass 2's compile flow is untouched.
- Don't auto-deploy on git push or similar magic. Deploy is always a
  user-initiated UI action.
- Don't auto-compile after deploy. User clicks Compile All when ready
  (may deploy multiple strategies before compiling).
- Don't migrate the `algos/` subsystem beyond removing the now-empty
  `lucid_flex/` directory if it exists. Forex bots stay where they are.

---

## 9. After Pass 2.5 ships

Strategy iteration workflow becomes:

1. Edit `strategies/ninjatrader/ORB.cs` in VS Code
2. Open command center → Strategies tab
3. Click "Deploy" next to ORB (badge turns green)
4. Click "Compile All"
5. Run backtest

About 20 seconds of clicking. The Deployed tab exists as fallback for
external files but you'd rarely touch it.

Then proceed to strategy improvements — adding the regime filter to ORB,
trailing stop, daily P&L circuit breaker, optional re-entry. Each iteration
uses the new one-click deploy flow.

---

*End of Pass 2.5 spec.*
