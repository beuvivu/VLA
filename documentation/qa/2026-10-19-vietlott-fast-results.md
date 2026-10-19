# Keno/Bingo18 — khắc phục cơ chế đồng bộ ngày 19/10/2026

## Sự cố được xác nhận

Run [39207003570](https://github.com/beuvivu/VLA/actions/runs/39207003570), job `117911915366`:
nguồn trực tiếp trả Cloudflare, NhanAZ timeout, Keno ở 299797, Bingo18 ở 191942, cả hai `not_advancing`.
Artifact `12166372541` giữ cùng trạng thái; bước dựng trang thành công không chứng minh dữ liệu đã tiến.

## Thay đổi

- Dừng challenge kể cả HTTP 200; không giải/vượt xác minh hoặc xoay proxy.
- Ngân sách archive 90 giây độc lập với nguồn trực tiếp 20 giây. Workflow: request 10 giây, 2 retry, sản phẩm 360 giây.
- Đưa đọc/parse seed lớn ra ngoài event loop; ghi nguyên tử được đợi hoàn tất trước khi nhả khóa lúc hủy.
- Gate live Keno/Bingo18 yêu cầu confirmed + valid + provenance official_vietlott, từ chối pending và mirror/snapshot thiếu xác thực.
- Exclusion mới chỉ chứng minh kỳ bỏ qua khi là not_confirmed có URL HTTPS chính thức; không mặc định kỳ thiếu là kỳ loại.
- Không nhảy cursor qua gap; thử nguồn sau để bổ sung gap mới/lịch sử. Dữ liệu mâu thuẫn không ghi đè lịch sử.
- Giữ đoạn liên tục đã xác thực và journal bền khi phần sau lỗi; checkpoint vẫn lưu chẩn đoán và workflow trả lỗi.
- `latest_verified` chỉ phản ánh dòng đã qua cổng nguồn trong lượt hiện tại, không tự chứng nhận cursor lịch sử cũ.

## Kiểm chứng

- 41 ca hồi quy thu thập Keno/Bingo18, gồm shutdown, dữ liệu sai xen dòng hợp lệ, exclusion giả, sửa chính thức và nguồn dự phòng lấp gap.
- Bộ engine đầy đủ: 801 đạt, 4 bỏ qua, 43 subtest đạt (514,88 giây). Có cảnh báo deprecation từ Starlette/httpx.
- Bộ hồi quy và updater/journal trên bản cuối: 95 đạt; riêng file hồi quy: 41 đạt.
- 41 phép kiểm ở repository chủ về layout engine/workflow/tóm tắt trạng thái đạt.
- Ruff `F,B023` và `git diff --check` đạt.
- 21/21 đột biến hành vi trên bản sao tạm bị kiểm thử phát hiện: challenge, deadline/retry, event loop, trust, continuity, exclusion,
  conflict, journal diagnostics, hủy/shutdown, mã thoát CLI, sửa chính thức, ngày VN và giữ phần dữ liệu hợp lệ;
  các kiểm thử tương ứng phải đỏ.
- Rà soát độc lập đã phát hiện và kiểm chứng sửa các nhánh báo thành công sai, hủy khi shutdown,
  exclusion chưa xác thực và dừng fallback trước khi lấp gap lịch sử.

## Probe nguồn thật, vùng tạm — không ghi thêm vào repo

| Sản phẩm | Cursor đã lưu | Mã mới nhất chỉ quan sát từ archive | Dòng archive bị từ chối | Dòng mới nhập | Gap lịch sử còn thiếu |
| --- | ---: | ---: | ---: | ---: | ---: |
| Keno | 299797 | 299835 | 959 | 0 | 119 |
| Bingo18 | 191942 | 191992 | 973 | 0 | 73 |

Archive tải trong khoảng 6 giây mỗi sản phẩm, không timeout trong probe. Nguồn trực tiếp vẫn trả Cloudflare;
archive chứa provenance đăng lại/pending nên không được nhập. Các cursor cũ được bảo toàn, không được gắn nhãn
đã xác thực chính thức. Các con số trên là snapshot của probe, không phải chứng nhận mới nhất theo thời gian thực.

## Điều kiện xác nhận khôi phục

Phải đọc log và artifact của lượt Actions sau khi áp dụng, xác nhận kết quả chính thức được nhận, đối chiếu mã kỳ/ngày/số,
không có gap chưa giải thích và không có pending/mâu thuẫn dùng để tiến cursor. Nếu Cloudflare vẫn chặn và nguồn dự phòng
vẫn pending, trạng thái đúng là lỗi có chẩn đoán, **chưa khôi phục đồng bộ dữ liệu**. Không đổi mã thoát để làm xanh workflow.
