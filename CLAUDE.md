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
    src/assets/app-shell.js       thu/mở, đổi nhóm, hai tìm kiếm độc lập
    src/assets/app-theme.js       khôi phục/đổi màu, OS và storage sync
    src/app_icons.py              SVG Lucide cho nội dung / global search
    src/nexlink_icons.py          SVG Nexlink gốc cho rail / sidebar / header

Điều hướng lấy nguyên từ `ui_theme.SITE_NAV` — 7 nhóm, 39 mục. Thêm mục thì
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
cuối thân trang và bước bóc bỏ cuộc. Dock đã nghỉ; mẫu lịch sử được lưu trong
`tests/fixtures/legacy_ui_dock_script.html`. `wrap_page` gỡ cả nav lẫn script,
kể cả khung có thứ tự thuộc tính đã chuẩn hóa, và
`test_a_page_nested_the_way_the_pipeline_nested_live_is_repaired` dựng lại
đúng hình dạng ấy. Job `verify-published-pages` trong `update-data.yml` chạy
các phép kiểm bất biến trang trên mỗi commit của pipeline.

## Giao diện — trạng thái hiện tại

Giao diện đang phát triển theo yêu cầu ngày 26-09-2026 kết hợp Crafto Application
với khung Nexlink. Dark/Light phải đồng bộ trên mọi trang; KHÔNG khôi phục
khối pinlight cũ. Dock chân trang đã nghỉ, không sinh lại. Bộ "Master Design System" trong lịch sử không phải nguồn chuẩn. Mười bốn
trình dựng rời (`build_docs`, `build_docs_ml`, `build_dashboard`,
`build_model_quality`, `build_confidence_page`, `build_position_bridges`,
`build_bridge_pages`,
`build_markdown_dashboard_v3`,
`build_statistics_dashboard`, `build_landing_page`, `build_fun_prediction`,
`build_research_lab`, `build_stat_pages`, `build_traditional_results`) sinh
ra 39 trang trong `docs/`, gọi từ khối `if not args.skip_docs` của
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
  prefers-color-scheme`, `.dark` và `[data-ui-theme="dark"]` phải trùng nhau.
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

  `docs/**/*.js` phải khai riêng, không suy ra được từ `src`: các tệp trong
  `docs/assets/` (`matrix-virt.js`,
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

## Độ tin thành phần ML — không có kỹ năng thì không tin

`ml_train.model_trust` = `clip(20·s, 0, 1)`, s là kỹ năng thẩm định (kém hơn trong logloss/Brier).
Sàn 0,35 cũ trộn 35% mô hình thô cả khi s ≤ 0; walk-forward 997 kỳ đo nó làm LOTO kém hằng số
(z = −2,40), bỏ sàn hơn sàn z = +2,44 (`scripts/benchmark_model_trust.py`). Đừng khôi phục sàn. Khi
trust = 0 mọi xác suất ML bằng nền; `ml_predict.rank_predictions` xếp hoà theo xác suất thô.

Cầu-kèo (`cau_keo_ml`, trọng số tổ hợp 0,30) dùng CÙNG luật từ 04-10-2026: cột `prob` =
`trust·thô + (1 − trust)·nền`, trust và nền học trên khối thẩm định, lưu trong gói và đọc CHỈ qua
`cau_keo_ml.trust_from_pack` — không có mặc định; gói thiếu luật tin thì học lại. `ml_prob_raw` giữ
xác suất thô cho điểm và lý do. Walk-forward 1 000 kỳ đo xác suất thô kém hằng số (Đặc Biệt
z = −2,18); `validate_cau_keo_domain` canh `prob` đúng bằng bản đã co. Dòng `p_cau` cũ trong sổ
`data/history/pred_<mode>.csv` là xác suất THÔ: sổ ghi `policy_cau` cho dòng mới, và nơi HỌC từ sổ
(trọng số, hiệu chỉnh, xếp chồng) gọi `availability_from_history_day(..., current_policy=True)`.
Đổi định nghĩa một thành phần thì tăng `ensemble_components.COMPONENT_POLICY`, đừng viết lại sổ.

## Neo mức LOTO của tổ hợp — một phép chốt cho mọi nơi

`ensemble_utils.finalize_blend(p, mode)` là phép chốt của tổ hợp tuyến tính TRƯỚC hiệu chỉnh:
Đặc Biệt = `floor_distribution`; LOTO = `anchor_loto_level`, tức `Σp = 100·(1 − 0,99²⁷) ≈ 23,77`
(số con khác nhau kỳ vọng mỗi kỳ), nhân cùng một hệ số nên giữ thứ hạng. Hai nhánh cầu vị trí
thổi tổng lên 24,5 và 26,5 (lời nguyền người thắng khi chọn top quy tắc), nên trước đó tổ hợp LOTO
kém hằng số chỉ vì SAI MỨC. Mọi nơi chấm vector tổ hợp — `predict_nextday_2d`,
`learn_ensemble_weights`, `meta_predictor._baseline_validation`, `model_quality`,
`feature_attribution` — phải gọi hàm ấy; đừng chép lại `clip01`
(`tests/test_loto_level_anchor.py`). Ngoại lệ duy nhất là dựng lại ngày ĐÃ công bố: sổ ghi
`policy_blend`, và trang Chất lượng chốt dòng cũ (không có cột) bằng `anchor_loto=False`.
Số đo: `scripts/benchmark_component_trust.py`,
`documentation/research/2026-10-04-ra-soat-thanh-phan-to-hop.md`.

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

Sổ `data/prob_eval/ensemble_history.csv` ghi đơn vị Brier trên từng dòng (`brier_unit`): Đặc Biệt
trước 04-09-2026 là TRUNG BÌNH 100 lớp, sau đó là TỔNG — nhảy 100 lần là đổi đơn vị. Đừng sửa giá
trị cũ; nhãn được gắn bằng bất biến trong `prob_eval_history.label_brier_units`.

## Bảng mô phỏng và sổ nhật ký của nó

Bảng mô phỏng trang chủ (`build_fun_prediction.py`) rút 2 số cuối theo xác suất mô
hình; tiền tố là số ngẫu nhiên. `src/fun_draw_ledger.py` ghi mỗi kỳ bảng đang hiện
vào `data/fun_draw/ledger.csv` và chấm với kết quả thật (Đặc Biệt trúng đúng / trúng
lộn, số vị trí LOTO có về). Bảng chỉ được ghi TRƯỚC 18:10 giờ Việt Nam của kỳ đích;
sau đó dòng ấy đóng băng. Lịch sử trước khi có sổ nạp từ git bằng đúng luật đó
(`--backfill-from-git`). Đừng xoá sổ, đừng nới giờ khoá.

## Phòng thử thách mô hình `src/vla/`

`src/vla/` (đặc trưng → tiên nghiệm Dirichlet/Beta → LightGBM phần dư → hiệu chỉnh,
walk-forward, ROI) là KHUNG THÁCH ĐẤU, không nằm trong pipeline. Ngày 03-10-2026 nó không
hơn dự báo hằng số trên 1 000 kỳ và không thắng ML production, nên không được đề bạt
(`documentation/research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md`). Ý tưởng mô hình mới
phải qua `scripts/benchmark_probability_models.py` (kèm `--power-check`) trước; chỉ đề
bạt khi thắng CẢ hằng số LẪN mô hình đang chạy. Top-5 Đặc Biệt từng ra 7,0% chỉ vì PMI làm
trơn sai (cặp chưa có dữ liệu được PMI = log N); sửa xong còn 5,4% — đừng trích nó như tín hiệu.

## Độ tin cậy dự báo — hiệu chỉnh đa kiểm, không phải hậu nghiệm thô

`src/confidence_matrix.py` dựng Confidence Score ba tầng (High: cả Bayes,
Markov, cầu > 85%; Medium: hai trong ba ≥ 60%; còn lại Low/Noise) và
`build_confidence_page.py` in ra `docs/do-tin-cay.html`. Tin cậy của một thành
phần là tỉ lệ lịch sử CÔNG BẰNG mà tín hiệu mạnh nhất của cả họ còn yếu hơn
nó. Đừng thay bằng hậu nghiệm từng con: con cao nhất trong 100 con của một lịch
sử ngẫu nhiên đạt hậu nghiệm > 99% ở 60% lịch sử.

Phân phối null 10 000 lịch sử nằm ở `data/confidence/null_quantiles.json`,
tính lại khi số kỳ trôi quá 2% hoặc `STAT_VERSION` đổi (~8 phút, 4 lõi). Đổi
định nghĩa thống kê nào trong `stats()` thì PHẢI tăng `STAT_VERSION`. Phân vị
lưu ĐỦ độ chính xác: làm tròn 7 chữ số từng thổi tin cậy cầu Đặc Biệt từ
50,7% lên 66,5% vì cả khối giá trị hoà bị đếm là "nhỏ hơn".

## Top LOTO và giả thuyết "đuôi nóng"

Top LOTO (tệp top-4/8/10 và trang chủ) chọn qua `pick_diversity.diversified_order`:
tối đa 3 con cùng đuôi, xác suất không đổi. Ngày 28-09-2026 cả 10 con đuôi 4 vì đặc
trưng `tail_freq_7d` của mô hình cầu kèo — mười con cùng đuôi gần như là MỘT lần đặt.

`src/hot_tail_test.py` là phép kiểm TIẾN CỨU đã đăng ký ngày 28-09-2026 (từ kỳ
29-09, 180 kỳ, một phía α = 0,01). KHÔNG sửa tham số của nó: muốn đổi thì đăng ký giả
thuyết mới với ngày bắt đầu mới. Sổ cái `data/hypotheses/hot_tail.csv` giữ lần ghi đầu.
Chi tiết: `documentation/research/2026-09-28-duoi-4-va-gia-thuyet-duoi-nong.md`.

## Soi cầu vị trí — đúng luật của trang tham chiếu, kèm kiểm chứng

`src/position_bridges.py` dò cầu trên 107 vị trí chữ số (ĐB 0–4 … G7 99–106),
`build_position_bridges.py` in `docs/soi-cau-vi-tri.html` và ô "cầu đẹp nhất"
cạnh bảng LOTO ở trang chủ (cột `.tr-day-extra` của `render_result_board`). Luật
đã đối chiếu từng con số với trang tham chiếu ngày 29-09-2026 và bị ghim trong
`tests/test_position_bridges.py`: lộn thì CỘNG GỘP nháy của cả hai chiều; cầu
chạy theo KỲ QUAY; số kép chỉ là một số — số bóng (44 → 99) chỉ HIỆN kèm, tính nó
vào phép trúng thì ra 64 cầu thay vì 43. Bản JS (`templates/position_bridges.js`)
tính lại cho mọi tham số và phải ra đúng từng cầu như bản Python —
`tests/frontend/position-bridges.test.mjs` so tám bộ tham số.

Cầu dài KHÔNG trúng nhiều hơn: trên 4 217 kỳ, cầu LOTO đã chạy ≥ 10 kỳ trúng tiếp
39,2% so với kỳ vọng 40,5%; nhiều cầu cùng báo một cặp cũng không hơn. Trang in
kết luận ấy TỪ SỐ ĐO (`verdict`), đừng viết cứng. Đừng thêm "điểm tin cậy" theo độ
dài cầu. Thứ tự ô "đẹp nhất" là quy tắc tự đặt (độ dài, rồi số cầu cùng báo).

### Bảy kiểu cầu của trang tham chiếu thứ hai + phôi tuần

`src/bridge_rules.py` + `build_bridge_pages.py` in bảy trang `docs/soi-cau-*.html`
(LOTO, hai nháy, bạch thủ, Đặc Biệt, bộ số, Đặc Biệt theo thứ, LOTO theo thứ) và
`docs/tao-phoi-tuan.html`. Mọi kiểu dùng cặp vị trí a < b, số `10·d[a]+d[b]`; chỉ
luật "bước trúng" khác nhau — ghi trong docstring và bị ghim từng ô bởi
`tests/test_bridge_rules.py` với `tests/fixtures/bridge_reference_2026-09-28.json`.
Hai điểm dễ sai: hai nháy BẤT ĐỐI XỨNG (số lộn về hai nháy KHÔNG tính); bộ số là
"số giữ nguyên trong một bộ qua các kỳ", không phải "ĐB rơi vào bộ". Hai trang
tần suất cũ `cau-giai-dac-biet.html`, `cau-dac-biet-theo-bo-so.html` là thống kê
khác, giữ nguyên.

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

Số kiểm thử và bằng chứng phát hành gần nhất nằm trong PR và `docs/audit/`.
Bốn kịch bản chốt phát hành
(`release_check.sh`, `domain_challenger_check.sh`, `number_integrity_check.sh`,
`research_release_check.sh`) cũng xanh. Đỏ một phép kiểm nghĩa là thay đổi của
bạn làm đỏ nó — không có sẵn phép kiểm đỏ nào để đổ lỗi.

## Nguồn & bằng chứng suy luận của con số — 03-10-2026

Mọi con số trong `#app-main` có tooltip (rê chuột/tiêu điểm: nguồn tóm tắt, số
bước, gợi ý thao tác) và ngăn kéo `<dialog>` (nhấp: ngữ cảnh, nguồn, các bước,
độ tin cậy nếu có). `src/assets/app-evidence.js` dùng ủy quyền sự kiện ở cấp
tài liệu nên phủ cả bảng do JS dựng sau khi tải; nhận diện "con số" bằng chữ
của phần tử (≤ 24 ký tự, khớp `NUM`), không gắn lớp sẵn cho từng ô.

- Danh mục: `src/evidence_catalog.py` → khối `#app-evidence-data` trong
  `<head>`, chèn bởi `page_output._attach_evidence` (bóc rồi chèn, lũy đẳng).
  KHÔNG đặt thẻ ở đuôi khung: `_DUOI_KHUNG` neo vào đó. Trang mới phải có mục
  trong `_catalog` (`test_the_catalog_covers_every_page_a_reader_can_reach`).
- "Nguồn" là bộ dữ liệu và phép tính mô tả bằng lời; luật riêng tư của kho áp
  lên MỌI chuỗi danh mục. Liên kết nguồn chỉ trỏ tới trang nội bộ đã xuất bản.
- Số đã có chức năng nhấp (`[data-key]`, `.tr-number`, nút, liên kết,
  `[onclick]`, `[tabindex]`) GIỮ chức năng ấy; bằng chứng mở bằng Alt + nhấp
  (pha bắt, chặn trình xử lý của trang) hoặc nhấn giữ trên màn hình cảm ứng.
- Bằng chứng riêng cho giá trị: `data-evidence="<id>"` trên phần tử hoặc
  `data-evidence-row="<id>"` trên hàng bảng, mục nằm trong khối JSON
  `[data-app-evidence-values]` (`evidence_catalog.values_block`) hoặc
  `window.appEvidence.register`. Ví dụ: `ml_top10_*` in phép co
  `p = trust·thô + (1 − trust)·nền` bằng số thật, `confidenceScore` = model_trust.
- Bàn phím: mỗi bảng hoặc khối có số (`section`, `article`, `.ui-card`…) là
  MỘT điểm dừng Tab (`data-evidence-region`, gắn khi quét và khi DOM đổi);
  mũi tên chọn số (lên/xuống theo cột trong bảng), Enter/Space mở bằng chứng,
  `aria-live` đọc giá trị. ĐỪNG gắn tabindex cho từng con số: trang thống kê có
  hàng nghìn con số. tabindex do module tự gắn không làm số thành "đã có chức
  năng nhấp".
- Câu nhắc dự báo (`_GHI_CHU_DU_BAO`) phải đúng với số đo của kho; đừng viết
  cứng kết luận mà trang khác in TỪ SỐ ĐO (ví dụ "cầu dài có đáng tin hơn?").

## Hợp đồng giao diện bổ sung — 26-09-2026

- `app-theme.js` chạy đồng bộ trong head sau CSP, trước CSS. `.dark` biểu thị
  màu đã phân giải; không có `data-ui-theme` là theo OS. Nút theme đảo màu
  thực tế ngay lần bấm đầu, lưu `app-theme`, đồng bộ các tab và chịu lỗi storage.
- Global Search: `#app-global-search` / `#app-global-search-input`, Ctrl/Cmd+K;
  đích lấy SITE_NAV + LANDING_SECTIONS, dedup href. Dialog đặt trước app-main
  để quy tắc bóc/bọc shell vẫn lũy đẳng.
- Sidebar Filter: `#app-sidebar-filter`, chỉ lọc nhóm đang hiển thị. Không
  dùng lại input, query hoặc handler global search.
- Theo yêu cầu mới ngày 26/09/2026, rail/header dùng SVG gốc Nexlink tại
  `src/assets/nexlink`, giữ đúng đường nét, opacity, thứ tự 11 icon và header.
  Sidebar dùng outline Flaticon Rounded chuyển nguyên hình học sang SVG.
  `nexlink_icons.py` là renderer của shell; không thay bằng Lucide tương tự.
  Lucide tại `src/assets/icons` chỉ còn dùng trong nội dung/global search.
  Mọi bộ icon có provenance; không vẽ lại hoặc dùng Unicode/icon font.
- Mọi bề mặt/chữ/viền/control/modal phải đọc token; màu có nghĩa dữ liệu dùng
  cặp token riêng, kiểm AA cả hai theme. Không dùng OS media riêng để bỏ qua
  lựa chọn sáng tường minh. Bản in đặt lại token sáng để chữ đọc được.
- Sửa ui_theme thì dựng ui.css, chạy `scripts/extract_critical_css.py`, rồi
  dựng HTML bằng process mới để không giữ module critical đã import.
- `tests/frontend` chạy bằng `npm ci --prefix tests/frontend` và
  `npm test --prefix tests/frontend`; fixture shell lấy từ generator nguồn.

Đặc tả: `docs/superpowers/specs/2026-09-26-theme-search-icons-design.md`.
