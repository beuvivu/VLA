"""Phiên bản tài nguyên theo nội dung; kiểm gói trang trước khi xuất bản.

Chỉ dùng thư viện chuẩn để mọi job Pages gọi cùng một cổng kiểm tra.
Không lưu cache băm trong tiến trình: tệp thay đổi là URL thay đổi ngay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

_SUFFIXES = {".css", ".js", ".json", ".png", ".webp", ".svg", ".ico"}
_ATTR = re.compile(
    r'''(?P<name>[^\s"'<>/=]+)(?:\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s"'=<>`]+)))?'''
)
_TAG = re.compile(r"<[^\s/>]+")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _asset_path(page: Path, url: str) -> Path | None:
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return None
    relative = Path(unquote(parts.path))
    if not relative.parts or relative.parts[0] != "assets" or relative.suffix.lower() not in _SUFFIXES:
        return None
    assets = (page.parent / "assets").resolve()
    target = (page.parent / relative).resolve()
    if not target.is_relative_to(assets):
        return None
    return target


class _AssetReferences(HTMLParser):
    """Lấy thuộc tính thật và đếm khung, không đọc nhầm dữ liệu trong script."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.references: list[tuple[int, int, str, bool]] = []
        self.shell_counts = dict.fromkeys(("app-main", "app-header", "app-rail"), 0)
        self._lines = [0]
        for match in re.finditer("\n", source):
            self._lines.append(match.end())
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = next((value for name, value in attrs if name == "class"), "") or ""
        for name in classes.split():
            if name in self.shell_counts:
                self.shell_counts[name] += 1
        wanted = {"script": "src", "link": "href", "a": "href", "img": "src"}.get(tag)
        if not wanted:
            return
        raw = self.get_starttag_text()
        opening = _TAG.match(raw)
        if opening is None:
            return
        line, column = self.getpos()
        offset = self._lines[line - 1] + column
        for match in _ATTR.finditer(raw, opening.end()):
            if match["name"].lower() != wanted:
                continue
            for group in ("double", "single", "bare"):
                if match[group] is not None:
                    self.references.append((offset + match.start(group), offset + match.end(group),
                                            unescape(match[group]), group == "bare"))
                    break


def rewrite_assets(page: Path, source: str, *, strip: bool = False) -> str:
    """Gắn băm vào URL cục bộ; bóc băm trước khi bọc lại khung trang."""
    replacements: list[tuple[int, int, str]] = []
    for start, end, url, bare in _AssetReferences(source).references:
        target = _asset_path(page, url)
        if target is None:
            continue
        parts = urlsplit(url)
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "rev"]
        if not strip:
            if not target.is_file():
                continue
            query.append(("rev", _hash(target)[:16]))
        updated = urlunsplit(parts._replace(query=urlencode(query)))
        if updated != url:
            value = escape(updated, quote=True)
            replacements.append((start, end, f'"{value}"' if bare else value))
    for start, end, value in reversed(replacements):
        source = source[:start] + value + source[end:]
    return source


def _reference_issues(page: Path, source: str) -> list[str]:
    issues: list[str] = []
    parsed = _AssetReferences(source)
    if any(parsed.shell_counts.values()):
        for name, count in parsed.shell_counts.items():
            if count != 1:
                issues.append(f"{page.name}: khung {name} có {count} bản, cần đúng 1")
    for _, _, url, _ in parsed.references:
        target = _asset_path(page, url)
        if target is None:
            continue
        if not target.is_file():
            issues.append(f"{page.name}: thiếu tài nguyên {urlsplit(url).path}")
        elif [value for key, value in parse_qsl(urlsplit(url).query) if key == "rev"] != [_hash(target)[:16]]:
            issues.append(f"{page.name}: phiên bản cũ hoặc thiếu của {urlsplit(url).path}")
    return issues


def _manifest(root: Path) -> dict[str, object]:
    assets = {path.relative_to(root).as_posix(): _hash(path)
              for path in sorted((root / "assets").rglob("*"))
              if path.is_file() and path.suffix.lower() in _SUFFIXES
              and path != root / "assets/release.json"}
    pages = {path.name: _hash(path) for path in sorted(root.glob("*.html"))}
    payload: dict[str, object] = {"schema_version": 1, "assets": assets, "pages": pages}
    payload["release_id"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def refresh_site(root: Path) -> dict[str, object]:
    """Chuẩn hóa toàn bộ tham chiếu sau trình dựng cuối cùng; không đổi dữ liệu."""
    pages = sorted(root.glob("*.html"))
    if not pages:
        raise ValueError(f"Không có trang HTML trong {root}")
    issues: list[str] = []
    updates: list[tuple[Path, str]] = []
    for page in pages:
        source = rewrite_assets(page, page.read_text(encoding="utf-8"))
        issues.extend(_reference_issues(page, source))
        updates.append((page, source))
    if issues:
        raise ValueError("\n".join(issues))
    for page, source in updates:
        if page.read_text(encoding="utf-8") != source:
            page.write_text(source, encoding="utf-8")
    manifest = _manifest(root)
    target = root / "assets/release.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def check_site(root: Path) -> list[str]:
    """Báo lệch manifest, tệp thiếu hoặc phiên bản không khớp nội dung."""
    issues: list[str] = []
    pages = sorted(root.glob("*.html"))
    if not pages:
        issues.append("Không có trang HTML")
    for page in pages:
        issues.extend(_reference_issues(page, page.read_text(encoding="utf-8")))
    try:
        expected = json.loads((root / "assets/release.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return issues + [f"Không đọc được manifest: {exc}"]
    actual = _manifest(root)
    if not isinstance(expected, dict):
        return issues + ["Manifest phải là object"]
    for kind in ("assets", "pages"):
        before = expected.get(kind)
        after = actual[kind]
        if not isinstance(before, dict):
            issues.append(f"Manifest thiếu danh mục {kind}")
            continue
        for name in sorted(set(before) | set(after)):
            if before.get(name) != after.get(name):
                issues.append(f"{name}: nội dung khác manifest")
    if expected.get("release_id") != actual["release_id"] or expected.get("schema_version") != 1:
        issues.append("Manifest có mã phiên bản không hợp lệ")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", type=Path, help="Thư mục trang cần chốt lại")
    parser.add_argument("--root", type=Path, default=Path("docs"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.refresh or args.root
    if args.refresh:
        refresh_site(root)
    if args.check:
        issues = check_site(root)
        if issues:
            parser.exit(1, "\n".join(issues) + "\n")
    print(f"Đã kiểm gói trang: {root}")


if __name__ == "__main__":
    main()
