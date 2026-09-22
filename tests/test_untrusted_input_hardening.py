"""Ranh giới với thứ KHÔNG đáng tin: đầu vào CI và thân phản hồi của nguồn.

Hai ranh giới này nhận dữ liệu do bên ngoài quyết định, nên chúng là nơi một
lỗi nhỏ đổi thành thực thi mã hoặc cạn bộ nhớ. Tệp này khoá cả hai lại.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

import sources

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

#: Ngữ cảnh do người ngoài quyết định nội dung. `github.event_name` và
#: `repository.default_branch` không nằm ở đây: chúng lấy giá trị từ một tập
#: cố định do GitHub đặt, không phải văn bản tự do.
#:
#: PHẢI bắt cả dạng RÚT GỌN ``${{ inputs.x }}``, không chỉ dạng đầy đủ
#: ``${{ github.event.inputs.x }}``. Bản đầu của biểu thức này chỉ có dạng đầy
#: đủ, và nó bỏ lọt trọn vẹn ``backfill-history.yml`` — nơi bốn đầu vào nội
#: suy thẳng vào ``run:`` và job lại mang token ``contents: write``, tức nặng
#: hơn hẳn ca nó bắt được. Một phép kiểm an ninh bắt hụt đúng dạng phổ biến
#: nhất thì tệ hơn không có, vì nó phát ra cảm giác an toàn.
UNTRUSTED = re.compile(
    r"\$\{\{\s*(?:github\.event\.)?"
    r"(inputs|client_payload|issue|pull_request|comment|head_commit)\."
)


def _run_blocks(document: dict) -> list[tuple[str, str]]:
    """Mọi khối ``run:`` trong một workflow, kèm tên bước để báo lỗi cho rõ."""
    found: list[tuple[str, str]] = []
    for job_name, job in (document.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                found.append((f"{job_name}/{step.get('name', '?')}", step["run"]))
    return found


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_no_untrusted_context_is_interpolated_into_a_shell_block(workflow: Path) -> None:
    """Runner thay ``${{ }}`` TRƯỚC khi shell nhìn thấy dòng lệnh.

    Dấu nháy trong YAML vì thế không bảo vệ được gì: một đầu vào dạng
    ``18:15" ; curl ... | sh ; echo "`` trở thành một lệnh độc lập chạy trên
    runner. Đã đo được đúng dạng ấy trong ``daily_update.yml``.

    Cách đúng — và đã có sẵn ở bước liền trước trong chính tệp đó — là đưa qua
    ``env:`` rồi tham chiếu ``"$VAR"``, khi ấy shell nhận chuỗi làm DỮ LIỆU
    chứ không làm cú pháp.
    """
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    offenders = [
        f"{where}: {UNTRUSTED.search(script).group(0)}"
        for where, script in _run_blocks(document)
        if UNTRUSTED.search(script)
    ]
    assert not offenders, f"{workflow.name} nội suy ngữ cảnh không tin cậy vào shell: {offenders}"


#: Thư mục DUY NHẤT được phép xuất bản lên GitHub Pages.
PAGES_ROOT = "docs"


def pages_upload_paths(document: dict) -> list[str]:
    """Mọi đường dẫn mà workflow này nạp lên làm hiện vật GitHub Pages."""
    found: list[str] = []
    for job in (document.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if "upload-pages-artifact" not in str((step or {}).get("uses") or ""):
                continue
            found.append(str(((step or {}).get("with") or {}).get("path", "")))
    return found


def pages_paths_outside_docs(document: dict) -> list[str]:
    """Các đường dẫn Pages KHÔNG phải ``docs``.

    Bỏ dấu nháy trước khi so: YAML giữ nguyên nháy trong giá trị, nên
    ``path: 'docs'`` và ``path: docs`` là cùng một thư mục nhưng khác chuỗi.
    So thô sẽ báo động giả cho cách viết thứ nhất.
    """
    return [
        path
        for path in pages_upload_paths(document)
        if path.strip().strip("\"'").rstrip("/") != PAGES_ROOT
    ]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_publishes_pages_from_outside_the_docs_tree(workflow: Path) -> None:
    """Chỉ ``docs`` được xuất bản. Chốt chặn cho một SỰ CỐ ĐÃ XẢY RA.

    Ngày 2026-09-21, `static.yml` nạp ``path: '.'`` — toàn bộ gốc kho — và
    chạy trên MỌI push vào `main`, trong khi `pages.yml` chỉ chạy khi
    ``docs/**`` đổi. Hai workflow cùng deploy Pages, và bên deploy SAU thắng.
    Đo bằng dấu thời gian của cùng một commit: `pages.yml` xong lúc 21:29:28,
    `static.yml` xong lúc 21:29:31. Bản được phục vụ là bản của `static.yml`,
    tức gốc kho — nơi không có ``index.html``. Site trả 404.

    Hai hậu quả, và cái thứ hai tệ hơn: trang chết, VÀ toàn bộ 473 MB dữ liệu
    cùng model trong kho bị xuất bản công khai.
    """
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    offenders = pages_paths_outside_docs(document)
    assert not offenders, (
        f"{workflow.name} xuất bản Pages từ {offenders} thay vì {PAGES_ROOT!r} — "
        "gốc kho không có index.html và mang cả dữ liệu lẫn model"
    )


def _pages_step(path: str | None) -> dict:
    step: dict = {"uses": "actions/upload-pages-artifact@v5"}
    if path is not None:
        step["with"] = {"path": path}
    return {"jobs": {"deploy": {"steps": [step]}}}


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        (_pages_step("docs"), []),
        (_pages_step("'docs'"), []),
        (_pages_step("docs/"), []),
        (_pages_step("."), ["."]),
        (_pages_step("'.'"), ["'.'"]),
        (_pages_step(None), [""]),
        ({"jobs": {"d": {"steps": [{"uses": "actions/checkout@v4"}]}}}, []),
    ],
    ids=["docs", "docs có nháy", "docs có gạch cuối", "gốc kho", "gốc kho có nháy", "thiếu path", "không nạp Pages"],
)
def test_the_pages_path_rule_handles_every_way_of_writing_the_path(
    document: dict, expected: list[str]
) -> None:
    """Luật phải tự kiểm được, vì kho hiện KHÔNG còn workflow nào nạp gốc kho.

    `static.yml` đã bị xóa nên phép kiểm trên chạy qua các workflow lành và
    xanh miễn phí. Hai ca đáng kể: ``'.'`` có nháy phải BỊ BẮT, còn ``'docs'``
    có nháy phải ĐƯỢC CHO QUA — thiếu phép bỏ nháy thì ca sau thành báo động
    giả, và một báo động giả sẽ bị ai đó tắt đi cùng với cả phép kiểm.
    """
    assert pages_paths_outside_docs(document) == expected


def jobs_without_token_scope(document: dict) -> list[str]:
    """Các job nhận phạm vi ``GITHUB_TOKEN`` mặc định rộng.

    Khai ở cấp TÀI LIỆU thì mọi job được che, nên trả về rỗng. Không khai ở
    cấp tài liệu thì từng job phải tự khai; thiếu một job là job ấy nhận phạm
    vi mặc định, đúng điều bất biến này cấm.

    Tách hàm ra vì kho hiện KHÔNG có workflow nào khai một phần — mọi workflow
    hoặc khai ở cấp tài liệu, hoặc khai đủ mọi job. Đo bằng đột biến: nới
    ``all`` thành ``any`` thì không phép kiểm nào đỏ. Nên luật phải ghim trên
    tài liệu dựng sẵn, chứ không chỉ chạy qua tệp thật.

    Args:
        document: Workflow đã nạp bằng ``yaml.safe_load``.

    Returns:
        Tên các job thiếu khai báo; rỗng nghĩa là đạt. ``["<không có job>"]``
        khi tài liệu không khai ở cấp nào và cũng không có job nào.
    """
    if "permissions" in document:
        return []
    jobs = document.get("jobs") or {}
    if not jobs:
        return ["<không có job>"]
    return [name for name, job in jobs.items() if "permissions" not in (job or {})]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_workflow_declares_its_token_scope(workflow: Path) -> None:
    """Không khai báo thì ``GITHUB_TOKEN`` nhận phạm vi mặc định rộng.

    Đặc quyền tối thiểu là thứ giữ cho một lỗi thực thi mã KHÔNG leo thang
    thành chiếm quyền kho — đúng lý do mà lỗi chèn lệnh ở trên tuy có thật
    nhưng không phải thảm hoạ.

    Nhận cả khai báo ở cấp JOB, vì nó hẹp hơn cấp tài liệu chứ không lỏng
    hơn. Bản trước chỉ nhận cấp tài liệu nên cáo buộc SAI bốn workflow
    (`patch_css_links`, `optimize_dom`, `patch_csp`, `hotfix_ui_csp`) là
    "không khai báo permissions" trong khi cả bốn đều khai `contents: write`
    ngay trong job của mình. Bốn phép kiểm đỏ vô cớ làm mờ những phép kiểm đỏ
    có thật.
    """
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    thieu = jobs_without_token_scope(document)
    assert not thieu, f"{workflow.name}: job thiếu khai báo permissions: {thieu}"


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"permissions": {"contents": "read"}, "jobs": {"a": {}}}, []),
        ({"jobs": {"a": {"permissions": {"contents": "write"}}}}, []),
        (
            {
                "jobs": {
                    "a": {"permissions": {"contents": "read"}},
                    "b": {"runs-on": "ubuntu-latest"},
                }
            },
            ["b"],
        ),
        ({"jobs": {"a": None}}, ["a"]),
        ({"name": "chỉ có tên"}, ["<không có job>"]),
    ],
    ids=["cấp tài liệu", "cấp job", "một job thiếu", "job rỗng", "không có job"],
)
def test_the_token_scope_rule_requires_every_job_not_merely_one(
    document: dict, expected: list[str]
) -> None:
    """Một job khai mà job kia không khai thì KHÔNG đạt.

    Ca "một job thiếu" là ca duy nhất phân biệt ``all`` với ``any``, và kho
    không có tệp thật nào ở hình dạng ấy — nới thành ``any`` mà chỉ chạy qua
    tệp thật thì suite vẫn xanh. Nên nó được dựng sẵn ở đây.
    """
    assert jobs_without_token_scope(document) == expected


class _Response:
    def __init__(self, text: str, *, status: int = 200, headers: dict | None = None) -> None:
        self.text = text
        self.status_code = status
        self.headers = headers or {}


class _Client:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls = 0

    def get(self, url: str, timeout: int | float = 20, **kwargs: object) -> _Response:
        self.calls += 1
        return self.response


def test_a_page_within_the_cap_passes_through_untouched() -> None:
    body = "<html>" + "x" * 1000 + "</html>"
    client = _Client(_Response(body, headers={"Content-Length": str(len(body))}))
    assert sources._request_page(client, "https://nguon/x") == body


def test_a_body_declared_larger_than_the_cap_is_refused_before_parsing() -> None:
    """Máy chủ khai lớn hơn trần thì từ chối ngay, không đụng tới thân."""
    huge = sources.MAX_PAGE_BYTES + 1
    client = _Client(_Response("nội dung", headers={"Content-Length": str(huge)}))
    assert sources._request_page(client, "https://nguon/x") == ""


def test_a_body_that_lies_about_its_length_is_still_refused() -> None:
    """Máy chủ có thể khai sai hoặc không khai. Trần phải chặn được cả khi ấy.

    Không có chốt chặn thứ hai thì kẻ tấn công chỉ cần bỏ ``Content-Length``
    là vượt qua toàn bộ phép kiểm.
    """
    oversized = "x" * (sources.MAX_PAGE_BYTES + 1)
    for headers in ({}, {"Content-Length": "42"}, {"Content-Length": "không phải số"}):
        client = _Client(_Response(oversized, headers=headers))
        assert sources._request_page(client, "https://nguon/x") == "", headers


def test_the_cap_is_generous_enough_for_a_real_results_page() -> None:
    """Trần quá chặt thì nó thành lỗi sản xuất chứ không phải lớp bảo vệ.

    Trang kết quả thật nặng vài trăm KB; 8 MiB rộng gấp hơn hai chục lần.
    """
    assert sources.MAX_PAGE_BYTES >= 4 * 1024 * 1024
    realistic = "<html>" + "y" * (600 * 1024) + "</html>"
    client = _Client(_Response(realistic))
    assert sources._request_page(client, "https://nguon/x") == realistic
