# skool-transcript

Rip a clean text transcript off a Skool course video and file it in the SMC
course library so we can read it, search it, and summarize it.

Personal use only: this reads the caption track from a video you already have a
paid, logged-in account for. It does not download the video and it does not
bypass any paywall.

---

## Setup (one time)

From anywhere in the repo:

```bash
bash tools/skool-transcript/setup.sh
```

That installs the dependencies (Homebrew's `yt-dlp`, `ffmpeg`, `python3`) and
links the `skool-transcript` command onto your PATH. If you don't have Homebrew
yet, the script tells you the one line to run first.

---

## Ripping a video

1. Log into Skool in Chrome and open the video.
2. Open DevTools: **Cmd + Option + I** → **Network** tab.
3. Type **`m3u8`** in the filter box, then **press play** (reload the page if it
   was already open).
4. A row appears — `stream.video.skool.com` for most videos, or `luna.loom.com`
   for Loom-hosted ones (both work). Right-click it → **Copy → Copy link
   address**.
5. In Terminal, run it with the **module** the video belongs to:

```bash
skool-transcript -m "Start Here"
```

It asks for the video's title (type what Skool shows), reads the URL from your
clipboard, and files everything under that module in `education/smc/`:

```
education/smc/
├── README.md                          ← auto-generated index, grouped by module
├── modules.txt                        ← the course's module order (edit to reorder)
└── 01-start-here/
    ├── transcripts/
    │   ├── 01-<slug>.txt              ← clean transcript (read / paste to AI)
    │   └── 01-<slug>.en.vtt           ← raw captions with timings
    └── summaries/
        └── 01-<slug>.md              ← summary stub, ready to fill in
```

The **module folder** is numbered by its place in the course (from `modules.txt`),
so a module lands in the right spot even if you rip it out of order. **Videos**
inside a module are numbered in the order you rip them, so rip each module's
videos top to bottom.

---

## Options

```bash
skool-transcript -m "Start Here"              # module given, asks title, URL from clipboard
skool-transcript -m "Start Here" "Trading OS"  # module + title, URL from clipboard
skool-transcript -m "Start Here" "Title" "<url>"  # module + title + URL
skool-transcript "Title"                       # no module -> lands in 00-unsorted/
skool-transcript -c ict -m "Intro" "Title"     # a different course (education/ict/)
skool-transcript -d ~/some/folder ...          # plain dump outside the library
skool-transcript --help                        # usage
```

New module name? Just pass it to `-m` — it's added to `modules.txt` after the
known ones. To fix course order, edit `modules.txt` and re-run the index.

---

## Good to know

- **The URL expires.** Each m3u8 link has a signed token that dies after about a
  day and is tied to your session. Copy a fresh one right before you run; you
  can't reuse or share one.
- **Some videos have no captions.** If a video was uploaded without a caption
  track, there's nothing to pull and the tool says so.
- **403 Forbidden?** The Skool CDN rejects requests with no `Referer`. The tool
  already sends the right headers, so this shouldn't happen — if Skool changes
  their setup, that's the knob to fix.

## Why the m3u8 step is manual

Skool is a JavaScript app: the real video URL is built by the player after you
log in and is signed per-session, so there's no stable link to hand the tool.
You grab the live stream URL once from the Network tab; everything after that is
automated.
