# INC-0003 — Live và mô phỏng cập nhật trễ

Date: 2026-09-04

## Observe

Kết quả live đã được xác minh nhưng dữ liệu chuẩn và bảng mô phỏng có thể vẫn
giữ kỳ cũ đến lượt cron daily kế tiếp.

## Reproduce

Live workflow trước đây chạy lúc 18:04 Việt Nam, trong khi daily chỉ bắt đầu
18:18 và chỉ truyền `ref`, không phân biệt dispatch sau khi live đã hoàn tất.
Một số kiểm tra dashboard vẫn tìm marker tiếng Anh đã bị Việt hóa.

## Root cause

GitHub cron biểu diễn theo UTC; cutoff và lịch fallback không thống nhất. Bàn
giao live→daily thiếu tín hiệu `live_verified`, còn bước dashboard có thể làm
workflow thất bại sau khi dữ liệu đã sẵn sàng.

## Fix

- Centralize clock policy in `src/time_policy.py` (UTC+7, cutoff 18:35).
- Start live at 18:00 VN, poll 15 seconds for up to 60 minutes.
- Dispatch daily with `reason=live_verified`; add watchdog recovery windows.
- Align dashboard assertions and documentation with Vietnamese labels.
- Normalize UTC/UTC+7 timestamps in live snapshots.

## Regression

`284 passed`; focused workflow/live/time-policy tests pass. Ruff binary in the
workspace is currently unusable (segmentation fault), so Python AST compilation
and `git diff --check` were run instead.
