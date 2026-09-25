# VLA — Chỉ dẫn cho Claude

## Ngôn ngữ

Mọi trao đổi với chủ dự án bằng **tiếng Việt**. Docstring và chú thích trong
mã nguồn cũng tiếng Việt.

## Bảo mật — tuyệt đối

KHÔNG BAO GIỜ hỏi, nhận, hay xử lý GitHub PAT của chủ dự án. Token chỉ được
đưa vào terminal của họ và cron-job.org, không đi qua phiên làm việc này.

## Khung ứng dụng

Mọi trang đi qua `page_output.write_page`, và **chỉ ở đó** khung dùng chung
được bọc vào (`_attach_shell` -> `app_shell.wrap_page`). Đừng chép khung vào
từng trình dựng: chép là để chúng trôi khỏi nhau.

    src/app_shell.py              dựng HTML: dải biểu tượng, dải chi tiết, thanh trên
    src/templates/app_shell.css   hình học và màu, theo số đo trang tham chiếu
    src/assets/app-shell.js       thu/mở, đổi nhóm, tìm, đổi chế độ màu

Điều hướng lấy nguyên từ `ui_theme.SITE_NAV` — 7 nhóm, 32 mục. Thêm mục thì
thêm ở đó, không thêm ở `app_shell.py`.

**Tiền tố lớp phải là `app-`, không phải `vla-`.** Phép kiểm riêng tư
`test_no_page_spells_out_where_the_data_lives` cấm chuỗi `vla` trong mọi tệp
xuất bản, vì nó xuất hiện trong đường dẫn GitHub Pages của kho.

Số đo phải giữ (`test_every_page_pins_the_measured_shell_geometry` canh):
dải biểu tượng 80px, dải chi tiết 240px, thanh trên 80px, bo 8px. Và dải chi
tiết **phủ lên** nội dung — `margin-left` của `.app-main` không đổi khi mở.

**Bọc khung phải LUỸ ĐẲNG và phải SỬA được trang đã bọc chồng.**
`docs/live.html` là trang duy nhất viết tay, nên mỗi lượt pipeline đọc lại
chính bản đã có khung. Ngày 24-09 nó dày lên 11 lớp vì `ui_theme.dock()` trả
`<nav>` KÈM một `<script>`: gỡ nav mà sót script thì đuôi khung không còn ở
cuối thân trang và bước bóc bỏ cuộc. `wrap_page` nay gỡ cả hai, và
`test_a_page_nested_the_way_the_pipeline_nested_live_is_repaired` dựng lại
đúng hình dạng ấy. Job `verify-published-pages` trong `update-data.yml` chạy
các phép kiểm bất biến trang trên mỗi commit của pipeline.

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

### Ngôn ngữ thị giác — lấy từ trang tham chiếu, ĐÃ ĐO

Bảng màu và hiệu ứng lấy theo trang mẫu chủ dự án chọn (một chủ đề thương mại
dựng trên Bootstrap 5). Ta KHÔNG bê tệp của họ về — kho này viết CSS tay,
không framework — mà đọc ngôn ngữ thị giác rồi tự viết. Proxy môi trường phát
triển chặn trang đó, nên đọc qua runner Actions:
`.github/workflows/inspect-reference-design.yml`.

    nền           --solitude-blue #f0f4fd -> --selago #eaedff
    nhấn          --base-color #2946f3, --majorelle-blue #724ade
    bóng          luôn đen 8%: 0 0 10px / 0 0 25px / 0 20px 60px
    bo góc        16px cho thẻ, 24px cho dải tiêu đề, 50px cho viên thuốc
    nhịp          .3s; đường cong cubic-bezier(.12,0,.39,0) và (.37,0,.63,1)
    quầng sáng    radial-gradient thay cho phần tử có filter:blur(20-30px)

**KHÔNG lấy nguyên mọi mã màu của họ.** Màu chữ mờ `--medium-gray #717580` của
trang mẫu chỉ đạt **3,96:1** trên nền `#eaedff` — trượt AA. Lấy sắc độ của họ,
còn độ đậm thì phải đo lại. Cùng lý do với `--green #2ebb79` (2,24:1),
`--golden-yellow #fd961e` (1,99:1) và `--red #dc3131` (4,21:1): chúng là màu
TÔ, không phải màu CHỮ.

Đổi bảng màu thì đổi ở **`src/ui_theme.py`** (token dùng chung) và
**`src/templates/ui_visual_system.css`** (lớp skin). Bốn phép kiểm canh:

- `test_every_text_token_reaches_aa_on_every_surface_it_sits_on` — mọi token
  chữ trên mọi bề mặt, cả ba khối màu.
- `test_both_dark_blocks_declare_the_same_tokens` — `@media
  prefers-color-scheme` và `[data-ui-theme="dark"]` phải trùng nhau.
- `test_the_three_copies_of_the_page_background_agree` và
  `test_the_first_frame_paints_the_background_from_tokens_not_a_copy` — màu nền
  từng có BỐN bản sao (`ui_theme`, module sinh ra, bản dự phòng trong
  `css_links`, và một chuỗi ghim trong `scripts/extract_critical_css.py`).
- `PAGE_GROUND` / `BRAND_RAMP` trong `tests/test_ui_design_system.py` là HỢP
  ĐỒNG: mọi chủ sở hữu style phải khai cùng một nền và cùng một dốc nhấn.

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
- **Không cống HTML, trên TOÀN kho.** Mọi mã dựng DOM đi bằng `createElement`
  + `textContent`. Ba hàm dùng chung ở đầu `src/templates/stat_pages.js` —
  `mk`, `put`, `fill` — là lối duy nhất; `frequency_bento.js` dùng lại chúng
  vì cả hai tệp nằm trong CÙNG một thẻ `<script>`.

  Trong `mk(tag, attrs, kids)`, thứ tự khoá của `attrs` LÀ thứ tự thuộc tính
  in ra, và giá trị rỗng thì bỏ hẳn thuộc tính. Hai quy ước ấy không phải
  thẩm mỹ: chúng giữ cho `outerHTML` sau khi dựng trùng từng byte với bản
  chuỗi cũ, tức phép so DOM trước/sau là phép so thật.

  Nợ này TỪNG có: 15 chỗ trong `stat_pages.js` và `frequency_bento.js`, và
  phép kiểm khi ấy chỉ soi ba đường dẫn nên không thi hành được luật. Nay
  `test_nothing_published_to_the_browser_uses_an_untrusted_html_dom_sink` quét
  mọi `src/**/*.js`, `src/**/*.py`, `docs/**/*.html` VÀ `docs/**/*.js`, còn
  `test_the_dom_sink_rule_itself_catches_a_sink` ghim chính luật trên mẫu dựng
  sẵn để một lần `rglob` hỏng không thu tập quét về rỗng. Luật cấm cả việc
  NHẮC TÊN cống trong chú thích — viết "gán chuỗi HTML" thay vì gọi tên.

  `docs/**/*.js` phải khai riêng, không suy ra được từ `src`: năm tệp trong
  `docs/assets/` (`live-board.js`, `matrix-virt.js`, `ui-dock.js`,
  `apply-data-styles.js`, `css-async.js`) KHÔNG có bản nguồn nào dưới `src`
  mà trang sinh ra vẫn nạp chúng.
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

Cổng của mô hình xếp chồng (`meta_predictor.quality_gate`) cùng tinh thần:
phải thắng CẢ tổ hợp tuyến tính hiệu chỉnh LẪN dự báo hằng số (Đặc Biệt 1/100,
LOTO tần suất của các ngày trước lát thẩm định). Ngày 25-09-2026 tổ hợp tuyến
tính làm nhọn xác suất (a=4,89) và thua cả hằng số, nên một mô hình không hơn
hằng số (+0,0086%) vẫn "thắng 46%" và được trộn vào production. Thắng một đối
thủ hỏng không chứng minh được gì.

## Chất lượng mô hình — chấm thứ đã CÔNG BỐ

Trang Chất lượng mô hình và bộ theo dõi `src/skill_monitor.py` chấm chính
vector xác suất đã công bố trước kỳ quay
(`data/predict/predict_next_<mode>_all_<ngày>.csv`) với kết quả quay thật.
Bản dựng lại từ `data/history/pred_<mode>.csv` bỏ qua hiệu chỉnh và tầng xếp
chồng — tức chấm một mô hình KHÁC — nên chỉ dùng khi chưa đủ `MIN_DAYS` kỳ.

`skill_monitor` chạy trong job `verify-published-pages` trên mỗi commit của
pipeline và làm lượt đỏ khi kỹ năng ngoài mẫu rời vùng 0 theo HƯỚNG NÀO CŨNG
VẬY (z=3, cửa sổ 60 kỳ). Kỳ quay đã kiểm là ngẫu nhiên: tệ hơn là hồi quy,
tốt hơn thì phải kiểm lại trước khi tin. Đừng "sửa" báo động ấy bằng cách nới
ngưỡng.

`cleanup_artifacts` xoá artifact quá 45 ngày, nên kỹ năng từng kỳ được ghi
vào sổ cái `data/model_quality/published_skill.csv` TRƯỚC khi dọn (lần ghi đầu
giữ nguyên, không bị đè). Đừng xoá sổ ấy: nó là chuỗi đánh giá duy nhất dài
hơn hạn giữ artifact.

## Kỷ luật kiểm thử

Phép kiểm phải ĐỎ khi hành vi nó đặt tên bị đảo. Mỗi phép kiểm mới phải được
thử bằng đột biến — đổi đúng thứ nó canh và xác nhận nó đỏ. Một phép kiểm
quét qua tập rỗng là phép kiểm không thể đỏ: khi tập có thể rỗng, ghim chính
LUẬT trên dữ liệu dựng sẵn.

Chạy bộ kiểm: `PYTHONPATH=src python3 -m pytest tests -q`

Khối `run:` của workflow là MÃ, không phải văn bản:
`tests/test_workflow_shell_behaviour.py` chạy nguyên khối lấy từ YAML bằng
đúng lệnh shell của GitHub, chỉ thay đồng hồ, lệnh ngủ, nguồn và lệnh đẩy.
Soi chuỗi trong YAML không thấy được lỗi hệ bát phân của `$(date +%H)` hay
một vòng thử lại tự kẹt giữa rebase — cả hai đã xảy ra thật.

Bộ kiểm hiện **xanh hết: 2 124 phép kiểm**. Bốn kịch bản chốt phát hành
(`release_check.sh`, `domain_challenger_check.sh`, `number_integrity_check.sh`,
`research_release_check.sh`) cũng xanh. Đỏ một phép kiểm nghĩa là thay đổi của
bạn làm đỏ nó — không có sẵn phép kiểm đỏ nào để đổ lỗi.
