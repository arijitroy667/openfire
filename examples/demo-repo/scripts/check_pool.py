from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pool_config import MAX_CONNECTIONS


def main() -> int:
    if MAX_CONNECTIONS < 4:
        print("Connection pool exhausted: only one worker can acquire a connection")
        return 1
    print("Pool check passed: concurrent workers acquired connections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
