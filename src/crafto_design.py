"""Gắn lớp trình bày và chuyển động sau khung, không thay dữ liệu trang."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parent
_EFFECTS = re.compile(r'<aside\b[^>]*\bdata-app-effects\b[^>]*>.*?</aside>\s*', re.S | re.I)
_STYLE = re.compile(r'<link\b[^>]*\bdata-app-design-style\b[^>]*>\s*', re.I)
_SCRIPT = re.compile(r'<script\b[^>]*\bdata-app-motion-script\b[^>]*>\s*</script>\s*', re.I)
_MAIN = re.compile(r'(<main\b[^>]*\bid="app-main"[^>]*>)', re.I)


def attach_crafto_design(path: Path, html: str) -> str:
    """Xuất tài nguyên nội bộ và chèn một lớp hiệu ứng duy nhất, lũy đẳng."""
    if "</head>" not in html or not _MAIN.search(html):
        return html
    # Nhập trễ tránh vòng giữa ranh giới ghi trang và lớp trình bày.
    from page_output import write_stylesheet_text

    assets = path.parent / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    write_stylesheet_text(assets / "app-design.css", (_ROOT / "templates/app_design.css").read_text(encoding="utf-8"))
    (assets / "app-motion.js").write_text((_ROOT / "assets/app-motion.js").read_text(encoding="utf-8"), encoding="utf-8")

    head, body = html.split("</head>", 1)
    head = _SCRIPT.sub("", _STYLE.sub("", head))
    # Script ở head để không phá mẫu đuôi mà bộ gỡ shell dùng khi dựng lại.
    head = (head.rstrip() + '\n<link rel="stylesheet" href="assets/app-design.css" data-app-design-style>\n'
            '<script src="assets/app-motion.js" defer data-app-motion-script></script>\n')
    body = _EFFECTS.sub("", body)
    body = re.sub(r'(<body\b[^>]*?)\sdata-app-design="[^"]*"', r'\1', body, count=1, flags=re.I)
    body = re.sub(r'<body\b', '<body data-app-design="crafto"', body, count=1, flags=re.I)
    particles = "".join(f'<span class="app-particle" style="--app-i:{i}"></span>' for i in range(12))
    effects = (
        '<aside data-app-effects aria-label="Tùy chọn hiển thị">'
        '<div class="app-ambience" aria-hidden="true">'
        '<span class="app-orb app-orb--one"></span><span class="app-orb app-orb--two"></span>'
        '<span class="app-orb app-orb--three"></span>' + particles + '</div>'
        '<span class="app-cursor" aria-hidden="true"></span>'
        '<button id="app-motion-toggle" type="button" aria-pressed="false" hidden>'
        'Hiệu ứng: Tắt</button></aside>'
    )
    # Đặt cuối vùng nội dung để thứ tự đọc và các điều khiển gốc không đổi.
    body = re.sub(r'</main\s*>', lambda _: effects + '</main>', body, count=1, flags=re.I)
    return head + "</head>" + body
