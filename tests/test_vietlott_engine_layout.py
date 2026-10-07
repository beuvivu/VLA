"""Engine Vietlott chép từ VLM sống trong ``vietlott/`` như một dự án TỰ ĐỦ.

Chủ dự án yêu cầu (07-10-2026): VLA có đủ tính năng của VLM nhưng hai bên chạy
riêng rẽ, để sau còn tách thành hai trang. Vì vậy engine không bị trộn vào
``src/`` hay ``data/`` của VLA: nó giữ nguyên bố cục của kho VLM, và các phép
kiểm dưới đây canh để bố cục ấy không trôi.

GitHub chỉ đọc workflow ở gốc kho, nên workflow của engine nằm ở
``.github/workflows/vlm-*.yml`` và chạy trong thư mục con. Chúng KHÔNG được
triển khai Pages: ``pages.yml`` là workflow triển khai duy nhất (CLAUDE.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "vietlott"
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("vlm-*.yml"))
PAGES_ACTIONS = ("actions/deploy-pages", "actions/upload-pages-artifact", "actions/configure-pages")


def test_the_engine_is_a_self_contained_project() -> None:
    """Đủ những gì engine dùng để tự nhận ra thư mục dự án (``paths._is_project``)."""
    for rel in ("pyproject.toml", "src/vietlott_engine/__init__.py", "src/vlm/__init__.py",
                "data/seed", "scripts/persist_site.py", "scripts/build_site.py", "tests/conftest.py"):
        assert (ENGINE / rel).exists(), rel
    assert {p.name for p in WORKFLOWS} == {
        "vlm-ci.yml", "vlm-installer.yml", "vlm-release.yml", "vlm-results.yml", "vlm-update.yml",
    }


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def pages_violations(document: dict) -> list[str]:
    """Bước hoặc quyền triển khai Pages trong một workflow."""
    found = []
    if (document.get("permissions") or {}).get("pages"):
        found.append("permissions.pages")
    for name, job in (document.get("jobs") or {}).items():
        if (job.get("permissions") or {}).get("pages") or "environment" in job:
            found.append(f"{name}: quyền/môi trường Pages")
        for step in job.get("steps") or []:
            uses = str(step.get("uses", ""))
            if uses.startswith(PAGES_ACTIONS):
                found.append(f"{name}: {uses}")
    return found


def cache_paths_outside_engine(document: dict) -> list[str]:
    """Đường dẫn cache không nằm dưới ``vietlott/``.

    ``working-directory`` chỉ áp lên ``run:``; ``actions/cache`` đọc đường dẫn
    tính từ gốc workspace. Thiếu tiền tố thì cache lưu và khôi phục nhầm chỗ,
    và trạng thái bộ dự báo âm thầm mất giữa các lần chạy.
    """
    bad = []
    for job in (document.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if str(step.get("uses", "")).startswith("actions/cache"):
                for line in str((step.get("with") or {}).get("path", "")).splitlines():
                    if line.strip() and not line.strip().startswith("vietlott/"):
                        bad.append(line.strip())
    return bad


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_engine_workflows_run_inside_the_engine_and_never_deploy_pages(workflow: Path) -> None:
    document = _load(workflow)
    assert document["defaults"]["run"]["working-directory"] == "vietlott"
    assert pages_violations(document) == []
    assert cache_paths_outside_engine(document) == []


def _cache_paths(document: dict, action: str) -> list[list[str]]:
    return [
        [line.strip() for line in str(step["with"]["path"]).splitlines() if line.strip()]
        for job in (document.get("jobs") or {}).values()
        for step in job.get("steps") or []
        if str(step.get("uses", "")).startswith(action)
    ]


def test_the_page_build_restores_exactly_what_the_engine_saves() -> None:
    """``actions/cache`` tính phiên bản theo danh sách đường dẫn: khôi phục bằng một
    danh sách khác bước lưu thì không bao giờ trúng cache nào, và trang mất bảng giải
    mới lẫn trạng thái bộ dự báo mà không báo lỗi."""
    saved = {tuple(p) for name in ("vlm-results.yml", "vlm-update.yml")
             for p in _cache_paths(_load(ROOT / ".github" / "workflows" / name), "actions/cache/save")}
    assert len(saved) == 1, saved
    restored = _cache_paths(_load(ROOT / ".github" / "workflows" / "vietlott-results.yml"), "actions/cache/restore")
    assert [tuple(p) for p in restored] == list(saved)


def test_the_rules_themselves_catch_violations() -> None:
    """Ghim chính LUẬT trên mẫu dựng sẵn: quét qua tệp thật có thể không bao giờ đỏ."""
    deploy = {
        "permissions": {"contents": "write", "pages": "write"},
        "jobs": {"deploy": {"environment": {"name": "github-pages"},
                            "steps": [{"uses": "actions/deploy-pages@v5"}]}},
    }
    assert len(pages_violations(deploy)) == 3
    cache = {"jobs": {"j": {"steps": [{"uses": "actions/cache/save@v6",
                                       "with": {"path": "vietlott/data/products\ndata/parquet\n"}}]}}}
    assert cache_paths_outside_engine(cache) == ["data/parquet"]
