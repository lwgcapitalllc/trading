# education/

Course libraries — transcripts and our summaries of the trading courses this
repo's work is built on. One folder per course.

Personal use — content is from paid courses we're members of. Not for
redistribution outside this repo.

## Courses

- [`smc/`](smc/) — SMC engine course (the source material behind the engines).

## One-off videos

- [`learned/`](learned/) — notes from single videos, written by Claude via `/learn <url>`.
  Not a course library: no transcripts kept, one note per video. See that folder's README.

## Adding a course

Rip its videos with [`tools/skool-transcript`](../tools/skool-transcript/) and a
course flag, e.g. `skool-transcript -c ict "Video Title"`. That creates
`education/ict/` with the same `transcripts/`, `summaries/`, and auto-generated
`README.md` layout. Then add a row above.
