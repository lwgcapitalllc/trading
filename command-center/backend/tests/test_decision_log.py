"""
Trade decision-log unit tests (services/decision_log).

Pure module — these build records inline and round-trip them through a temp .jsonl.
Covers: exit classification, the three outcomes (taken / blocked / skipped), gate
ordering + blocked_by, chainable builders, extensibility (arbitrary gate names), and
the append-only file round trip.
"""

from services.decision_log import (
    TradeDecision, GateVerdict, SizingDecision, DecisionLog, classify_exit,
    OUTCOME_TAKEN, OUTCOME_BLOCKED, OUTCOME_SKIPPED,
    EXIT_TARGET, EXIT_STOP, EXIT_TIME_FLAT, EXIT_BREAKEVEN, EXIT_OTHER,
)


# ── Exit classification ───────────────────────────────────────────────────────

def test_classify_exit_maps_common_labels():
    assert classify_exit("ORB_Long Profit target") == EXIT_TARGET
    assert classify_exit("Stop loss") == EXIT_STOP
    assert classify_exit("ForceFlat") == EXIT_TIME_FLAT
    assert classify_exit("Breakeven") == EXIT_BREAKEVEN
    assert classify_exit("") == EXIT_OTHER
    assert classify_exit(None) == EXIT_OTHER


# ── Outcomes ──────────────────────────────────────────────────────────────────

def test_blocked_by_first_failing_gate():
    d = (TradeDecision(timestamp="2024-01-02T09:40:00", instrument="MNQ", direction=1)
         .gate("session", True, "inside RTH")
         .gate("daily_loss", False, "day already down past the halt")
         .gate("regime", True, "trending"))   # later pass doesn't un-block
    d.finalize()
    assert d.blocked_by == "daily_loss"
    assert d.outcome == OUTCOME_BLOCKED


def test_taken_records_full_life():
    d = (TradeDecision(timestamp="2024-01-02T09:40:00", instrument="MNQ", direction=1,
                       setup_score="A+", setup_reason="range break + 1 confirm",
                       stop_distance=5.0)
         .gate("session", True, "inside RTH")
         .set_sizing(SizingDecision(contracts=2, bound_by="contract_ladder",
                                    room_to_floor=2000.0, ladder_cap=2))
         .snapshot(balance=50000, day_pnl=0.0, floor_distance=2000.0)
         .set_entry(time="2024-01-02T09:40:00", price=17000, stop=16995, target=17010)
         .set_exit(time="2024-01-02T10:05:00", price=17010, reason=EXIT_TARGET,
                   gross=40.0, net=38.0, r_multiple=2.0))
    d.finalize()
    assert d.outcome == OUTCOME_TAKEN
    assert d.blocked_by is None
    assert d.exit["reason"] == EXIT_TARGET
    assert d.sizing.contracts == 2


def test_skipped_when_sized_to_zero():
    d = (TradeDecision(timestamp="2024-01-02T09:40:00", instrument="MNQ", direction=-1)
         .gate("session", True, "inside RTH")
         .set_sizing(SizingDecision(contracts=0, bound_by="drawdown_clamp",
                                    room_to_floor=80.0, skipped=True,
                                    note="one contract's risk exceeds the room left")))
    d.finalize()
    assert d.outcome == OUTCOME_SKIPPED


# ── Extensibility ─────────────────────────────────────────────────────────────

def test_arbitrary_future_gate_is_accepted():
    # A gate the logger has never heard of just works — no schema change.
    d = TradeDecision(timestamp="2024-01-02T09:40:00", instrument="EURUSD", direction=1)
    d.gate("news_blackout", False, "high-impact NFP in 5 min", event="NFP", minutes=5)
    d.finalize()
    assert d.outcome == OUTCOME_BLOCKED
    assert d.gates[0].detail == {"event": "NFP", "minutes": 5}


# ── File round trip ───────────────────────────────────────────────────────────

def test_append_only_round_trip(tmp_path):
    path = tmp_path / "run123" / "decisions.jsonl"
    log = DecisionLog(path)
    log.write(TradeDecision(timestamp="2024-01-02T09:40:00", instrument="MNQ", direction=1)
              .gate("session", True, "ok")
              .set_sizing(SizingDecision(contracts=1, bound_by="risk_budget")))
    log.write(TradeDecision(timestamp="2024-01-02T09:55:00", instrument="MNQ", direction=-1)
              .gate("daily_loss", False, "halted"))

    rows = DecisionLog.read(path)
    assert len(rows) == 2
    assert rows[0]["outcome"] == OUTCOME_TAKEN
    assert rows[1]["outcome"] == OUTCOME_BLOCKED
    assert rows[1]["gates"][0]["gate"] == "daily_loss"


def test_read_missing_file_is_empty(tmp_path):
    assert DecisionLog.read(tmp_path / "nope.jsonl") == []
