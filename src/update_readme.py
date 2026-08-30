from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
README = Path("README.md")

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

    # Backward-compatible regex replacement (older READMEs)
    pat = re.compile(
        r"\| Lottery \(Xổ số\) \| Loto \(Lô tô\) \|\n\| :\-+:\s*\| :\-+:\s*\|\n\|\s*<table>.*?</table>\s*\|\s*<table>.*?</table>\s*\|\n",
        re.DOTALL,
    )
    if pat.search(text):
        return pat.sub(new_block, text, count=1)

    # Fallback: prepend
    return new_block + "\n\n" + text


def main() -> None:
    raw_csv = DATA_DIR / "xsmb.csv"
    two_csv = DATA_DIR / "xsmb-2-digits.csv"
    if not raw_csv.exists() or not two_csv.exists():
        raise FileNotFoundError("Missing data files under data/: xsmb.csv and/or xsmb-2-digits.csv")

    latest_raw = _load_latest_row(raw_csv)
    latest_2d = _load_latest_row(two_csv)

    lottery_html = _build_lottery_table(latest_raw)
    loto_html = _build_loto_table(latest_2d)
    new_block = _render_block(lottery_html, loto_html)

    if not README.exists():
        raise FileNotFoundError("README.md not found")

    txt = README.read_text(encoding="utf-8")
    new_txt = _replace_between_markers(txt, new_block)
    README.write_text(new_txt, encoding="utf-8")

    print("README updated for date:", pd.to_datetime(latest_raw["date"]).date())


if __name__ == "__main__":
    main()
