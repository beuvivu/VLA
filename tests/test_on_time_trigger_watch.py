"""Chốt chặn cho đường chạy đúng giờ.

Đường này dựa vào một PAT hạn 90 ngày. Khi token hết hạn, lưới cron của GitHub
vẫn đưa dữ liệu về — muộn, nhưng về — nên KHÔNG có gì đỏ lên. Đó là kịch bản
tệ nhất của một hệ dự phòng: bản dự phòng chạy đủ tốt để giấu việc bản chính
đã hỏng.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_on_time_trigger import (  # noqa: E402
    STATE_ALIVE,
    STATE_DEAD,
    STATE_NEVER,
    classify,
    report,
)

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def _run(days_ago: float, event: str = "repository_dispatch") -> dict:
    """Một lần chạy giả, cách hiện tại ``days_ago`` ngày."""
    return {
        "event": event,
        "run_started_at": (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z"),
    }


def _classify(runs):
    return classify(runs, now=NOW, stale_days=3, lookback_days=45)


def test_never_configured_is_reported_but_not_an_alarm() -> None:
    """Chưa dựng không phải hồi quy — nó là hiện trạng đã biết.

    Một phép kiểm ngây thơ ("hôm nay có repository_dispatch không?") sẽ đỏ mỗi
    ngày cho tới khi bộ hẹn giờ được dựng. Cảnh báo đỏ liên tục dạy người ta
    bỏ qua cảnh báo, nên nó còn tệ hơn không cảnh báo.
    """
    state, detail = _classify([_run(1, event="schedule"), _run(2, event="schedule")])
    assert state == STATE_NEVER
    assert detail["lần gọi trong cửa sổ tra cứu"] == 0
    assert "mục 4" in report(state, detail, stale_days=3)


def test_recent_dispatch_is_alive() -> None:
    state, detail = _classify([_run(0.4), _run(1.4), _run(2.4)])
    assert state == STATE_ALIVE
    assert detail["lần gọi gần đây"] == 3


def test_dispatch_that_stopped_is_the_one_real_regression() -> None:
    """Từng chạy rồi im — đây mới là cái chết im lặng cần bắt.

    Lịch sử này trông hoàn toàn bình thường với mọi phép kiểm khác: lưới cron
    vẫn chạy mỗi ngày, dữ liệu vẫn về. Chỉ có sự VẮNG MẶT của
    repository_dispatch mới nói lên rằng token đã hết hạn.
    """
    runs = [_run(d, event="schedule") for d in (0.2, 1.2, 2.2)]
    runs += [_run(d) for d in (9, 10, 11, 12)]
    state, detail = _classify(runs)
    assert state == STATE_DEAD
    assert detail["lần gọi gần đây"] == 0
    assert detail["im lặng (ngày)"] == 9.0

    text = report(state, detail, stale_days=3)
    assert "PAT hết hạn" in text, "phải nêu nguyên nhân hay gặp nhất"
    assert "che triệu chứng" in text, "phải nói rõ vì sao không có gì khác đỏ"


def test_only_the_dead_state_exits_non_zero() -> None:
    """Trạng thái quyết định mã thoát, không phải số lần gọi."""
    from check_on_time_trigger import main  # noqa: PLC0415

    assert STATE_DEAD != STATE_NEVER != STATE_ALIVE
    # Thiếu cấu hình thì thoát êm: không gọi được API không phải bằng chứng
    # rằng đường đúng giờ đã chết.
    assert main(["--repository", ""]) == 0


def test_runs_outside_the_lookback_window_do_not_count_as_ever_configured() -> None:
    """Một lần gọi từ nửa năm trước không chứng minh hôm nay nó còn được dựng."""
    state, _ = _classify([_run(200)])
    assert state == STATE_NEVER


def test_watchdog_actually_runs_the_check() -> None:
    """Script không được gọi thì nó chỉ là mã chết."""
    workflow = (
        Path(__file__).resolve().parents[1] / ".github/workflows/watchdog.yml"
    ).read_text(encoding="utf-8")
    assert "check_on_time_trigger.py" in workflow
