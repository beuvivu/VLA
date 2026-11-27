from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "worker" / "test" / "run_patch.mjs"
SETUP = ROOT / "worker" / "setup.mjs"


def _require_node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "CI phải có node để chạy phép kiểm bộ cài đặt Worker; "
                "xem bước 'Thiết lập Node' trong .github/workflows/ci.yml"
            )
        pytest.skip("không có node trên máy chạy kiểm")
    return node


def _run(cases: list[dict], tmp_path: Path) -> list[dict]:
    payload = tmp_path / "cases.json"
    payload.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [_require_node(), str(RUNNER), str(payload)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, f"bản JS hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


KV_ID = "0123456789abcdef0123456789abcdef"

KV_OUTPUTS = [
    f'✨ Success!\n[[kv_namespaces]]\nbinding = "LIVE"\nid = "{KV_ID}"\n',
    f'{{"binding": "LIVE", "id": "{KV_ID}"}}',
    f'\x1b[32mid\x1b[0m = "{KV_ID}"',
]
DEPLOY_OUTPUTS = [
    "Total Upload: 12.34 KiB\nDeployed ui-live triggers (0.87 sec)\n"
    "  https://ui-live.beuvivu.workers.dev\nCurrent Version ID: abc-123",
    "Published ui-live (1.02 sec)\n  https://ui-live.beuvivu.workers.dev\n",
]


def test_kv_id_is_extracted_from_every_known_wrangler_output_shape(tmp_path: Path) -> None:
    results = _run([{"fn": "extractKvId", "args": [out]} for out in KV_OUTPUTS], tmp_path)
    for out, result in zip(KV_OUTPUTS, results, strict=True):
        assert result["ok"], f"không bóc được id từ:\n{out}"
        assert result["value"] == KV_ID


def test_worker_url_is_extracted_from_every_known_deploy_output(tmp_path: Path) -> None:
    results = _run([{"fn": "extractWorkerUrl", "args": [out]} for out in DEPLOY_OUTPUTS], tmp_path)
    for result in results:
        assert result["ok"]
        assert result["value"] == "https://ui-live.beuvivu.workers.dev"


def test_extraction_fails_loudly_instead_of_returning_something_wrong(tmp_path: Path) -> None:
    results = _run([
        {"fn": "extractKvId", "args": ["Error: something went wrong"]},
        {"fn": "extractKvId", "args": ['id = "qua-ngan"']},
        {"fn": "extractWorkerUrl", "args": ["Deployed but no url here"]},
        {"fn": "extractWorkerUrl", "args": ["https://example.com/khong-phai-worker"]},
        {"fn": "patchWranglerKvId", "args": ["[[kv_namespaces]]\nid = \"x\"", "khong-phai-hex"]},
        {"fn": "patchLiveWorkerUrl", "args": ["<html>không có dòng nào</html>", "https://a.workers.dev"]},
    ], tmp_path)
    for n, result in enumerate(results):
        assert not result["ok"], f"ca #{n} lẽ ra phải nổ"
        assert result["error"], "lỗi phải có nội dung đọc được"


def test_patching_the_real_repository_files_works_and_is_idempotent(tmp_path: Path) -> None:
    toml = (ROOT / "worker" / "wrangler.toml").read_text(encoding="utf-8")
    html = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    url = "https://ui-live.beuvivu.workers.dev"

    once = _run([
        {"fn": "patchWranglerKvId", "args": [toml, KV_ID]},
        {"fn": "patchLiveWorkerUrl", "args": [html, url]},
    ], tmp_path)
    assert all(r["ok"] for r in once), once

    patched_toml, patched_html = once[0]["value"], once[1]["value"]
    assert KV_ID in patched_toml
    assert "THAY_BANG_ID_KV_CUA_BAN" not in patched_toml
    assert patched_toml.count("[[kv_namespaces]]") == 1

    assigns = [
        line for line in patched_html.splitlines()
        if "window.LIVE_WORKER_URL" in line and not line.strip().startswith("//")
        and "=" in line and "urls.push" not in line
    ]
    assert len(assigns) == 1, assigns
    assert assigns[0].strip() == f"window.LIVE_WORKER_URL = '{url}/live.json';"

    assert not _comment_lines(patched_html), _comment_lines(patched_html)[:3]

    twice = _run([
        {"fn": "patchWranglerKvId", "args": [patched_toml, KV_ID]},
        {"fn": "patchLiveWorkerUrl", "args": [patched_html, url]},
    ], tmp_path)
    assert twice[0]["value"] == patched_toml, "vá lần hai phải là phép đồng nhất"
    assert twice[1]["value"] == patched_html
    assert twice[0]["value"].count("[[kv_namespaces]]") == 1


def test_the_setup_script_no_longer_touches_the_results_page() -> None:
    setup = (ROOT / "worker" / "setup.mjs").read_text(encoding="utf-8")
    patch = (ROOT / "worker" / "setup" / "patch.mjs").read_text(encoding="utf-8")
    assert "so-ket-qua-truyen-thong" not in setup
    assert "VLA_RESULTS_API_URL" not in setup
    assert "VLA_RESULTS_API_URL" not in patch, "hàm vá đã chết phải gỡ, không để lại"


def test_the_verification_step_reads_the_anonymised_snapshot_fields() -> None:
    setup = (ROOT / "worker" / "setup.mjs").read_text(encoding="utf-8")
    assert "(r) => !r.failed" in setup
    assert "!r.error" not in setup
    assert "row.error" not in setup
    assert "row.source_code" in setup


def test_the_verification_step_reads_a_503_as_waiting_for_the_first_cron() -> None:
    setup = (ROOT / "worker" / "setup.mjs").read_text(encoding="utf-8")
    block = setup.split("/live.json`, { cache: \"no-store\" })")[1].split("} catch (error)")[0]
    waiting, snapshot = block.split("} else {")
    assert "response.status === 503" in waiting
    assert "nguồn trả lời được`" not in waiting
    assert "nguồn trả lời được`" in snapshot
    assert "ép thu thập" not in setup, "Worker không còn thu thập theo yêu cầu"


def test_a_trailing_slash_in_the_worker_url_does_not_double_up(tmp_path: Path) -> None:
    html = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    result = _run([
        {"fn": "patchLiveWorkerUrl", "args": [html, "https://ui-live.beuvivu.workers.dev/"]},
    ], tmp_path)[0]
    assert result["ok"]
    assert "workers.dev/live.json'" in result["value"]
    assert "//live.json" not in result["value"]


def test_the_dry_run_touches_nothing(tmp_path: Path) -> None:
    before = {
        path: (ROOT / path).read_bytes()
        for path in (
            "worker/wrangler.toml",
            "docs/live.html",
            "docs/so-ket-qua-truyen-thong.html",
        )
    }
    proc = subprocess.run(
        [_require_node(), str(SETUP), "--dry-run"],
        cwd=ROOT / "worker", capture_output=True, text=True, timeout=180, check=False,
    )
    for path, content in before.items():
        assert (ROOT / path).read_bytes() == content, f"thử khô đã sửa {path}"
    assert proc.returncode == 0, f"thử khô phải chạy trót lọt:\n{proc.stderr[-800:]}"
    assert "(thử khô)" in proc.stdout, proc.stdout[-500:]
    assert proc.stdout.count("(thử khô)") >= 4, "phải xem trước đủ các bước"


def test_setup_is_wired_into_npm_scripts() -> None:
    package = json.loads((ROOT / "worker" / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["setup"] == "node setup.mjs"
    assert package["scripts"]["setup:dry"] == "node setup.mjs --dry-run"
    assert SETUP.exists()

def _comment_lines(html: str) -> list[str]:
    import re

    found: list[str] = []
    for match in re.finditer(r"<(script|style)\b[^>]*>(.*?)</\1>", html, re.S | re.I):
        body = match.group(2)
        body = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", body)
        body = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', body)
        body = re.sub(r"`(?:[^`\\]|\\.)*`", "``", body)
        body = re.sub(r"/(?:[^/\\\n\[]|\\.|\[(?:[^\]\\]|\\.)*\])+/[a-z]*", "/re/", body)
        for line in body.splitlines():
            if line.lstrip().startswith("//") or "/*" in line:
                found.append(line.strip()[:70])
    return found
