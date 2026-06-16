"""Package-level smoke tests for __init__ and __main__."""

import runpy
import sys

import transcribe
from transcribe import cli


def test_version_string_present():
    assert isinstance(transcribe.__version__, str)
    assert transcribe.__version__  # non-empty
    assert "__version__" in transcribe.__all__


def test_main_dunder_invokes_cli_main(monkeypatch):
    called = []
    monkeypatch.setattr(cli, "main", lambda: called.append(True))
    # Run the module as __main__ so the `if __name__ == "__main__"` block fires.
    monkeypatch.setattr(sys, "argv", ["transcribe"])
    runpy.run_module("transcribe.__main__", run_name="__main__")
    assert called == [True]
