from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from version_policy import SUPPORTED_URLLIB3  # noqa: E402

_PIN = re.compile(r"^urllib3==([^\s;]+)", re.MULTILINE)


def pinned_urllib3() -> str | None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = _PIN.search(text)
    return match.group(1) if match else None


def main() -> int:
    pinned = pinned_urllib3()
    if pinned is None:
        print("urllib3 is not pinned in requirements.txt")
        return 1
    if pinned != SUPPORTED_URLLIB3:
        print(
            "urllib3 runtime bound mismatch: requirements.txt pins urllib3==%s "
            "while the import-time guard rejects versions above %s."
            % (pinned, SUPPORTED_URLLIB3)
        )
        return 1
    print("urllib3 pin and runtime bound agree at %s" % pinned)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())