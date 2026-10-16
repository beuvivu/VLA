# Tích hợp bộ tự học đa thuật toán vào Vietlott

## Phạm vi đã được yêu cầu

Tích hợp trực tiếp vào VLA, commit main và cập nhật Pages. Engine vẫn là dự án
tự đủ dưới vietlott/. Không đổi sổ dự báo cũ hoặc giao thức benchmark H đã đăng ký.

## Thiết kế

Đặt bộ mã đã kiểm thử tại vlm.multi_agent. Adapter trong vlm.forecast nối bộ nhớ,
ba chuyên gia và MetaLearner vào MLComponent của các thành phần SetSpec. Các
thành phần chữ số giữ mô hình riêng: không biến số có lặp thành tập không lặp.

Nhóm mới là một chuyên gia cấp trên với bốn phân phối con. Law lưu phân phối
con và trọng số đã nhân đầy đủ; loss cấp trên gộp đúng bốn likelihood bằng
logsumexp. Không chuyển một mixture thành tích các xác suất biên. Power vẫn
chấm joint main/bonus theo hợp đồng Law; bộ nhớ nhóm mới học tập số chính.

MLConfig.multi_agent mặc định False cho caller nghiên cứu cũ. Settings sản xuất
bật ml_multi_agent=True. Cập nhật production nâng cấp checkpoint cũ bằng học lại
từ lịch sử xác thực với cấu hình mới, giữ nguyên ledger và bản issue đầu tiên.
Checkpoint version 4 đọc được version 3 khi chưa bật nhóm mới. Evidence hồi cứu
của nhóm chỉ là chẩn đoán; cổng live family-adjusted hiện có vẫn là nơi duy nhất
chứng nhận và quyết định xác suất deployed của trang/API.

Khi nâng cấp, chấm pending của mô hình cũ trước khi refit; nếu kết quả chưa
đến thì giữ nguyên pending đã issue. Snapshot cũ/rỗng bị từ chối trước nhánh
nâng cấp. Sổ cũ không đổi, điểm số mới nối vào sổ, evidence của chính sách mới
bắt đầu bảo thủ từ 0. Tắt nhóm và refit sẽ xóa tóm tắt công bố cũ của sản phẩm.

Trang đọc báo cáo nhóm mới từ checkpoint đã xác thực, hiển thị trọng số, số kỳ
đã học, nhiệt độ và độ tin cậy live; không in nguồn, đường dẫn hoặc tên host.
Trang được dựng qua page_output.write_page, sử dụng style hiện hành.

Tóm tắt multi-agent-summary.json được ghi nguyên tử và commit cùng sổ dự báo;
trang đọc được các trọng số và cutoff đã xác thực ngay cả khi mất cache ML.
Tóm tắt chỉ là trạng thái học hiện tại, không thay thế phân phối của kỳ đã khóa.
Sau khi khôi phục cache, workflow dựng trang lấy lại tóm tắt từ HEAD để cache
cũ không đè số đo đã commit.

## Kế hoạch thực hiện

1. Ghim baseline và viết test đỏ cho adapter: mixture chính xác, update trước/sau,
   state replay, rollback, nhóm không áp lên DigitSpec và cổng live không bị mở.
2. Đưa bộ mã vào engine; thêm đường đồng bộ dùng cùng tính toán bất biến với API
   async. Adapter giữ state JSON trong checkpoint ML hiện hữu.
3. Nối MLComponent, Settings/CLI/service; lưu thông tin giải thích vào pending
   cùng law để không trình bày trọng số mới như của dự báo cũ.
4. Bổ sung phần hiển thị từ dữ liệu thật; kiểm source privacy và giao diện mobile.
5. Chạy hai suite, lint, browser checks; dựng trang; kiểm diff; commit/push main.
6. Theo dõi Actions và xác minh nội dung public của trang tổng quan/sản phẩm.

## Trọng tâm rà soát

Tổng xác suất toàn bộ tập; số phụ Power; giữ issue cũ khi nâng cấp; cache bị mất;
không trộn chẩn đoán hồi cứu vào bằng chứng live; ngân sách CPU và checkpoint.
