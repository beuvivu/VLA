from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path("data")
README = Path("README.md")
FUN_PREDICTION = DATA_DIR / "predict" / "fun_draw_next.json"

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
    ("Special (Đặc biệt)", ["special"]),
    ("First (Giải nhất)", ["prize1"]),
    ("Second (Giải nhì)", ["prize2_1", "prize2_2"]),
    ("Third (Giải ba)", ["prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6"]),
    ("Fourth (Giải tư)", ["prize4_1", "prize4_2", "prize4_3", "prize4_4"]),
    ("Fifth (Giải năm)", ["prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6"]),
    ("Sixth (Giải sáu)", ["prize6_1", "prize6_2", "prize6_3"]),
    ("Seventh (Giải bảy)", ["prize7_1", "prize7_2", "prize7_3", "prize7_4"]),
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
        raise ValueError(f"Invalid data file: {csv_path}")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    return df.iloc[-1]


def _build_lottery_table(latest_raw: pd.Series) -> str:
    d = pd.to_datetime(latest_raw["date"]).date()
    d_str = d.strftime("%d-%m-%Y")
    rows = [f"<tr><td>Date (Ngày)</td><td>{d_str}</td></tr>"]
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
        except Exception:
            continue

    tails_by_head: dict[int, list[int]] = {h: [] for h in range(10)}
    for n in nums:
        head = n // 10
        tail = n % 10
        if 0 <= head <= 9:
            tails_by_head[head].append(tail)

    rows = ["<tr><td>First (Đầu)</td><td>Last (Đuôi)</td></tr>"]
    for head in range(10):
        tails = ", ".join(str(t) for t in tails_by_head[head])
        rows.append(f"<tr><td>{head}</td><td>{tails}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def _render_block(lottery_html: str, loto_html: str) -> str:
    return (
        "<!-- SNAPSHOT:BEGIN -->\n"
        "| Lottery (Xổ số) | Loto (Lô tô) |\n"
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
        raise ValueError(f"Invalid fun prediction payload: {path}")
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
        rows = ["| # | Số | Xác suất model |", "|---:|:---:|---:|"]
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
        f"> **Anchor:** kết quả thực đến **{anchor}**. **Không phải kết quả thật.** {disclaimer}\n\n"
        "### Bảng mô phỏng đầy đủ\n\n"
        f"{prize_table}\n\n"
        "### Top Loto ngày mai\n\n"
        f"{loto_table}\n\n"
        "### Top Đặc biệt ngày mai\n\n"
        f"{de_table}\n\n"
        "> Xác suất ở bảng Loto là xác suất model cho số 00–99 xuất hiện trong kỳ; xác suất ĐB là distribution riêng cho 2 số cuối giải đặc biệt. Các chữ số tiền tố trong bảng mô phỏng đầy đủ được sinh deterministic để tạo bảng vui, không phải dự báo xác suất cho toàn bộ số 3–5 chữ số.\n"
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

    marker = "## Kiến trúc production"
    if marker in text:
        pre, post = text.split(marker, 1)
        return pre.rstrip() + "\n\n" + new_block + "\n\n" + marker + post
    return text.rstrip() + "\n\n" + new_block


def _render_automation_block() -> str:
    return """<!-- AUTOMATION:BEGIN -->
## ⚙️ Zero-touch automation

Hệ thống vận hành tự động bằng GitHub Actions; không cần chạy cron/VPS bên ngoài trong cấu hình mặc định.

| Lớp tự động | Giờ Việt Nam | Hành vi |
|---|---|---|
| Near-live chính | **18:04** | Mở cửa sổ live, poll khoảng 25 giây/lần và kiểm chứng nhiều nguồn. |
| Live watchdog | **18:10, 18:20** | Nếu live chưa có heartbeat của ngày hiện tại, tự dispatch lại live workflow. |
| Daily finalization | **18:18, 18:28, 18:38, 18:48, 18:58, 19:13, 19:28** | Poll/fetch, yêu cầu ≥2 provider group độc lập, commit canonical trước rồi mới chạy Statistics + AI/ML + prediction + README + Pages. |
| Canonical recovery | **19:35, 20:05** | Nếu canonical còn stale hoặc artifact audit fail, tự dispatch lại daily finalization. |
| Pages recovery | **20:20** | Retry deploy Pages độc lập khi canonical đã ổn. |
| Overnight safety net | **07:15** | Kiểm tra lại canonical, prediction, README, model artifacts, dashboards và live reconciliation. |
| Post-finalization | Sau mỗi daily success | Full production audit và đồng bộ branch `live` về đúng canonical `complete_verified`. |

Recovery workflows kiểm tra trạng thái trước khi dispatch để tránh tạo job trùng khi workflow mục tiêu đang `queued/in_progress`. Daily canonical commit vẫn độc lập với Pages/watchdog, nên lỗi dashboard hoặc hậu kiểm không giữ lại kết quả daily đã xác minh.

> GitHub scheduled workflows là best-effort và nguồn dữ liệu bên thứ ba có thể thay đổi/gián đoạn. Watchdog + nhiều recovery slots giúp hệ thống tự phục hồi tối đa trong giới hạn kiến trúc GitHub-only, nhưng không thể tạo SLA tuyệt đối như một scheduler/server chuyên dụng.
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
    legacy = re.compile(r"\n## Lịch daily finalization\n.*?(?=\n## Dashboard\n)", re.DOTALL)
    text = legacy.sub("\n", text, count=1)
    marker = "## Dashboard"
    if marker in text:
        pre, post = text.split(marker, 1)
        return pre.rstrip() + "\n\n" + block + "\n" + marker + post
    return text.rstrip() + "\n\n" + block


def main() -> None:
    raw_csv = DATA_DIR / "xsmb.csv"
    two_csv = DATA_DIR / "xsmb-2-digits.csv"
    if not raw_csv.exists() or not two_csv.exists():
        raise FileNotFoundError("Missing data files under data/: xsmb.csv and/or xsmb-2-digits.csv")

    latest_raw = _load_latest_row(raw_csv)
    latest_2d = _load_latest_row(two_csv)
    lottery_html = _build_lottery_table(latest_raw)
    loto_html = _build_loto_table(latest_2d)
    snapshot_block = _render_block(lottery_html, loto_html)

    if not README.exists():
        raise FileNotFoundError("README.md not found")

    txt = README.read_text(encoding="utf-8")
    new_txt = _replace_between_markers(txt, snapshot_block)

    fun_payload = _load_fun_prediction()
    if fun_payload:
        fun_block = _render_fun_prediction_block(fun_payload)
        new_txt = _replace_fun_prediction_block(new_txt, fun_block)

    new_txt = _replace_automation_block(new_txt)
    README.write_text(new_txt, encoding="utf-8")

    print("README updated for date:", pd.to_datetime(latest_raw["date"]).date())
    if fun_payload:
        print("README fun prediction target:", fun_payload.get("target_date"))
    print("README zero-touch automation block updated")


if __name__ == "__main__":
    main()
