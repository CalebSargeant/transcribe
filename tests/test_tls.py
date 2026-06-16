"""Tests for transcribe.tls: CA bundle hardening."""

from transcribe.tls import _ensure_tls_ca_bundle


def test_clears_invalid_env_overrides(monkeypatch, tmp_path):
    missing = str(tmp_path / "nope.pem")
    monkeypatch.setenv("SSL_CERT_FILE", missing)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", missing)

    valid = tmp_path / "ca.pem"
    valid.write_text("cert")
    # Force certifi to report our valid file.
    import certifi

    monkeypatch.setattr(certifi, "where", lambda: str(valid))

    _ensure_tls_ca_bundle()

    import os

    # Invalid paths were replaced (setdefault won't run because env was popped).
    assert os.environ.get("SSL_CERT_FILE") == str(valid)
    assert os.environ.get("REQUESTS_CA_BUNDLE") == str(valid)


def test_keeps_valid_existing_env(monkeypatch, tmp_path):
    valid = tmp_path / "ca.pem"
    valid.write_text("cert")
    monkeypatch.setenv("SSL_CERT_FILE", str(valid))
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    other = tmp_path / "other.pem"
    other.write_text("cert2")
    import certifi

    monkeypatch.setattr(certifi, "where", lambda: str(other))

    _ensure_tls_ca_bundle()

    import os

    # Existing valid SSL_CERT_FILE preserved (setdefault is a no-op).
    assert os.environ.get("SSL_CERT_FILE") == str(valid)
    # REQUESTS_CA_BUNDLE was unset -> filled from certifi.
    assert os.environ.get("REQUESTS_CA_BUNDLE") == str(other)


def test_never_raises(monkeypatch):
    # Even if certifi/ssl blow up, the function must swallow it.
    import certifi

    monkeypatch.setattr(certifi, "where", lambda: (_ for _ in ()).throw(RuntimeError()))
    # Should not raise.
    _ensure_tls_ca_bundle()
