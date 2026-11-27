from __future__ import annotations

import argparse
import re
import subprocess
import sys

MANIFEST = "docs/assets/release.json"
STAMP = re.compile(r"(Bản dữ liệu được dựng lúc )\d{2}:\d{2} \d{2}/\d{2}/\d{4}")


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], capture_output=True, check=False)


def _blob(spec: str) -> str | None:
    shown = _git("show", spec)
    return shown.stdout.decode("utf-8") if shown.returncode == 0 else None


def masked(text: str) -> str:
    return STAMP.sub(r"\1<giờ dựng>", text)


def only_stamp_changed() -> bool:
    listed = _git("diff", "--cached", "--name-only", "-z")
    if listed.returncode != 0:
        return False
    paths = [p for p in listed.stdout.decode("utf-8").split("\0") if p]
    pages = [p for p in paths if p != MANIFEST]
    if not paths:
        return True
    if not pages:
        return False
    for path in pages:
        if not path.endswith(".html"):
            return False
        before, after = _blob(f"HEAD:{path}"), _blob(f":{path}")
        if before is None or after is None or masked(before) != masked(after):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    return 0 if only_stamp_changed() else 1


if __name__ == "__main__":
    sys.exit(main())
