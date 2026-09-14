"""Where did this machine's Claude Code tokens go? Reads the local session logs; changes nothing.

usage: python3 tools/token-usage/usage_report.py [--days 7] [--project-dir <path>]

Reads ~/.claude/projects/<this repo's folder>/ — the transcripts Claude Code writes for sessions
started in this repo ON THIS MACHINE. Each person runs it on their own machine; nothing is shared.

What the numbers are:
  * "input processed" is every token the model READ, summed over every turn: fresh input + cache
    reads + cache writes. Every turn re-reads the whole conversation, so this is roughly
    (conversation size x number of turns) — the figure long sessions blow up.
  * Byte counts (tool output, auto-loaded docs) are bytes in the log, not tokens. Rough rule:
    ~4 bytes per token for English text.
"""

import argparse
import collections
import datetime
import glob
import json
import os
import re
import subprocess
import time

M = 1e6


def project_dir(override):
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    top = subprocess.run(
        ["git", "-C", here, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    repo = os.path.dirname(top) if top.endswith("/.git") else top
    slug = re.sub(r"[^A-Za-z0-9]", "-", repo)
    return os.path.expanduser(f"~/.claude/projects/{slug}")


def ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


BASH_KINDS = (
    "run_all_tests",
    "scripts/test.sh",
    "pytest",
    "git diff",
    "git log",
    "git show",
    "grep",
    "rg ",
    "sed -n",
    "cat ",
    "curl",
    "ssh ",
    "npx tsc",
    "npm",
    "find ",
)


def bash_kind(cmd):
    first = cmd.strip().split("\n")[0]
    for k in BASH_KINDS:
        if k in first:
            return k.strip()
    return "other"


def _typed_by_a_person(d, cont):
    """A message a person typed — not a tool result, a system reminder, or a compaction summary.

    ⚠ A compaction summary is logged as a user message, so counting every user message counted
    each compaction as a prompt (the first version of this report did exactly that).
    """
    if d.get("isMeta") or d.get("isCompactSummary"):
        return False
    if isinstance(cont, str):
        return not cont.startswith("<")
    if isinstance(cont, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in cont):
            return False
        texts = [c.get("text", "") for c in cont if isinstance(c, dict) and c.get("type") == "text"]
        return bool(texts) and not texts[0].startswith("<")
    return False


def scan(path, agg):
    msgs, uses = {}, {}
    prompts = compacts = 0
    t0 = t1 = None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t = ts(d.get("timestamp", ""))
            if t:
                t0 = t if t0 is None else min(t0, t)
                t1 = t if t1 is None else max(t1, t)
            if d.get("isCompactSummary"):
                compacts += 1
            kind, m = d.get("type"), d.get("message") or {}
            if kind == "assistant":
                if m.get("id"):
                    msgs[m["id"]] = m.get("usage") or {}
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        uses[c.get("id")] = (c.get("name"), c.get("input") or {})
                        if c.get("name") in ("Agent", "Task"):
                            agg["agents"][
                                (c.get("input") or {}).get("model") or "same as session"
                            ] += 1
            elif kind == "user":
                cont = m.get("content")
                if _typed_by_a_person(d, cont):
                    prompts += 1
                if isinstance(cont, list):
                    for c in cont:
                        if not isinstance(c, dict) or c.get("type") != "tool_result":
                            continue
                        name, inp = uses.get(c.get("tool_use_id"), ("?", {}))
                        n = len(json.dumps(c.get("content")))
                        if name == "Bash":
                            agg["bash"][bash_kind(inp.get("command", ""))] += n
                        elif name == "Read":
                            agg["read"][inp.get("file_path", "?")] += n
                        else:
                            agg["tool"][name] += n
            elif kind == "attachment":
                a = d.get("attachment") or {}
                if a.get("type") == "nested_memory":
                    agg["docs"][a.get("path", "?")] += 1
    ctx = [
        u.get("input_tokens", 0)
        + u.get("cache_read_input_tokens", 0)
        + u.get("cache_creation_input_tokens", 0)
        for u in msgs.values()
    ]
    return {
        "name": os.path.basename(path)[:8],
        "input": sum(ctx),
        "out": sum(u.get("output_tokens", 0) for u in msgs.values()),
        "rebuilt": sum(
            u.get("cache_creation_input_tokens", 0)
            for u in msgs.values()
            if u.get("cache_creation_input_tokens", 0) > 100_000
        ),
        "turns": len(msgs),
        "first": ctx[0] if ctx else 0,
        "peak": max(ctx) if ctx else 0,
        "prompts": prompts,
        "compacts": compacts,
        "hours": (t1 - t0) / 3600 if t0 else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--project-dir")
    a = ap.parse_args()
    root = project_dir(a.project_dir)
    if not os.path.isdir(root):
        raise SystemExit(f"no session logs at {root} — pass --project-dir")
    cutoff = time.time() - a.days * 86400
    agg = {k: collections.Counter() for k in ("bash", "read", "tool", "docs", "agents")}
    mains, subs = [], []
    for p in glob.glob(root + "/*.jsonl") + glob.glob(root + "/*/subagents/*.jsonl"):
        if os.path.getmtime(p) >= cutoff:
            (subs if "/subagents/" in p else mains).append(scan(p, agg))
    if not mains:
        raise SystemExit(f"no sessions in the last {a.days:g} days under {root}")

    tot = sum(r["input"] for r in mains + subs)
    print(f"LAST {a.days:g} DAYS — {len(mains)} sessions, {len(subs)} subagents ({root})")
    print(
        f"  input processed: {tot / M:,.0f}M  (sessions {sum(r['input'] for r in mains) / M:,.0f}M,"
        f" subagents {sum(r['input'] for r in subs) / M:,.0f}M)"
    )
    print(
        f"  output: {sum(r['out'] for r in mains + subs) / M:,.1f}M   "
        f"memory rebuilt after idle (>100k at once): {sum(r['rebuilt'] for r in mains) / M:,.0f}M"
    )
    firsts = sorted(r["first"] for r in mains if r["first"])
    if firsts:
        print(f"  context before your first message: median {firsts[len(firsts) // 2]:,} tokens")
    print()
    print("BIGGEST SESSIONS")
    print("  input    share  msgs  turns  compactions  hours  peak ctx")
    for r in sorted(mains, key=lambda r: -r["input"])[:10]:
        print(
            f"  {r['input'] / M:6.0f}M  {100 * r['input'] / tot:4.0f}%  {r['prompts']:4d}  {r['turns']:5d}"
            f"  {r['compacts']:11d}  {r['hours']:5.0f}  {r['peak']:8,}  {r['name']}"
        )
    print()
    print("DOCS LOADED AUTOMATICALLY (times loaded x size today)")
    for p, n in agg["docs"].most_common(10):
        size = os.path.getsize(p) if os.path.exists(p) else 0
        flag = "  <- over 40 KB" if size > 40_000 else ""
        print(f"  {n:5d} x {size / 1000:5.0f} KB  {p}{flag}")
    print()
    print("TOOL OUTPUT INTO CONTEXT (MB)")
    for k, v in agg["bash"].most_common(8):
        print(f"  {v / M:6.1f}  shell: {k}")
    for k, v in agg["read"].most_common(5):
        print(f"  {v / M:6.1f}  read: {k}")
    print()
    print("SUBAGENTS LAUNCHED, BY MODEL:", dict(agg["agents"]) or "none")
    print()
    print("WHAT TO LOOK AT")
    long_ = [r for r in mains if r["hours"] > 24]
    if long_:
        print(
            f"  - {len(long_)} session(s) open more than a day: start a fresh one per task (/clear)."
        )
    big = [
        p for p, _ in agg["docs"].most_common() if os.path.exists(p) and os.path.getsize(p) > 40_000
    ]
    if big:
        print(
            f"  - {len(big)} auto-loaded doc(s) over 40 KB: move detail into their notes/ folders."
        )
    if agg["agents"].get("same as session"):
        print(
            "  - subagents ran on the session's model: pass a cheaper model for routine searches."
        )


if __name__ == "__main__":
    main()
