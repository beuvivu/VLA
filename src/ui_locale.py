"""Từ điển Việt hóa dùng chung cho lớp trình bày.

Tên cột, khóa JSON và định danh mô hình vẫn giữ nguyên để bảo toàn hợp đồng
dữ liệu. Chỉ nhãn hiển thị cho người dùng được chuyển sang tiếng Việt tại
biên dựng báo cáo/trang web.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MODE_LABELS = {
    "loto": "Lô tô",
    "de": "Đặc Biệt",
    "both": "Cả hai",
}

PATH_KIND_LABELS = {
    "active": "Đang chạy",
    "stable": "Ổn định",
}

PERIOD_LABELS = {
    "day": "ngày",
    "week": "tuần",
    "month": "tháng",
    "year": "năm",
}

GROUP_LABELS = {
    "head": "Đầu / hàng chục",
    "tail": "Đuôi / hàng đơn vị",
    "total": "Tổng",
    "db_cham": "Chạm ĐB",
    "db_head": "Đầu ĐB",
    "db_tail": "Đuôi ĐB",
    "db_total": "Tổng ĐB",
}

COLUMN_LABELS = {
    "a": "Số A",
    "active_path_count": "Số cầu đang chạy",
    "ai_cau_score": "Điểm AI",
    "ai_evidence": "Bằng chứng AI",
    "ai_ml_signal_score": "Điểm AI/ML",
    "ai_prob_percent": "Xác suất AI (%)",
    "all_groups_final_brier_skill": "Kỹ năng Brier của toàn bộ nhóm",
    "all_groups_final_logloss_skill": "Kỹ năng LogLoss của toàn bộ nhóm",
    "anchor_date": "Ngày neo",
    "avg_hits_per_day": "Số lần trúng trung bình/ngày",
    "avg_per_draw": "Trung bình/kỳ",
    "b": "Số B",
    "base_count": "Cỡ mẫu",
    "base_date": "Ngày gốc",
    "brier": "Brier",
    "calib_start": "Bắt đầu hiệu chỉnh",
    "category": "Nhóm",
    "cau_score": "Điểm cầu",
    "cooccur_days": "Số ngày cùng về",
    "conditional_rate": "Tỷ lệ có điều kiện",
    "confirmation": "Xác nhận",
    "confirmed_groups": "Nhóm đã xác nhận",
    "count": "Số lần",
    "current_gap": "Gan hiện tại",
    "current_streak": "Chuỗi hiện tại",
    "date": "Ngày",
    "days_hit": "Số ngày về",
    "days_hit_7d": "Ngày về trong 7 ngày",
    "days_hit_30d": "Ngày về trong 30 ngày",
    "days_hit_365d": "Ngày về trong 365 ngày",
    "digit_i": "Chữ số A",
    "digit_j": "Chữ số B",
    "draws": "Số kỳ",
    "domain_active": "Challenger miền số đang hoạt động",
    "domain_trust": "Độ tin cậy miền số",
    "evidence": "Bằng chứng",
    "expected_freq": "Tần suất kỳ vọng",
    "explain_text": "Giải thích",
    "feature_groups": "Nhóm đặc trưng",
    "final_brier_skill": "Kỹ năng Brier cuối cùng",
    "final_logloss_skill": "Kỹ năng LogLoss cuối cùng",
    "fold": "Lát kiểm định",
    "folds": "Các lát kiểm định",
    "freq": "Tần suất",
    "freq_7d": "Tần suất 7 ngày",
    "freq_30d": "Tần suất 30 ngày",
    "freq_365d": "Tần suất 365 ngày",
    "freq_current_year": "Tần suất năm nay",
    "generated_at": "Tạo lúc",
    "group_type": "Loại nhóm",
    "group_value": "Giá trị nhóm",
    "hit_any_days": "Ngày có ít nhất một lần trúng",
    "hit_any_rate": "Tỷ lệ ngày trúng",
    "hit_count": "Số lần về",
    "hit_rate": "Tỷ lệ ngày về",
    "hits": "Số lần trúng",
    "is_bong_prev_special": "Bóng ĐB trước",
    "is_reverse_prev_special": "Đảo ĐB trước",
    "lag_days": "Độ trễ (ngày)",
    "last_seen": "Lần về gần nhất",
    "logloss": "LogLoss",
    "loto_occ_today": "Số lần lô tô hôm nay",
    "max_current_streak": "Chuỗi hiện tại dài nhất",
    "max_gap": "Gan lớn nhất",
    "max_path_p_mean": "Xác suất cầu lớn nhất",
    "max_streak": "Chuỗi dài nhất",
    "mean_gap": "Gan trung bình",
    "mean_brier_skill": "Kỹ năng Brier trung bình",
    "mean_logloss_skill": "Kỹ năng LogLoss trung bình",
    "ml_prob": "Xác suất ML",
    "ml_prob_raw": "Xác suất ML thô",
    "mode": "Loại",
    "next_loto": "Lô tô ngày sau",
    "number": "Số",
    "number_str": "Bộ số",
    "p_mean": "Tỷ lệ lịch sử",
    "pair": "Cặp",
    "path_line": "Đường cầu",
    "path_lines_count": "Số đường cầu",
    "path_support": "Mức hỗ trợ cầu gốc",
    "period_key": "Mốc kỳ",
    "period_kind": "Kỳ",
    "policy": "Chính sách",
    "pos_i_label": "Vị trí A",
    "pos_j_label": "Vị trí B",
    "predict_for_date": "Ngày dự báo",
    "positive_skill_threshold": "Ngưỡng kỹ năng dương",
    "prev_loto": "Lô tô ngày trước",
    "prev_special_2d": "ĐB ngày trước",
    "primary_reason": "Nhận định chính",
    "prob": "Xác suất",
    "prob_percent": "Xác suất (%)",
    "production_feature_count": "Số đặc trưng production",
    "production_selected_groups": "Nhóm được chọn cho production",
    "rank_in_period": "Hạng trong kỳ",
    "rank_in_period_group": "Hạng trong nhóm",
    "rate": "Tỷ lệ",
    "reason": "Căn cứ",
    "reason_1": "Lý do 1",
    "reason_2": "Lý do 2",
    "reason_3": "Lý do 3",
    "reverse_hit_today": "Cặp lộn chạm hôm nay",
    "rhythm_pressure": "Áp lực nhịp",
    "rule_kind": "Loại cầu",
    "rule_score": "Điểm cầu",
    "same_weekday_freq_364": "Tần suất cùng thứ (364 ngày)",
    "scope_label": "Phạm vi",
    "score_band": "Mức điểm",
    "schema_version": "Phiên bản lược đồ",
    "screen_summary": "Tóm tắt sàng lọc",
    "screened_groups": "Nhóm đã sàng lọc",
    "selected_features": "Đặc trưng đã chọn",
    "snapshot_as_of": "Cập nhật đến",
    "stable_path_count": "Số cầu ổn định",
    "target": "Trúng",
    "target_date": "Ngày mục tiêu",
    "top_k": "Số lượng chọn (K)",
    "top_path_score": "Điểm cầu cao nhất",
    "trend_7_vs_30": "Xu hướng 7/30 ngày",
    "trials": "Cỡ mẫu",
    "val_brier": "Brier kiểm định",
    "val_logloss": "LogLoss kiểm định",
    "val_start": "Bắt đầu kiểm định",
    "validation_days": "Số ngày kiểm định",
    "val_end_exclusive": "Kết thúc kiểm định (không gồm)",
    "weights": "Trọng số",
    "w_active": "Trọng số cầu đang chạy",
    "w_ml": "Trọng số ML",
    "w_stable": "Trọng số cầu ổn định",
    "note": "Ghi chú",
    "week_key": "Tuần",
    "month_key": "Tháng",
    "z_score": "Điểm chuẩn hóa Z",
    "z_score_current_year": "Điểm Z năm nay",
}


VALUE_LABELS = {
    **MODE_LABELS,
    **PERIOD_LABELS,
    "active": "Đang chạy",
    "stable": "Ổn định",
    "high": "Cao",
    "medium": "Trung bình",
    "low": "Thấp",
    "pass": "Đạt",
    "passed": "Đạt",
    "fail": "Không đạt",
    "failed": "Không đạt",
    "review": "Cần xem xét",
    "baseline": "Mô hình nền",
    "screen": "Sàng lọc",
    "confirmation_diagnostic": "Kiểm tra xác nhận",
    "research_only": "Chỉ phục vụ nghiên cứu",
    "concat": "Ghép xuôi",
    "reverse_concat": "Ghép đảo",
    "reverse_pair": "Cặp lộn",
    "partner": "Cặp đối tác",
    "cap_50": "Cặp 50",
    "bo": "Bộ",
    "bong": "Bóng",
    "cham": "Chạm",
    "tong": "Tổng",
    "true": "Có",
    "false": "Không",
}

STRATEGY_LABELS = {
    "Cold 30d top5": "5 số lạnh nhất trong 30 ngày",
    "Gan top5": "5 số gan nhất",
    "Hot 30d top5": "5 số nóng nhất trong 30 ngày",
    "Hot 90d top5": "5 số nóng nhất trong 90 ngày",
    "Vị trí head-tail plurality": "Đồng thuận vị trí đầu–đuôi",
    "Vị trí tail-tail plurality": "Đồng thuận vị trí đuôi–đuôi",
}


def column_label(column: str) -> str:
    """Trả về nhãn tiếng Việt nhưng không làm thay đổi tên cột gốc."""

    return COLUMN_LABELS.get(column, column)


def mode_label(mode: object) -> str:
    return MODE_LABELS.get(str(mode).lower(), str(mode))


def path_kind_label(kind: object) -> str:
    return PATH_KIND_LABELS.get(str(kind).lower(), str(kind))


def value_label(value: Any) -> Any:
    """Việt hóa giá trị phân loại đơn; giữ nguyên số và giá trị chưa biết."""

    if not isinstance(value, str):
        return value
    return VALUE_LABELS.get(value.strip().lower(), value)


def strategy_label(value: object) -> str:
    return STRATEGY_LABELS.get(str(value), str(value))


def localize_mapping_for_display(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Tạo bản sao đã Việt hóa để hiển thị; không sửa artifact nguồn."""

    localized: dict[str, Any] = {}
    for key, value in payload.items():
        label = column_label(str(key))
        if isinstance(value, Mapping):
            localized[label] = localize_mapping_for_display(value)
        elif isinstance(value, list):
            localized[label] = [
                localize_mapping_for_display(item)
                if isinstance(item, Mapping)
                else value_label(item)
                for item in value
            ]
        else:
            localized[label] = value_label(value)
    return localized
