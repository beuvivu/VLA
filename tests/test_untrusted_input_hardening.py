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


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_workflow_declares_its_token_scope(workflow: Path) -> None:
    """Không khai báo thì ``GITHUB_TOKEN`` nhận phạm vi mặc định rộng.

    Đặc quyền tối thiểu là thứ giữ cho một lỗi thực thi mã KHÔNG leo thang
    thành chiếm quyền kho — đúng lý do mà lỗi chèn lệnh ở trên tuy có thật
    nhưng không phải thảm hoạ.
    """
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert "permissions" in document, f"{workflow.name} không khai báo permissions"


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
