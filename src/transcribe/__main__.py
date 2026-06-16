"""Module entry point: ``python -m transcribe`` and PyInstaller bootstrap.

PyInstaller runs this file directly as the top-level ``__main__`` script (see
``transcribe.spec``), so it is NOT imported as part of the ``transcribe``
package in the frozen binary. A relative import (``from .cli import main``)
therefore fails at startup with "attempted relative import with no known
parent package". Use an absolute import so the entry point works both as
``python -m transcribe`` and inside the PyInstaller bundle.
"""

from transcribe.cli import main

if __name__ == "__main__":
    main()
