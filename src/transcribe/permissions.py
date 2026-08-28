"""Working out which application a macOS permission has to be granted to.

macOS attributes a permission request to the *responsible* process, which for a
command-line tool is the terminal it was launched from, not the tool itself.
That is rarely obvious, and Full Disk Access in particular never populates its
list from a denied request, so nothing appears there to click. Naming the app
turns "which of these do I add?" into a single instruction.

A prompt also only appears when there is a UI session to show it in. A launchd
agent, or a tool invoked by another process, gets a silent denial instead, which
is why these permissions have to be granted interactively once.
"""

import os
import re
import subprocess

_APP_BUNDLE = re.compile(r"/([^/]+\.app)/Contents/MacOS/")

# A shell chain is short; this only guards against a pathological process tree.
_MAX_DEPTH = 12


def responsible_app():
    """Return the name of the enclosing .app bundle, or None outside one."""
    pid = os.getpid()
    for _ in range(_MAX_DEPTH):
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.SubprocessError, OSError):
            return None

        parts = result.stdout.strip().split(None, 1)
        if len(parts) != 2:
            return None
        parent, command = parts

        match = _APP_BUNDLE.search(command)
        if match:
            return match.group(1)[:-4]

        try:
            pid = int(parent)
        except ValueError:
            return None
        if pid <= 1:
            return None
    return None


def grant_hint(pane, *, needs_manual_add=False):
    """Explain which app to grant a permission to, and where.

    ``pane`` is the System Settings pane name, e.g. "Calendars".
    ``needs_manual_add`` covers panes that never list an app until you add it.
    """
    app = responsible_app()
    target = f"{app}" if app else "the terminal app you are running this from"

    lines = [
        f"Grant it to {target} under System Settings > Privacy & Security > {pane}.",
    ]
    if needs_manual_add:
        lines.append(
            f"  {pane} never fills itself in from a denied request, so nothing appears "
            "there on its own; add the app yourself with the '+' button."
        )
    lines.append(
        f"  Quit {app or 'the app'} completely (Cmd-Q) and reopen it afterwards: "
        "the permission is only re-read at launch."
    )
    return "\n".join(lines)
