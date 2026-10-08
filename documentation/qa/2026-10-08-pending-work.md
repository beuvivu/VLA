# Hoàn tất PR và công việc còn dở — 08-10-2026

## Phạm vi

Chủ dự án yêu cầu rà soát các việc/PR còn dang dở, commit và push main.
Điểm bắt đầu là main `5e19d9f0`; sáu PR còn mở là #114–118 và #149.
Giữ các bản sửa giao diện, banner, số đặc biệt và tính thưởng Vietlott đã
triển khai trước lượt này. Không đổi lịch sử sổ dự báo hay chính sách mô hình.

## Các thay đổi đã kiểm

| PR | Nội dung | Điều chỉnh trước khi hợp nhất |
|---|---|---|
| #149 | Worker đọc KV, cron thu thập; API an toàn; ghi sổ nguyên tử; polling live | Bỏ cache phản hồi v1; ẩn lỗi upstream; thử lại bảng thiếu giải; xác thực API dưới mount/root_path; Authorize trong Swagger |
| #114 | Optuna 5 | Kiểm API tuning với seed; không đưa challenger nghiên cứu vào production |
| #115 | SHAP 0.52 | Python 3.11 dùng `>=0.51,<0.52`; Python >=3.12 dùng `>=0.52,<1` |
| #116 | tzdata 2026.4 | Kiểm lịch quay và đối chiếu Asia/Ho_Chi_Minh với bản cũ |
| #117 | NetworkX 3.7 | Python 3.11 dùng `>=3.6.1,<3.7`; Python >=3.12 dùng `>=3.7,<4` |
| #118 | Matplotlib 3.11.2 | Kiểm năm bộ dựng biểu đồ PNG với NumPy/Pandas hiện hành |

Hai nhánh SHAP/NetworkX nguyên trạng không cài được trên Python 3.11 vì
phiên bản mới yêu cầu Python >=3.12. Marker giữ hỗ trợ cả hai phiên bản Python,
không hạ toàn bộ pipeline hoặc bỏ nâng cấp cho môi trường 3.12.

Kiểm menu điện thoại nay cuộn bằng đầu vào người dùng tới đủ 59 liên kết.
Đường dẫn Chromium cố định đã được thay bằng Playwright mặc định, có tùy chọn
executable/args cho môi trường kiểm cục bộ. Browser CI bắt buộc chạy ca này:
thiếu Chromium hoặc khóa cuộn phải làm kiểm thử đỏ. Ca cũ báo sai 7/59 mục
không chạm được vì không cuộn tới chúng; đột biến `overflow-y:hidden` đã xác
nhận ca mới vẫn bắt được menu không cuộn được.

Swagger `/docs` nay có **Authorize** khi đặt `VQE_API_TOKEN`, khai báo HTTP
Bearer cho đúng thao tác được bảo vệ. Kiểm schema chạy đỏ rồi xanh; kiểm
Chromium thực tế đã nhập token, bấm Try it out/Execute và xác nhận đầu mục
Authorization cùng HTTP 200. Không đưa giá trị token vào OpenAPI.

Collector được cấu hình dùng `httpx` ở workflow triển khai và Docker Compose,
theo `SECURITY.md`; đây là phần hoàn tất A7 của bản audit trước. Các module
crawler tùy chọn không được bật mặc định bằng cấu hình triển khai này.

## Bằng chứng kiểm thử

| Phép kiểm | Kết quả cục bộ |
|---|---|
| VLA, Python 3.12.14, cả Chromium cho app shell | 3.278 passed, 2 skipped; 438,67 giây |
| Engine Vietlott sau bản sửa Swagger | 436 passed, 3 skipped (XGBoost/curl tùy chọn, DuckDB CLI); 150,13 giây |
| JavaScript frontend | 154 passed, 0 skipped |
| App shell riêng | 163 passed, gồm cuộn menu dài trên điện thoại |
| Worker/ghi sổ/handler/setup liên quan | 42 passed |
| Xác thực API | 36 passed |
| Swagger Chromium thật | Authorize → Try it out gửi Bearer → HTTP 200 |
| Ruff và compileall | Qua cổng lỗi Python của VLA; toàn bộ Ruff engine qua |
| Release gate sau pytest/lint | Exit 0, đủ cổng nguồn/dữ liệu/model/build/production audit |
| Domain challenger | Exit 0; hai chế độ không được promote khi chưa vượt gate |
| Number/pair/Excel integrity | Exit 0, bảo toàn 114.183 ô giải và số 0 đầu |
| Research release gate | Exit 0, giữ research-only và kiểm artifact/trang |
| Resolver toàn bộ requirements, wheel Python 3.11 | Qua; chọn SHAP 0.51 và NetworkX 3.6.1 |
| Resolver toàn bộ requirements, wheel Python 3.12 | Qua; chọn SHAP 0.52 và NetworkX 3.7 |

Hai ca bị bỏ qua là nhóm đánh dấu cặp có Chromium ghim ở đường dẫn khác và
ca đối chiếu PDF vùng chưa có Chromium mặc định. Browser CI có các cổng
đánh dấu và bảng kết quả riêng; không tính hai skip thành bằng chứng đạt.

Máy kiểm cục bộ có Python 3.12, chưa có runtime 3.11; resolver 3.11 chỉ chứng
minh khả năng cài các wheel. CI trên main dùng Python 3.11 để kiểm cả runtime.
Các cổng phát hành được chạy trong bản sao riêng để không ghi đè dữ liệu,
model hoặc trang đã xuất trong workspace. Phần pytest/lint của release gate
dùng kết quả toàn bộ suite ở trên; các bước còn lại chạy nguyên từ script.

## Lượt cập nhật Vietlott đã báo đỏ

Run `37786019322` đã qua cập nhật, dựng trang và lưu dữ liệu. Bước báo lỗi
cuối cùng phát hiện Bingo18 không tăng mã kỳ trong giờ bán, nên run đỏ.
Artifact trạng thái cho thấy kỳ `190304`, lần thấy kỳ mới lúc 19:50, kiểm lại
lúc 20:40 ngày 08-10 theo giờ Việt Nam. Đây là cảnh báo nguồn trễ; không được
xóa cảnh báo hoặc bịa thời gian quay để biến run thành xanh.

Keno/Bingo18 đang có dữ liệu `date_only` từ nguồn dự phòng. Chúng vẫn là
tham khảo, chưa đủ bằng chứng thời gian để dùng cho chấm dự báo nội ngày.
Giữ trạng thái chưa xác minh; dữ liệu đầy đủ của các sản phẩm khác tiếp tục
được lưu khi một nguồn chưa sẵn sàng.

## Những đề xuất chưa phải việc triển khai đã bắt đầu

Các mục A10 (gom Wilson/BH), A11 (CSP hash), A13 (retry dashboard push) trong
audit gốc là đề xuất, không phải bản vá hoặc PR đang dở. Tương tự, lộ trình
registry/OOS/cross-validation Vietlott chưa được áp dụng hàng loạt trong lượt
này. Các thay đổi ấy cần phạm vi kiểm riêng để giữ hành vi thống kê hiện có.
Optuna 5 đổi mặc định TPE trong module nghiên cứu; lời gọi hiện tại đã được
smoke test, nhưng không đồng nghĩa đường tuning cho kết quả giống Optuna 4.

## Tích hợp và triển khai

Review tổng thể không thấy Critical; một Important về Swagger đã được sửa
bằng RED→GREEN và chạy lại full engine. Review không thay thế kiểm triển khai.

Sáu PR #114, #115, #116, #117, #118 và #149 đã được hợp nhất bằng merge
commit và head SHA đã kiểm. Xung đột requirements được hòa giải bằng cách
hợp nhất main vào nhánh SHAP/NetworkX, giữ Optuna 5 và marker Python.
Không force-push main; giữ các commit dữ liệu tự động. CI/Pages của source
commit cuối được đối chiếu riêng sau khi đẩy phần CI/vận hành bổ sung.

## Quyết định phạm vi và ghi chú nhỏ

- Chạy phần release sau suite/lint đã qua trong bản sao riêng để giữ dữ liệu
  production. Nếu trích script sai có thể bỏ một cổng; CI cuối chạy script
  nguyên bản để đối chiếu.
- Giữ các merge tới sau review tổng thể; chi phí là tích hợp muộn hơn.
- Giữ A10/A11/A13 và roadmap nghiên cứu thành phạm vi riêng; chi phí là trì
  các cải tiến đó, tránh đổi thống kê/CSP hàng loạt khi chốt PR hiện tại.
- Rate limit/hàng đợi cho GET tính nặng chưa đổi; API mặc định loopback và
  lệnh ghi đã được bảo vệ. Nếu mở API ra mạng, sức chịu tải cần phạm vi riêng.
- CI/Pages/cron sau xuất bản được kiểm riêng bằng SHA cuối; không suy diễn
  từ checkout. Nếu bỏ qua bước này, bằng chứng cục bộ không đủ cho triển khai.
- Ghi chú nhỏ chưa đổi: Optuna 5 dùng mặc định TPE mới trong module nghiên cứu;
  chỉ xác nhận API và tính lặp với seed, chưa hứa kết quả giống Optuna 4.
