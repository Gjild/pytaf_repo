from __future__ import annotations

import sys

from .broker import main_broker

if __name__ == "__main__":
    sys.exit(main_broker(sys.stdin.fileno(), sys.stdout.fileno()))
