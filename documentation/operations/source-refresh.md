# Làm mới source và tài nguyên xuất bản

Cập nhật: 17-10-2026. Source tại `src/`, trình vận hành tại `scripts/ops/`,
kiểm thử tại `tests/`, tài liệu tại `documentation/`; `docs/` chỉ chứa website.

## Biên xuất trang

Mọi trình dựng vẫn gọi `page_output.write_page`. Biên này bóc tham số `rev`
cũ trước khi sửa/bọc khung, rồi gắn `?rev=<16 ký tự SHA-256>` vào tài nguyên
CSS, JavaScript và JSON cục bộ. Cùng nội dung dùng cùng URL trên mọi trang;
đổi nội dung tự đổi URL, kể cả trong cùng tiến trình. Không sửa thân script,
JSON nhúng, CSS nội tuyến hoặc URL bên ngoài. Không có service worker riêng.

Sau trình dựng cuối, pipeline và cả năm bước đóng gói Pages gọi chung:

```bash
python3 src/web/site_assets.py --refresh docs --check
```

Lệnh kiểm sự tồn tại và phiên bản của tham chiếu tài nguyên, đồng thời chặn
trang có khung `app-main`/`app-header`/`app-rail` bị nhân đôi hoặc thiếu một
thành phần. Sau đó chốt lại mọi
trang, ghi `docs/assets/release.json` chứa băm trang/tài nguyên và mã phát
hành xác định theo nội dung. Thiếu tệp hoặc kiểm tra không khớp thì dừng
đóng gói. Có thể kiểm lại mà không ghi:

```bash
python3 src/web/site_assets.py --root docs --check
```

Manifest mô tả gói trang cụ thể; nó không phải chữ ký số, không xác nhận
kỹ năng dự báo. Job cập nhật một phần chốt manifest ngay trước upload để
không dùng manifest của lượt dựng trước.

Bot dựng trang Vietlott còn chốt trước bước ghi git, rồi stage toàn bộ
`docs/*.html` và `docs/assets`. Nhờ đó commit chứa cả trang mới, URL tài
nguyên và manifest tương ứng. Bước chốt ngay trước upload vẫn được giữ để
kiểm lại ảnh chụp sau khi đồng bộ nhánh.

Ba luồng ghi website (Vietlott, kết quả vùng, phân tích XSMB) dùng
`scripts/ops/push_generated_site.py`. Helper chỉ nhận cây mã đã commit và
sạch, gộp nhánh remote rồi chốt lại gói trang trước khi đẩy fast-forward.
Nếu chỉ `docs/assets/release.json` xung đột, nó tái tạo tệp dẫn xuất này từ
cây mã đã gộp; xung đột HTML, source hoặc dữ liệu vẫn làm job dừng. Manifest
cũng được kiểm lại sau lần gộp không xung đột. Không force-push, không chọn
bỏ nội dung của một bot; số lần thử lại khi remote tiến thêm được giới hạn.

## Dựng lại giao diện từ nguồn chuẩn

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/refresh_navigation.py
```

Lệnh dựng stylesheet, sinh Critical CSS rồi mở tiến trình Python mới để
đồng bộ khung từng trang. Tiến trình mới đọc module Critical CSS vừa sinh;
không tái sử dụng module đã nạp trong lượt trước. Cuối cùng chốt và kiểm gói.
Workflow cập nhật vùng cũng dùng chính lệnh này, không gọi trực tiếp
`app_shell.wrap_page`; HTML, tài nguyên và manifest được ghi cùng commit.
Đuôi khung nhận cả URL script có tham số phiên bản để sửa được trang cũ đã lồng.
Muốn dựng lại cả nội dung thống kê, dùng pipeline theo đúng thứ tự hiện có;
landing phải sau `build_docs`, mô phỏng phải sau landing, thống kê chi tiết
phải sau khi dữ liệu được chốt.

## Phạm vi xóa cache

Cache dẫn xuất Python/pytest/ruff có thể xóa rồi dựng lại; không xóa sổ dự
báo, lịch sử quay, trọng số đã lưu, mô hình hoặc phân phối null nghiên cứu.
Đó là trạng thái và bằng chứng của hệ tự học.

Workflow `cache-purge.yml` chạy thủ công hoặc khi sửa chính workflow/script
bảo trì trên `main`. Script chụp toàn bộ danh sách, kiểm ID rồi DELETE từng
`/actions/caches/{id}`. Sau xóa phải liệt kê lại và xác nhận các ID ban đầu
không còn. Cache mới sinh đồng thời được báo riêng. Lỗi API, dữ liệu hỏng
hoặc xác minh thất bại khiến workflow thất bại; không nuốt lỗi.

Các job engine có thể tạo cache mới phục vụ kỳ sau. Xóa cache không thay
thế việc quản lý phiên bản tài nguyên; URL theo nội dung mới là cơ chế giúp
trình duyệt tải đúng CSS/JavaScript khi website thay đổi.

## Kiểm chứng bắt buộc khi sửa luồng này

- `tests/test_site_assets.py`: băm theo byte, tính lũy đẳng, bảo toàn dữ liệu
  nhúng, tham chiếu ngoài phạm vi, manifest, thiếu tệp và thứ tự pipeline.
- `tests/test_cache_purge.py`, `tests/test_workflows.py`: hợp đồng API,
  phân trang, lỗi mạng, xác minh xóa và phạm vi trigger/quyền workflow.
- `tests/test_vietlott_release_snapshot.py`: chạy shell ghi trang trong kho
  tạm, kiểm manifest từ nội dung đã commit và không để sót thay đổi `docs/`.
- `tests/test_push_generated_site.py`: các bot dùng clone và bare remote
  tạm thật; bảo toàn thay đổi hai phía, chốt manifest sau rebase và chặn
  xung đột ngoài tệp dẫn xuất.
- Bộ kiểm trang đã xuất, JavaScript, và Chromium trên desktop/mobile.
- Sau cập nhật main, kiểm kết quả CI/Pages/cache purge cùng mã phát hành public.
