from __future__ import annotations

"""Ghi CSS và JavaScript của Design System vào ``docs/assets/``.

Hai tệp, và cả hai đều SINH RA hoặc COPY từ nguồn trong ``src/`` — không có
bản viết tay nào trong ``docs/``. Lý do: ``docs/`` là thư mục xuất bản, và một
tệp sửa tay ở đó sẽ bị lượt dựng sau ghi đè, hoặc tệ hơn là không bị ghi đè và
trôi khỏi nguồn mà không ai biết bên nào đúng.
"""

import shutil
from pathlib import Path

from vla_design.stylesheet import full_css

ASSET_DIR_NAME = "assets"
CSS_NAME = "vla.css"
JS_NAME = "vla-shell.js"

_JS_SOURCE = Path(__file__).resolve().parent / "assets" / JS_NAME


def write_assets(docs_dir: Path) -> tuple[Path, Path]:
    """Ghi ``vla.css`` và ``vla-shell.js``, trả về đường dẫn hai tệp."""
    asset_dir = Path(docs_dir) / ASSET_DIR_NAME
    asset_dir.mkdir(parents=True, exist_ok=True)

    css_path = asset_dir / CSS_NAME
    css_path.write_text(full_css(), encoding="utf-8")

    js_path = asset_dir / JS_NAME
    shutil.copyfile(_JS_SOURCE, js_path)
    return css_path, js_path
