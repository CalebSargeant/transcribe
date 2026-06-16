"""TLS CA bundle hardening for bundled binaries."""

import os
import ssl


def _ensure_tls_ca_bundle():
    """Ensure HTTPS clients have a valid CA bundle, even in bundled binaries.

    In some PyInstaller/Homebrew environments, SSL_CERT_FILE/REQUESTS_CA_BUNDLE
    can point at a non-existent path (e.g. a stale _MEI* directory), which breaks
    all outbound HTTPS (Slack, OpenAI, Google APIs).

    This helper cleans up invalid env vars and picks a sane CA file from either
    certifi (if available) or the system defaults.
    """
    try:
        from pathlib import Path as _Path

        # Clear invalid env overrides first
        for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            value = os.environ.get(var)
            if value and not _Path(value).exists():
                print(f"Warning: {var} points to missing path: {value} - ignoring it")
                os.environ.pop(var, None)

        cafile = None

        # Prefer certifi if available and valid
        try:
            import certifi  # type: ignore

            candidate = certifi.where()
            if candidate and _Path(candidate).exists():
                cafile = candidate
        except Exception:
            cafile = None

        # Fallback to system default verify paths
        if cafile is None:
            default = ssl.get_default_verify_paths().cafile
            if default and _Path(default).exists():
                cafile = default

        if cafile:
            # Help both requests (REQUESTS_CA_BUNDLE) and httpx/OpenAI (SSL_CERT_FILE)
            os.environ.setdefault("SSL_CERT_FILE", cafile)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", cafile)
    except Exception:
        # Never let TLS configuration crash the tool
        pass
