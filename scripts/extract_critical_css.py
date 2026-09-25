#!/usr/bin/env python3
"""Auto-extract Critical CSS from docs/assets/ui.css for CRP inlining.

Usage:
  python scripts/extract_critical_css.py

Writes:
  - docs/assets/critical.css
  - src/critical_css_generated.py

Run after editing docs/assets/ui.css (or wire into the Pages build).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_CSS = ROOT / "docs" / "assets" / "ui.css"
OUT_PY = ROOT / "src" / "critical_css_generated.py"
OUT_CSS = ROOT / "docs" / "assets" / "critical.css"
BUDGET = 3500

SHELL = re.compile(
    r"^\s*(\*|html|body)\s*$|"
    r"\.ui-app\b|\.ui-shell\b|\.ui-header\b|\.ui-sub\b|\.ui-nav\b|"
    r"\.ui-card\b|\.ui-card-head\b|\.ui-card-body\b|\.ui-grid\b|"
    r"\.ui-badge\b|\.ui-table-wrap\b|"
    r"\.path-shell\b|\.path-hero\b|\.main\b|\.app\b|\.ui-c12\b|\.ui-c6\b",
    re.I,
)
SKIP = re.compile(
    r"data-ui-theme|nth-child|ui-table\.ui-[mr]|ui-chart|ui-matrix|keyframes",
    re.I,
)
DROP_PROP = re.compile(
    r"(?:^|;)\s*(?:box-shadow|filter|backdrop-filter|transition|animation|will-change|"
    r"text-shadow|user-select|scroll-behavior)\s*:[^;]*",
    re.I,
)


def parse_rules(text: str):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    rules = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        if text[i] == "@":
            brace = text.find("{", i)
            semi = text.find(";", i)
            if brace >= 0 and (semi < 0 or brace < semi):
                depth = 0
                j = brace
                while j < n:
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                rules.append(("at", text[i:brace].strip(), text[brace + 1 : j - 1]))
                i = j
                continue
            if semi >= 0:
                i = semi + 1
                continue
        brace = text.find("{", i)
        if brace < 0:
            break
        sel = text[i:brace].strip()
        depth = 0
        j = brace
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        rules.append(("rule", sel, text[brace + 1 : j - 1].strip()))
        i = j
    return rules


def slim_body(body: str) -> str:
    body = DROP_PROP.sub("", body)
    body = re.sub(r"\s+", " ", body).strip()
    body = re.sub(r"\s*([:{;])\s*", r"\1", body)
    return body.strip(";")


def extract(css_text: str) -> str:
    rules = parse_rules(css_text)
    shell_rules: list[tuple[str, str]] = []
    for r in rules:
        if r[0] != "rule":
            continue
        if SKIP.search(r[1]):
            continue
        if r[1].strip() == ":root" or r[1].strip().startswith(":root"):
            continue
        if not SHELL.search(r[1]):
            continue
        body = slim_body(r[2])
        if not body:
            continue
        sel = re.sub(r"\s+", " ", r[1]).strip()
        shell_rules.append((sel, body))

    shell_css = "".join(f"{s}{{{b}}}" for s, b in shell_rules)
    used_vars = set(re.findall(r"var\((--[a-zA-Z0-9-]+)", shell_css))
    used_vars |= {
        "--ui-bg", "--ui-bg-2", "--ui-surface", "--ui-surface-2", "--ui-border",
        "--ui-ink", "--ui-ink-2", "--ui-ink-soft", "--ui-brand", "--ui-brand-ink",
        "--ui-brand-soft", "--ui-on-brand", "--ui-font", "--ui-page-max",
        "--ui-page-gutter", "--ui-r-xl", "--ui-r-lg", "--s4",
    }
    used_vars.discard("--ui-bg-mesh")

    root_body = next((r[2] for r in rules if r[0] == "rule" and r[1].strip() == ":root"), "")
    root_decls: list[str] = []
    for decl in root_body.split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, val = decl.partition(":")
        prop = prop.strip()
        if prop in used_vars and "mesh" not in prop:
            root_decls.append(f"{prop}:{val.strip()}")

    # Giá trị đỡ cho token mà quét không tìm thấy trong ui.css. Đây là BẢN SAO
    # thứ tư của bảng màu, nên nó trôi được: trước khi sửa, danh sách này còn
    # nguyên #F2F4FF/#4f46e5 của bảng cũ. Chỉ dùng khi ui.css thật sự không
    # khai token đó, nên giữ giống ui.css chứ không nghĩ ra màu mới.
    for m in (
        "--ui-bg:#f0f4fd", "--ui-bg-2:#eaedff", "--ui-surface:#fff", "--ui-border:#e4e7f2",
        "--ui-ink:#202329", "--ui-ink-2:#262b35", "--ui-ink-soft:#5c6270",
        "--ui-brand:#2946f3", "--ui-brand-ink:#2038cf", "--ui-brand-soft:#eaedff",
        "--ui-on-brand:#fff",
        '--ui-font:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif',
        "--ui-page-max:1280px", "--ui-page-gutter:clamp(16px,2.5vw,32px)",
        "--ui-r-xl:24px",
    ):
        if m.split(":")[0] not in {d.split(":")[0] for d in root_decls}:
            root_decls.append(m)

    root_css = ":root{" + ";".join(root_decls) + "}"
    base = (
        "*,::before,::after{box-sizing:border-box}"
        "html{-webkit-text-size-adjust:100%}"
        # Nền lấy TỪ TOKEN, không viết lại mã màu. Bản trước ghim
        # `linear-gradient(162deg,#F2F4FF,#E6EAFB)` ngay ở đây, nên đổi bảng
        # màu trong `ui_theme.py` xong thì khung vẽ đầu tiên vẫn là nền cũ:
        # người đọc thấy nền cũ lóe lên rồi mới đổi.
        "body{margin:0;color:var(--ui-ink-2);"
        "background:linear-gradient(180deg,var(--ui-bg) 0%,var(--ui-bg-2) 100%);"
        "background-color:var(--ui-bg);font-family:var(--ui-font);font-size:14px;line-height:1.6;"
        "min-height:100vh;-webkit-font-smoothing:antialiased}"
    )
    media = (
        "@media (max-width:640px){"
        ".ui-shell,.main{padding-left:14px;padding-right:14px}"
        "}"
    )

    prio: list[tuple[int, int, str, str]] = []
    for s, b in shell_rules:
        score = 0
        for k, w in (
            (".ui-shell", 5), (".ui-header", 5), (".ui-card", 4), (".ui-nav", 4),
            (".ui-app", 5), (".ui-grid", 3), (".ui-sub", 2),
            (".ui-badge", 1), (".path-", 2),
        ):
            if k in s:
                score += w
        prio.append((score, len(b), s, b))
    prio.sort(key=lambda x: (-x[0], x[1]))

    pieces: list[str] = []
    size = len(root_css) + len(base) + len(media)
    for score, _, s, b in prio:
        piece = f"{s}{{{b}}}"
        if size + len(piece) > BUDGET and score < 3:
            continue
        if size + len(piece) > BUDGET + 500:
            continue
        pieces.append(piece)
        size += len(piece)

    critical = root_css + base + "".join(pieces) + media
    critical = re.sub(r"\s*([{}:;,])\s*", r"\1", critical).replace(";}", "}")
    critical = re.sub(r"and\(", "and (", critical)
    return critical


def main() -> None:
    if not UI_CSS.is_file():
        print(f"missing {UI_CSS}", file=sys.stderr)
        sys.exit(1)
    critical = extract(UI_CSS.read_text(encoding="utf-8"))
    OUT_CSS.parent.mkdir(parents=True, exist_ok=True)
    OUT_CSS.write_text(critical + "\n", encoding="utf-8")
    OUT_PY.write_text(
        '"""AUTO-GENERATED by scripts/extract_critical_css.py \u2014 do not edit."""\n'
        f'CRITICAL_CSS = r"""{critical}"""\n',
        encoding="utf-8",
    )
    print(f"wrote {OUT_CSS.relative_to(ROOT)} ({len(critical)} bytes)")
    print(f"wrote {OUT_PY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
