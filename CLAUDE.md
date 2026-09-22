# VLA — Chỉ dẫn cho Claude

## Ngôn ngữ

Mọi trao đổi với chủ dự án bằng **tiếng Việt**. Docstring và chú thích trong
mã nguồn cũng tiếng Việt.

## Bảo mật — tuyệt đối

KHÔNG BAO GIỜ hỏi, nhận, hay xử lý GitHub PAT của chủ dự án. Token chỉ được
đưa vào terminal của họ và cron-job.org, không đi qua phiên làm việc này.

## Giao diện — trạng thái hiện tại

Giao diện đang chạy là **giao diện cũ**, đã được khôi phục từ git history sau
khi bản "Master Design System" bị gỡ theo yêu cầu của chủ dự án. Mười hai
trình dựng rời (`build_docs`, `build_docs_ml`, `build_dashboard`,
`build_model_quality`, `build_markdown_dashboard_v3`,
`build_statistics_dashboard`, `build_landing_page`, `build_fun_prediction`,
`build_research_lab`, `build_stat_pages`, `build_traditional_results`) sinh
ra 29 trang trong `docs/`, gọi từ khối `if not args.skip_docs` của
`src/pipeline.py`.

Đọc trước khi sửa frontend:

    documentation/architecture/ui-design-system.md

Stylesheet chuẩn là **`assets/ui.css`**. `assets/vla.css` là tên đã nghỉ;
`tests/test_published_ui_contract.py` làm đỏ trang nào còn trỏ vào nó.

`docs/ui-ux/VLA_MASTER_UIUX_SPEC.md` là bản prompt thiết kế của chủ dự án,
giữ lại để tham chiếu. Nó **chưa có hiệu lực** — tầng trình bày nó mô tả đã
bị gỡ. Đừng coi nó là luật của kho cho tới khi chủ dự án nói bắt đầu lại.

Thứ tự dựng có ràng buộc thật, không phải quy ước: `build_docs.py` và
`build_landing_page.py` cùng ghi `docs/index.html`, và bản của landing là bản
đúng; `build_fun_prediction.py` chèn bảng vào `docs/index.html` nên phải chạy
SAU landing; `build_stat_pages.py` nhúng lịch sử nên phải chạy sau khi dữ
liệu đã chốt.

Giữ nguyên các phép tính thống kê, dữ liệu lịch sử, mô hình học máy và hợp
đồng dữ liệu đang có.

Luôn soi trang đã render thật và chạy các phép kiểm liên quan TRƯỚC khi nói
là xong.

## Ràng buộc kỹ thuật đã đo, không phải gợi ý

- **CSS viết tay**, không Tailwind, không framework JS. Kho không có
  `package.json` và GitHub Pages phục vụ tệp tĩnh từ `docs/`.
- **Nợ đã đo — `.innerHTML`.** 14 trang thống kê xuất bản dùng `.innerHTML`.
  Nguồn là hai tệp kịch bản `src/templates/stat_pages.js` và
  `src/templates/frequency_bento.js`, không phải trình dựng Python.
  `test_static_page_builders_do_not_use_untrusted_html_dom_sinks` XANH nhưng
  chỉ soi ba đường dẫn: `build_landing_page.py`, `build_statistics_dashboard.py`
  và `docs/live.html` — nó KHÔNG phủ hai tệp kia, nên luật không được thi hành
  trên toàn kho. Mã MỚI phải dùng `createElement` + `textContent`; đừng thêm
  chỗ vi phạm mới.
- **Không vẽ danh tính nguồn dữ liệu ra trình duyệt.** Hai phép kiểm canh:
  `test_no_page_spells_out_where_the_data_lives` (mọi trang) và
  `test_the_live_page_never_renders_a_source_field` (trang live).
- **Chỉ `Content-Security-Policy` được phép chứa tên host thật.** Phép kiểm
  `test_the_only_place_a_real_host_may_appear_is_the_policy_header`. Lưu ý
  không có phép kiểm nào bảo đảm MỌI trang đều khai CSP — đừng nói là có.
- **`frame-ancestors` bị bỏ qua trong `<meta>`.** Nó chỉ có hiệu lực ở HTTP
  header, và GitHub Pages không đặt được header.
- **Giữ `docs/.nojekyll`.** Thiếu nó, Jekyll ăn mất mọi tệp bắt đầu bằng `_`.
  Chưa có phép kiểm nào canh việc này.
- **Không thêm workflow nào xuất bản Pages từ GỐC KHO.** `static.yml` từng
  làm thế và thắng cuộc đua deploy với `pages.yml`, khiến site 404.
  `pages.yml` là workflow deploy duy nhất.

## Thuật ngữ hiển thị

Chữ **"Đề"** hiển thị cho người đọc phải viết là **"Đặc Biệt"**. KHÔNG đổi
định danh kỹ thuật: `mode="de"`, `p_de`, `weights_de.json`, `picks_de.json`,
tên cột, tên biến — giữ nguyên hết.

## Trọng số tổ hợp

Đọc trọng số CHỈ qua `ensemble_utils.load_ensemble_weights(data_dir, mode)`.
Hiện xuất xứ CHỈ qua `ensemble_utils.weights_provenance(data_dir, mode)`.
Không tự đọc `weights_<mode>.json` rồi suy ra, và không suy xuất xứ bằng cách
so trọng số với mặc định — phép suy ấy nói sai với một tệp hoàn toàn lành.

Cổng thẩm định ngoài mẫu trong `src/learn_ensemble_weights.py` chỉ đề bạt
vector đã học khi nó thắng **mặc định** trên lát kiểm ngoài mẫu. Mốc so sánh
KHÔNG được là vector đương nhiệm: lần chạy trước đã khớp trên chính những
ngày đó, nên phép so ấy rò rỉ và luôn báo thắng.

## Kỷ luật kiểm thử

Phép kiểm phải ĐỎ khi hành vi nó đặt tên bị đảo. Mỗi phép kiểm mới phải được
thử bằng đột biến — đổi đúng thứ nó canh và xác nhận nó đỏ. Một phép kiểm
quét qua tập rỗng là phép kiểm không thể đỏ: khi tập có thể rỗng, ghim chính
LUẬT trên dữ liệu dựng sẵn.

Chạy bộ kiểm: `PYTHONPATH=src python3 -m pytest tests -q`

Bộ kiểm hiện **xanh hết: 2 175 phép kiểm**. Bốn kịch bản chốt phát hành
(`release_check.sh`, `domain_challenger_check.sh`, `number_integrity_check.sh`,
`research_release_check.sh`) cũng xanh. Đỏ một phép kiểm nghĩa là thay đổi của
bạn làm đỏ nó — không có sẵn phép kiểm đỏ nào để đổ lỗi.
