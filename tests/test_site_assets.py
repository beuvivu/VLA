"""Khóa phiên bản tài nguyên theo nội dung và kiểm tra gói xuất bản thật."""

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from bs4 import BeautifulSoup

from site_assets import check_site, refresh_site, rewrite_assets


def _site(tmp_path: Path) -> tuple[Path, Path]:
    assets = tmp_path / "assets"
    assets.mkdir()
    asset = assets / "app.js"
    asset.write_text("const value = 1;", encoding="utf-8")
    page = tmp_path / "index.html"
    page.write_text('<!doctype html><html><head><script src="assets/app.js"></script>'
                    '</head><body>07</body></html>', encoding="utf-8")
    return page, asset


def test_revision_tracks_bytes_without_process_cache(tmp_path: Path) -> None:
    page, asset = _site(tmp_path)
    original = page.read_text()
    first = rewrite_assets(page, original)
    revision = hashlib.sha256(asset.read_bytes()).hexdigest()[:16]
    assert f'assets/app.js?rev={revision}' in first
    assert rewrite_assets(page, first) == first
    assert rewrite_assets(page, first, strip=True) == original
    asset.write_text("const value = 2;", encoding="utf-8")
    second = rewrite_assets(page, first)
    assert second != first
    assert rewrite_assets(page, original) == second


def test_rewrites_only_real_attributes_and_preserves_payload(tmp_path: Path) -> None:
    page, _ = _site(tmp_path)
    payload = '''<script type="application/json">{"html":"<script src='assets/app.js'>"}</script>
<style>.x{content:'href="assets/app.js"'}</style>'''
    source = payload + '''<script data-label='src="assets/wrong.js"'
        src='assets/app.js?mode=fast&amp;rev=old#anchor'></script>
<script src="https://example.org/assets/app.js?rev=old"></script>'''
    updated = rewrite_assets(page, source)
    assert updated.startswith(payload)
    doc = BeautifulSoup(updated, "html.parser")
    target = doc.select_one("script[data-label]")
    parts = urlsplit(target["src"])
    assert parts.fragment == "anchor"
    assert parse_qs(parts.query)["mode"] == ["fast"]
    assert parse_qs(parts.query)["rev"] != ["old"]
    assert target["data-label"] == 'src="assets/wrong.js"'
    assert 'https://example.org/assets/app.js?rev=old' in updated


def test_outside_assets_and_symlinks_are_never_fingerprinted(tmp_path: Path) -> None:
    page, _ = _site(tmp_path)
    (tmp_path / "secret.js").write_text("private", encoding="utf-8")
    (tmp_path / "assets/link.js").symlink_to(tmp_path / "secret.js")
    for url in ("assets/%2e%2e/secret.js", "assets/link.js", "secret.js", "//host/assets/app.js"):
        source = f'<script src="{url}"></script>'
        assert rewrite_assets(page, source) == source


def test_site_refresh_is_deterministic_and_checks_bytes(tmp_path: Path) -> None:
    page, asset = _site(tmp_path)
    manifest = refresh_site(tmp_path)
    once = (tmp_path / "assets/release.json").read_bytes()
    assert manifest["assets"]["assets/app.js"] == hashlib.sha256(asset.read_bytes()).hexdigest()
    assert check_site(tmp_path) == []
    assert refresh_site(tmp_path) == manifest
    assert (tmp_path / "assets/release.json").read_bytes() == once
    assert json.loads(once)["pages"][page.name] == hashlib.sha256(page.read_bytes()).hexdigest()
    asset.write_text("changed", encoding="utf-8")
    assert any("app.js" in issue for issue in check_site(tmp_path))
    refresh_site(tmp_path)
    assert check_site(tmp_path) == []
    page.write_text(page.read_text().replace("?rev=", "?rev=stale"), encoding="utf-8")
    assert any("index.html" in issue for issue in check_site(tmp_path))


def test_missing_asset_blocks_release(tmp_path: Path) -> None:
    page, asset = _site(tmp_path)
    asset.unlink()
    with pytest.raises(ValueError, match="app.js"):
        refresh_site(tmp_path)
    assert not (tmp_path / "assets/release.json").exists()


def test_duplicate_revision_and_missing_manifest_are_rejected(tmp_path: Path) -> None:
    page, _ = _site(tmp_path)
    assert check_site(tmp_path)
    refresh_site(tmp_path)
    page.write_text(page.read_text().replace('?rev=', '?rev=wrong&amp;rev='), encoding="utf-8")
    assert any("phiên bản" in issue for issue in check_site(tmp_path))
    (tmp_path / "assets/release.json").write_text("[]", encoding="utf-8")
    assert any("object" in issue for issue in check_site(tmp_path))


@pytest.mark.parametrize("component", ["app-main", "app-header", "app-rail"])
def test_duplicate_shell_blocks_release_before_writing(tmp_path: Path, component: str) -> None:
    page, _ = _site(tmp_path)
    shell = ''.join(f'<div class="{name}">07</div>' for name in ("app-main", "app-header", "app-rail", component))
    page.write_text(page.read_text().replace('07', shell), encoding="utf-8")
    with pytest.raises(ValueError, match="khung"):
        refresh_site(tmp_path)
    assert not (tmp_path / 'assets/release.json').exists()


def test_output_boundary_is_idempotent_with_versioned_shell(tmp_path: Path) -> None:
    from page_output import write_page

    page, _ = _site(tmp_path)
    write_page(page, page.read_text())
    first = page.read_text()
    assert 'assets/app-shell.js?rev=' in first
    write_page(page, first)
    assert page.read_text() == first
    soup = BeautifulSoup(first, "html.parser")
    assert len(soup.select(".app-main")) == 1
    assert len(soup.select("script[data-app-theme]")) == 1


def test_every_pages_upload_finalizes_the_same_source_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    uploads = 0
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for job in workflow.get("jobs", {}).values():
            steps = job.get("steps", [])
            for index, step in enumerate(steps):
                if not step.get("uses", "").startswith("actions/upload-pages-artifact@"):
                    continue
                uploads += 1
                assert step["with"]["path"] == "docs", path.name
                assert "src/site_assets.py --refresh docs --check" in steps[index - 1].get("run", ""), path.name
                assert steps[index - 1].get("if") == step.get("if"), path.name
    assert uploads >= 5


@pytest.mark.parametrize("skip_docs", [False, True])
def test_pipeline_finalizes_after_all_builders_and_fails_closed(monkeypatch, skip_docs: bool) -> None:
    import sys
    import pipeline

    calls = []
    monkeypatch.setattr(pipeline, "_run", lambda cmd, **kwargs: calls.append((cmd, kwargs)))
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--skip-sync", "--skip-ml"]
                        + (["--skip-docs"] if skip_docs else []))
    pipeline.main()
    finalizers = [(cmd, opts) for cmd, opts in calls if "src/site_assets.py" in cmd]
    if skip_docs:
        assert finalizers == []
    else:
        assert len(finalizers) == 1
        assert calls[-1] == finalizers[0]
        assert finalizers[0][0][-3:] == ["--refresh", "docs", "--check"]
        assert finalizers[0][1]["allow_fail"] is False
