#!/usr/bin/env python
"""Launcher shim so Conduit runs from a checkout without installing it.

    python start.py run --tray
    python start.py check

Deliberately *not* named ``conduit.py``: a module of that name in the project
root shadows the ``conduit`` package for anything doing ``import conduit`` with
the root on sys.path, which breaks tests and one-liners in confusing ways.

If you would rather install it (``pip install -e .``), the ``conduit`` command
does exactly the same thing.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from conduit.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
