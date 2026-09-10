"""The terminal scan must never attach to a terminal a bot is trading through.

🔴 **Every test here exists because the tool got one of these wrong during its own build.**

The scan attaches to MT5 terminals to read which account each is logged into. Attaching is not
free: `mt5.initialize(path=...)` LAUNCHES a terminal that is not already running, and the box runs
two armed bots through one of these terminals. So the tool's safety rests entirely on it knowing
which installs it must leave alone — and that knowledge comes from reading the bots' instance
configs off disk.

**Both ways of losing that knowledge were live defects, and both were silent.**

  1. Running the script from outside the repo made the instances directory unfindable, which the
     first version answered as *"no bot owns any terminal"* — the exact value that makes every
     terminal on the box eligible, including the live one. Caught by copying the file somewhere
     convenient to test it, which is how somebody will run it next.
  2. Windows paths do not split on a Mac. `pathlib` treated `C:\\MT5_FFT\\terminal64.exe` as one
     filename, so all three bots hashed to the same key and the live install matched nothing.
     That failure reads as MORE terminals protected, not fewer, which is why nothing looked wrong.

⚠ **The second is the one worth remembering: the test host is not the box.** A rule about Windows
paths that is only ever exercised on a Mac is a rule tested against a machine you do not have.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_SRC = _REPO / "algos" / "tools" / "scan_terminals.py"


def _load():
    """A fresh module per test — several tests rewrite its module-level paths."""
    spec = importlib.util.spec_from_file_location("scan_terminals_under_test", _SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------
# The safety property: no instance list, no scan
# ------------------------------------------------------------------------------------------


def test_missing_instance_dir_refuses_rather_than_reporting_nothing_owned(tmp_path):
    """A directory it cannot read must REFUSE, never answer "nobody owns anything".

    Watched red: returning `{}` here (the original code) makes this pass a plain "did it not
    raise" check while leaving every terminal on the box probeable, so the assertion is on the
    refusal itself rather than on the absence of a crash.
    """
    st = _load()
    st.INSTANCES = tmp_path / "not-here"
    with pytest.raises(st.ScanRefused):
        st.bot_terminals()


def test_a_refused_scan_says_asked_false_and_lists_no_terminals(tmp_path):
    """The refusal must survive to the payload — an empty terminal list is not the message."""
    st = _load()
    st.INSTANCES = tmp_path / "not-here"
    result = st.scan()
    assert result["asked"] is False
    assert result["terminals"] == []
    assert "refusing to scan" in result["reason"]


def test_a_refused_scan_exits_non_zero(tmp_path, capsys):
    """A caller reading only the exit code still has to notice."""
    st = _load()
    st.INSTANCES = tmp_path / "not-here"
    assert st.main([]) == 2
    assert json.loads(capsys.readouterr().out)["asked"] is False


def test_one_unreadable_config_is_tolerated_because_the_directory_was_found(tmp_path):
    """The tolerated case, kept apart from the refused one.

    A single corrupt config costs one terminal's protection and the rest are still known. Folding
    this into the refusal would make the tool stop over a typo; folding the refusal into this
    would make it scan the whole box. They are different failures.
    """
    st = _load()
    st.INSTANCES = tmp_path
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "config.json").write_text(
        json.dumps({"mt5_path": r"C:\MT5_FFT\terminal64.exe"})
    )
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "config.json").write_text("{not json")
    owned = st.bot_terminals()
    assert owned == {r"c:\mt5_fft": ["good"]}


# ------------------------------------------------------------------------------------------
# Windows path semantics, on whatever host is running the tests
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given,expected",
    [
        (r"C:\MT5_FFT\terminal64.exe", r"c:\mt5_fft"),
        (r"C:\MT5_FFT", r"c:\mt5_fft"),
        ("C:\\MT5_FFT\\\\", r"c:\mt5_fft"),
        (r"c:\mt5_fft\TERMINAL64.EXE", r"c:\mt5_fft"),
        (
            r"C:\Program Files\PU Prime MT5 Terminal\terminal64.exe",
            r"c:\program files\pu prime mt5 terminal",
        ),
        ("", ""),
    ],
)
def test_install_dir_uses_windows_semantics_on_any_host(given, expected):
    """The exe form and the folder form must land on ONE key, on Mac and on Windows alike.

    Watched red by swapping `ntpath.dirname` back for `Path(...).parent`: every case carrying a
    backslash then returns `.` on this host, which is what silently un-protected the live
    terminal.
    """
    assert _load()._install_dir(given) == expected


def test_every_bot_on_one_install_collapses_to_that_install_not_to_a_dot(tmp_path):
    """The defect as it actually appeared: three bots, one key, and it was the wrong key."""
    st = _load()
    st.INSTANCES = tmp_path
    for name in ("a_bot", "b_bot", "c_bot"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "config.json").write_text(
            json.dumps({"mt5_path": r"C:\MT5_FFT\terminal64.exe"})
        )
    owned = st.bot_terminals()
    assert list(owned) == [r"c:\mt5_fft"]
    assert owned[r"c:\mt5_fft"] == ["a_bot", "b_bot", "c_bot"]


# ------------------------------------------------------------------------------------------
# What the scan does with each terminal
# ------------------------------------------------------------------------------------------


def _scan_with(st, *, running, installed, owned, probe_result=None):
    """Drive `scan` against a described box. The probe is recorded, never really run."""
    probed: list[str] = []

    def _probe(exe):
        probed.append(exe)
        return dict(probe_result or {}, exe=exe, install=st._install_dir(exe), probed=True)

    st.running_terminals = lambda: running
    st.installed_terminals = lambda: installed
    st.bot_terminals = lambda: owned
    st._run_probe_subprocess = _probe
    return st.scan(), probed


def test_a_terminal_a_bot_owns_is_never_attached_to(tmp_path):
    """The whole point of the tool. The assertion is on the PROBE not happening.

    Watched red by deleting the `bots and skip_owned` branch: the terminal is then probed and
    `probed` carries the live exe.
    """
    st = _load()
    result, probed = _scan_with(
        st,
        running=[{"exe": r"C:\MT5_FFT\terminal64.exe", "pid": 5016}],
        installed=[r"C:\MT5_FFT"],
        owned={r"c:\mt5_fft": ["sos_fade_demo", "extreme_leg_demo"]},
    )
    assert probed == []
    (entry,) = result["terminals"]
    assert entry["state"] == "owned_by_bot"
    assert entry["account"] is None
    # Sorted, not config order: this list is read by a human off a screen, and a set that
    # reorders itself between scans reads as the fleet having changed.
    assert entry["owned_by_bots"] == ["extreme_leg_demo", "sos_fade_demo"]
    assert "deliberately not" in entry["reason"]


def test_an_unowned_running_terminal_is_probed():
    """The case the feature exists for — the idle terminal somebody logged a live account into."""
    st = _load()
    result, probed = _scan_with(
        st,
        running=[{"exe": r"C:\MT5_Scalper\terminal64.exe", "pid": 6816}],
        installed=[r"C:\MT5_Scalper"],
        owned={},
        probe_result={"account": 123456, "server": "ICMarkets-Live02", "kind": "live"},
    )
    assert probed == [r"C:\MT5_Scalper\terminal64.exe"]
    (entry,) = result["terminals"]
    assert entry["account"] == 123456
    assert entry["kind"] == "live"


def test_an_install_that_is_not_running_reports_that_it_could_not_be_asked():
    """`account: None` here must carry its reason, or it reads as an empty terminal.

    Watched red by dropping the `reason` key: the record then differs from a probed-and-empty one
    only by a field nothing asserts on.
    """
    st = _load()
    result, probed = _scan_with(
        st,
        running=[],
        installed=[r"C:\Program Files\MetaTrader 5"],
        owned={},
    )
    assert probed == []
    (entry,) = result["terminals"]
    assert entry["state"] == "not_running"
    assert entry["running"] is False
    assert entry["account"] is None
    assert "could not be asked" in entry["reason"]


def test_include_bot_terminals_is_opt_in_and_off_by_default():
    """The escape hatch exists, and it must be something somebody TYPES."""
    st = _load()
    st.running_terminals = lambda: [{"exe": r"C:\MT5_FFT\terminal64.exe", "pid": 5016}]
    st.installed_terminals = lambda: []
    st.bot_terminals = lambda: {r"c:\mt5_fft": ["sos_fade_demo"]}
    probed = []
    st._run_probe_subprocess = lambda exe: probed.append(exe) or {"probed": True}

    st.scan()
    assert probed == [], "the default must not attach to a bot's terminal"
    st.scan(skip_owned=False)
    assert probed == [r"C:\MT5_FFT\terminal64.exe"]


def test_every_row_joins_on_the_same_key_whichever_branch_produced_it():
    """🔴 The first real scan spelled one terminal three ways in one report.

    An owned row carried the exe, a probed row carried a lowercased directory, and a stopped row
    carried the original casing. The consumer is the Command Center matching these against
    terminal paths a human typed into the account list, so a join key that depends on which
    branch produced the row is a join that works right up until it silently does not.

    Watched red by letting the probe's own identity keys overwrite the scan's: the probed row
    then joins on a different string from the other two.
    """
    st = _load()
    result, _ = _scan_with(
        st,
        running=[
            {"exe": r"C:\MT5_FFT\terminal64.exe", "pid": 1},
            {"exe": r"C:\MT5_Scalper\terminal64.exe", "pid": 2},
        ],
        installed=[r"C:\MT5_Scalper", r"C:\Program Files\MetaTrader 5"],
        owned={r"c:\mt5_fft": ["sos_fade_demo"]},
        probe_result={"key": "WRONG", "install": "WRONG", "exe": "WRONG", "account": 42},
    )
    by_state = {t["state"]: t for t in result["terminals"]}
    assert by_state["owned_by_bot"]["key"] == r"c:\mt5_fft"
    assert by_state["probed"]["key"] == r"c:\mt5_scalper"
    assert by_state["not_running"]["key"] == r"c:\program files\metatrader 5"
    # the probe may report an account; it may not redefine which terminal it was
    assert by_state["probed"]["account"] == 42
    assert by_state["probed"]["install"] == r"C:\MT5_Scalper"
    assert all(t["key"] == t["key"].lower() for t in result["terminals"])


# ------------------------------------------------------------------------------------------
# Reading the account: demo/live, and the symbol suffix
# ------------------------------------------------------------------------------------------


class _Sym:
    def __init__(self, name):
        self.name = name


class _FakeMt5:
    def __init__(self, names):
        self._names = names

    def symbols_get(self):
        return [_Sym(n) for n in self._names]


def test_suffix_is_measured_when_the_probe_instruments_agree():
    st = _load()
    suffix, how = st._measure_suffix(_FakeMt5(["XAUUSD.p", "EURUSD.p", "GBPUSD.p", "USDJPY.p"]))
    assert suffix == ".p"
    assert "common to" in how


def test_the_real_pu_prime_instrument_list_measures_dot_p():
    """🔴 The case that killed the first rule, taken off the live terminal on 2026-09-10.

    Every base is ambiguous on its own here — gold is offered as `.crp`, `.p` and `247`, and the
    majors are offered bare as well as `.p` — so a rule asking each base to resolve to exactly
    one variant abstained on all four and measured nothing. It refused safely and it refused
    ALWAYS, which is decoration rather than a check.

    Watched red against the previous rule: it returns `None` for this list.
    """
    st = _load()
    suffix, how = st._measure_suffix(
        _FakeMt5(
            [
                "XAUUSD.crp",
                "XAUUSD.p",
                "XAUUSD247",
                "XAUEUR.p",
                "XAUJPY.p",
                "BTCXAU",
                "EURUSD",
                "EURUSD.p",
                "GBPUSD",
                "GBPUSD.p",
                "USDJPY",
                "USDJPY.p",
            ]
        )
    )
    assert suffix == ".p"


def test_a_broker_offering_every_instrument_under_two_suffixes_refuses_and_names_them():
    """When both survive the intersection it is a CHOICE, and this tool does not make choices."""
    st = _load()
    suffix, how = st._measure_suffix(
        _FakeMt5(["XAUUSD.p", "XAUUSD.s", "EURUSD.p", "EURUSD.s", "GBPUSD.p", "GBPUSD.s"])
    )
    assert suffix is None
    assert "CHOICE" in how
    assert ".p" in how and ".s" in how


def test_a_broker_quoting_bare_symbols_measures_as_empty_not_as_unrecorded():
    """`""` and `None` are different answers and the registry already treats them so."""
    st = _load()
    suffix, _ = st._measure_suffix(_FakeMt5(["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]))
    assert suffix == ""


def test_disagreeing_probe_instruments_record_nothing_rather_than_picking_one():
    """Rebasing a live symbol onto a guessed suffix is a wrong-symbol order.

    Watched red by taking the first vote instead of refusing: this then returns `.p`, which is a
    plausible answer and a coin flip.
    """
    st = _load()
    suffix, how = st._measure_suffix(_FakeMt5(["XAUUSD.p", "EURUSD.s", "GBPUSD.s"]))
    assert suffix is None
    assert "share no common suffix" in how


def test_a_terminal_with_no_known_instruments_records_nothing():
    st = _load()
    suffix, how = st._measure_suffix(_FakeMt5(["BTCUSD", "ETHUSD"]))
    assert suffix is None
    assert "none of the probe instruments" in how


def test_an_empty_instrument_list_is_not_read_as_bare_symbols():
    """The failure that would silently rebase every symbol to no suffix at all."""
    st = _load()
    suffix, how = st._measure_suffix(_FakeMt5([]))
    assert suffix is None
    assert "no instruments" in how


@pytest.mark.parametrize("mode,expected", [(0, "demo"), (1, "contest"), (2, "live")])
def test_account_mode_comes_from_the_brokers_own_flag(mode, expected):
    assert _load()._TRADE_MODE[mode] == expected


def test_an_unrecognised_account_mode_is_not_folded_into_demo():
    """The dangerous direction. An unknown mode must not become the safe-sounding word."""
    st = _load()
    assert st._TRADE_MODE.get(7) is None


# ------------------------------------------------------------------------------------------
# The rule that cannot be expressed as behaviour
# ------------------------------------------------------------------------------------------


def test_the_scanner_never_calls_login():
    """`mt5.login()` re-points a terminal, so one call here moves a terminal under a live bot.

    This is a grep rather than a behaviour test because the defect is a line that does not exist
    yet: no fixture can prove a call is absent from every future path through the file. It goes
    red the moment somebody adds one.
    """
    src = _SRC.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith(("#", "*", '"""'))
    )
    assert "mt5.login" not in code.replace("`mt5.login()`", "")


# ------------------------------------------------------------------------------------------
# Reading the terminal's own index of installs
# ------------------------------------------------------------------------------------------


def test_origin_txt_is_decoded_as_utf16_because_that_is_what_mt5_writes():
    """🔴 The defect that made every install appear twice in the first real scan.

    MT5 writes this file UTF-16. Read as UTF-8 it does not raise — it yields a string with a null
    between every character, which matches no running terminal, so each install showed up once
    correctly and once as a garbled phantom reporting itself NOT RUNNING. That is the worst shape
    available to this tool: a phantom whose message is identical to a genuinely-down terminal's.

    Watched red by restoring `read_text(encoding="utf-8", errors="replace")` — the assertion
    fails on a string carrying nulls.
    """
    st = _load()
    raw = r"C:\MT5_Scalper".encode("utf-16")  # BOM included, as the terminal writes it
    assert st._decode_origin(raw) == r"C:\MT5_Scalper"


def test_a_plain_utf8_origin_still_reads():
    """Not every install writes UTF-16, and the fix may not break the ones that do not."""
    st = _load()
    assert st._decode_origin(b"C:\\MT5_Lab\r\n") == r"C:\MT5_Lab"


def test_a_utf16_origin_with_no_byte_order_mark_still_decodes():
    """🔴 The gap the first fix left, found by a mutation that SURVIVED it.

    Keying the decode on the byte-order mark fixes exactly the file that happened to be in front
    of us. A mark-less UTF-16 file falls to the UTF-8 branch and decodes to the same null-riddled
    garbage — and stripping nulls cannot rescue it, because `strip` only touches the ENDS while
    the nulls are between every character.

    Watched red against the mark-only version: this returns a string carrying interior nulls.
    """
    st = _load()
    raw = r"C:\MT5_Scalper".encode("utf-16-le")  # deliberately no BOM
    assert st._decode_origin(raw) == r"C:\MT5_Scalper"


def test_a_mark_less_utf16_is_read_with_the_right_endianness():
    """The half a mutation caught with nothing asserting on it.

    Endianness is guessed from where the null byte falls, and "always little-endian" passed the
    whole file until this existed. Windows will realistically never write the big-endian form, so
    this is a branch kept because it is CHEAP AND CORRECT — but an untested branch reads exactly
    like a covered one, which is the state this repo deletes branches over.
    """
    st = _load()
    assert st._decode_origin(r"C:\MT5_Lab".encode("utf-16-be")) == r"C:\MT5_Lab"
    assert st._decode_origin(r"C:\MT5_Lab".encode("utf-16-le")) == r"C:\MT5_Lab"


def test_a_trailing_null_terminator_is_stripped():
    """A path with a null on the end matches no running terminal, so it becomes a phantom.

    ⚠ **This test exists because the one it replaced could not fail.** The old test asserted that
    a correctly-decoded UTF-16 string contains no nulls — which the decode already guarantees, so
    deleting the strip entirely left it green. That is the repo's own rule arriving here: check
    that a test's inputs can distinguish the behaviours it names. A trailing terminator is an
    input where keeping the strip and dropping it give different answers.
    """
    st = _load()
    assert st._decode_origin("C:\\MT5_FFT\x00".encode("utf-16")) == r"C:\MT5_FFT"
