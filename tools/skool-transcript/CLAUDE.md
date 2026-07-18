# CLAUDE.md — tools/skool-transcript/

**Purpose:** Standing instructions for this tool. Read before touching it.

## What this is

`skool-transcript` is a Bash CLI that pulls the caption track off a Skool course
video, cleans it to plain text, and files it in a **course library** under
`<repo>/education/<course>/` (course defaults to `smc`). Built 2026-07-18 for
Aaron. The SMC engine work in this repo is built around the SMC course, so the
library is the source material; the tool is how it gets in. `education/` is a
parent so more courses can be added later (`-c <course>`). Shared with Aaron's
brother — this repo is the source of truth for both the tool and the library.

Authorized use only: it reads captions from videos the user already has a paid,
logged-in account for. It does not download video and does not bypass a paywall.

## How it works

1. The user grabs the signed HLS manifest URL from Chrome DevTools → Network tab
   (filter `m3u8`). Manual and unavoidable — Skool is a JS SPA and the URL is
   built client-side, per-session, expiring in ~1 day.
2. **Two hosts, auto-detected.** Videos on Skool's own player
   (`stream.video.skool.com`) carry captions inside the HLS manifest — `yt-dlp`
   pulls them, and the **`Referer: https://www.skool.com/` and `Origin` headers
   are load-bearing** (without them the CDN returns 403; do not remove them).
   Videos embedded from **Loom** (`luna.loom.com`) do NOT ship captions in the
   stream — the tool reads the Loom video id out of the URL and fetches the
   caption `.vtt` from Loom's GraphQL `FetchVideoTranscript` endpoint. The `-m`
   URL the user pastes works for both; the tool branches on the host.
3. An inline `python3` pass strips WEBVTT timings, cue numbers, inline tags, and
   consecutive duplicate lines, producing the clean `.txt`.
4. The library is organised by **module**. `-m "<Module>"` picks the module;
   its folder is `NN-<module-slug>` where NN is the module's position in
   `education/<course>/modules.txt` (the course-order manifest — a module ripped
   late still lands in the right place). Files inside are `MM-<title-slug>` where
   MM is the next number within that module. Without `-m`, the video goes to
   `00-unsorted/`. A summary stub is created from `templates/summary.md`, and
   `lib_index.py` regenerates that course's grouped `README.md`.

The tool finds the repo by resolving its own (symlinked) path — so the default
library location is correct in any clone, for any user. `-d` bypasses the
library and dumps to a plain folder.

## Layout

- `skool-transcript` — the tool (canonical copy; PATH symlink points here)
- `setup.sh` — one-command install: brew deps + link onto PATH
- `lib_index.py` — regenerates the grouped `education/<course>/README.md` index
- `templates/summary.md` — the per-video summary stub
- `README.md` — user-facing how-to (written for the brother)

The course-order manifest (`modules.txt`) lives in the library
(`education/<course>/modules.txt`), not here — it is course data, not tool code.

## Dependencies

`yt-dlp`, `ffmpeg`, `python3` (Homebrew), plus `pbpaste` (macOS built-in).
macOS-only as written.

## If you change it

- Keep the two HTTP headers. They are the reason it works.
- The token in the m3u8 URL expires (~1 day) and is per-session — never hardcode
  one, never commit one.
- The tool is standalone. Nothing to do with the trading engines/algos/command-
  center. Do not wire it into any subsystem.
- The library (`education/<course>/`) holds transcripts of a paid course —
  personal use, not for redistribution outside this repo.
