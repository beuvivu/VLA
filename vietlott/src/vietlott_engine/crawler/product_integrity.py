"""Kiểm tra chuyển tiếp mã kỳ, không suy diễn kết quả từ lịch hoặc đồng hồ."""
from __future__ import annotations

import asyncio
import contextvars

from vietlott_engine.core.products import ProductCode, parse_product_rows


def identities(history):  # type: ignore[no-untyped-def]
    return {int(did):(str(day), tuple(int(n) for n in values))
            for did,day,values in zip(history.draw_ids,history.dates,history.values)}


def missing_ranges(ids, excluded=()):  # type: ignore[no-untyped-def]
    """Khoảng hở nội bộ; không coi phần trước mã đầu tiên là đã được chứng minh."""
    ordered=sorted(set(ids) | set(excluded))
    return [[a+1,b-1] for a,b in zip(ordered,ordered[1:]) if b>a+1]


def parse_fast_rows(product, rows, source):  # type: ignore[no-untyped-def]
    """Không để thao tác dedup che hai kết quả khác nhau của cùng mã kỳ."""
    seen, duplicates = {}, set()
    for row in rows:
        try:
            did=int(str(row['id']).lstrip('#'))
            values=tuple(int(n) for n in row['result'])
            value=(str(row['date'])[:10],tuple(sorted(values)) if product==ProductCode.KENO else values)
        except (KeyError,ValueError,TypeError):
            continue  # parse_product_rows sẽ giữ chẩn đoán của dòng sai cấu trúc
        if did in seen and seen[did]!=value:
            duplicates.add(did)
        seen[did]=value
    parsed,rejected=parse_product_rows(product,rows,source)
    return parsed,rejected,sorted(duplicates)


def contiguous_results(known, candidates, excluded):  # type: ignore[no-untyped-def]
    """Chỉ cho cursor tiến qua các kỳ đã có số xác thực hoặc thông báo loại kỳ."""
    last=max(known,default=0)
    latest=max(candidates,default=last)
    anchor=last if known else min(candidates,default=1)-1
    points={i for i in candidates if i>anchor} | {i for i in excluded if anchor<i<=latest}
    gaps=missing_ranges({anchor, *points}) if points else []
    through=gaps[0][0]-1 if gaps else max(last,latest)
    accepted=[{'id':did,'date':day,'result':list(values)}
              for did,(day,values) in sorted(candidates.items()) if did<=through and did not in excluded]
    # Thông báo loại kỳ ngoài khoảng lịch sử không tạo thêm khoảng hở giả.
    first=min(known,default=0)
    repaired=set(known) | {row['id'] for row in accepted if row['id']<=last}
    historical=missing_ranges(repaired, [i for i in excluded if first<=i<=last])
    return accepted, {'cursor_before':last or None, 'contiguous_through':through or None,
                      'latest_observed':max(last,latest) or None, 'missing_ranges':gaps,
                      'historical_missing_ranges':historical}


async def finish_store_write(write):  # type: ignore[no-untyped-def]
    """Ghi nguyên tử ngoài event loop; hủy vẫn đợi thread xong trước khi nhả khóa."""
    # Future executor không nằm trong asyncio.all_tasks(): shutdown chỉ hủy
    # caller, không hủy một task trung gian rồi làm vòng shield quay mãi.
    task=asyncio.get_running_loop().run_in_executor(None,contextvars.copy_context().run,write)
    cancelled=None
    while True:
        try:
            result=await asyncio.shield(task)
            break
        except asyncio.CancelledError as exc:
            if task.cancelled():
                raise
            cancelled=exc
    if cancelled is not None:
        raise cancelled
    return result
