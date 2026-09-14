"""Hành vi vận hành của Worker mà phép đối chiếu Python/JS không chạm tới.

Ba phép đối chiếu kia chứng minh Worker TÍNH giống bản Python. Tệp này kiểm
những thứ chỉ Worker mới có, và đều là loại hỏng âm thầm:

* chặn khuếch đại yêu cầu ra trang nguồn,
* một lượt cron hỏng không được làm đổ lượt sau,
* thiếu ràng buộc KV phải báo lỗi đọc hiểu được,
* định tuyến và tiêu đề CORS.

Mỗi kịch bản chạy trong MỘT TIẾN TRÌNH RIÊNG vì ``index.js`` giữ mốc chặn ở
cấp module; gộp chung thì ca sau thừa hưởng khoá của ca trước.
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


@pytest.mark.parametrize("scenario", ["amplification_kv_broken", "amplification_kv_healthy"])
def test_many_viewers_cannot_amplify_into_a_flood_of_source_requests(scenario: str) -> None:
    """Trang live thăm dò 5 giây/lần; không chặn thì mỗi lượt kéo theo sáu lượt.

    Nhánh "KV rỗng thì thu thập ngay" là đúng cho lần gọi đầu sau khi triển
    khai. Nhưng nếu KV ghi hỏng thì nó biến thành: mỗi người xem, 5 giây một
    lần, dội sáu lượt vào trang nguồn — đúng lúc các trang ấy tải nặng nhất
    trong ngày. Mười người xem là hơn 700 lượt mỗi phút.

    Hai lớp khoá: một trong KV, một trong bộ nhớ của isolate. Ca
    ``kv_broken`` tắt hẳn lớp đầu để chứng minh lớp sau thật sự đỡ được —
    bản đầu tôi viết chỉ có lớp KV, và đo được 12 lượt sinh 72 lượt gọi.
    """
    out = _scenario(scenario)
    assert out["all_ok"], "mọi lượt vẫn phải trả lời bình thường"
    assert out["outbound_fetches"] == SOURCES_PER_COLLECTION, (
        f"{out['requests']} lượt truy cập sinh {out['outbound_fetches']} lượt gọi ra "
        f"nguồn; chỉ được phép đúng một vòng thu thập ({SOURCES_PER_COLLECTION})"
    )


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
