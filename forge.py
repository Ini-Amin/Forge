#!/usr/bin/env python3
"""forge — CLI runner and entrypoint for modular forge package."""
import sys
from pathlib import Path

# Ensure package directory is importable
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from forge.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
