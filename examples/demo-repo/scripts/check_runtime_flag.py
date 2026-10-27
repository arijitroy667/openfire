from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from runtime_flags import debug_enabled  # noqa: E402


def main() -> int:
    # Simulate a shell that exported the flag with no value: FOO="" ./run.
    os.environ["ENGBRAIN_DEMO_DEBUG"] = ""
    if debug_enabled(os.environ.get("ENGBRAIN_DEMO_DEBUG")):
        print("Debug mode was enabled by an empty ENGBRAIN_DEMO_DEBUG value")
        return 1
    print("An empty ENGBRAIN_DEMO_DEBUG value correctly keeps debug mode off")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())