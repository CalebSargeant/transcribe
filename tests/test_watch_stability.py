"""Tests for waiting until a recording has finished being written."""

import transcribe.watch as watch_mod
from transcribe.watch import wait_until_stable


def _fake_clock(monkeypatch, sizes):
    """Drive wait_until_stable deterministically over a scripted size sequence.

    ``time.sleep`` becomes a no-op and ``os.path.getsize`` yields the next
    scripted size, so the loop runs at full speed with no real waiting.
    """
    remaining = list(sizes)
    monkeypatch.setattr(watch_mod.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        watch_mod.os.path, "getsize", lambda path: remaining.pop(0) if remaining else sizes[-1]
    )


def test_waits_while_the_file_is_still_growing(monkeypatch):
    """A recorder writes for the whole meeting, so growth must not look finished."""
    # Grows for three polls, then holds steady long enough to count as stable.
    _fake_clock(monkeypatch, [10, 20, 30, 40, 40, 40, 40])
    assert wait_until_stable("/rec.mov", stable_seconds=10, poll_seconds=5) is True


def test_returns_true_once_size_holds(monkeypatch):
    _fake_clock(monkeypatch, [100] * 10)
    assert wait_until_stable("/rec.mov", stable_seconds=10, poll_seconds=5) is True


def test_zero_length_file_is_never_considered_stable(monkeypatch):
    """An empty placeholder must not be transcribed as if it were finished."""
    _fake_clock(monkeypatch, [0] * 20)
    monkeypatch.setattr(watch_mod.time, "monotonic", _counter(step=30))
    assert wait_until_stable("/rec.mov", stable_seconds=10, poll_seconds=5, timeout=60) is False


def test_missing_file_returns_false(monkeypatch):
    monkeypatch.setattr(watch_mod.time, "sleep", lambda seconds: None)

    def _gone(path):
        raise OSError("no such file")

    monkeypatch.setattr(watch_mod.os.path, "getsize", _gone)
    assert wait_until_stable("/rec.mov") is False


def test_gives_up_after_the_timeout(monkeypatch, capsys):
    """A file that never settles must not block the watcher forever."""
    sizes = iter(range(1, 10_000))
    monkeypatch.setattr(watch_mod.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(watch_mod.os.path, "getsize", lambda path: next(sizes))
    monkeypatch.setattr(watch_mod.time, "monotonic", _counter(step=100))

    assert wait_until_stable("/rec.mov", stable_seconds=10, poll_seconds=5, timeout=300) is False
    assert "still growing" in capsys.readouterr().out


def _counter(step):
    """Return a monotonic() stand-in that advances by ``step`` on every call."""
    state = {"now": 0.0}

    def _monotonic():
        state["now"] += step
        return state["now"]

    return _monotonic
