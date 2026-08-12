# education/learned/

Notes from videos, written by Claude via `/learn`.

One file per video, named `YYYY-MM-DD-<slug>.md`. Each carries the source link, the
title, how long it was, and the date it was watched, then: what the video covers with
timestamps, what is worth acting on, and what to skip.

Unlike [`smc/`](../smc/) and the other course folders, these are not course libraries —
they are one-off videos somebody dropped a link to. No transcripts are kept, only the
note.

## Using it

```
/learn https://youtu.be/<id>
/learn https://youtu.be/<id> what's their entry rule?
/learn ~/Movies/screen-recording.mov what breaks here?
```

The optional second part decides what the note emphasises.

⚠ **One-time setup per machine** — `/learn` ships with this repo but the video tools
under it do not:

```bash
bash scripts/setup_learning_mode.sh
```

## Why the notes are committed

The point is that both of us read the same one. A video watched and summarised into a
chat window is gone the moment the session ends, and the next person re-watches it.
These are also the cheap half — the frames are the whole token cost, so a note on disk
is what stops the same video being paid for twice.

Read the note before re-running `/learn` on a link that already has one.
