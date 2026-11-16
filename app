#!/usr/bin/env python3
"""Entry point for offline-focus-stats.

Both ``./app`` and ``python app`` are equivalent; the real implementation lives
in ``focus_stats.py`` next to this file.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from focus_stats import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
