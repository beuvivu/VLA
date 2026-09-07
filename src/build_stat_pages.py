"""Dựng các trang thống kê riêng biệt có bộ lọc thời gian tùy biến.

Vì sao tính ở trình duyệt chứ không dựng sẵn
--------------------------------------------
Người dùng cần chọn dải ngày/tháng/năm tùy ý. Dựng sẵn mọi tổ hợp là không
khả thi, còn gọi API thì cần server — mà kho này phát hành site tĩnh trên
GitHub Pages, không có tiến trình nào chạy.

Lối thoát nằm ở kích thước dữ liệu: toàn bộ lịch sử là **35 KB** ở dạng hai
chữ số. Nhúng thẳng vào trang rồi tính bằng JavaScript cho ra bộ lọc tức thì,
không server, không độ trễ mạng. Đây là cách duy nhất thoả cả hai ràng buộc.

Ngưỡng cần theo dõi: nhúng dữ liệu bắt đầu bất tiện quanh mốc vài MB. Với
mức tăng hiện tại (một kỳ mỗi ngày, ~90 byte) thì mốc đó còn xa hàng chục
năm.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from ui_theme import app_shell_close, app_shell_open, stylesheet_link
from web_security import json_for_html_script, security_meta_tags

logger = logging.getLogger(__name__)

#: Xác suất một con lô bất kỳ về trong một kỳ: 1 - (99/100)^27.
LOTO_BASELINE = 1.0 - 0.99**27

#: Xác suất HAI con cụ thể cùng về trong một kỳ, theo bao hàm-loại trừ.
#: Không phải bình phương của tỉ lệ đơn: hai biến cố không độc lập vì cùng
#: rút từ 27 ô giải.
PAIR_BASELINE = 1.0 - 2.0 * (0.99**27) + (0.98**27)

#: Độ rộng chữ số của từng giải. CSV lưu kiểu số nguyên nên mất số 0 ở đầu;
#: đo được 10,3% số ô ngắn hơn độ rộng đúng. Thiếu bảng này thì mọi phép cắt
#: chữ số theo vị trí đều lệch.
PRIZE_WIDTH: dict[str, int] = {
    "special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
    "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2,
}


@dataclass(frozen=True)
class StatPage:
    """Mô tả một trang thống kê.

    Attributes:
        slug: Tên tệp không kèm ``.html``.
        title: Tiêu đề trang.
        subtitle: Mô tả ngắn dưới tiêu đề.
        controls: HTML của thanh điều khiển bộ lọc.
        body: HTML phần thân (thường là khung rỗng cho JS đổ vào).
        render: Tên hàm JavaScript vẽ lại trang khi bộ lọc đổi.
    """

    slug: str
    title: str
    subtitle: str
    controls: str
    body: str
    render: str


def load_draws(repo_root: Path) -> list[dict[str, object]]:
    """Đọc lịch sử và trả về dạng gọn để nhúng vào trang.

    Args:
        repo_root: Thư mục gốc của kho.

    Returns:
        Danh sách kỳ quay, mỗi phần tử ``{"d": ngày, "s": ĐB 5 chữ số,
        "n": [27 số hai chữ số]}``, sắp xếp tăng dần theo ngày.

    Raises:
        FileNotFoundError: Nếu thiếu ``data/xsmb.csv``.
    """
    path = repo_root / "data" / "xsmb.csv"
    if not path.exists():
        raise FileNotFoundError(f"thiếu {path}")

    frame = pd.read_csv(path, dtype=str).fillna("")
    frame = frame.sort_values("date").reset_index(drop=True)

    prize_cols = [c for c in frame.columns if c != "date"]
    draws: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        two_digits: list[str] = []
        special = ""
        for col in prize_cols:
            base = col.split("_")[0]
            width = PRIZE_WIDTH[base]
            # zfill là bắt buộc: CSV lưu số nguyên nên "05225" thành "5225".
            digits = str(row[col]).strip().zfill(width)
            if len(digits) != width or not digits.isdigit():
                continue
            two_digits.append(digits[-2:])
            if col == "special":
                special = digits
        if len(two_digits) == 27:
            draws.append({"d": str(row["date"]), "s": special, "n": two_digits})
    return draws


def _range_controls(*, mode: str = "day") -> str:
    """Thanh chọn dải thời gian.

    Args:
        mode: ``day`` cho hai ô chọn ngày, ``preset`` cho các nút nhanh.

    Returns:
        Chuỗi HTML.
    """
    presets = "".join(
        f'<button class="sp-chip" data-days="{d}">{label}</button>'
        for d, label in (
            (30, "30 kỳ"), (60, "60 kỳ"), (90, "90 kỳ"),
            (180, "180 kỳ"), (365, "1 năm"), (0, "Tất cả"),
        )
    )
    if mode == "preset":
        return f'<div class="sp-controls"><div class="sp-chips">{presets}</div></div>'
    return f"""
    <div class="sp-controls">
      <label>Từ ngày <input type="date" id="sp-from"></label>
      <label>Đến ngày <input type="date" id="sp-to"></label>
      <div class="sp-chips">{presets}</div>
      <span class="sp-count" id="sp-count"></span>
    </div>
    """


PAGES: tuple[StatPage, ...] = (
    StatPage(
        slug="bang-dac-biet",
        title="Bảng đặc biệt theo ngày",
        subtitle="Hai số cuối giải đặc biệt xếp theo ngày trong tháng và tháng trong năm.",
        controls='<div class="sp-controls"><label>Năm <select id="sp-year"></select></label>'
                 '<span class="sp-count" id="sp-count"></span></div>',
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialByDay",
    ),
    StatPage(
        slug="bang-dac-biet-thang",
        title="Bảng đặc biệt theo tháng",
        subtitle="Tần suất hai số cuối giải đặc biệt gom theo từng tháng.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialByMonth",
    ),
    StatPage(
        slug="bang-dac-biet-nam",
        title="Bảng đặc biệt theo năm",
        subtitle="Tần suất hai số cuối giải đặc biệt gom theo từng năm.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialByYear",
    ),
    StatPage(
        slug="tan-suat-loto",
        title="Tần suất lô tô",
        subtitle="Số lần mỗi con 00–99 về trong dải đã chọn, kèm mốc kỳ vọng.",
        controls=_range_controls(),
        body='<div id="sp-matrix" class="sp-matrix"></div>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderLotoFrequency",
    ),
    StatPage(
        slug="tan-suat-cap-loto",
        title="Tần suất cặp lô tô",
        subtitle="Số lần hai con lô cùng về trong một kỳ, kèm mốc cực đại ngẫu nhiên.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderPairFrequency",
    ),
    StatPage(
        slug="dau-duoi-loto",
        title="Đầu đuôi lô tô",
        subtitle="Phân bố chữ số đầu và chữ số đuôi của toàn bộ lô tô trong dải đã chọn.",
        controls=_range_controls(),
        body='<div class="sp-duo">'
             '<div><h3>Theo chữ số ĐẦU</h3><table class="sp-table" id="sp-head"></table></div>'
             '<div><h3>Theo chữ số ĐUÔI</h3><table class="sp-table" id="sp-tail"></table></div>'
             "</div>",
        render="renderHeadTail",
    ),
    StatPage(
        slug="chu-ky-dac-biet",
        title="Chu kỳ giải đặc biệt",
        subtitle="Số kỳ chưa về của từng con 00–99 ở giải đặc biệt, và chu kỳ dài nhất trong lịch sử.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialCycle",
    ),
    StatPage(
        slug="cau-dac-biet-theo-bo-so",
        title="Cầu giải đặc biệt theo bộ số",
        subtitle="Điểm rơi của từng bộ số ở giải đặc biệt: lần về gần nhất, khoảng cách và số lần.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialBySet",
    ),
    StatPage(
        slug="giai-db-ngay-mai",
        title="Giải đặc biệt ngày mai",
        subtitle="Xếp hạng tham khảo cho kỳ kế tiếp, dựng từ chu kỳ và tần suất lịch sử.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderTomorrow",
    ),
    StatPage(
        slug="thong-ke-tong-hop",
        title="Thống kê tổng hợp",
        subtitle="Bảng tổng hợp đa chiều: tần suất, chu kỳ gan, đầu đuôi và tổng trên cùng một dải.",
        controls=_range_controls(),
        body='<div id="sp-kpi" class="sp-kpi"></div>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderOverview",
    ),
)


#: Ghi chú mốc ngẫu nhiên cho từng trang. Trang xếp hạng nào cũng phải có,
#: nếu không bảng trông như quy luật trong khi đó là mức ngẫu nhiên thường
#: tạo ra. Con số lấy từ mô phỏng, ghi trong
#: documentation/architecture/soi-cau-ml-mapping.md.
CHANCE_NOTES: dict[str, str] = {
    "tan-suat-loto": (
        "Kỳ vọng mỗi con là <b>1 − (0,99)²⁷ ≈ 23,77%</b> mỗi kỳ. Con dẫn đầu "
        "trong 100 con luôn cao hơn kỳ vọng kể cả khi dữ liệu hoàn toàn ngẫu "
        "nhiên — cột “So kỳ vọng” là để so, không phải để chọn."
    ),
    "tan-suat-cap-loto": (
        "Có <b>4 950</b> cặp số. Mô phỏng 400 lần lịch sử ngẫu nhiên 393 kỳ cho "
        "cực đại trung bình <b>39,8</b> lần (khoảng 90%: 37–43), trong khi kỳ "
        "vọng mỗi cặp chỉ 21,6. Một cặp chỉ đáng chú ý khi vượt hẳn khoảng đó."
    ),
    "chu-ky-dac-biet": (
        "Giải đặc biệt có 100 kết quả hai số nên khoảng gan trung bình là 100 "
        "kỳ. Gan dài không làm con số “sắp về”: mỗi kỳ vẫn là 1/100 độc lập "
        "với lịch sử."
    ),
    "cau-dac-biet-theo-bo-so": (
        "Bảng này mô tả lịch sử điểm rơi, không phải dự báo. Khoảng cách giữa "
        "hai lần về của cùng một bộ số phân bố hình học quanh trung bình 100 kỳ."
    ),
    "giai-db-ngay-mai": (
        "⚠️ Đây là <b>xếp hạng mô tả</b> dựng từ chu kỳ lịch sử, "
        "<b>không phải xác suất đã hiệu chuẩn</b> và không bảo đảm kết quả. "
        "Đo trên chính kho này: không mô hình nào trong 12 họ đã thử vượt được "
        "tỉ lệ nền."
    ),
}


def _asset(name: str) -> str:
    """Đọc tệp tài nguyên đi kèm mô-đun.

    Args:
        name: Tên tệp trong ``src/templates``.

    Returns:
        Nội dung tệp.
    """
    return (Path(__file__).resolve().parent / "templates" / name).read_text(encoding="utf-8")


def render_page(page: StatPage, draws: list[dict[str, object]], *, generated: str) -> str:
    """Dựng HTML hoàn chỉnh cho một trang thống kê.

    Args:
        page: Mô tả trang.
        draws: Lịch sử đã nạp, sẽ được nhúng vào trang.
        generated: Dấu thời gian dựng, hiển thị ở chân trang.

    Returns:
        Chuỗi HTML đầy đủ.
    """
    note = CHANCE_NOTES.get(page.slug, "")
    note_html = f'<p class="sp-note">{note}</p>' if note else ""
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>{page.title} · VLA</title>
<style>
{_asset("stat_pages.css")}
</style></head><body>
{app_shell_open(f"{page.slug}.html", wide=True)}
<div style="margin-bottom:1rem"><a href="index.html">← Trang chính</a></div>
<h1>{page.title}</h1>
<p class="vla-muted" style="max-width:60rem;line-height:1.65">{page.subtitle}</p>
{page.controls}
{page.body}
{note_html}
<p class="vla-muted" style="margin-top:1.5rem;font-size:.75rem">
Dựng lúc {generated}. Toàn bộ tính toán chạy trong trình duyệt trên
{len(draws)} kỳ đã nhúng — không gọi mạng, không máy chủ.</p>
{app_shell_close(f"{page.slug}.html")}
<script>window.__VLA_DRAWS__={json_for_html_script(draws)};</script>
<script>
{_asset("stat_pages.js")}
boot({json.dumps(page.render)});
</script>
</body></html>
"""


def build(repo_root: Path, docs_dir: Path) -> list[Path]:
    """Dựng toàn bộ trang thống kê.

    Args:
        repo_root: Thư mục gốc của kho.
        docs_dir: Thư mục đầu ra.

    Returns:
        Danh sách tệp đã ghi.
    """
    draws = load_draws(repo_root)
    if not draws:
        raise SystemExit("không nạp được kỳ nào từ data/xsmb.csv")

    docs_dir.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    written: list[Path] = []
    for page in PAGES:
        target = docs_dir / f"{page.slug}.html"
        target.write_text(render_page(page, draws, generated=generated), encoding="utf-8")
        written.append(target)
        logger.info("đã ghi %s", target.name)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    """Điểm vào dòng lệnh.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát 0.
    """
    parser = argparse.ArgumentParser(description="Dựng các trang thống kê riêng biệt.")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(__file__).resolve().parents[1]
    files = build(root, root / args.docs_dir)
    logger.info("Xong: %d trang", len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
