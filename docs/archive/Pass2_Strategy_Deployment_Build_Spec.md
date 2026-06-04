# Pass 2 — Strategy Deployment Manager
## Build Spec

**For Claude Code.** This pass adds a deployment manager that lets the user
upload, overwrite, delete, and compile NinjaScript strategy files on the VPS
directly from the command center UI. Eliminates manual SSH for strategy
iteration.

Read `backend/CLAUDE.md`, `frontend/CLAUDE.md`, and
`Command_Center_Backtest_Engine_Design.md` first. Pass 1 must be shipped
and verified before starting.

---

## 0. Communication rules (same as always)

- Plain English replies. No code blocks unless I ask.
- One clear question with concrete options when you need input.
- Update CLAUDE.md in the same session as approved changes.
- This is "Pass 2 — Strategy Deployment" — not a numbered milestone.

---

## 1. What Pass 2 delivers (acceptance checklist)

- [ ] New "Files" sub-tab under the Strategies tab in the UI
- [ ] User can see all `.cs` files in NT8's strategy folder with
  last-modified dates and file sizes
- [ ] User can drag-and-drop a `.cs` file from their Mac to upload it to
  the VPS strategy folder
- [ ] Uploading an existing filename shows a confirmation modal before
  overwriting
- [ ] User can delete a strategy file (with confirmation)
- [ ] User can click "Compile" to trigger NT8 recompile, sees result
  (success / errors) in the UI
- [ ] Each strategy in the existing DB list shows a sync-status badge:
  ● In sync (file on VPS matches expected) / ● Needs deploy (DB has
  strategy but file missing or stale on VPS)
- [ ] Lock-detection: if NT8 has a strategy file open/locked, the upload
  surfaces a clear "Cannot overwrite — strategy is in use" error
- [ ] Both CLAUDE.md files updated

---

## 2. Backend endpoints

New router: `routers/strategy_files.py`

```
GET    /strategy-files
       → list all .cs files in NT8's strategy folder
       Response: [
         { "filename": "ORB.cs", "size_bytes": 8421, "modified_at": "..." },
         ...
       ]

POST   /strategy-files/upload
       → upload a .cs file (multipart/form-data)
       Body: file (the .cs content) + filename + overwrite (bool)
       Response 200: { "filename": "...", "size_bytes": ..., "modified_at": "..." }
       Response 409: file already exists and overwrite=false
       Response 423: file is locked (NT8 has it open)

DELETE /strategy-files/{filename}
       → delete a strategy file from the VPS
       Response 200: { "deleted": true }
       Response 423: file is locked

POST   /strategy-files/compile
       → trigger NT8 recompile (F5 or equivalent)
       Response 202: { "compile_job_id": "..." }

GET    /strategy-files/compile/{compile_job_id}
       → poll for compile result
       Response: {
         "status": "running" | "success" | "failed",
         "errors": [...],   // empty on success
         "warnings": [...]
       }

GET    /strategy-files/sync-status
       → for each strategy in the DB, report whether the .cs file exists
         on the VPS and whether it matches what we expect
       Response: [
         {
           "strategy_id": "orb",
           "expected_filename": "ORB.cs",
           "file_exists_on_vps": true,
           "file_size_bytes": 8421,
           "file_modified_at": "...",
           "in_sync": true
         },
         ...
       ]
```

### Determining "in_sync"

A strategy is "in sync" when:
- The expected `.cs` file exists on the VPS (`<class_name>.cs`)
- The file's last-modified timestamp is newer than or equal to the last
  successful compile timestamp for that strategy

For now, treat any existing file as "in sync." We can refine later if
needed by storing the expected file hash in the DB and comparing.

If the file doesn't exist on the VPS but the strategy is in the DB:
`in_sync = false`, reason = "missing_on_vps."

### VPS agent extensions

The existing VPS agent on the Windows machine needs new endpoints:

```
GET   /files/strategies
POST  /files/strategies/{filename}    (upload via multipart)
DELETE /files/strategies/{filename}
POST  /compile                        (triggers F5 in NT8)
GET   /compile/{job_id}
```

The strategy folder path on the VPS is fixed:
`C:\Users\Administrator\Documents\NinjaTrader 8\bin\Custom\Strategies\`

If your VPS uses a different user, adjust accordingly — but document the
hardcoded path in `backend/CLAUDE.md`.

### Compile implementation

Two approaches, in order of preference:

**Approach A — F5 via pywinauto.** Bring NT8 window to foreground, send
F5. Wait for the compile status bar to update. Read errors/warnings
from NT8's output window.

**Approach B — NinjaTrader.Client API or NCompile.exe.** NT8 ships with
`NCompile.exe` in its installation folder. Running it from PowerShell
compiles all strategies and returns exit code. Errors go to stderr.

**Decision rule:** try Approach B first. `NCompile.exe` is cleaner — no
window focus issues, no race conditions, plain stdout/stderr. If it
doesn't exist on your NT8 version or doesn't behave as expected, fall
back to Approach A.

Document which approach was used in `backend/CLAUDE.md`.

### Lock detection

NT8 holds file locks on strategies that are currently loaded in any
chart or running. To detect locks before uploading:

```python
import os
def is_locked(filepath):
    try:
        with open(filepath, 'r+b') as f:
            pass
        return False
    except IOError:
        return True
```

Lock detection runs on the VPS agent side, before attempting to write.
If locked, the agent returns HTTP 423 (Locked) with a message:
"File is in use by NT8. Stop the running strategy or close it from
charts before redeploying."

### Upload size limit

Cap uploads at 256KB per file. NinjaScript files are typically 5-30KB.
Anything larger is suspicious.

---

## 3. Frontend changes

### New "Files" sub-tab under Strategies

The existing Strategies tab structure:

```
Strategies
├── Strategies (list, existing)
├── Runs (existing)
├── Sweeps (existing)
├── Optimizations (existing)
├── Stress Tests (existing)
└── Files (NEW)
```

### Files page layout

```
┌─ Strategy Files on VPS ─────────────────────────────────────────┐
│                                                                  │
│  Last refreshed: 2 mins ago    [↻ Refresh]    [⚙ Compile All]    │
│                                                                  │
│  ┌─ Drop .cs files here to upload ──────────────────────────┐   │
│  │              (or click to browse)                         │   │
│  │                                                            │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Filename          Size    Modified           Status    Actions  │
│  ──────────────────────────────────────────────────────────────  │
│  ORB.cs           8.4 KB   2026-06-02 14:33   ● In use  [⋯]      │
│  VWAP_MR.cs       7.1 KB   2026-06-02 14:33   ● In sync [⋯]      │
│  Momentum.cs      6.8 KB   2026-06-02 14:33   ● In sync [⋯]      │
│  StaleOldFile.cs  4.2 KB   2026-04-15 10:22   ● Unknown [⋯]      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

- **Drop zone:** drag/drop a `.cs` file or click to browse
- **Actions menu (⋯):** Download / Replace / Delete
- **Status badges:**
  - ● In sync (green) — file matches a known strategy in DB
  - ● In use (orange) — file is currently locked (NT8 has it open)
  - ● Unknown (gray) — file exists but isn't tracked in DB
  - ● Missing (red) — strategy in DB but file not on VPS

### Compile button + result modal

"Compile All" button at the top runs `POST /strategy-files/compile` and
shows a modal with live polling:

```
┌─ Compiling NinjaScript ─────────────────────┐
│                                              │
│  ⟳ Compiling...  (Elapsed: 4s)              │
│                                              │
│  When complete, results will appear here.    │
│                                              │
└──────────────────────────────────────────────┘
```

On success:

```
┌─ Compile Successful ────────────────────────┐
│                                              │
│  ✓ All strategies compiled successfully.     │
│                                              │
│  Warnings: 2 (click to view)                 │
│  Compiled at: 14:35:12                       │
│                                              │
│                              [ Close ]       │
└──────────────────────────────────────────────┘
```

On failure:

```
┌─ Compile Failed ────────────────────────────┐
│                                              │
│  ✗ Compilation failed with 1 error.          │
│                                              │
│  ORB.cs(42,18): error CS0103: The name       │
│  'DailyHaltFraction' does not exist in the   │
│  current context.                            │
│                                              │
│  Fix the code and try again.                 │
│                                              │
│                              [ Close ]       │
└──────────────────────────────────────────────┘
```

### Upload flow

1. User drops `ORB.cs` on the drop zone
2. Frontend checks if `ORB.cs` exists in the current file list
3. If yes → confirmation modal: "ORB.cs already exists. Overwrite?"
4. POST to `/strategy-files/upload` with `overwrite=true`
5. If 423 (locked) → show error: "Cannot overwrite — strategy is in use
   by NT8. Stop the strategy from charts first."
6. If success → refresh file list, show toast: "ORB.cs uploaded
   successfully. Click 'Compile All' to recompile."

### Sync-status badges on the Strategies list

The existing Strategies list (the main tab) gains a small status indicator
per strategy:

- ● In sync — `.cs` file exists on VPS, recently compiled
- ● Needs deploy — strategy exists in DB but file missing on VPS, or file
  older than last DB update

Click the badge to jump to the Files tab.

---

## 4. Build order

Strict. Stop and report after each:

1. **VPS agent file endpoints.** Build the file listing, upload,
   delete, and lock-detection endpoints on the VPS agent. Smoke test:
   list strategies, upload a dummy file, delete it.

2. **VPS agent compile endpoint.** Try `NCompile.exe` first. If it works,
   build the compile + polling endpoints. If not, fall back to F5
   pywinauto. Document the decision. Smoke test: compile after making a
   trivial change to one of the strategies (add a comment), verify
   success.

3. **Backend router.** Build the new `strategy_files.py` router that
   proxies to the VPS agent. Includes sync-status logic.

4. **Files page UI.** Build the new tab with file list, drop zone,
   actions menu. No compile or sync-status badges yet — just file
   management.

5. **Compile flow.** Add the "Compile All" button + result modal with
   polling. Test against a file with a deliberate error to verify the
   error display works.

6. **Sync-status badges on Strategies tab.** Add the small indicator on
   each strategy card in the main Strategies list.

7. **End-to-end test.** Upload a new strategy file (use a renamed copy of
   ORB.cs called `TestStrategy.cs`), compile, verify it shows up, run a
   small backtest against it. Then delete TestStrategy.cs and verify it's
   gone.

8. **Update CLAUDE.md.**

---

## 5. What NOT to do in Pass 2

- Don't try to compile *just one strategy*. NT8 recompiles all strategies
  together. The button is "Compile All" and that's it.
- Don't auto-compile on upload. User decides when to compile. (Some users
  upload multiple files in sequence then compile once.)
- Don't restart NT8 to force-unlock files. If a strategy is locked,
  surface the error and let the user handle it. Restarting NT8 silently
  could disrupt other running strategies.
- Don't sync the file's contents back to the DB. The DB tracks the
  strategy's metadata (params, instrument suggestions, etc.). The file
  on disk is the source of truth for the code.
- Don't allow uploading non-`.cs` files. Reject everything else with
  HTTP 400.
- Don't preview the file contents in the UI. Use VS Code for editing
  — this UI is for deployment management only.

---

## 6. CLAUDE.md updates

**backend/CLAUDE.md additions:**
- New router: `strategy_files.py`
- VPS agent path: `C:\Users\Administrator\Documents\NinjaTrader 8\bin\Custom\Strategies\`
- Compile approach used (NCompile.exe vs F5 via pywinauto) and why
- The 256KB upload size limit
- Lock detection mechanism
- New endpoints documented

**frontend/CLAUDE.md additions:**
- New components: FilesTab, FileDropZone, FileActionsMenu, CompileModal,
  SyncStatusBadge
- New sub-tab under Strategies
- The upload / compile / delete flows documented
- Sync-status badge meaning

---

## 7. After Pass 2 ships

Strategy iteration workflow becomes:
1. Edit ORB.cs locally in VS Code
2. Drag the file to the command center's Files tab
3. Click "Compile All"
4. Run a backtest

Total time: 30 seconds. No SSH. No manual file copying. No F5-in-RDP gymnastics.

Then proceed to **strategy improvements pass** — adding the regime filter
to ORB, trailing stop, daily P&L circuit breaker, optional re-entry. Each
iteration deploys via the new manager.

---

*End of Pass 2 spec.*
