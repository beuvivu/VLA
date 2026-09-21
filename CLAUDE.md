# VLA — Chỉ dẫn cho Claude

## Ngôn ngữ

Mọi trao đổi với chủ dự án bằng **tiếng Việt**. Docstring và chú thích trong
mã nguồn cũng tiếng Việt.

## Bảo mật — tuyệt đối

KHÔNG BAO GIỜ hỏi, nhận, hay xử lý GitHub PAT của chủ dự án. Token chỉ được
đưa vào terminal của họ và cron-job.org, không đi qua phiên làm việc này.

## Giao diện

Trước khi sửa bất kỳ trang frontend nào, đọc:

    docs/ui-ux/VLA_MASTER_UIUX_SPEC.md

Đặc biệt là **mục XXIII** — nó ghi các sự thật đã kiểm chứng của kho và chỗ
nào trong spec hiện không còn đối tượng.

Mọi thi hành giao diện phải tuân Master Design System và các yêu cầu về
responsive, accessibility, chức năng, và QA hình ảnh của spec.

Không dựng lại thiết kế riêng cho một trang theo cách trái với design system
dùng chung.

Giữ nguyên các phép tính thống kê, dữ liệu lịch sử, mô hình học máy và hợp
đồng dữ liệu đang có.

Luôn soi trang đã render thật và chạy các phép kiểm liên quan TRƯỚC khi nói
là xong.

Ghi tiến độ và việc chưa xong vào:

    docs/ui-ux/implementation-progress.md

## Ràng buộc kỹ thuật đã đo, không phải gợi ý

- **CSS viết tay**, không Tailwind, không framework JS. Kho không có
  `package.json` và GitHub Pages phục vụ tệp tĩnh từ `docs/`. Lý do đầy đủ ở
  mục 23.3 của spec.
- **Cấm `.innerHTML`, `insertAdjacentHTML`, `outerHTML`, `document.write`.**
  Phép kiểm `test_nothing_that_emits_markup_uses_an_untrusted_dom_sink` tự dò
  mọi tệp phát sinh thẻ HTML. Thao tác DOM động dùng `createElement` +
  `textContent`.
- **Mọi trang HTML phải khai `Content-Security-Policy`.** Phép kiểm
  `test_every_published_page_declares_a_content_security_policy` làm đỏ trang
  thiếu nó.
- **Không vẽ danh tính nguồn dữ liệu ra trình duyệt.** Phép kiểm
  `test_no_published_page_renders_a_source_field`.
- **Giữ `docs/.nojekyll`.** Thiếu nó, Jekyll ăn mất mọi tệp bắt đầu bằng `_`.

## Thuật ngữ hiển thị

Chữ **"Đề"** hiển thị cho người đọc phải viết là **"Đặc Biệt"**. KHÔNG đổi
định danh kỹ thuật: `mode="de"`, `p_de`, `weights_de.json`, `picks_de.json`,
tên cột, tên biến — giữ nguyên hết.

## Trọng số tổ hợp

Đọc trọng số CHỈ qua `ensemble_utils.load_ensemble_weights(data_dir, mode)`.
Hiện xuất xứ CHỈ qua `ensemble_utils.weights_provenance(data_dir, mode)`.
Không tự đọc `weights_<mode>.json` rồi suy ra, và không suy xuất xứ bằng cách
so trọng số với mặc định — phép suy ấy nói sai với một tệp hoàn toàn lành.

## Kỷ luật kiểm thử

Phép kiểm phải ĐỎ khi hành vi nó đặt tên bị đảo. Mỗi phép kiểm mới phải được
thử bằng đột biến — đổi đúng thứ nó canh và xác nhận nó đỏ. Một phép kiểm
quét qua tập rỗng là phép kiểm không thể đỏ: khi tập có thể rỗng, ghim chính
LUẬT trên dữ liệu dựng sẵn.

Chạy bộ kiểm: `PYTHONPATH=src python3 -m pytest tests -q`
