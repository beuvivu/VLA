from __future__ import annotations

import re
from pathlib import Path

import pytest

from ingest.sources import (
    FALLBACK_SOURCE_NAMES,
    HISTORY_API_SOURCE_NAMES,
    PRIMARY_SOURCE_NAMES,
    REGIONAL_SOURCE_NAMES,
)

ROOT = Path(__file__).resolve().parents[2]

ALLOWED = {
    *PRIMARY_SOURCE_NAMES,
    *FALLBACK_SOURCE_NAMES,
    *REGIONAL_SOURCE_NAMES,
    *HISTORY_API_SOURCE_NAMES,
    "hainhay.net",
    "www.hainhay.net",
}

INFRASTRUCTURE = re.compile(
    r"(github\.(com|io)|githubusercontent\.com|shields\.io|openxmlformats\.org"
    r"|workers\.dev|deno\.dev|cloudflare\.com|pytest\.org|cron-job\.org"
    r"|example\.com|schemas\.|fonts\.g)",
    re.IGNORECASE,
)

SCANNED_SUFFIXES = (".py", ".js", ".mjs", ".yml", ".yaml", ".json", ".html", ".j2", ".sh", ".toml")
SKIPPED_DIRECTORIES = {".git", "__pycache__", ".ruff_cache", "node_modules", ".pytest_cache"}

LOTTERY_SHAPED = re.compile(
    r"https?://((?:[a-z0-9-]+\.)*[a-z0-9-]*"
    r"(?:xoso|xskt|kqxs|ketqua|loto|lo-de|soicau|rongbach|caulo|minhngoc|hainhay)"
    r"[a-z0-9-]*\.[a-z.]{2,12})\b",
    re.IGNORECASE,
)


def _scanned_files() -> list[Path]:
    out: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if SKIPPED_DIRECTORIES & set(path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return out


def test_the_scan_actually_reaches_the_source_catalogue() -> None:
    files = _scanned_files()
    assert (ROOT / "src" / "ingest" / "sources.py") in files
    assert (ROOT / "worker" / "src" / "sources.js") in files
    assert len(files) > 100
    found = LOTTERY_SHAPED.findall((ROOT / "src" / "ingest" / "sources.py").read_text(encoding="utf-8"))
    assert set(found) == {"xoso.com.vn", "mketqua.net", "www.minhngoc.net.vn"}, (
        "biểu thức nhận diện không bắt được danh mục thật"
    )


def test_no_lottery_domain_outside_the_approved_list_appears_in_code_or_data() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for raw in LOTTERY_SHAPED.findall(text):
            domain = raw.lower().rstrip(".")
            if domain in ALLOWED or INFRASTRUCTURE.search(domain):
                continue
            offenders.setdefault(domain, []).append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "có nguồn xổ số ngoài danh sách được duyệt:\n"
        + "\n".join(f"  {d}: {sorted(set(files))[:4]}" for d, files in offenders.items())
    )


@pytest.mark.parametrize(
    "removed",
    ["rongbachkim.net", "caulo100.com", "soicauvn247.com", "ketqua.net", "xosome.vn"],
)
def test_the_scan_would_catch_a_source_that_crept_back_in(removed: str, tmp_path) -> None:
    assert LOTTERY_SHAPED.search(f'URL = "https://{removed}/thongke.html"')
    assert LOTTERY_SHAPED.search(f"tham khảo {removed} cho phương pháp này") is None
    assert removed not in ALLOWED
