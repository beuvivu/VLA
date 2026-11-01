"""Cho biết lần dựng lại trang có CHỈ đổi dấu giờ dựng hay không, để workflow bỏ commit thừa.

Đo 01-11-2026: 78/100 commit «docs: dựng lại trang Vietlott từ engine» chỉ đổi câu «Bản dữ liệu
được dựng lúc HH:MM dd/mm/yyyy» trong `docs/vietlott.html` cùng mã băm kéo theo trong
`docs/assets/release.json`; tháng 10 tệp ấy bị commit 548 lần. Mỗi commit thừa là một lần đua đẩy
với bot khác và thêm dung lượng kho, trong khi người đọc không thấy gì mới.

Đọc thay đổi ĐÃ STAGE so với HEAD. Mã thoát:

* 0 — không có gì, hoặc mọi trang đổi chỉ khác nhau ở dấu giờ dựng (manifest được phép đổi theo):
  workflow khôi phục bản HEAD và không commit. Câu trên trang vẫn đúng, vì nó nói «đây là bản chụp
  tại lần dựng trang» và nội dung bản chụp ấy không đổi.
* 1 — có thay đổi nội dung (trang khác ngoài dấu giờ, tệp không phải trang, trang mới hoặc bị xoá,
  hoặc manifest đổi một mình): commit như cũ. Lỗi bất ngờ cũng ra 1, tức mặc định là GHI.
"""
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
        return False  # manifest đổi một mình không phải hệ quả của dấu giờ
    for path in pages:
        if not path.endswith(".html"):
            return False
        before, after = _blob(f"HEAD:{path}"), _blob(f":{path}")
        if before is None or after is None or masked(before) != masked(after):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    return 0 if only_stamp_changed() else 1


if __name__ == "__main__":
    sys.exit(main())
