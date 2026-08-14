#!/usr/bin/env python3
"""Regenerate a course's README.md — the library index (e.g. education/smc/).

The library is organised by MODULE: each module is a folder named "NN-slug"
holding its own transcripts/ and summaries/. Module ORDER comes from the
course's modules.txt manifest; videos are listed in their in-module NN order.

This scans every module folder's summaries/*.md front matter (title, status),
groups by module, and writes one grouped table per module. Called by the
skool-transcript tool after each rip; safe to run by hand any time.
"""

import re
import sys
from pathlib import Path


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def front_matter(md_text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", md_text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def read_manifest(lib: Path) -> list:
    """Ordered list of module display names from modules.txt (may be empty)."""
    f = lib / "modules.txt"
    if not f.exists():
        return []
    names = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            names.append(ln)
    return names


BADGE = {"done": "✅ done", "in-progress": "🟡 in progress"}


def module_rows(mod_dir: Path) -> list:
    """Rows for one module folder, in in-module number order."""
    summaries = mod_dir / "summaries"
    transcripts = mod_dir / "transcripts"
    rows = []
    for md in sorted(summaries.glob("*.md")):
        base = md.stem
        num = re.match(r"^(\d+)", base)
        num = num.group(1) if num else "--"
        fm = front_matter(md.read_text(encoding="utf-8"))
        title = fm.get("title", base)
        status = fm.get("status", "to-summarize")
        rel = mod_dir.name
        txt = transcripts / f"{base}.txt"
        t_link = f"[transcript]({rel}/transcripts/{base}.txt)" if txt.exists() else "—"
        s_link = f"[summary]({rel}/summaries/{base}.md)"
        badge = BADGE.get(status, "⬜ to summarize")
        rows.append((num, title, t_link, s_link, badge))
    return rows


def main(root: str) -> None:
    lib = Path(root)

    # every "NN-slug" child dir that holds a summaries/ folder is a module
    mod_dirs = {}
    for d in lib.iterdir():
        if d.is_dir() and re.match(r"^\d+-", d.name) and (d / "summaries").is_dir():
            mod_dirs[slugify(re.sub(r"^\d+-", "", d.name))] = d

    # order modules by the manifest; then any unlisted ones (e.g. 00-unsorted)
    manifest = [slugify(n) for n in read_manifest(lib)]
    ordered = [mod_dirs[s] for s in manifest if s in mod_dirs]
    leftover = sorted(
        (d for s, d in mod_dirs.items() if s not in manifest),
        key=lambda d: d.name,
    )
    ordered += leftover

    total = summarized = 0
    body = []
    for mod_dir in ordered:
        rows = module_rows(mod_dir)
        if not rows:
            continue
        # human module title = manifest name if we have it, else de-slugged folder
        slug = slugify(re.sub(r"^\d+-", "", mod_dir.name))
        title = next(
            (n for n in read_manifest(lib) if slugify(n) == slug),
            re.sub(r"^\d+-", "", mod_dir.name).replace("-", " ").title(),
        )
        total += len(rows)
        summarized += sum(1 for r in rows if r[4].startswith("✅"))
        body.append(f"## {title}")
        body.append("")
        body.append("| # | Video | Transcript | Summary | Status |")
        body.append("|---|-------|-----------|---------|--------|")
        for num, vtitle, t_link, s_link, badge in rows:
            body.append(f"| {num} | {vtitle} | {t_link} | {s_link} | {badge} |")
        body.append("")

    lines = [
        "# SMC Course Library",
        "",
        "Transcripts and summaries of the SMC engine course, organised by module",
        "in course order. Personal use — both members paid for the course; not for",
        "redistribution outside this repo.",
        "",
        "Ripped with [`tools/skool-transcript`](../../tools/skool-transcript/). Each",
        "row links the clean transcript and our summary. This file is",
        "auto-generated — edit the summaries, not this table. Module order lives in",
        "[`modules.txt`](modules.txt).",
        "",
        f"**{total} video(s)** across {len([m for m in ordered if module_rows(m)])} "
        f"module(s) · {summarized} summarized",
        "",
    ]
    if not body:
        lines.append("_Nothing ripped yet._")
        lines.append("")
    else:
        lines += body

    (lib / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {lib / 'README.md'} ({total} entries)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "education/smc")
