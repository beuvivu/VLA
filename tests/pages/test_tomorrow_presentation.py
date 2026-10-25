"""Tra cứu hôm sau phải giải thích đúng phép đối chiếu lịch sử."""
import json
from web.evidence_catalog import registry


def test_tomorrow_evidence_describes_calendar_successor_not_gap_ranking():
    text=json.dumps(registry('giai-db-ngay-mai.html'),ensure_ascii=False)
    assert 'ngày lịch kế tiếp' in text
    assert 'cùng hai số cuối' in text
    assert 'dựng từ chu kỳ và tần suất' not in text
