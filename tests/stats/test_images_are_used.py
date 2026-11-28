from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README_TEMPLATE = ROOT / "src" / "web" / "templates" / "README.j2"


def embedded_images(text: str) -> set[str]:
    return set(re.findall(r"images/([\w.-]+\.(?:jpg|jpeg|png|svg))", text))


def written_images(source: str) -> set[str]:
    return set(re.findall(r"[\"']([\w.-]+\.(?:jpg|jpeg|png))[\"']", source))


def test_the_rules_themselves_read_names() -> None:
    assert embedded_images('![a](images/heatmap.jpg) <img src="images/top-10.jpg">') == {"heatmap.jpg", "top-10.jpg"}
    assert written_images('out = paths.images_dir / "delta.jpg"; x = f"{p}.jpg"') == {"delta.jpg"}


def test_every_committed_image_is_embedded_in_the_readme() -> None:
    shown = embedded_images(README_TEMPLATE.read_text(encoding="utf-8"))
    committed = {path.name for path in (ROOT / "images").iterdir() if path.is_file()}
    assert shown, "README.j2 không nhúng ảnh nào — luật đang so trên tập rỗng"
    assert committed - shown == set()


def test_no_stats_module_draws_an_image_nobody_embeds() -> None:
    shown = embedded_images(README_TEMPLATE.read_text(encoding="utf-8"))
    drawn: dict[str, set[str]] = {}
    for path in sorted((ROOT / "src" / "stats").rglob("*.py")):
        names = written_images(path.read_text(encoding="utf-8")) - shown
        if names:
            drawn[path.name] = names
    assert drawn == {}
    dynamic = [path.name for path in sorted((ROOT / "src" / "stats").rglob("*.py"))
               if re.search(r"images_dir\s*/\s*f[\"']", path.read_text(encoding="utf-8"))]
    assert dynamic == []
