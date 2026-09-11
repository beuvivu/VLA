"""Báo động khi ĐƯỜNG ĐÚNG GIỜ chết im lặng.

Vì sao cần
==========

Kho có hai đường chạy công việc hằng ngày:

* **Lưới cron của GitHub** — phủ khoảng 88,4 % số ngày. Lịch của GitHub là
  "cố gắng tốt nhất": đo trên chính kho này, độ trễ trung vị 144 phút, tối đa
  305. 11,6 % còn lại là ngày GitHub trễ cả khối, thêm mốc không cứu được.
* **Bộ hẹn giờ ngoài** gọi ``repository_dispatch`` lúc 18:10 giờ Việt Nam.
  Đây là đường duy nhất chạy đúng giờ một cách chắc chắn.

Đường thứ hai dựa vào một fine-grained PAT có hạn 90 ngày. Tài liệu
``documentation/operations/on-time-trigger.md`` tự nêu rủi ro:

    token hết hạn thì đường đúng giờ chết IM LẶNG, và lưới cron sẽ che mất
    triệu chứng.

Đó chính là kịch bản tệ nhất của mọi hệ dự phòng: bản dự phòng hoạt động đủ
tốt để không ai nhận ra bản chính đã hỏng. Dữ liệu vẫn về, chỉ là về muộn —
và không có gì đỏ lên.

Script này biến im lặng đó thành tiếng động.

Nó phân biệt ba trạng thái, chứ không chỉ "có/không"
====================================================

Một phép kiểm ngây thơ ("hôm nay có repository_dispatch không?") sẽ đỏ mỗi
ngày cho tới khi bộ hẹn giờ được dựng — mà nó chưa từng được dựng. Cảnh báo
đỏ liên tục dạy người ta bỏ qua cảnh báo, nên nó còn tệ hơn không cảnh báo.

Ba trạng thái:

``chưa dựng``
    Không có lần ``repository_dispatch`` nào trong cả cửa sổ tra cứu. Đây là
    hiện trạng đã biết, không phải hồi quy. Báo cáo, không báo động.

``đang chạy``
    Có lần gọi trong ``--stale-days`` ngày gần nhất. Mọi thứ bình thường.

``ĐÃ CHẾT``
    Từng có lần gọi trong cửa sổ tra cứu, nhưng im lặng suốt
    ``--stale-days`` ngày gần nhất. Đây mới là hồi quy thật — và là trạng
    thái duy nhất trả mã thoát khác 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

#: Workflow mang đường đúng giờ. Bộ hẹn giờ ngoài POST ``daily-collect``
#: vào đây; xem ``.github/workflows/daily_update.yml``.
WORKFLOW = "daily_update.yml"

#: Sự kiện mà một lần gọi từ bên ngoài sinh ra.
DISPATCH_EVENT = "repository_dispatch"

STATE_NEVER = "chưa dựng"
STATE_ALIVE = "đang chạy"
STATE_DEAD = "ĐÃ CHẾT"


def fetch_runs(repository: str, token: str, *, per_page: int = 100) -> list[dict]:
    """Lấy các lần chạy gần nhất của workflow đúng giờ.

    Args:
        repository: Dạng ``chủ/kho``.
        token: Token có quyền đọc Actions.
        per_page: Số lần chạy cần lấy.

    Returns:
        Danh sách lần chạy, mới nhất trước.

    Raises:
        RuntimeError: Khi API trả về lỗi.
    """
    url = (
        f"https://api.github.com/repos/{repository}"
        f"/actions/workflows/{WORKFLOW}/runs?per_page={per_page}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:  # pragma: no cover - phụ thuộc mạng
        raise RuntimeError(f"API trả về HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - phụ thuộc mạng
        raise RuntimeError(f"Không gọi được API: {exc.reason}") from exc
    runs = payload.get("workflow_runs")
    return list(runs) if isinstance(runs, list) else []


def classify(
    runs: Sequence[dict], *, now: datetime, stale_days: int, lookback_days: int
) -> tuple[str, dict]:
    """Xếp đường đúng giờ vào một trong ba trạng thái.

    Args:
        runs: Các lần chạy lấy từ API.
        now: Mốc thời gian hiện tại (UTC).
        stale_days: Im lặng quá ngần này ngày thì coi là chết.
        lookback_days: Cửa sổ tra cứu để biết nó ĐÃ TỪNG chạy hay chưa.

    Returns:
        Cặp ``(trạng thái, chi tiết)``.
    """
    stale_before = now - timedelta(days=stale_days)
    lookback_before = now - timedelta(days=lookback_days)

    newest: datetime | None = None
    in_lookback = 0
    in_window = 0

    for run in runs:
        if run.get("event") != DISPATCH_EVENT:
            continue
        raw = str(run.get("run_started_at") or run.get("created_at") or "")
        if not raw:
            continue
        try:
            started = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if started < lookback_before:
            continue
        in_lookback += 1
        if newest is None or started > newest:
            newest = started
        if started >= stale_before:
            in_window += 1

    detail = {
        "lần gọi trong cửa sổ tra cứu": in_lookback,
        "lần gọi gần đây": in_window,
        "lần gọi mới nhất": newest.isoformat() if newest else None,
        "im lặng (ngày)": round((now - newest).total_seconds() / 86400, 2) if newest else None,
    }

    if in_lookback == 0:
        return STATE_NEVER, detail
    if in_window > 0:
        return STATE_ALIVE, detail
    return STATE_DEAD, detail


def report(state: str, detail: dict, *, stale_days: int) -> str:
    """Dựng thông điệp cho log của Actions.

    Args:
        state: Trạng thái từ :func:`classify`.
        detail: Chi tiết kèm theo.
        stale_days: Ngưỡng im lặng đã dùng.

    Returns:
        Chuỗi nhiều dòng.
    """
    lines = [f"Đường đúng giờ ({WORKFLOW} ← {DISPATCH_EVENT}): {state}"]
    for key, value in detail.items():
        lines.append(f"  {key}: {value if value is not None else '—'}")

    if state == STATE_NEVER:
        lines += [
            "",
            "Bộ hẹn giờ ngoài CHƯA từng gọi vào kho này. Lưới cron vẫn chạy, nên",
            "dữ liệu vẫn về — chỉ là muộn khoảng 11,6 % số ngày.",
            "Các bước dựng: documentation/operations/on-time-trigger.md mục 4.",
        ]
    elif state == STATE_DEAD:
        lines += [
            "",
            f"Bộ hẹn giờ ngoài TỪNG chạy nhưng đã im lặng quá {stale_days} ngày.",
            "Nguyên nhân hay gặp nhất: fine-grained PAT hết hạn (mặc định 90 ngày).",
            "Lưới cron đang che triệu chứng — dữ liệu vẫn về nên không có gì khác đỏ.",
            "Kiểm token bằng bước 2 trong documentation/operations/on-time-trigger.md.",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Điểm vào dòng lệnh.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        0 khi đang chạy hoặc chưa dựng, 1 khi đã chết.
    """
    parser = argparse.ArgumentParser(description="Kiểm đường chạy đúng giờ còn sống không.")
    parser.add_argument("--repository", default=os.environ.get("REPOSITORY", ""))
    parser.add_argument("--stale-days", type=int, default=3)
    parser.add_argument("--lookback-days", type=int, default=45)
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN", "")
    if not args.repository or not token:
        print("Thiếu REPOSITORY hoặc GH_TOKEN — bỏ qua phép kiểm đường đúng giờ.")
        return 0

    try:
        runs = fetch_runs(args.repository, token)
    except RuntimeError as exc:
        # Không gọi được API là sự cố của phép kiểm, không phải bằng chứng
        # rằng đường đúng giờ đã chết. Báo rồi thoát êm.
        print(f"Không kiểm được đường đúng giờ: {exc}")
        return 0

    state, detail = classify(
        runs,
        now=datetime.now(UTC),
        stale_days=args.stale_days,
        lookback_days=args.lookback_days,
    )
    print(report(state, detail, stale_days=args.stale_days))
    return 1 if state == STATE_DEAD else 0


if __name__ == "__main__":
    sys.exit(main())
