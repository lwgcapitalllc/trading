---
name: learn
description: Watch a video (URL or local file) and file a durable note about it. Use when the user types /learn <url>, or pastes a video link and asks you to learn/study/take notes on it. Wraps the `watch` skill for the actual watching, then writes the note to disk.
argument-hint: "<video-url-or-path> [what to focus on]"
allowed-tools: Skill, Bash, Read, Write, Edit, Glob
user-invocable: true
---

# /learn

Watch a video, then leave a written record of it. `/watch` answers a question and the answer scrolls away. `/learn` answers *and* files a note, so the video becomes something searchable months later.

## Step 0 — is learning mode set up on this machine?

`/learn` ships with this repo. The `watch` skill it drives does **not** — it is third-party and installed per machine. Check once per session:

```bash
test -f ~/.claude/skills/watch/scripts/watch.py && echo installed
```

If that prints nothing, stop and tell the user to run the one-time setup, then wait:

```bash
bash scripts/setup_learning_mode.sh
```

Do not try to work around a missing install by shelling out to `yt-dlp` or `ffmpeg` yourself. The setup script is the one path, and re-running it is also how the watch skill is updated.

If it printed `installed`, say nothing and continue.

## Step 1 — parse the input

Split the argument into:
- **source** — a URL (YouTube, Loom, TikTok, X, Vimeo, most yt-dlp sites) or a local path (`.mp4`, `.mov`, `.mkv`, `.webm`).
- **focus** — anything the user said after the source. Optional. If present it decides what the note emphasises; if absent, take general notes.

If no source is present, ask for one. Do not guess.

## Step 2 — check for an existing note first

```bash
grep -rl "<source-url>" <NOTES_DIR> 2>/dev/null
```

If a note for this exact source already exists, **read it and say so** before doing anything else. Ask whether to update it or leave it. Re-watching a video you already filed is wasted tokens.

`<NOTES_DIR>` is resolved in Step 4.

## Step 3 — watch it

Invoke the bundled `watch` skill on the source (Skill tool, `skill: "watch"`). It handles setup preflight, captions, download, frames and transcript. Follow its instructions in full, including reading every frame it prints.

Detail mode:
- Default to `balanced` — let the watch skill use its own default. Do not pass `--detail` unless there's a reason.
- If the video is **over ~20 minutes** and the user gave no focus, say so and offer `--detail transcript` (no frames, near-free, still gives you everything spoken) before burning image tokens on a sparse visual scan. A talking-head or podcast rarely needs frames.
- If the user's focus is about something **on screen** — code, a chart, a UI, slides — keep frames, and use `--resolution 1024` so on-screen text is readable.

## Step 4 — resolve where the note goes

In order:

1. If the current working directory is inside a git repo, `NOTES_DIR = <repo-root>/education/learned/`.
2. Otherwise, `NOTES_DIR = ~/.claude/learned/`.

```bash
git rev-parse --show-toplevel
```

Create the directory if it does not exist. Filename: `YYYY-MM-DD-<slug>.md`, where the slug is the video title lowercased, non-alphanumerics collapsed to hyphens, trimmed to ~60 characters.

## Step 5 — write the note

The note is the deliverable. Write it with the Write tool. Shape:

```markdown
---
source: <the URL or absolute local path>
title: <video title>
uploader: <channel / author, if known>
duration: <MM:SS>
watched: <YYYY-MM-DD>
detail: <the detail mode used>
focus: <what the user asked for, or "general">
---

# <Title>

<One paragraph. What this video is and who it is for. Plain English.>

## What it covers

<The substance, in order, with timestamps. This is the part that has to survive
without the video. Do not write "he explains the setup" — write what the setup IS.
A reader who never watches this should be able to act on this section.>

## Worth acting on

<Only if there is something. Concrete things this suggests trying, building or
checking — in the current project where that applies. If there is nothing
actionable, delete this heading rather than padding it.>

## Not worth your time

<Only if true. Sections to skip, claims that are oversold, things it got wrong.
Delete the heading if the video is clean.>
```

Rules for the note:
- **Facts, not gestures.** "Uses a 200-day MA as the trend filter" beats "discusses trend filtering". A note that only says what topics were mentioned is worthless.
- **Timestamps on anything specific**, so the video can be re-entered at the right place.
- **Quote sparingly** — only a line that would lose its meaning if paraphrased.
- **Do not paste the transcript.** Ever. Synthesise it.
- **Say when the video didn't answer something** the user's focus asked about. An absence is a finding.
- Length follows content. A dense 40-minute technical talk earns a long note; a 3-minute demo earns ten lines. Do not inflate.

## Step 6 — answer in chat, short

Say what the video was, the two or three things that actually matter, and the path to the note. Under ten lines. The file carries the detail — do not repeat it in chat.

If the note landed in a git repo, mention that it is untracked and offer to commit it. Do not commit unprompted.

## Step 7 — clean up

The watch script prints a working directory. Delete it with `rm -rf <dir>` unless the user is likely to ask follow-ups about the same video.

## Follow-ups

If the user asks another question about a video you just learned in this session, **do not re-run anything** — the frames and transcript are already in your context. Answer from them, and update the note file if the answer adds something durable.
