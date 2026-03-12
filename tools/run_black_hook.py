from __future__ import annotations

import subprocess
import sys


def main(paths: list[str]) -> int:
    for path in paths:
        result = subprocess.run([sys.executable, "-m", "black", path], check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
