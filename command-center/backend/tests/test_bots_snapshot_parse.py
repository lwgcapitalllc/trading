"""Parsing the batched VPS snapshot.

Everything on the Bots page comes from ONE `ssh` call whose output is a set of
`===SECTION===` markers. Two Windows-cmd behaviours have silently merged those sections,
and both failed the same way — no exception, no empty result, just a bot reporting nothing
about itself while showing as RUNNING:

  * `if exist X (type X) & next` binds `next` to the if-block, so a MISSING file swallows
    every section after it;
  * `type` emits no trailing newline, so the next marker lands glued to the file's last
    character (`}===TELEGRAM_START===`) and stops being recognised as a marker at all.

The second only appears once a state file has CONTENT, i.e. after a bot has run once — so
it cannot be caught before the thing it breaks starts mattering. Hence these tests.
"""

import inspect
import json

from routers import bots

# The section NAME is derived from the registry, never spelled out here — the whole point
# of the 2026-08-04 registry change is that a bot is declared once. A literal in the test
# would keep passing while the fetch command asked for a different section entirely.
_SECTION = bots._BOTS[0].state_section  # e.g. "state_sos_fade_demo"
_MARKER = f"==={_SECTION.upper()}==="


def _state_blob() -> str:
    return json.dumps(
        {
            "sos_fade_demo": {
                "name": "SOS Fade",
                "status": "live",
                "started": 1785471363.6,
                "account": 700107749,
                "balance": 2000.0,
                "mt5_link": True,
                "last_updated": "2026-07-31T04:18:43+00:00",
            },
            "last_updated": "2026-07-31T04:18:43.940729",
        },
        indent=2,
    )


def test_a_section_marker_glued_to_the_previous_line_is_still_found():
    """`type` leaves no trailing newline. Without the `echo.` guard in the fetch command
    this is exactly what comes back, and BOTH sections are lost."""
    raw = f'{_MARKER}\n{_state_blob()}===TELEGRAM_START===\n{{"started": 1785468642.7}}'
    sections = bots._parse_sections(raw, "head")
    assert "telegram_start" in sections, "the glued marker was not recognised"
    json.loads(sections[_SECTION])  # must be parseable on its own


def test_bot_state_is_read_out_of_its_section():
    raw = f"{_MARKER}\n{_state_blob()}\n===TELEGRAM_START===\n"
    states = bots._parse_bot_states(bots._parse_sections(raw, "head"))
    assert states["sos_fade_demo"]["balance"] == 2000.0


def test_a_bot_that_has_never_run_leaves_the_later_sections_intact():
    """The empty-state-file case — the first cmd quirk. A bot with no state file yet must
    not take the Telegram row down with it."""
    raw = f'{_MARKER}\n===TELEGRAM_START===\n{{"started": 1785468642.7}}'
    sections = bots._parse_sections(raw, "head")
    assert sections[_SECTION] == ""
    assert json.loads(sections["telegram_start"])["started"] == 1785468642.7


def test_every_declared_state_section_has_a_path_to_fetch_it():
    """The fetch command is BUILT from _BOT_STATE_SECTIONS. A section with no path entry
    would raise KeyError mid-snapshot; a path with no section would never be fetched."""
    assert {s for s, _ in bots._BOT_STATE_SECTIONS} == set(bots._BOT_STATE_PATHS)


def test_schtasks_paths_resolve_to_task_names():
    """schtasks reports `\\SYS_MONITOR`, not `SYS_MONITOR`. Matching the raw value meant
    _parse_tasks returned {} and EVERY job read UNKNOWN from the day it was written."""
    raw = (
        "===TASKS===\n"
        '"\\SYS_MONITOR","N/A","Disabled"\n'
        '"\\SYS_TELEGRAM","N/A","Running"\n'
        '"\\Folder\\SYS_DEADMAN","N/A","Ready"\n'
    )
    tasks = bots._parse_tasks(bots._parse_sections(raw, "head"))
    assert tasks["SYS_MONITOR"] == "Disabled"
    assert tasks["SYS_TELEGRAM"] == "Running"
    assert tasks["SYS_DEADMAN"] == "Ready"  # nested folders resolve too


def test_the_bot_key_is_what_identifies_the_process():
    """`runner.py --bot <key>` — the key is on the commandline. Matching on the script name
    would make every live bot indistinguishable the moment there are two."""
    snap = {"procs": r"python  C:\trading\algos\live\runner.py --bot sos_fade_demo"}
    assert bots._is_python_running(snap, "sos_fade_demo")
    assert not bots._is_python_running(snap, "some_other_bot")


def test_an_armed_watchdog_is_not_reported_as_stopped():
    """`Ready` is schtasks for ARMED — enabled, waiting for its next trigger — and it is the
    state a once-a-minute watchdog is in for 59 seconds out of every 60.

    🔴 It was folded into STOPPED alongside every unrecognised value, so `GET /bots/snapshot`
    said the dead-man switch was STOPPED while the box said `Status: Ready, Scheduled Task
    State: Enabled, Last Result: 0` (MEASURED 2026-08-21). The page was unharmed — both fell
    to the same gold "waiting for next trigger" dot — but the API is what the tooling, the
    tests and anyone with curl reads.

    The property that actually matters is the SPLIT, not the word: while the two shared a
    value, a genuinely odd status was indistinguishable from a healthy one. So this asserts
    all four map apart, and would go red on any change that collapsed them again.

    Watched RED by mutation: deleting the `Ready` branch fails this on ARMED alone.
    """
    statuses = {}
    for raw in ("Running", "Ready", "Disabled", "Queued", ""):
        # Mirrors the mapping in _snapshot; the branch under test is the elif chain there.
        if raw == "Running":
            statuses[raw] = "RUNNING"
        elif raw == "Disabled":
            statuses[raw] = "DISABLED"
        elif raw == "Ready":
            statuses[raw] = "ARMED"
        elif raw:
            statuses[raw] = "STOPPED"
        else:
            statuses[raw] = "UNKNOWN"

    # The real router must agree with that table — read it out of the source rather than
    # trusting this copy, or the test passes while the code it describes has moved.
    src = inspect.getsource(bots)
    assert 't_status == "Ready"' in src, "the Ready branch is gone — armed reads as stopped again"
    assert 'status = "ARMED"' in src

    assert statuses["Ready"] == "ARMED"
    assert statuses["Ready"] != statuses["Queued"], "armed and odd must not share a value"
    assert len({statuses[k] for k in statuses}) == 5, "each schtasks state needs its own answer"


# ── the box's own ledger rides on the same connection ────────────────────────────────────────
#
# 🔴 **The account's balance and the bots' realised results are subtracted from each other, and
# until 2026-09-09 they were read off two different clocks** — the balance seconds old over SSH,
# the bots' figures out of this machine's committed archive, which is behind by however long ago
# the box committed AND this machine pulled (MEASURED at 66 minutes, no upper bound). A trade
# closed inside that gap was in the balance and in no bot's row, and rendered as money nobody's
# bot made. These pin the live top-up that closes it.


def test_what_the_fetch_ASKS_FOR_is_what_the_parse_LOOKS_FOR(monkeypatch):
    """MUTATION: spell the section differently in the fetch than in the parse. RUN — red.

    🔴 This is the pairing that fails in SILENCE. A section fetched under one name and looked
    for under another is always absent — which is indistinguishable from a box that could not
    be reached, i.e. exactly the state the whole read exists to move away from. Nothing errors
    and the page looks healthy.

    ⚠ It drives the REAL fetch and answers it the way the box would, rather than grepping the
    source for a marker — a source check compares the fetch against a literal in this file, and
    a literal can agree with itself for ever."""
    sent: list[str] = []
    row = {
        "ts": "2026-09-09T07:15:02+00:00",
        "kind": "trade",
        "event": "closed",
        "pnl_usd": 1305.58,
    }

    def fake_ssh(cmd, timeout=60):
        sent.append(cmd)
        if "===TASKS===" in cmd:
            return ""
        # Answer every marker the command asked for; put a trade row under each LEDGER one,
        # exactly as findstr would (path prefix and all).
        out = []
        for part in cmd.split(" & "):
            part = part.strip()
            if not part.startswith("echo ==="):
                continue
            marker = part[len("echo ") :]
            out.append(marker)
            if marker.startswith("===LEDGER_"):
                out.append(r"C:\trading\x\decisions-2026-09-09.jsonl:" + json.dumps(row))
        return "\n".join(out)

    monkeypatch.setattr(bots, "_ssh", fake_ssh)
    snap = bots._fetch_vps_snapshot()
    live = bots._parse_live_trades(snap)

    assert set(live) == {b.key for b in bots._BOTS}
    for b in bots._BOTS:
        assert live[b.key] == [row], f"{b.key}: fetched under a name the parse does not read"


def _ledger_command(monkeypatch) -> str:
    """The part of the real fetch command that reads the ledgers.

    🔴 **Read off the COMMAND, never off `inspect.getsource`.** The first version of these two
    tests grepped the function's source for `findstr /c:pnl_usd` — and that string is also in
    the COMMENT above the line, so replacing the whole filter with `type` left them GREEN. **A
    test that greps a function's source is reading the prose as readily as the code**, which is
    the trap `test_deploy_commit_gate.py` hit on its own docstring."""
    sent: list[str] = []

    def fake_ssh(cmd, timeout=60):
        sent.append(cmd)
        return ""

    monkeypatch.setattr(bots, "_ssh", fake_ssh)
    bots._fetch_vps_snapshot()
    return sent[-1]


def test_the_fetch_asks_for_TRADE_rows_only_and_not_the_whole_ledger(monkeypatch):
    """MUTATION: `type` the whole file instead of filtering. RUN — red.

    A day's decision record is ~120 KB of bar rows against ~500 bytes of trades, and this rides
    on an endpoint the Bots page POLLS. The filter is what makes freshness cost nothing."""
    cmd = _ledger_command(monkeypatch)
    for b in bots._BOTS:
        asks = [p for p in cmd.split(" & ") if f"\\{b.instance_dir}\\ledger\\" in p]
        assert asks, f"{b.key}: nothing reads its ledger"
        for part in asks:
            assert part.strip().startswith("findstr /c:pnl_usd "), part


def test_the_live_window_is_BOUNDED_by_month_rather_than_reading_all_history(monkeypatch):
    """MUTATION: one wildcard over the whole ledger folder. RUN — red.

    The whole of both bots' trade history is 3.1 KB today, so a full read would be free — and
    it grows with every trade for ever, on an endpoint the page polls. A window bounded by month
    stays the same size whatever the history reaches."""
    cmd = _ledger_command(monkeypatch)
    assert "decisions-*.jsonl" not in cmd
    for b in bots._BOTS:
        asks = [p for p in cmd.split(" & ") if f"\\{b.instance_dir}\\ledger\\" in p]
        assert len(asks) == bots._LIVE_LEDGER_MONTHS
    months = bots._ledger_months(bots.datetime(2026, 1, 15, tzinfo=bots.timezone.utc))
    assert months == ["2026-01", "2025-12"]  # the year rolls back, not just the month


def test_a_section_the_box_did_not_answer_is_NOT_an_empty_trade_list():
    """MUTATION: return `[]` for a missing section. RUN — red.

    🔴 The whole value of the live read is that it says WHETHER it happened. `None` means the
    box could not be asked, so that bot's figures are as stale as the last sync; `[]` means it
    answered and the bot has closed nothing this month, which is the ordinary case. Collapsing
    them prints a confident split off a record that may be an hour behind the balance."""
    key = bots._BOTS[0].key
    assert bots._parse_live_trades({})[key] is None
    assert bots._parse_live_trades({bots._ledger_section(key): ""})[key] == []


def test_findstrs_FILE_PREFIX_is_stripped_and_a_windows_colon_does_not_confuse_it():
    """MUTATION: split each line on `:` and take the last part. RUN — red.

    `findstr` over a wildcard prefixes every hit with its path, and a Windows path carries a
    drive colon — while the JSON is full of colons too. The row is found by its opening brace,
    which a filename cannot contain."""
    key = bots._BOTS[0].key
    row = {
        "ts": "2026-09-09T07:15:02+00:00",
        "kind": "trade",
        "event": "closed",
        "pnl_usd": 1305.58,
    }
    line = (
        r"C:\trading\algos\markets\fx\instances\x\ledger\decisions-2026-09-09.jsonl:"
        + json.dumps(row)
    )
    out = bots._parse_live_trades({bots._ledger_section(key): line})
    assert out[key] == [row]


def test_the_string_filter_does_the_cheap_half_and_the_PARSED_fields_decide():
    """MUTATION: keep every line that parsed. RUN — red.

    `pnl_usd` is a PREFILTER chosen because only a closed trade carries it today — checked
    against the whole archive. A future row type carrying that field must cost a parse and
    nothing else, never a wrong sum. Same rule the archive reader follows."""
    key = bots._BOTS[0].key
    section = (
        "\n".join(
            json.dumps(r)
            for r in [
                {"ts": "1", "kind": "trade", "event": "closed", "pnl_usd": 10.0},
                {"ts": "2", "kind": "trade", "event": "opened", "pnl_usd": 0.0},
                {"ts": "3", "kind": "summary", "pnl_usd": 999.0},
            ]
        )
        + '\n{"ts": "4", "kind": "trade", "event": "closed", "pnl_u'
    )  # a torn last line
    out = bots._parse_live_trades({bots._ledger_section(key): section})
    assert [r["pnl_usd"] for r in out[key]] == [10.0]
