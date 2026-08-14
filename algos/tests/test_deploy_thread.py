"""A deploy is ONE event, and it produced three messages from two machines.

Aaron, 2026-08-14, on the health channel: *"Look at the messages every time I promote also; can
this be a thread instead of individual messages?"* — STOPPED, PROMOTED and ONLINE arriving as
three unrelated bubbles, of which the command center sends one and this bot sends two.

So the command center sends the PROMOTED root, writes its Telegram message id into the bot's
instance directory, and the bot replies to it. The channel is the one those two processes
already share (`stop.request`, `bot_state.json`, `review.json`).

⚠ **THE TESTS ARE WEIGHTED TOWARD THE STALE-FILE FAILURE**, exactly as `test_graceful_stop.py`
is, and for the same reason: **a file in an instance directory that outlives what it describes
is this system's most-repeated hazard.** There it was a leftover request stopping a healthy bot;
here it is a leftover id quietly parenting every future lifecycle message under an ancient
deploy — in the channel whose whole job is saying what is happening NOW. That is the one way
this feature could be worse than not threading at all.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from runner import LiveRunner  # noqa: E402


def _runner(tmp_path):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", instance_dir=tmp_path)
    r.log = SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    return r


def _write(r, message_id, *, ttl=900.0):
    r.alert_thread_path().write_text(
        json.dumps({"message_id": message_id, "expires_at": time.time() + ttl}), encoding="utf-8"
    )


# ── reading it ──────────────────────────────────────────────────────────────────


def test_a_live_thread_is_the_message_the_alerts_reply_to(tmp_path):
    r = _runner(tmp_path)
    _write(r, 4242)
    assert r._deploy_thread() == 4242


def test_no_file_means_send_it_LOOSE_rather_than_fail(tmp_path):
    """None is *no thread*, which is the behaviour every bot had before this existed. A
    notifier convenience must never be able to cost a lifecycle message."""
    assert _runner(tmp_path)._deploy_thread() is None


# ── the stale-file hazard ───────────────────────────────────────────────────────


def test_an_EXPIRED_thread_is_ignored(tmp_path):
    """The guard that cannot be forgotten. A restart that never completes leaves nobody to
    delete the file, so without an expiry the next ONLINE — days later — replies under a deploy
    that failed."""
    r = _runner(tmp_path)
    _write(r, 4242, ttl=-1.0)
    assert r._deploy_thread() is None


def test_a_file_with_no_expiry_at_all_is_ignored(tmp_path):
    """A record written by something that did not state one is not a live thread. Defaulting
    the expiry to *forever* would make the missing field the most dangerous value in the file."""
    r = _runner(tmp_path)
    r.alert_thread_path().write_text(json.dumps({"message_id": 4242}), encoding="utf-8")
    assert r._deploy_thread() is None


def test_ONLINE_consumes_the_thread_so_the_next_deploy_starts_a_new_one(tmp_path):
    """A bot restarted twice inside the TTL must not put its second boot under its first
    deploy. `clear_alert_thread` runs immediately after the ONLINE alert — the last message a
    deploy produces."""
    r = _runner(tmp_path)
    _write(r, 4242)
    r.clear_alert_thread()
    assert r._deploy_thread() is None
    r.clear_alert_thread()  # idempotent — a missing file is the normal case


def test_a_message_id_of_zero_is_not_a_thread(tmp_path):
    """`send_telegram_id` answers 0 for *delivered, but the id was unreadable*. Replying to
    message zero is a send Telegram refuses outright, which would cost the alert."""
    r = _runner(tmp_path)
    _write(r, 0)
    assert r._deploy_thread() is None


@pytest.mark.parametrize("body", ["{not json", "", "[]", '{"message_id": "abc"}'])
def test_an_unreadable_thread_file_is_no_thread_not_a_crash(tmp_path, body):
    r = _runner(tmp_path)
    r.alert_thread_path().write_text(body, encoding="utf-8")
    assert r._deploy_thread() is None


# ── which messages thread, and which must not ───────────────────────────────────


def test_a_threaded_message_replies_and_does_not_consume(tmp_path):
    """Sending is not consuming. Only ONE call site clears the thread, and the test below is
    what pins WHICH."""
    r = _runner(tmp_path)
    _write(r, 4242)

    sent: list[tuple] = []
    r._notify = lambda text, kind, reply_to=None: sent.append((text, reply_to))
    r._notify_health("STOPPED", thread=True)

    assert sent == [("STOPPED", 4242)]
    assert r._deploy_thread() == 4242


def test_the_thread_is_consumed_in_exactly_ONE_place(tmp_path):
    """🔴 The ONLINE that follows a promote is sent by a DIFFERENT PROCESS, so the STOPPING bot
    must not delete the file — the message the reader is actually waiting for would land loose,
    the one that says the bot came back.

    ⚠ **This READS THE SOURCE, and it does so because the behavioural version was VACUOUS.**
    Calling `_notify_health(thread=True)` and checking the file survives proves something about
    the notifier and nothing about the stop path — MEASURED: adding `clear_alert_thread()` beside
    the STOPPED alert left all twelve tests green. The risk is a second call site, so the guard
    counts call sites. The same arrangement `test_bot_versions.py` uses to pin two files that
    must agree.
    """
    src = (_REPO / "algos" / "live" / "runner.py").read_text(encoding="utf-8")
    calls = src.count("self.clear_alert_thread()")
    assert calls == 1, (
        f"{calls} call sites clear the deploy thread. Exactly one may — the ONLINE alert, which "
        f"is the last message a deploy produces. Clearing it anywhere earlier orphans the "
        f"message sent by the process that comes after."
    )
    # And it is the ONLINE one: the consume sits between the two lifecycle alerts, so it follows
    # ONLINE and never STOPPED.
    #
    # ⚠ **Matched on the single label literals, NOT on `'"🟢", "ONLINE"'`.** The first version of
    # this assertion did the latter and broke the moment a formatter put the two arguments on
    # separate lines — a source-reading test must key off something the LAYOUT cannot move, or it
    # goes red for a reformat and teaches the next reader that it is noise.
    assert src.index('"ONLINE"') < src.index("self.clear_alert_thread()") < src.index('"STOPPED"')


def test_an_ORDINARY_health_message_is_not_threaded(tmp_path):
    """Only the two lifecycle messages a promote causes belong to it. Threading everything
    would file an unrelated 3am reconnect under a deploy from that morning."""
    r = _runner(tmp_path)
    _write(r, 4242)

    sent: list[tuple] = []
    r._notify = lambda text, kind, reply_to=None: sent.append((text, reply_to))
    r._notify_health("RECONNECTED")

    assert sent == [("RECONNECTED", None)]
