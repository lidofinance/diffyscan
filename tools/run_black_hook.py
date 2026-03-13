from __future__ import annotations

import subprocess
import sys


def main(paths: list[str]) -> int:
    if not paths:
        return 0
    result = subprocess.run([sys.executable, "-m", "black", *paths], check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
