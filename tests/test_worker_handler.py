"""Hành vi vận hành của Worker mà phép đối chiếu Python/JS không chạm tới.

Ba phép đối chiếu kia chứng minh Worker TÍNH giống bản Python. Tệp này kiểm
những thứ chỉ Worker mới có, và đều là loại hỏng âm thầm:

* lượt yêu cầu của người xem không bao giờ gọi trang nguồn,
* một lượt cron hỏng không được làm đổ lượt sau,
* thiếu ràng buộc KV phải báo lỗi đọc hiểu được,
* định tuyến và tiêu đề CORS.

Mỗi kịch bản chạy trong MỘT TIẾN TRÌNH RIÊNG để không ca nào thừa hưởng trạng thái
cấp module của ca trước.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "worker" / "test" / "run_handler.mjs"

def _primary_round_fetches() -> int:
    """Số lượt gọi ra ngoài của MỘT vòng thu thập tầng chính.

    Suy từ danh mục Python chứ không chép cứng một con số: mỗi nguồn thử lần
    lượt các đường dẫn ứng viên cho tới khi bóc đủ 27 giá trị, và trang giả
    trong kịch bản kiểm chỉ trả 5 giá trị nên không nguồn nào dừng sớm.

    Danh mục Python và JS đã được `test_worker_sources_parity.py` buộc khớp
    nhau, nên đây là một phép suy ĐỘC LẬP với bản JS đang được kiểm.
    """
    from datetime import date

    from sources import primary_sources

    return sum(len(s.live_urls(date(2026, 9, 5))) for s in primary_sources())


#: Chỉ tầng CHÍNH được gọi khi nó đủ để xác minh. Trang giả trong kịch bản
#: kiểm trả cùng một nội dung cho mọi nguồn, nên hai nguồn chính luôn khớp
#: nhau và tầng dự phòng không bao giờ được chạm tới.
SOURCES_PER_COLLECTION = _primary_round_fetches()

#: Số HÀNG nguồn trong bản chụp — khác hẳn số lượt gọi ra ngoài ở trên.
#: Một nguồn có thể thử nhiều đường dẫn ứng viên nên hai con số không bằng
#: nhau, và dùng lẫn chúng là cách một phép kiểm trông như đang kiểm điều
#: này mà thật ra kiểm điều kia.
PRIMARY_SOURCE_ROWS = 2
ALL_SOURCE_ROWS = 8


def _require_node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "CI phải có node để chạy phép kiểm handler của Worker; "
                "xem bước 'Thiết lập Node' trong .github/workflows/ci.yml"
            )
        pytest.skip("không có node trên máy chạy kiểm")
    return node


def _scenario(name: str) -> dict:
    proc = subprocess.run(
        [_require_node(), str(RUNNER), name],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert proc.returncode == 0, f"kịch bản {name} hỏng:\n{proc.stderr}"
    return json.loads(proc.stdout)


@pytest.mark.parametrize("kv_state", ["kv_empty", "kv_put_drops"])
def test_viewer_requests_never_call_the_sources(kv_state: str) -> None:
    """Trang live thăm dò 5 giây/lần; nếu lượt yêu cầu được thu thập thì mỗi lượt kéo theo sáu.

    Trước 08-10-2026, KV rỗng thì lượt yêu cầu thu thập ngay, chặn bằng khoá KV cộng mốc trong
    bộ nhớ. KV nhất quán sau, không đọc-ghi nguyên tử, nên lúc khởi động lạnh mỗi isolate tự
    chạy một vòng: đo được 12 lượt gọi nguồn cho 12 yêu cầu luân phiên hai isolate. Nay chỉ cron
    gọi nguồn; KV rỗng thì trả 503 có CORS để trang live chuyển sang live.json dự phòng.
    """
    out = _scenario("requests_never_collect")
    assert out["outbound_fetches"] == 0, (
        f"lượt yêu cầu đã gọi nguồn {out['outbound_fetches']} lần; chỉ cron được gọi"
    )
    assert out[kv_state]["statuses"] == [503], "KV rỗng phải báo lỗi để trang đọc nguồn kế tiếp"
    assert out[kv_state]["cors"] == ["*"], "thiếu CORS thì trình duyệt chỉ thấy lỗi mạng"
    assert out[kv_state]["body_status"] == "waiting"


def test_the_live_page_treats_a_non_ok_worker_reply_as_a_reason_to_fall_back() -> None:
    """503 của Worker chỉ có ích khi trang live coi nó là lỗi và đọc nguồn kế tiếp."""
    page = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    block = page.split("async function fetchSnapshot()")[1].split("throw lastError")[0]
    assert "if (!response.ok) throw" in block


def test_the_scheduled_run_writes_once_and_reads_come_from_storage() -> None:
    """Cron gọi nguồn; lượt đọc của người xem thì KHÔNG."""
    out = _scenario("normal")
    assert out["outbound_on_cron"] == SOURCES_PER_COLLECTION
    assert out["outbound_after_read"] == SOURCES_PER_COLLECTION, (
        "lượt đọc sau khi cron đã ghi không được gọi nguồn lần nữa"
    )
    assert out["schema_version"] == 2, "phải khớp lược đồ bản Python"
    assert out["source_count"] == PRIMARY_SOURCE_ROWS, (
        "tầng chính đủ thì không được chạm tới nguồn dự phòng"
    )
    assert out["special"] == ["83772"], "dữ liệu phải đi hết đường từ HTML tới payload"
    assert out["cors"] == "*", "trang live ở tên miền khác nên bắt buộc có CORS"
    assert "max-age" in out["cache_control"]
    assert out["health_ok"] and out["health_has_snapshot"]


def test_every_source_failing_still_publishes_a_waiting_snapshot() -> None:
    """Mọi nguồn cùng chặn là kịch bản đã lường trước, không phải sự cố.

    Worker gọi từ mạng trung tâm dữ liệu nên có thể bị chặn. Khi ấy nó vẫn
    phải ghi một ảnh chụp trạng thái "waiting" kèm lỗi từng nguồn — có thế thì
    /health mới nói được là đang hỏng ở đâu. Im lặng thì không ai biết gì.
    """
    out = _scenario("all_sources_down")
    assert out["scheduled_threw"] is False, "một lượt cron hỏng không được đổ lượt sau"
    assert out["wrote_snapshot"] is True
    assert out["status"] == "waiting"
    assert out["fallback_activated"] is True, (
        "tầng chính hỏng thì PHẢI kích hoạt dự phòng"
    )
    assert out["source_rows"] == ALL_SOURCE_ROWS
    assert out["errors"] == ALL_SOURCE_ROWS, "phải ghi lỗi của TỪNG nguồn"


def test_a_missing_kv_binding_says_exactly_what_to_do() -> None:
    """Quên tạo KV là lỗi hay gặp nhất lúc triển khai lần đầu.

    Không bắt riêng thì nó hiện ra là "Cannot read properties of undefined",
    vô nghĩa với người vừa chạy `wrangler deploy` lần đầu.
    """
    message = _scenario("missing_kv")["message"]
    assert message is not None, "thiếu KV phải nổ, không được lặng lẽ chạy tiếp"
    assert "wrangler kv namespace create LIVE" in message
    assert "live-worker.md" in message


def test_a_settled_draw_stops_the_cron_from_calling_sources_again() -> None:
    """Cron chạy mỗi phút suốt khung quay số; đã xong thì không gọi nữa.

    Không có chốt này thì sau khi đủ 27 ô và đã xác minh, cron vẫn gọi sáu
    nguồn thêm vài chục lần nữa mà không thêm được thông tin gì — chỉ tốn hạn
    mức và dội vào đúng những trang đang tải nặng nhất trong ngày.

    Chốt so theo NGÀY QUAY chứ không chỉ theo trạng thái, nếu không ảnh chụp
    đã xác minh của hôm qua sẽ chặn luôn việc thu thập hôm nay — hệ thống đứng
    im vĩnh viễn sau đúng một ngày thành công.
    """
    out = _scenario("settled_stops_collecting")
    assert out["status"] == "complete_verified"
    # Trang giả ở kịch bản này trả TRỌN một kỳ, nên mỗi nguồn dừng ngay ở
    # đường dẫn ứng viên đầu tiên: đúng một lượt gọi cho mỗi nguồn chính.
    assert out["outbound_after_first_cron"] == PRIMARY_SOURCE_ROWS
    assert out["outbound_after_six_crons"] == PRIMARY_SOURCE_ROWS, (
        "năm lượt cron sau khi đã xác minh không được gọi nguồn lần nào nữa"
    )
    assert out["outbound_after_stale_date"] == PRIMARY_SOURCE_ROWS * 2, (
        "ảnh chụp của NGÀY KHÁC phải cho thu thập lại, không được chặn"
    )


def test_routing_and_methods() -> None:
    out = _scenario("routing")
    assert out["unknown_path"] == 404
    assert out["post"] == 405, "chỉ đọc, không nhận ghi"
    assert out["options"] == 204, "preflight CORS phải qua"


def test_a_kv_that_cannot_write_does_not_break_the_cron_or_the_reply() -> None:
    """KV hết hạn mức ghi: lỗi của lượt cron chỉ vào log, lượt sau thử lại; người xem nhận 503
    có CORS (trang chuyển sang nguồn dự phòng) và lượt đọc không gọi nguồn."""
    out = _scenario("kv_put_throws")
    assert out["cron_rejected"] is False, "một lượt cron hỏng không được đổ lượt sau"
    assert out["outbound_on_cron"] == SOURCES_PER_COLLECTION
    assert out["statuses"] == [503]
    assert out["cors"] == ["*"]
    assert out["outbound_after_reads"] == SOURCES_PER_COLLECTION


def test_health_survives_a_corrupt_stored_snapshot() -> None:
    assert _scenario("health_corrupt_kv") == {"status": 200, "has_snapshot": False}
