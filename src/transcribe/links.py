"""Resolving a web URL for a destination folder, for use in notifications.

Cloud storage differs in what it will let you link to:

* **Google Drive** exposes folder ids through its API, so a notification can
  deep-link straight to the meeting's folder.
* **iCloud Drive** has no path-addressable web URL. A shareable link exists only
  once a person shares an item, and there is no API to mint one, so the best
  available link is iCloud Drive itself.

``file://`` is deliberately never returned. Slack does not linkify it, so it
renders as dead text and looks broken; a local path is shown as plain text
instead, which people can paste into Finder.
"""

from pathlib import Path

# Every iCloud Drive path contains this component.
ICLOUD_MARKER = "com~apple~CloudDocs"

# Directory names Google Drive's desktop client uses for a mounted account.
GOOGLE_DRIVE_MARKERS = ("Google Drive", "GoogleDrive")

DEFAULT_ICLOUD_URL = "https://www.icloud.com/iclouddrive/"


def storage_kind(folder_path):
    """Classify a folder as ``icloud``, ``google_drive``, or ``local``."""
    path = str(folder_path)
    if ICLOUD_MARKER in path:
        return "icloud"
    if any(marker in path for marker in GOOGLE_DRIVE_MARKERS):
        return "google_drive"
    return "local"


def icloud_folder_url(folder_path, config=None):
    """Return a link to iCloud Drive on the web.

    This cannot point at ``folder_path`` itself: iCloud Drive has no
    path-addressable URL, and share links are minted by a person sharing an
    item, not by an API. The link lands in iCloud Drive, and the notification
    names the folder so it can be found from there.
    """
    return (config or {}).get("icloud_base_url") or DEFAULT_ICLOUD_URL


def folder_url(folder_path, config=None):
    """Best available web URL for ``folder_path``, or None if there is none.

    Returns None rather than a ``file://`` URL so callers can present the local
    path as text instead of a link that does not work.
    """
    config = config or {}
    kind = storage_kind(folder_path)

    if kind == "icloud":
        return icloud_folder_url(folder_path, config)

    if kind == "google_drive":
        from .gdrive import get_google_drive_folder_url

        return get_google_drive_folder_url(folder_path)

    return None


def describe_location(folder_path, config=None):
    """Return ``(url, label, local_path)`` describing where a meeting was filed.

    ``url`` is None when the storage offers no linkable address. ``label`` is
    what a link should say; ``local_path`` is always present so a notification
    can show where the files actually are.
    """
    config = config or {}
    kind = storage_kind(folder_path)
    url = folder_url(folder_path, config)
    labels = {
        "icloud": "Open iCloud Drive",
        "google_drive": "Open folder in Google Drive",
        "local": "Open folder",
    }
    return url, labels.get(kind, "Open folder"), str(Path(folder_path))
