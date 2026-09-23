"""The REV SETUP student feed — and the one property it exists to guarantee.

**What this is for.** The user's students read a Telegram channel (MPC Signals) and he wants the
rev-setup bot's own behaviour in it: a setup forming, where the entry would be, the limit going on,
each stop move, and how it ended. `algos/tools/rev_setup_feed.py` renders that from the bot's
decision records.

🔴 **THE TEST THAT MATTERS IS THE FIRST ONE.** The bot's own Telegram messages carry the lot size
and the dollar risk, so a channel of students must never be fed them — that publishes one owner's
position sizing, and his balance by arithmetic, to a class. The feed therefore reads a WHITELIST of
fields per record, and `test_no_account_number_can_ever_reach_the_channel` feeds records stuffed
with money and asserts not one of those digits appears in any rendered line.

**Watched RED (2026-09-23), seven mutations, each reddening only its own test:**
- adding `"lots"` to the `trade_opened` whitelist and rendering it -> the money test, and the
  whitelist test beside it;
- publishing a stage whenever it is in `STAGES` rather than when it RISES -> the stage test
  (it would announce the same stage on every bar for hours);
- advancing the cursor past a send that failed -> the retry test;
- dropping the minimum stop move -> the cosmetic-nudge test;
- dropping the repeat guard -> the one-message-per-trail-move test;
- sizing a student's add off the bot's own estimate rather than the fill the message shows ->
  the add-multiple test (it would publish 0.47x where the price in front of them allows 0.32x);
- repeating "risk off" on every trail step -> the said-once test.

⚠ **The retry test earned its keep.** The first version rolled back only the line cursor after a
failed send, leaving the stage and last-stop cursors ahead — so the retried run suppressed the very
message that had not gone out, as a duplicate. The whole state is snapshotted now.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
for _p in (_ALGOS / "tools", _ALGOS / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import rev_setup_feed as feed  # noqa: E402

# Distinctive values, so a leak is unmistakable in an assertion rather than arguable.
_LOTS = 0.24
_RISK_USD = 545.71
_PNL = -123.45
_TICKET = 365501068


def _cfg(tmp_path, **over):
    path = tmp_path / "rev_feed.json"
    doc = {"enabled": True, "bot": "sos_fade_1", "chat": "-100students", "label": "REV SETUP"}
    doc.update(over)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _ledger(tmp_path, *rows, name=None):
    """A decisions file shaped like the real one, and the state cursor already set to line 0 —
    so the rows below are NEW rather than a first sight of the file."""
    from datetime import datetime, timezone

    d = tmp_path / "ledger"
    d.mkdir(exist_ok=True)
    day = datetime.now(timezone.utc).date()
    path = d / (name or f"decisions-{day}.jsonl")
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (d / feed.STATE_NAME).write_text(json.dumps({"lines": {path.name: 0}}), encoding="utf-8")
    return d


@pytest.fixture(autouse=True)
def _no_real_bot(monkeypatch):
    """Never resolve a real bot folder: these tests own their ledger and their symbol."""
    monkeypatch.setattr(feed, "_symbol", lambda bot: "XAUUSD")


def _posted(monkeypatch, *, fail_from=None):
    """Capture what would be sent. `fail_from` makes the Nth send (0-based) fail, as Telegram
    refusing a message does — `send_telegram_id` answers None."""
    sent = []

    def _send(text, kind, chat_id="", token_key="", reply_to=None, markdown=True, account=None):
        if fail_from is not None and len(sent) >= fail_from:
            return None
        sent.append((chat_id, text, kind))
        return 11

    import notify

    monkeypatch.setattr(notify, "send_telegram_id", _send)
    return sent


# ── the property this feed exists to guarantee ───────────────────────────────


def test_no_account_number_can_ever_reach_the_channel(tmp_path, monkeypatch):
    """🔴 THE RULE. Every record here carries money; not one of those numbers may be rendered.

    MUTATION: add `lots` to the `trade_opened` whitelist and render it -> red.
    """
    # ⚠ The field names and the two `trade` shapes are copied from `live/ledger.py`'s writers,
    # not invented here: an open and a close share `kind: "trade"` and differ by `event`.
    rows = [
        {
            "kind": "trade",
            "event": "opened",
            "dir": "SHORT",
            "symbol": "XAUUSD.p",
            "price": 4369.93,
            "stop": 4391.88,
            "tp1": 4351.2,
            "lots": _LOTS,
            "risk_pct": 5.0,
            "risk_usd": _RISK_USD,
            "ticket": _TICKET,
            "intent": "primary",
        },
        {
            "kind": "trade",
            "event": "closed",
            "dir": "SHORT",
            "price": 4369.63,
            "pnl_usd": _PNL,
            "r": 0.62,
            "reason": "stop moved to break even",
            "lots": _LOTS,
            "gross_usd": 99.9,
            "swap_usd": -1.5,
            "commission_usd": -2.4,
            "ticket": _TICKET,
        },
        {
            "kind": "event",
            "event": "order_placed",
            "dir": -1,
            "price": 4369.93,
            "stop": 4391.88,
            "lots": _LOTS,
            "ticket": _TICKET,
            "intent": "primary",
        },
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    assert feed.run(config_path=_cfg(tmp_path)) == 0
    blob = " | ".join(t for _, t, _ in sent)
    assert blob, "nothing was rendered, so this test proved nothing"
    for forbidden in ("0.24", "545", "123", "365501068", "5.0%", "$"):
        assert forbidden not in blob, f"{forbidden!r} reached the channel: {blob}"
    assert "4,369.93" in blob and "4,391.88" in blob and "+0.62R" in blob


def test_the_whitelist_itself_names_no_money_field():
    """Belt to the test above's braces: the list is the mechanism, so pin the list.

    A future edit that adds a money field is a two-line change — this is the line that refuses it.
    """
    banned = {
        "lots",
        "risk_pct",
        "risk_usd",
        "risk_pct_realised",
        "pnl_usd",
        "gross_usd",
        "swap_usd",
        "commission_usd",
        "balance",
        "equity",
        "ticket",
    }
    for kind, fields in feed._RENDER.items():
        assert not (banned & set(fields)), f"{kind} whitelists a money field"


# ── the forming half, off the per-bar records ────────────────────────────────


def test_a_stage_is_published_when_it_RISES_and_not_on_every_bar(tmp_path, monkeypatch):
    """The bar records carry each side's stage, so a rise is the "setup forming" event. Publishing
    on presence instead would announce the same stage every bar for hours.

    MUTATION: publish whenever `stage in STAGES` -> red.
    """
    rows = [
        {"kind": "bar", "s_stage": 2, "short_edge": 4369.93, "s_arm_src": "SWP"},
        {"kind": "bar", "s_stage": 2, "short_edge": 4369.93, "s_arm_src": "SWP"},
        {"kind": "bar", "s_stage": 3, "short_edge": 4369.93, "s_arm_src": "SWP"},
        {"kind": "bar", "s_stage": 3, "short_edge": 4369.93, "s_arm_src": "SWP"},
        {"kind": "bar", "s_stage": 4, "short_edge": 4369.93, "s_arm_src": "SWP"},
        {"kind": "bar", "s_stage": 0},
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    texts = [t for _, t, _ in sent]
    assert len(texts) == 3
    # The bot's own shape, with his label and no live/demo tag: the count is the same three
    # confluences the bot counts, not the four internal stages.
    assert texts[0].startswith("\U0001f440 SETUP FORMING \u00b7 SHORT")
    assert "REV SETUP \u00b7 XAUUSD \u00b7 2 of 3" in texts[0]
    assert "Sweep \u00b7 SOS confirmed \u00b7 not tagged yet" in texts[0]
    assert "3 of 3" in texts[1] and "tagged the 50%" in texts[1]
    assert "3 of 3" in texts[2] and "tagged the 61.8%" in texts[2]
    # Stage 4 is the one a student acts on, so it gets the entry-zone icon rather than the eyes.
    assert texts[2].startswith("\U0001f3af ENTRY ZONE \u00b7 SHORT")
    assert all("Entry 4,369.93" in t for t in texts)


def test_a_liquidity_sweep_alone_is_never_published(tmp_path, monkeypatch):
    """Stage 1 fires constantly. A channel that pings all day is muted before the day it matters."""
    d = _ledger(tmp_path, {"kind": "bar", "l_stage": 1, "long_edge": 4300.0})
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert sent == []


# ── the rest of the bot's own behaviour ──────────────────────────────────────


def test_each_kind_of_record_says_what_the_bot_DID(tmp_path, monkeypatch):
    rows = [
        {"kind": "event", "event": "order_placed", "dir": 1, "price": 4300.5, "stop": 4290.0},
        {"kind": "event", "event": "stop_moved", "was": 4290.0, "now": 4300.5, "ticket": _TICKET},
        {
            "kind": "blocked",
            "dir": -1,
            "edge": 4369.93,
            "reasons": ["Final-hour rule - no new entries 16:00-18:00 New York."],
        },
        {"kind": "missed", "dir": 1, "edge": 4300.5, "met": 2, "of": 3},
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    texts = [t for _, t, _ in sent]
    assert texts[0].startswith("\U0001f3af BUY LIMIT RESTING \u00b7 LONG")
    assert "Entry 4,300.50 \u00b7 stop 4,290.00" in texts[0]
    assert "4,290.00 \u2192 4,300.50" in texts[1] and texts[1].startswith("\U0001f512 STOP MOVED")
    assert texts[2].startswith("\U0001f6ab BLOCKED \u00b7 SHORT") and "Final-hour rule" in texts[2]
    assert "It would have entered at 4,369.93" in texts[2]
    assert texts[3].startswith("\U0001f44b NO TRADE \u00b7 LONG")
    assert "Setup died at 2 of 3" in texts[3]


def test_a_cosmetic_stop_nudge_is_not_published(tmp_path, monkeypatch):
    """MEASURED on the real day this was built against (sos_fade_1, 2026-09-22): seven stop moves,
    four of them a cent to thirteen cents of trail. A channel that pings a class to say the stop
    moved by $0.01 is one they mute.

    MUTATION: drop the `min_stop_move` comparison -> red (all four are published).
    """
    rows = [
        {"kind": "event", "event": "stop_moved", "was": 4391.88, "now": 4369.63},
        {"kind": "event", "event": "stop_moved", "was": 4356.7972, "now": 4356.8643},
        {"kind": "event", "event": "stop_moved", "was": 4356.86, "now": 4357.9},
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path, min_stop_move=1.0))
    texts = [t for _, t, _ in sent]
    assert len(texts) == 2
    assert "4,391.88 \u2192 4,369.63" in texts[0] and "4,356.86 \u2192 4,357.90" in texts[1]


def test_one_trail_move_is_one_message_even_though_each_leg_records_it(tmp_path, monkeypatch):
    """🔴 REAL ROWS, 2026-09-22 07:45:02: two `stop_moved` records for the same move, one per leg
    (the primary and the scale-in), both 4357.86 -> 4356.69. Two identical sentences read as the
    stop having moved twice.

    MUTATION: drop the repeat guard -> red.
    """
    d = _ledger(
        tmp_path,
        {"kind": "event", "event": "stop_moved", "was": 4357.8588199999995, "now": 4356.6907},
        {"kind": "event", "event": "stop_moved", "was": 4357.86, "now": 4356.6907, "leg": "add"},
    )
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert len(sent) == 1 and "4,357.86 \u2192 4,356.69" in sent[0][1]


def test_a_market_add_publishes_where_it_FILLED_not_the_estimate(tmp_path, monkeypatch):
    """🔴 The real add of 2026-09-22 rested no order: `price` was the arming bar's close (4332.00)
    and it filled at 4320.58. Publishing the estimate would tell students the bot entered at a
    price it never traded — the bridge's own record says which field is which."""
    d = _ledger(
        tmp_path,
        {
            "kind": "event",
            "event": "order_placed",
            "dir": -1,
            "intent": "add",
            "price": 4332.0,
            "fill_price": 4320.58,
            "at_market": True,
            "stop": 4357.86,
            "lots": 0.17,
            "ticket": _TICKET,
        },
    )
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    text = sent[0][1]
    assert text.startswith("\u2795 ADDED TO THE SAME POSITION \u00b7 SHORT")
    assert "Added at 4,320.58" in text
    assert "4,332" not in text and "4332" not in text and "0.17" not in text


def test_the_add_multiple_is_worked_out_from_the_price_the_message_SHOWS(tmp_path, monkeypatch):
    """🔴 A SAFETY PROPERTY, not a cosmetic one, and the real rows are what exposed it.

    The bot sizes an add on the arming bar's close and then fills at market. On 2026-09-22 it
    sized 0.47x against an estimate of 4332.00 and sold at 4320.58 — where the same arithmetic
    allows only 0.32x. A student adding at the price in front of them and copying the bot's
    multiple would carry risk the locked profit does not cover.

    MUTATION: pass `f.get("price")` to `_add_multiple` instead of the fill -> red (0.47x).
    """
    rows = [
        {"kind": "bar", "s_stage": 4, "short_edge": 4369.93},
        {"kind": "event", "event": "stop_moved", "was": 4391.88, "now": 4357.8588199999995},
        {
            "kind": "event",
            "event": "order_placed",
            "dir": -1,
            "intent": "add",
            "price": 4332.0,
            "fill_price": 4320.58,
            "at_market": True,
            "stop": 4357.8588199999995,
            "lots": 0.17,
        },
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    add = sent[-1][1]
    assert "0.32× your first lot" in add and "0.47" not in add


def test_no_multiple_is_offered_when_the_stop_is_not_past_the_entry(tmp_path, monkeypatch):
    """The bot's rule permits nothing until the stop locks in profit, so there is no number to
    publish — and a blank beats a made-up one."""
    rows = [
        {"kind": "bar", "s_stage": 4, "short_edge": 4369.93},
        {
            "kind": "event",
            "event": "order_placed",
            "dir": -1,
            "intent": "add",
            "price": 4340.0,
            "fill_price": 4340.0,
            "at_market": True,
            "stop": 4380.0,
        },
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert "your first lot" not in sent[-1][1]


def test_risk_off_is_said_ONCE_per_trade(tmp_path, monkeypatch):
    """Three trail steps, one "risk off". Repeating it on every step turns the one line a student
    should act on into wallpaper.

    MUTATION: drop the `risk_off_said` guard -> red (three times).
    """
    rows = [
        {"kind": "bar", "s_stage": 4, "short_edge": 4369.93},
        {"kind": "event", "event": "stop_moved", "was": 4391.88, "now": 4369.63},
        {"kind": "event", "event": "stop_moved", "was": 4369.63, "now": 4357.86},
        {"kind": "event", "event": "stop_moved", "was": 4357.86, "now": 4350.0},
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert sum("Risk off" in t for _, t, _ in sent) == 1


def test_a_generic_close_reason_is_not_repeated_back(tmp_path, monkeypatch):
    """The bridge writes `reason: "closed"` when nothing more specific applies, and
    "OUT at 4356.86. closed." reads as a stutter. A real reason IS published."""
    d = _ledger(
        tmp_path,
        {
            "kind": "trade",
            "event": "closed",
            "dir": "SHORT",
            "price": 4356.86,
            "r": 0.59,
            "reason": "closed",
            "pnl_usd": 482.85,
            "lots": 0.37,
        },
        {
            "kind": "trade",
            "event": "closed",
            "dir": "LONG",
            "price": 4400.0,
            "r": -1.0,
            "reason": "stop",
            "pnl_usd": -100.0,
            "lots": 0.1,
        },
    )
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert "Out at 4,356.86 \u00b7 +0.59R" in sent[0][1] and "closed" not in sent[0][1]
    assert "Out at 4,400.00 \u00b7 -1.00R" in sent[1][1] and sent[1][1].endswith("Stop")
    assert sent[0][1].startswith("\u2705 CLOSED") and sent[1][1].startswith("\u274c CLOSED")


def test_an_unknown_record_renders_nothing(tmp_path, monkeypatch):
    """The decision stream grows new event names; an unlisted one is silence, never a raw dump."""
    d = _ledger(tmp_path, {"kind": "event", "event": "budget_shrunk", "was_lots": 0.24})
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert sent == []


def test_the_student_channel_is_the_only_destination(tmp_path, monkeypatch):
    d = _ledger(tmp_path, {"kind": "bar", "s_stage": 2, "short_edge": 4369.93})
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path, chat="-100mpc"))
    assert [c for c, _, _ in sent] == ["-100mpc"]


# ── the cursor: no backlog, no repeats, and a failure retries ────────────────


def test_a_first_sight_of_a_file_publishes_NOTHING(tmp_path, monkeypatch):
    """Turning the feed on must not replay a day of history into a student channel."""
    d = tmp_path / "ledger"
    d.mkdir()
    from datetime import datetime, timezone

    day = datetime.now(timezone.utc).date()
    (d / f"decisions-{day}.jsonl").write_text(
        "".join(
            json.dumps({"kind": "bar", "s_stage": s, "short_edge": 4369.93}) + "\n"
            for s in (2, 3, 4)
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert sent == []
    # ...and the cursor is now at the end, so only what happens NEXT is published.
    assert feed.read_state(d)["lines"][f"decisions-{day}.jsonl"] == 3


def test_a_second_run_publishes_only_what_is_new(tmp_path, monkeypatch):
    d = _ledger(tmp_path, {"kind": "bar", "s_stage": 2, "short_edge": 4369.93})
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    cfg = _cfg(tmp_path)
    sent = _posted(monkeypatch)
    feed.run(config_path=cfg)
    assert len(sent) == 1
    feed.run(config_path=cfg)
    assert len(sent) == 1
    path = next(p for p in d.glob("decisions-*.jsonl"))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "bar", "s_stage": 3, "short_edge": 4369.93}) + "\n")
    feed.run(config_path=cfg)
    assert len(sent) == 2 and "2 of 3" in sent[1][1] and "tagged the 50%" in sent[1][1]


def test_a_send_that_fails_is_RETRIED_rather_than_lost(tmp_path, monkeypatch):
    """A stop move the channel never gets is the failure this feed exists to prevent, so the
    cursor does not move past a message that did not go.

    MUTATION: record the new counts even when a send failed -> red.
    """
    rows = [
        {"kind": "bar", "s_stage": 2, "short_edge": 4369.93},
        {"kind": "event", "event": "stop_moved", "was": 4391.88, "now": 4369.63},
    ]
    d = _ledger(tmp_path, *rows)
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    cfg = _cfg(tmp_path)
    sent = _posted(monkeypatch, fail_from=1)
    feed.run(config_path=cfg)
    assert len(sent) == 1  # the stage went out, the stop move did not
    sent2 = _posted(monkeypatch)
    feed.run(config_path=cfg)
    assert any("STOP MOVED" in t for _, t, _ in sent2)


def test_a_corrupt_line_does_not_stop_the_rest(tmp_path, monkeypatch):
    """The bot is writing this file while the feed reads it, so a half-written last line is
    ordinary rather than exceptional."""
    d = _ledger(tmp_path, {"kind": "bar", "s_stage": 2, "short_edge": 4369.93})
    path = next(p for p in d.glob("decisions-*.jsonl"))
    with path.open("a", encoding="utf-8") as f:
        f.write('{"kind": "bar", "s_stage": 3, "short_ed\n')
        f.write(json.dumps({"kind": "event", "event": "stop_moved", "was": 1.0, "now": 2.0}) + "\n")
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path))
    assert any("STOP MOVED" in t for _, t, _ in sent)


# ── switched off, and unable to run ──────────────────────────────────────────


def test_switched_off_publishes_nothing_and_leaves_no_backlog(tmp_path, monkeypatch, capsys):
    """`enabled: false` is the shipped state. The cursor still advances, so switching it on
    publishes what happens next rather than everything since the file was written."""
    d = _ledger(tmp_path, {"kind": "bar", "s_stage": 2, "short_edge": 4369.93})
    monkeypatch.setattr(feed, "_ledger_dir", lambda bot: d)
    sent = _posted(monkeypatch)
    feed.run(config_path=_cfg(tmp_path, enabled=False))
    assert sent == []
    assert "would post" in capsys.readouterr().out
    assert feed.read_state(d)["lines"]


def test_a_config_it_cannot_read_is_NOT_the_same_as_switched_off(tmp_path):
    """Three states, never two: off, on, and *could not ask*. Answering "off" for an unreadable
    file is how a feed stops without anybody noticing."""
    with pytest.raises(feed.FeedError):
        feed.load_config(tmp_path / "nope.json")
    bad = tmp_path / "rev_feed.json"
    bad.write_text('{"enabled": true, "bot": ', encoding="utf-8")
    with pytest.raises(feed.FeedError):
        feed.load_config(bad)
    no_chat = tmp_path / "no_chat.json"
    no_chat.write_text(json.dumps({"enabled": True, "bot": "sos_fade_1"}), encoding="utf-8")
    with pytest.raises(feed.FeedError):
        feed.load_config(no_chat)


def test_a_feed_that_cannot_run_says_so_in_the_HEALTH_room_not_the_channel(tmp_path, monkeypatch):
    """A broken watcher must never read as a quiet market — and the complaint is machinery, so it
    goes where the machinery talks, never to the students.

    MUTATION: drop the health send from the failure path -> red.
    """
    said = []

    import notify

    monkeypatch.setattr(
        notify, "send_telegram", lambda text, kind, **kw: said.append((kind, text)) or True
    )
    assert feed.main(["--config", str(tmp_path / "missing.json")]) == 1
    assert said and said[0][0] == notify.HEALTH
    assert "cannot run" in said[0][1]
