# Khép công việc vận hành VLA — 10-10-2026

## Trạng thái đầu lượt

Đối chiếu GitHub trực tiếp: không còn PR hoặc issue mở; mọi nhánh remote đã
nằm trong main. PR #150 đã hợp nhất tại `318ec020`; mã nguồn, engine và
CodeQL đều qua CI. Main lúc bắt đầu là `61a1b3f4`, gồm các lần dựng trang
và lưu dữ liệu tự động sau PR. Không chạy lại nghiên cứu adaptive: kết quả
ngoài mẫu chưa chứng minh lợi thế, cấu hình mặc định tiếp tục tắt.

## Lỗi được xử lý

- `Lottery.dump()` ghi trực tiếp CSV/JSON và nhật ký nguồn: lỗi giữa lần ghi
  có thể cắt cụt tệp đang dùng. Tái sử dụng bộ ghi nguyên tử, giữ tên tệp khi
  định dạng CSV để bảo toàn số 0 đầu. Bảo đảm theo từng tệp; đây không phải
  giao dịch nguyên tử trên toàn bộ CSV/JSON/Excel.
- Dashboard Markdown chỉ thử push một lần. Khi main tiến lên, thử lại có
  giới hạn bằng cách dựng và kiểm lại dashboard từ dữ liệu main mới nhất.
- Vietlott đã phát hiện main tiến lên sau push nhưng ném `RuntimeError`
  ngoài nhánh bắt lỗi của vòng retry. Đưa trường hợp đó vào vòng thử lại
  hiện có; không đổi hay ghi lại luật dự báo đã phát.
- XSMT/XSMN công khai và dữ liệu trên main mới nhất là 08-10 trong lúc
  XSMB đã có 09-10. Collector vốn trả thành công ngay cả khi không lấy được
  ngày cần có. Bổ sung kiểm độ mới cho workflow sản xuất và giữ khả năng lưu
  phần dữ liệu hợp lệ khi một miền chưa đồng bộ được.
- Trạng thái Vietlott chỉ nằm trong artifact khó tải khi điều tra. Thêm
  bảng từng sản phẩm vào log và job summary, gồm mã kỳ/ngày, độ mới và cờ
  lỗi. Chỉ in giá trị đã lọc, không in lỗi nguồn tự do hoặc URL/token; thiếu
  trạng thái báo `unavailable`, không đổi điều kiện thành công của updater.

Mốc 18:00 giờ Việt Nam của kiểm độ mới vùng là quy tắc vận hành bảo thủ,
không phải công bố giờ quay: trước mốc đó yêu cầu hôm qua, sau mốc đó yêu
cầu hôm nay; `--end-date` tường minh được ưu tiên. Kiểm đầy đủ 18 giải cho
từng đài đã có, chưa chứng minh không thiếu nguyên một đài so với lịch quay
chính thức. CSV/JSON vùng cũng thay nguyên tử từng tệp.

## Kiểm chứng trước tích hợp

Các lỗi được tái hiện trước sửa và có phép kiểm đột biến. Kiểm Git cục bộ
chạy thật với remote bare, mô phỏng main tiến lên, xung đột dashboard và
remote từ chối push. Kiểm ghi tệp tiêm lỗi giữa lần ghi và tại `os.replace`,
đối chiếu bytes/schema/số 0 đầu và giữ nhật ký nguồn 120 ngày.

Kiểm trực tiếp 12 trang công khai và 12 CSS/JS dùng chung: HTTP 200 và khớp
bytes với bản trong repo. Chromium qua 64 trạng thái Vietlott, 112 trạng
thái bảng thống kê và 8 bố cục dashboard; thêm thao tác menu, bộ lọc, đánh
dấu và bàn phím trên trang chủ/vùng. Những phép kiểm này đánh giá giao diện
đã xuất bản, không biến dữ liệu ngày 08-10 thành dữ liệu mới.

## Bằng chứng vận hành trước bản sửa

| Cổng | Kết quả và bằng chứng |
| --- | --- |
| CI VLA trên source commit PR #150 | [37964939876](https://github.com/beuvivu/VLA/actions/runs/37964939876): thành công |
| CI engine | [37964939871](https://github.com/beuvivu/VLA/actions/runs/37964939871): thành công |
| CodeQL | [37964940168](https://github.com/beuvivu/VLA/actions/runs/37964940168): thành công |
| Nguồn Vietlott | [37964939932](https://github.com/beuvivu/VLA/actions/runs/37964939932): cập nhật trả lỗi; persistence, build, cache và artifact thành công |
| Đồng bộ vùng gần nhất | [37831047202](https://github.com/beuvivu/VLA/actions/runs/37831047202): thành công ngày 08-10, kể cả deploy |
| Review AI PR #150 | [37963201687](https://github.com/beuvivu/VLA/actions/runs/37963201687): hết hạn mức Copilot, HTTP 402; không phải kết luận phát hiện lỗ hổng |

CI nhánh bị hủy tại `46aa9b53` đã có lượt mới `56aa3d56` thành công. Các
lượt XSMB/dự báo bị hủy trước khi có job nằm trong nhóm concurrency dùng
chung; không tính chúng là lỗi assertion hoặc suy diễn rằng dữ liệu đã mất.

## Giới hạn cần giữ rõ

Log nguồn Vietlott xác nhận human challenge ở nguồn chính; có bản dự phòng
bị từ chối vì thiếu số. Không bỏ kiểm hợp lệ hoặc vượt challenge để đổi màu
workflow. Artifact trạng thái tồn tại nhưng đường tải trả HTTP 403 trong
lượt kiểm, nên không khẳng định challenge là nguyên nhân duy nhất của mã
thoát: checkpoint cũ cũng có thể báo `behind_schedule`/`not_advancing`.

Keno/Bingo18 có dữ liệu chỉ xác minh ngày, không đủ giờ từng kỳ để xác nhận
dự báo nội ngày. Giữ nhãn giới hạn trên trang. Wilson helpers khác hợp đồng,
CSP hash và các đề xuất kiến trúc/nghiên cứu mới chưa phải PR triển khai dở;
không gộp chúng vào bản sửa vận hành này. Không tuyên bố kho đã hết mọi lỗi.
