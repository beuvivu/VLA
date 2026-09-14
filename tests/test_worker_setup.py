"""Bộ cài đặt một lệnh cho Worker.

Chỗ dễ hỏng âm thầm nhất của một kịch bản cài đặt là biểu thức bóc dữ liệu
không khớp mà kịch bản vẫn báo "xong": người dùng tưởng đã xong, rồi 18:15 hôm
sau trang không có gì. Vì thế mọi hàm biến đổi đều phải NÉM LỖI khi không
khớp, và phép kiểm này đòi đúng điều đó.

Đầu ra của wrangler đổi dạng giữa các bản, nên bộ ca gồm cả dạng khối TOML,
dạng JSON, và dạng có mã màu ANSI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
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

# Ba dạng đầu ra thật đã gặp giữa các bản wrangler.
KV_OUTPUTS = [
    f'✨ Success!\n[[kv_namespaces]]\nbinding = "LIVE"\nid = "{KV_ID}"\n',
    f'{{"binding": "LIVE", "id": "{KV_ID}"}}',
    f'\x1b[32mid\x1b[0m = "{KV_ID}"',
]
DEPLOY_OUTPUTS = [
    "Total Upload: 12.34 KiB\nDeployed vla-live triggers (0.87 sec)\n"
    "  https://vla-live.beuvivu.workers.dev\nCurrent Version ID: abc-123",
    "Published vla-live (1.02 sec)\n  https://vla-live.beuvivu.workers.dev\n",
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
        assert result["value"] == "https://vla-live.beuvivu.workers.dev"


def test_extraction_fails_loudly_instead_of_returning_something_wrong(tmp_path: Path) -> None:
    """Không khớp thì phải nổ, kèm đầu ra thật để người dùng tự xử lý được.

    Trả về rỗng hay giữ nguyên bản gốc sẽ khiến kịch bản báo "xong" trong khi
    tệp chưa hề được sửa — đúng kiểu hỏng mà không ai phát hiện.
    """
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
    """Vá trên chính hai tệp thật trong kho, và chạy lại phải ra cùng kết quả.

    Kịch bản cài đặt được thiết kế để chạy lại nhiều lần vẫn an toàn; nếu lần
    hai sinh ra mục [[kv_namespaces]] thứ hai thì wrangler sẽ hỏng.
    """
    toml = (ROOT / "worker" / "wrangler.toml").read_text(encoding="utf-8")
    html = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    url = "https://vla-live.beuvivu.workers.dev"

    once = _run([
        {"fn": "patchWranglerKvId", "args": [toml, KV_ID]},
        {"fn": "patchLiveWorkerUrl", "args": [html, url]},
        {
            "fn": "patchTraditionalResultsApiUrl",
            "args": [
                (ROOT / "docs" / "so-ket-qua-truyen-thong.html").read_text(encoding="utf-8"),
                url,
            ],
        },
    ], tmp_path)
    assert all(r["ok"] for r in once), once

    patched_toml, patched_html = once[0]["value"], once[1]["value"]
    assert KV_ID in patched_toml
    assert "THAY_BANG_ID_KV_CUA_BAN" not in patched_toml
    assert patched_toml.count("[[kv_namespaces]]") == 1

    # Phải vá đúng DÒNG GÁN, không phải dòng chú thích ví dụ ngay phía trên.
    # Bản đầu tôi viết vá nhầm vào chú thích: kịch bản báo "xong" mà trang vẫn
    # không trỏ đi đâu. Kiểm từng dòng chứ không kiểm "chuỗi có mặt đâu đó".
    assigns = [
        line for line in patched_html.splitlines()
        if "window.LIVE_WORKER_URL" in line and not line.strip().startswith("//")
        and "=" in line and "urls.push" not in line
    ]
    assert len(assigns) == 1, assigns
    assert assigns[0].strip() == f"window.LIVE_WORKER_URL = '{url}/live.json';"

    comments = [
        line for line in patched_html.splitlines()
        if "window.LIVE_WORKER_URL" in line and line.strip().startswith("//")
    ]
    assert comments, "dòng chú thích hướng dẫn phải còn"
    assert all(url not in line for line in comments), "không được vá vào chú thích"

    twice = _run([
        {"fn": "patchWranglerKvId", "args": [patched_toml, KV_ID]},
        {"fn": "patchLiveWorkerUrl", "args": [patched_html, url]},
    ], tmp_path)
    assert twice[0]["value"] == patched_toml, "vá lần hai phải là phép đồng nhất"
    assert twice[1]["value"] == patched_html
    assert twice[0]["value"].count("[[kv_namespaces]]") == 1

    patched_results = once[2]["value"]
    assert (
        f"window.VLA_RESULTS_API_URL = '{url}/api/v1/traditional-results';"
        in patched_results
    )
    repeated = _run([
        {"fn": "patchTraditionalResultsApiUrl", "args": [patched_results, url]},
    ], tmp_path)[0]
    assert repeated["value"] == patched_results


def test_a_trailing_slash_in_the_worker_url_does_not_double_up(tmp_path: Path) -> None:
    html = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    result = _run([
        {"fn": "patchLiveWorkerUrl", "args": [html, "https://vla-live.beuvivu.workers.dev/"]},
    ], tmp_path)[0]
    assert result["ok"]
    assert "workers.dev/live.json'" in result["value"]
    assert "//live.json" not in result["value"]


def test_the_dry_run_touches_nothing(tmp_path: Path) -> None:
    """`--dry-run` phải cho xem trước mà không sửa tệp nào.

    Người ngại thao tác tay cần thấy kịch bản định làm gì trước khi cho nó
    chạy thật; nếu bản thử khô cũng ghi tệp thì nó vô nghĩa.
    """
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
    # Thử khô phải HERMETIC: không gọi wrangler, không cần mạng. Nếu nó tải
    # wrangler về thì mỗi lần chạy kiểm trong CI tốn ~30 MB và dễ chập chờn.
    assert proc.stdout.count("(thử khô)") >= 4, "phải xem trước đủ các bước"


def test_setup_is_wired_into_npm_scripts() -> None:
    """`npm run setup` phải chạy được — đó là toàn bộ giao diện người dùng."""
    package = json.loads((ROOT / "worker" / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["setup"] == "node setup.mjs"
    assert package["scripts"]["setup:dry"] == "node setup.mjs --dry-run"
    assert SETUP.exists()
