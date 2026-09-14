"""Chỉ tám tên miền trong danh sách được xuất hiện trong mã và dữ liệu.

Đây là bước "rà soát chéo" biến thành phép kiểm. Một lượt quét thủ công chỉ
đúng vào ngày quét; phép kiểm thì đỏ ngay khi ai đó thêm một nguồn ngoài danh
sách — kể cả khi họ thêm vào một tệp chưa từng có nguồn nào.

Phạm vi quét là MÃ và DỮ LIỆU, không phải tài liệu: tài liệu nghiên cứu có
trích dẫn học thuật tới nơi một phương pháp thống kê được mô tả, và đó không
phải nguồn cào dữ liệu. Xoá chúng sẽ làm mất khả năng kiểm chứng lại phương
pháp, nên chúng được giữ có chủ ý.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sources import FALLBACK_SOURCE_NAMES, PRIMARY_SOURCE_NAMES

ROOT = Path(__file__).resolve().parents[1]

ALLOWED = {
    *PRIMARY_SOURCE_NAMES,
    *FALLBACK_SOURCE_NAMES,
    # Cùng tên miền, khác tiền tố "www."
    "www.hainhay.net",
    "www.xosominhngoc.com",
}

#: Tên miền hạ tầng, không phải nguồn xổ số.
INFRASTRUCTURE = re.compile(
    r"(github\.(com|io)|githubusercontent\.com|shields\.io|openxmlformats\.org"
    r"|workers\.dev|deno\.dev|cloudflare\.com|pytest\.org|cron-job\.org"
    r"|example\.com|schemas\.|fonts\.g)",
    re.IGNORECASE,
)

SCANNED_SUFFIXES = (".py", ".js", ".mjs", ".yml", ".yaml", ".json", ".html", ".j2", ".sh", ".toml")
SKIPPED_DIRECTORIES = {".git", "__pycache__", ".ruff_cache", "node_modules", ".pytest_cache"}

#: Trang xổ số nhận diện theo hình dạng tên miền, để bắt cả nguồn chưa từng
#: biết tới — danh sách đen chép sẵn thì chỉ bắt được thứ đã biết.
#:
#: BẮT BUỘC có lược đồ ``http(s)://``. Yêu cầu là loại bỏ URL/API gọi ra
#: ngoài, nên phần còn lại không thuộc phạm vi — và bản đầu không đòi lược đồ
#: đã báo động giả ở ba thứ hoàn toàn vô hại: tên tệp trang cục bộ
#: (``tan-suat-loto.html``), truy cập thuộc tính Python (``loto.dtype``), và
#: chính các chuỗi mẫu trong tệp kiểm này.
LOTTERY_SHAPED = re.compile(
    r"https?://((?:[a-z0-9-]+\.)*[a-z0-9-]*"
    r"(?:xoso|xskt|kqxs|ketqua|loto|lo-de|soicau|rongbach|caulo|minhngoc|hainhay)"
    r"[a-z0-9-]*\.[a-z.]{2,12})\b",
    re.IGNORECASE,
)


def _scanned_files() -> list[Path]:
    out: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if SKIPPED_DIRECTORIES & set(path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return out


def test_the_scan_actually_reaches_the_source_catalogue() -> None:
    """Chốt chặn cho phép kiểm dưới: nếu phép quét không tới được tệp danh mục
    nguồn thì nó xanh mà chẳng chứng minh gì."""
    files = _scanned_files()
    assert (ROOT / "src" / "sources.py") in files
    assert (ROOT / "worker" / "src" / "sources.js") in files
    assert len(files) > 100
    found = LOTTERY_SHAPED.findall((ROOT / "src" / "sources.py").read_text(encoding="utf-8"))
    assert len(set(found)) >= 6, "biểu thức nhận diện không bắt được danh mục thật"


def test_no_lottery_domain_outside_the_approved_list_appears_in_code_or_data() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for raw in LOTTERY_SHAPED.findall(text):
            domain = raw.lower().rstrip(".")
            if domain in ALLOWED or INFRASTRUCTURE.search(domain):
                continue
            offenders.setdefault(domain, []).append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "có nguồn xổ số ngoài danh sách được duyệt:\n"
        + "\n".join(f"  {d}: {sorted(set(files))[:4]}" for d, files in offenders.items())
    )


@pytest.mark.parametrize(
    "removed",
    ["rongbachkim.net", "caulo100.com", "soicauvn247.com", "ketqua.net", "xosome.vn"],
)
def test_the_scan_would_catch_a_source_that_crept_back_in(removed: str, tmp_path) -> None:
    """Phép kiểm trên chỉ đáng tin nếu nó THẬT SỰ bắt được nguồn lạ.

    Năm tên ở đây gồm ba tên từng có trong tài liệu nghiên cứu và hai tên
    chưa từng xuất hiện — để chứng minh phép quét bắt theo hình dạng chứ
    không theo một danh sách đen chép sẵn.
    """
    assert LOTTERY_SHAPED.search(f'URL = "https://{removed}/thongke.html"')
    # Không có lược đồ thì KHÔNG bắt — đó là chủ ý, không phải sót.
    assert LOTTERY_SHAPED.search(f"tham khảo {removed} cho phương pháp này") is None
    assert removed not in ALLOWED
