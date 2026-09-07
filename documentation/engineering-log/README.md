# Nhật ký kỹ thuật

Sổ tay tích luỹ của kho: vì sao hệ thống có hình dạng như hiện tại, đã hỏng
những gì, và cách sửa nào đã được kiểm chứng.

**Thư mục này không liên quan gì tới ứng dụng ChatGPT Codex.** Trước đây nó
tên là `.codex/`, và cái tên đó khiến người ta tưởng nó là cấu hình của con
bot review — nên đã đổi. Không mã nào đọc thư mục này; nó dành cho người đọc.

| Tệp | Nội dung |
| --- | --- |
| `REPAIR_RULES.md` | Quy tắc chung khi sửa lỗi trong kho này |
| `REPAIR_MEMORY.md` | Các mẫu sửa lỗi đã kiểm chứng, kèm bối cảnh |
| `KNOWN_FAILURES.md` | Lỗi đã biết và trạng thái hiện tại |
| `RESEARCH_MEMORY.md` | Kết quả nghiên cứu đã đo, gồm cả hướng đã thử và thất bại |
| `TUNING_HISTORY.md` | Lịch sử tinh chỉnh tham số và lý do từng lần |
| `incidents/` | Hồ sơ sự cố theo mẫu Observe / Reproduce / Root cause / Fix / Regression test |

## Vì sao giữ lại

Phần đắt nhất của một sự cố không phải bản vá mà là quá trình chẩn đoán. Ghi
lại thì lần sau đọc mất năm phút; không ghi thì phải dò lại từ đầu.

Ví dụ cụ thể: `incidents/INC-0003-live-refresh-delay.md` giải thích vì sao có
tín hiệu `reason=live_verified` trong khâu bàn giao live → daily. Cơ chế đó
được dùng lại nguyên vẹn trong `.github/workflows/daily_update.yml`. Không có
hồ sơ này thì dòng mã đó trông như tuỳ tiện.
