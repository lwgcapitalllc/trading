"""The scan endpoint: what the box is logged into, and what it must never say.

Three rules carry the weight here, and all three are the same rule wearing different clothes:

  * a scan that could not RUN is a 502 carrying why — never a 200 describing zero terminals,
  * a scan the box REFUSED is a 200 saying so — the channel worked and the answer is "I won't",
  * nothing is written by any of it.

The third is the one a future change is most likely to erode, because auto-adopting a discovered
account looks like a convenience. It would turn an accidental login into configuration, and the
account-mismatch halt on the bot side exists precisely because a terminal's login can change under
a running bot.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import bot_account_registry as reg  # noqa: E402
from services import terminal_scan  # noqa: E402

_PROFILES = {"puprime_ecn", "puprime_standard"}


def _acct(**kw):
    base = dict(
        account=700152905,
        label="PU Prime ECN demo",
        broker="PU Prime",
        tier="ECN",
        kind="demo",
        server="PUPrime-Demo",
        mt5_path=r"C:\MT5_FFT\terminal64.exe",
        symbol_suffix=".p",
        account_profile="puprime_ecn",
    )
    base.update(kw)
    return reg.RegisteredAccount(**base)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    from routers import bots as bots_router

    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"accounts": []}), encoding="utf-8")
    monkeypatch.setattr(bots_router, "_registry_path", lambda: p)
    return p


def _payload(*terminals, asked=True, **extra):
    return {
        "asked": asked,
        "scanned_at": "2026-09-10T05:00:00Z",
        "terminals": list(terminals),
        **extra,
    }


_LIVE = {
    "key": r"c:\mt5_scalper",
    "install": r"C:\MT5_Scalper",
    "state": "probed",
    "running": True,
    "owned_by_bots": [],
    "account": 34957946,
    "server": "PUPrime-Live",
    "kind": "live",
    "company": "PU Prime Ltd",
    "currency": "USD",
    "leverage": 500,
    "symbol_suffix": ".p",
    "symbol_suffix_how": "common to EURUSD,GBPUSD,USDJPY,XAUUSD on this terminal",
}

_OWNED = {
    "key": r"c:\mt5_fft",
    "install": r"C:\MT5_FFT",
    "state": "owned_by_bot",
    "running": True,
    "owned_by_bots": ["extreme_leg_demo", "sos_fade_demo"],
    "account": None,
    "reason": "a bot trades through this terminal, so it was deliberately not attached to",
}


def _stub(monkeypatch, payload, observed=None):
    """Stub the ONE box call the route makes, with the bots' reports inside it as the box sends them.

    ⚠ The route used to make a second call for those reports; it now reads them off the scan, so a
    test that faked the second call would be testing a system that no longer exists.
    """
    from routers import bots as bots_router

    if observed:
        for t in payload.get("terminals") or []:
            if t.get("state") == "owned_by_bot":
                t["reported_by_bots"] = {b: observed.get(b) for b in t.get("owned_by_bots") or []}
    monkeypatch.setattr(bots_router, "_scan_terminals", lambda: payload)


def test_a_live_account_nobody_registered_comes_back_as_new_and_prefilled(
    client, registry, monkeypatch
):
    """The whole feature. This is the account that was invisible for a day."""
    _stub(monkeypatch, _payload(_LIVE, _OWNED))

    r = client.get("/bots/accounts/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["asked"] is True

    found = {t["install"]: t for t in body["terminals"]}
    live = found[r"C:\MT5_Scalper"]
    assert live["verdict"] == "new"
    assert live["account"] == 34957946
    assert live["kind"] == "live"
    assert live["suggested"]["server"] == "PUPrime-Live"
    assert live["suggested"]["mt5_path"] == r"C:\MT5_Scalper\terminal64.exe"
    # the judgement fields stay empty for a person
    assert live["suggested"]["account_profile"] == ""
    assert live["suggested"]["label"] == ""


def test_the_bots_own_terminal_is_reported_as_not_asked_never_as_empty(
    client, registry, monkeypatch
):
    """`account: null` here must arrive with its reason attached."""
    _stub(monkeypatch, _payload(_OWNED))

    (t,) = client.get("/bots/accounts/scan").json()["terminals"]
    assert t["state"] == "owned_by_bot"
    assert t["account"] is None
    assert t["verdict"] == "unasked"
    assert t["suggested"] is None
    assert "deliberately not attached" in t["reason"]


def test_a_row_pointing_at_a_terminal_on_another_account_is_contradicted(
    client, registry, monkeypatch
):
    """🔴 The live defect, end to end: a registered row whose terminal is on something else."""
    reg.upsert_account(
        registry,
        _acct(account=700107749, label="retired", mt5_path=r"C:\MT5_Scalper\terminal64.exe"),
        _PROFILES,
    )
    _stub(monkeypatch, _payload(_LIVE))

    (check,) = client.get("/bots/accounts/scan").json()["registry"]
    assert check["account"] == 700107749
    assert check["verdict"] == "contradicted"
    assert "34957946" in check["detail"]


def test_a_row_whose_terminal_could_not_be_asked_is_unverified_not_contradicted(
    client, registry, monkeypatch
):
    """Watched red by grading an unaskable terminal as a contradiction: the page then reports a
    finding against every account on the bots' own terminal, every single scan."""
    reg.upsert_account(registry, _acct(), _PROFILES)
    _stub(monkeypatch, _payload(_OWNED))

    (check,) = client.get("/bots/accounts/scan").json()["registry"]
    assert check["verdict"] == "unverified"
    assert "your bots' terminal" in check["detail"]


def test_an_unreachable_box_is_a_502_carrying_why_not_an_empty_scan(client, registry, monkeypatch):
    """🔴 The rule this whole feature is about, applied to the feature itself.

    Watched red by returning `{"asked": True, "terminals": []}` on failure: the page then renders
    a clean scan of a box with nothing on it, which is indistinguishable from a healthy machine
    with no terminals — and would quietly mark every registered account unverified.
    """
    from routers import bots as bots_router

    def _boom():
        raise terminal_scan.ScanUnavailable("ssh to forexvps failed and said nothing")

    monkeypatch.setattr(bots_router, "_scan_terminals", _boom)

    r = client.get("/bots/accounts/scan")
    assert r.status_code == 502
    assert "said nothing" in r.json()["detail"]


def test_unreadable_output_from_the_box_is_a_502(client, registry, monkeypatch):
    """A truncated pipe, an SSH banner, a Windows error page — none of them are a scan."""
    _stub(monkeypatch, {"not": "a scan"})

    r = client.get("/bots/accounts/scan")
    assert r.status_code == 502
    assert "UNKNOWN" in r.json()["detail"] or "readable" in r.json()["detail"]


def test_a_scan_the_box_refused_is_a_200_that_says_so(client, registry, monkeypatch):
    """The channel worked and the answer was "I will not" — that is a reading, not a failure.

    It must not be a 502: a 502 says the box could not be reached, and sending somebody to check
    the network when the script refused on purpose is the wrong repair.
    """
    _stub(
        monkeypatch,
        _payload(
            asked=False, reason="no instance directory - refusing to scan rather than attaching"
        ),
    )

    r = client.get("/bots/accounts/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["asked"] is False
    assert "refusing to scan" in body["reason"]
    assert body["terminals"] == [] and body["registry"] == []


def test_the_scan_writes_nothing_to_the_registry(client, registry, monkeypatch):
    """Watched red by having the endpoint upsert what it found: the file gains an account."""
    before = registry.read_text(encoding="utf-8")
    _stub(monkeypatch, _payload(_LIVE))

    assert client.get("/bots/accounts/scan").status_code == 200
    assert registry.read_text(encoding="utf-8") == before
    assert reg.load_accounts(registry) == []


def test_no_password_appears_anywhere_in_the_response(client, registry, monkeypatch):
    """It cannot be discovered — the terminal encrypts it — and a present-but-empty field would
    read as "this account has no password", which is a different claim."""
    _stub(monkeypatch, _payload(_LIVE))

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    body = client.get("/bots/accounts/scan").json()
    # ⚠ FIELD NAMES, not a substring of the whole body. Since 2026-09-10 the scan also carries the
    # sync preview, whose sentence for an added account says it "arrives with no terminal or
    # password" — which is the true state stated in words, not a password field. A substring
    # check would forbid saying so.
    assert not [k for k in keys(body) if "password" in k.lower()]


def test_the_stale_row_on_the_bots_terminal_is_contradicted_end_to_end(
    client, registry, monkeypatch
):
    """🔴 700107749 through the real route: the row claims the bots' terminal, the bots report
    700152905, so the claim is wrong. Before the runner reported its observed account this came
    back UNVERIFIED on every scan."""
    reg.upsert_account(
        registry,
        _acct(account=700107749, label="retired", mt5_path=r"C:\MT5_FFT\terminal64.exe"),
        _PROFILES,
    )
    _stub(monkeypatch, _payload(_OWNED), observed={"sos_fade_demo": 700152905})

    (check,) = client.get("/bots/accounts/scan").json()["registry"]
    assert check["verdict"] == "contradicted"
    assert "700152905" in check["detail"]


def test_the_bots_terminal_carries_where_its_account_came_from(client, registry, monkeypatch):
    """Provenance is served, because a bot's report and this tool's own reading are different
    strengths of evidence."""
    _stub(monkeypatch, _payload(_OWNED), observed={"sos_fade_demo": 700152905})

    (t,) = client.get("/bots/accounts/scan").json()["terminals"]
    assert t["account"] == 700152905
    assert t["account_source"] == "bot"


def test_the_scan_asks_the_box_ONCE(client, registry, monkeypatch):
    """The fleet snapshot is no longer fetched to read what the bots report — it arrives in the scan.

    Watched red by restoring the second trip: the snapshot fetch is called.
    """
    from routers import bots as bots_router

    fetched = []
    monkeypatch.setattr(bots_router, "_fetch_vps_snapshot", lambda: fetched.append(1) or {})
    _stub(monkeypatch, _payload(_OWNED), observed={"sos_fade_demo": 700152905})
    assert client.get("/bots/accounts/scan").status_code == 200
    assert fetched == []
