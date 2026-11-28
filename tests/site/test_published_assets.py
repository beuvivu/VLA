from __future__ import annotations

import re
import posixpath
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

DUOI_TAI_NGUYEN = (".css", ".js", ".woff2", ".woff", ".png", ".svg", ".webp", ".ico")

_THAM_CHIEU = re.compile(r'(?:href|src)="((?!https?:|data:|mailto:|#)[^"]+)"')

NGOAI_LE = {
    "assets/matrix-virt.js",
    "assets/apply-data-styles.js",
}


def _duong_dan_trang_tro_toi() -> dict[str, set[str]]:
    ra: dict[str, set[str]] = {}
    for trang in sorted(DOCS.glob("*.html")):
        noi_dung = trang.read_text(encoding="utf-8")
        for khop in _THAM_CHIEU.finditer(noi_dung):
            dich = khop.group(1).split("?")[0].split("#")[0]
            if dich and not dich.endswith("/"):
                ra.setdefault(dich, set()).add(trang.name)
    scanned = set()
    while True:
        pending = [name for name in ra if name.endswith('.css') and name not in scanned]
        if not pending:
            break
        for name in pending:
            scanned.add(name)
            stylesheet = DOCS / name
            if not stylesheet.is_file():
                continue
            for reference in re.findall(r'url\(\s*[\"\']?([^\s)\"\']+)', stylesheet.read_text()):
                if re.match(r'(?:[a-z]+:|//|#)', reference, re.I):
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), reference.split('?')[0].split('#')[0]))
                ra.setdefault(target, set()).update(ra[name])
    return ra


def test_the_published_tree_has_pages_to_scan() -> None:
    assert len(list(DOCS.glob("*.html"))) >= 29


def test_no_published_page_points_at_a_file_that_is_not_there() -> None:
    tro_toi = _duong_dan_trang_tro_toi()
    assert tro_toi, "không trang nào trỏ tới tài nguyên nào — quét hỏng"
    thieu = {
        f"{trang} -> {dich}"
        for dich, trangs in tro_toi.items()
        if not (DOCS / dich).exists()
        for trang in sorted(trangs)
    }
    assert thieu == set()


def test_every_published_asset_is_reachable_from_some_page() -> None:
    tro_toi = set(_duong_dan_trang_tro_toi())
    co_that = {
        tep.relative_to(DOCS).as_posix()
        for tep in DOCS.rglob("*")
        if tep.is_file() and tep.suffix in DUOI_TAI_NGUYEN
    }
    assert co_that, "không tìm thấy tài nguyên nào — quét hỏng"
    thua = co_that - tro_toi - NGOAI_LE
    assert thua == set(), (
        "tài nguyên không trang nào dùng; gỡ đi, hoặc thêm vào NGOAI_LE kèm "
        "lý do đo được"
    )
