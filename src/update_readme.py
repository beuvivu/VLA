from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path("data")
README = Path("README.md")
FUN_PREDICTION = DATA_DIR / "predict" / "fun_draw_next.json"
logger = logging.getLogger(__name__)

WIDTHS = {
    "special": 5,
    "prize1": 5,
    "prize2": 5,
    "prize3": 5,
    "prize4": 4,
    "prize5": 4,
    "prize6": 3,
    "prize7": 2,
}

GROUPS: list[tuple[str, list[str]]] = [
    ("Giải đặc biệt", ["special"]),
    ("Giải nhất", ["prize1"]),
    ("Giải nhì", ["prize2_1", "prize2_2"]),
    ("Giải ba", ["prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6"]),
    ("Giải tư", ["prize4_1", "prize4_2", "prize4_3", "prize4_4"]),
    ("Giải năm", ["prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6"]),
    ("Giải sáu", ["prize6_1", "prize6_2", "prize6_3"]),
    ("Giải bảy", ["prize7_1", "prize7_2", "prize7_3", "prize7_4"]),
]


def _fmt_width(field: str, val: int) -> str:
    key = "special"
    if field.startswith("prize"):
        key = field.split("_", 1)[0]
    w = WIDTHS.get(key, 0)
    return f"{int(val):0{w}d}" if w else str(int(val))


def _load_latest_row(csv_path: Path) -> pd.Series:
    df = pd.read_csv(csv_path)
    if "date" not in df.columns or df.empty:
        raise ValueError(f"Tệp dữ liệu không hợp lệ: {csv_path}")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    return df.iloc[-1]


def _build_lottery_table(latest_raw: pd.Series) -> str:
    d = pd.to_datetime(latest_raw["date"]).date()
    d_str = d.strftime("%d-%m-%Y")
    rows = [f"<tr><td>Ngày</td><td>{d_str}</td></tr>"]
    for label, fields in GROUPS:
        vals = ", ".join(_fmt_width(f, int(latest_raw[f])) for f in fields)
        rows.append(f"<tr><td>{label}</td><td>{vals}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def _build_loto_table(latest_2d: pd.Series) -> str:
    nums = []
    for k, v in latest_2d.items():
        if k == "date":
            continue
        try:
            nums.append(int(v))
        except (TypeError, ValueError) as exc:
            logger.debug("Bỏ qua giá trị lô tô không hợp lệ %r: %s", v, exc)
            continue

    tails_by_head: dict[int, list[int]] = {h: [] for h in range(10)}
    for n in nums:
        head = n // 10
        tail = n % 10
        if 0 <= head <= 9:
            tails_by_head[head].append(tail)

    rows = ["<tr><td>Đầu</td><td>Đuôi</td></tr>"]
    for head in range(10):
        tails = ", ".join(str(t) for t in tails_by_head[head])
        rows.append(f"<tr><td>{head}</td><td>{tails}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def _render_block(lottery_html: str, loto_html: str) -> str:
    return (
        "<!-- SNAPSHOT:BEGIN -->\n"
        "| Xổ số | Lô tô |\n"
        "| :------------: | :----------: |\n"
        f"| {lottery_html} | {loto_html} |\n"
        "<!-- SNAPSHOT:END -->\n"
    )


def _replace_between_markers(text: str, new_block: str) -> str:
    if "<!-- SNAPSHOT:BEGIN -->" in text and "<!-- SNAPSHOT:END -->" in text:
        pre, rest = text.split("<!-- SNAPSHOT:BEGIN -->", 1)
        _, post = rest.split("<!-- SNAPSHOT:END -->", 1)
        return pre.rstrip() + "\n\n" + new_block + post.lstrip()

    pat = re.compile(
        r"\| Lottery \(Xổ số\) \| Loto \(Lô tô\) \|\n\| :\-+:\s*\| :\-+:\s*\|\n\|\s*<table>.*?</table>\s*\|\s*<table>.*?</table>\s*\|\n",
        re.DOTALL,
    )
    if pat.search(text):
        return pat.sub(new_block, text, count=1)
    return new_block + "\n\n" + text


def _load_fun_prediction(path: Path = FUN_PREDICTION) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Dữ liệu mô phỏng vui không hợp lệ: {path}")
    return payload


def _fmt_iso_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d-%m-%Y")
    except Exception:
        return str(value or "—")


def _fmt_prob(value: Any, decimals: int) -> str:
    try:
        return f"{float(value):.{decimals}f}%"
    except Exception:
        return "—"


def _render_fun_prediction_block(payload: dict[str, Any]) -> str:
    target = _fmt_iso_date(payload.get("target_date"))
    anchor = _fmt_iso_date(payload.get("anchor_date"))
    groups = payload.get("groups") if isinstance(payload.get("groups"), list) else []
    prize_rows: list[str] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label") or group.get("key") or "Giải")
        values = group.get("values") if isinstance(group.get("values"), list) else []
        rendered = []
        for item in values:
            if isinstance(item, dict):
                value = str(item.get("value") or "")
                if value:
                    rendered.append(f"`{value}`")
        prize_rows.append(f"| {label} | {' · '.join(rendered) if rendered else '—'} |")

    def top_table(items: Any, *, decimals: int) -> str:
        if not isinstance(items, list) or not items:
            return "_Chưa có dữ liệu._"
        rows = ["| # | Số | Xác suất mô hình |", "|---:|:---:|---:|"]
        for idx, item in enumerate(items[:10], start=1):
            if not isinstance(item, dict):
                continue
            rank = item.get("rank", idx)
            number = str(item.get("number") or "").zfill(2)
            prob = _fmt_prob(item.get("prob_percent"), decimals)
            rows.append(f"| {rank} | **{number}** | **{prob}** |")
        return "\n".join(rows)

    prize_table = "\n".join(["| Giải | Dự đoán vui |", "|---|---|"] + prize_rows)
    loto_table = top_table(payload.get("top_loto"), decimals=2)
    de_table = top_table(payload.get("top_de"), decimals=3)
    disclaimer = str(
        payload.get("disclaimer")
        or "Dự đoán vui/mô phỏng để tham khảo; không phải kết quả thật và không bảo đảm kết quả tương lai."
    )

    return (
        "<!-- FUN_PREDICTION:BEGIN -->\n"
        f"## 🎲 Dự đoán vui ngày {target}\n\n"
        f"> **Ngày neo:** kết quả thực đến **{anchor}**. **Không phải kết quả thật.** {disclaimer}\n\n"
        "### Bảng mô phỏng đầy đủ\n\n"
        f"{prize_table}\n\n"
        "### Lô tô đứng đầu cho ngày mai\n\n"
        f"{loto_table}\n\n"
        "### Đặc biệt đứng đầu cho ngày mai\n\n"
        f"{de_table}\n\n"
        "> Xác suất ở bảng lô tô là xác suất mô hình cho số 00–99 xuất hiện trong kỳ; xác suất ĐB là phân phối riêng cho 2 số cuối giải đặc biệt. Các chữ số tiền tố trong bảng mô phỏng đầy đủ được sinh tất định để tạo bảng vui, không phải dự báo xác suất cho toàn bộ số 3–5 chữ số.\n"
        "<!-- FUN_PREDICTION:END -->\n"
    )


def _replace_fun_prediction_block(text: str, new_block: str) -> str:
    begin = "<!-- FUN_PREDICTION:BEGIN -->"
    end = "<!-- FUN_PREDICTION:END -->"
    if begin in text and end in text:
        pre, rest = text.split(begin, 1)
        _, post = rest.split(end, 1)
        return pre.rstrip() + "\n\n" + new_block + "\n" + post.lstrip()

    snapshot_end = "<!-- SNAPSHOT:END -->"
    if snapshot_end in text:
        pre, post = text.split(snapshot_end, 1)
        return pre + snapshot_end + "\n\n" + new_block + "\n" + post.lstrip()

    for marker in ("## Kiến trúc vận hành", "## Kiến trúc production"):
        if marker in text:
            pre, post = text.split(marker, 1)
            return pre.rstrip() + "\n\n" + new_block + "\n\n" + marker + post
    return text.rstrip() + "\n\n" + new_block


def _render_automation_block() -> str:
    return """<!-- AUTOMATION:BEGIN -->
## ⚙️ Tự động hóa không cần can thiệp

Hệ thống vận hành tự động bằng GitHub Actions; không cần chạy cron/VPS bên ngoài trong cấu hình mặc định.

| Lớp tự động | Giờ Việt Nam | Hành vi |
|---|---|---|
| Gần thời gian thực chính | **18:00** | Mở cửa sổ trực tiếp trước giờ quay, thăm dò khoảng 15 giây/lần và kiểm chứng nhiều nguồn. |
| Bộ giám sát trực tiếp | **17:55, 18:05, 18:15, 18:25, 18:45** | Nếu dữ liệu trực tiếp chưa có nhịp báo của ngày hiện tại, tự gọi lại quy trình trực tiếp. |
| Hoàn tất hằng ngày | **18:30, 18:40, 18:50, 19:00, 19:10, 19:20, 19:30, 19:45, 20:00** | Thăm dò/tải, yêu cầu ≥2 nhóm nhà cung cấp độc lập, ghi dữ liệu chuẩn trước rồi mới chạy thống kê + AI/ML + dự báo + README + Pages. |
| Phục hồi dữ liệu chuẩn | **19:05, 19:25, 19:45, 20:05** | Nếu dữ liệu chuẩn còn cũ hoặc kiểm toán artifact không đạt, tự gọi lại quy trình hoàn tất hằng ngày. |
| Phục hồi Pages | **20:10–20:35** | Thử lại việc triển khai Pages độc lập khi dữ liệu chuẩn đã ổn. |
| Lưới an toàn qua đêm | **07:15** | Kiểm tra lại dữ liệu chuẩn, dự báo, README, artifact mô hình, bảng điều khiển và đối soát dữ liệu trực tiếp. |
| Hậu kiểm hoàn tất | Sau mỗi lượt hằng ngày thành công | Kiểm toán vận hành đầy đủ và đồng bộ nhánh `live` về đúng dữ liệu chuẩn `complete_verified`. |

Các quy trình phục hồi kiểm tra trạng thái trước khi gọi để tránh tạo tác vụ trùng khi quy trình mục tiêu đang `queued/in_progress`. Việc ghi dữ liệu chuẩn hằng ngày vẫn độc lập với Pages/bộ giám sát, nên lỗi bảng điều khiển hoặc hậu kiểm không giữ lại kết quả hằng ngày đã xác minh.

> Quy trình GitHub theo lịch hoạt động theo khả năng tốt nhất và nguồn dữ liệu bên thứ ba có thể thay đổi/gián đoạn. Bộ giám sát cùng nhiều mốc phục hồi giúp hệ thống tự phục hồi tối đa trong giới hạn kiến trúc chỉ dùng GitHub, nhưng không thể tạo SLA tuyệt đối như bộ lập lịch/máy chủ chuyên dụng.
<!-- AUTOMATION:END -->
"""


def _replace_automation_block(text: str) -> str:
    block = _render_automation_block()
    begin = "<!-- AUTOMATION:BEGIN -->"
    end = "<!-- AUTOMATION:END -->"
    if begin in text and end in text:
        pre, rest = text.split(begin, 1)
        _, post = rest.split(end, 1)
        return pre.rstrip() + "\n\n" + block + "\n" + post.lstrip()

    # Remove the legacy schedule section so README cannot show contradictory times.
    legacy = re.compile(
        r"\n## Lịch daily finalization\n.*?(?=\n## (?:Dashboard|Bảng điều khiển)\n)",
        re.DOTALL,
    )
    text = legacy.sub("\n", text, count=1)
    for marker in ("## Bảng điều khiển", "## Dashboard"):
        if marker in text:
            pre, post = text.split(marker, 1)
            return pre.rstrip() + "\n\n" + block + "\n" + marker + post
    return text.rstrip() + "\n\n" + block


def main() -> None:
    raw_csv = DATA_DIR / "xsmb.csv"
    two_csv = DATA_DIR / "xsmb-2-digits.csv"
    if not raw_csv.exists() or not two_csv.exists():
        raise FileNotFoundError("Thiếu tệp xsmb.csv và/hoặc xsmb-2-digits.csv trong data/")

    latest_raw = _load_latest_row(raw_csv)
    latest_2d = _load_latest_row(two_csv)
    lottery_html = _build_lottery_table(latest_raw)
    loto_html = _build_loto_table(latest_2d)
    snapshot_block = _render_block(lottery_html, loto_html)

    if not README.exists():
        raise FileNotFoundError("Không tìm thấy README.md")

    txt = README.read_text(encoding="utf-8")
    new_txt = _replace_between_markers(txt, snapshot_block)

    fun_payload = _load_fun_prediction()
    if fun_payload:
        fun_block = _render_fun_prediction_block(fun_payload)
        new_txt = _replace_fun_prediction_block(new_txt, fun_block)

    new_txt = _replace_automation_block(new_txt)
    README.write_text(new_txt, encoding="utf-8")

    print("README đã cập nhật cho ngày:", pd.to_datetime(latest_raw["date"]).date())
    if fun_payload:
        print("Ngày mục tiêu của mô phỏng vui trong README:", fun_payload.get("target_date"))
    print("Đã cập nhật khối tự động hóa không cần can thiệp trong README")


if __name__ == "__main__":
    main()
