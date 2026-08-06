"""The ChartSpec cache — served as BYTES, written ATOMICALLY.

🔴 **`GET /runs/{id}/chart-spec` used to `json.loads` the cached file and return the dict, which
made FastAPI immediately `json.dumps` it again.** MEASURED end to end on run `997c14cc53bc`'s real
4 MB cache: **0.40s → 0.004s**, roughly 100x, for a round trip whose output is byte-equivalent to
its input (`json.loads` 0.089s + `json.dumps` 0.171s of it, timed directly). The saving scales with
the spec, which is what makes shipping a whole run's history a viable design rather than merely a
smaller one.

⚠ **Serving bytes means NOTHING PARSES THEM, and that moves a guarantee.** The old reader wrapped
its parse in `except ValueError: pass` and rebuilt a corrupt cache; bytes have no such moment, so a
half-written file would reach the browser as a JSON syntax error. The atomic write is therefore not
a tidy-up — it is what makes the fast path safe, and the tests below pin both halves together.
"""

import json

import pytest

from services import chart_spec


def _cache(tmp_path, run_id, text):
    d = tmp_path / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "chart_spec.json").write_text(text)
    return d


@pytest.fixture
def lab_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_spec, "LAB_RESULTS_DIR", tmp_path)
    return tmp_path


def test_a_warm_cache_comes_back_as_the_bytes_on_disk(lab_dir):
    """The whole point: no parse, no re-serialize — the file IS the response body."""
    raw = '{"candles":[{"time":1,"open":2.0}],"trades":[]}'
    _cache(lab_dir, "r1", raw)
    got = chart_spec.cached_chart_spec_bytes("r1")
    assert got == raw.encode()
    assert json.loads(got)["candles"][0]["time"] == 1


def test_no_cache_is_none_rather_than_an_error(lab_dir):
    """A run whose spec has never been built is the normal FIRST-OPEN case, not a failure — the
    router falls through to the build, which is the only thing that can tell an unbuilt spec from
    an unknown run."""
    assert chart_spec.cached_chart_spec_bytes("never-built") is None


def test_a_torn_write_is_refused_instead_of_being_streamed_to_the_browser(lab_dir):
    """The failure mode bytes-without-parsing introduces. A truncated file is perfectly readable
    and completely invalid, and serving it would surface as a JSON syntax error in the chart with
    nothing on the backend having noticed."""
    _cache(lab_dir, "r2", '{"candles":[{"time":1,"open":2.0},{"tim')
    assert chart_spec.cached_chart_spec_bytes("r2") is None


def test_an_empty_cache_file_is_refused(lab_dir):
    """Zero bytes is what a crash between `open` and `write` leaves behind."""
    _cache(lab_dir, "r3", "")
    assert chart_spec.cached_chart_spec_bytes("r3") is None


def test_surrounding_whitespace_does_not_disqualify_a_good_cache(lab_dir):
    """A cache written by an older build (or by hand) may carry a trailing newline. The shape check
    is a torn-write backstop, and it must not start rejecting valid caches — that would silently
    turn every warm open back into a 7-second rebuild."""
    _cache(lab_dir, "r4", '\n  {"candles":[]}\n')
    assert chart_spec.cached_chart_spec_bytes("r4") is not None


def test_the_cache_is_written_atomically_and_leaves_no_temp_behind(lab_dir, monkeypatch):
    """`os.replace` is atomic on one filesystem, so a reader sees the whole old file or the whole
    new one and never a prefix of the new one — which is the guarantee that lets the read path skip
    parsing entirely.

    ⚠ It SPIES on `os.replace` rather than only checking the resulting file, because the resulting
    file is identical either way: a plain `write_text` leaves correct content and no `.tmp`, so an
    output-only assertion passes against the non-atomic version and proves nothing. Mutation
    confirmed exactly that before this was rewritten."""
    calls = []
    real_replace = chart_spec.os.replace
    monkeypatch.setattr(chart_spec.os, "replace",
                        lambda a, b: (calls.append((str(a), str(b))), real_replace(a, b))[1])
    d = lab_dir / "r5"
    d.mkdir()
    chart_spec._write_spec_cache(d / "chart_spec.json", {"candles": [], "trades": []})

    assert len(calls) == 1, "the cache was not swapped into place atomically"
    src, dst = calls[0]
    assert src.endswith(".tmp") and dst.endswith("chart_spec.json")
    assert json.loads((d / "chart_spec.json").read_text()) == {"candles": [], "trades": []}
    assert list(d.glob("*.tmp")) == []


def test_the_cache_is_written_without_padding_whitespace(lab_dir):
    """These bytes ARE the response now, so `json.dumps`'s default ", " / ": " is 418 KB of padding
    shipped to the browser on a real spec (4,029,681 bytes against 3,611,888, measured). It is also
    what FastAPI's own JSONResponse emits, so a cached and a freshly-built response stay identical.
    """
    d = lab_dir / "r6"
    d.mkdir()
    chart_spec._write_spec_cache(d / "chart_spec.json", {"a": 1, "b": [1, 2]})
    assert (d / "chart_spec.json").read_text() == '{"a":1,"b":[1,2]}'


def test_what_is_written_is_what_is_served(lab_dir):
    """The round trip that matters, stated as one property: whatever the builder cached, the fast
    path hands back the same object. A separator or encoding change on one side alone breaks this
    before it can reach a browser."""
    spec = {"candles": [{"time": 1, "open": 1.5}], "trades": [], "runTimeframe": "M15"}
    d = lab_dir / "r7"
    d.mkdir()
    chart_spec._write_spec_cache(d / "chart_spec.json", spec)
    assert json.loads(chart_spec.cached_chart_spec_bytes("r7")) == spec
