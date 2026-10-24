# VLA — Chỉ dẫn cho Claude

## Ngôn ngữ

Mọi trao đổi với chủ dự án bằng **tiếng Việt**. Docstring và chú thích trong
mã nguồn cũng tiếng Việt.

## Bảo mật — tuyệt đối

KHÔNG BAO GIỜ hỏi, nhận, hay xử lý GitHub PAT của chủ dự án. Token chỉ được
đưa vào terminal của họ và cron-job.org, không đi qua phiên làm việc này.

## Bố cục `src/` — gói theo chức năng (23-10-2026)

Gốc `src/` chỉ còn `pipeline.py`; mọi module khác nằm trong một gói. TÊN MODULE GIỮ NGUYÊN
(chỉ thêm tiền tố gói), nên nhãn đã ghi vào sổ như `calendar_alignment.known_non_draw_days`
và mọi chỗ nhắc `module.hàm` trong tệp này vẫn đúng.

    core        miền XSMB, lịch quay, đồng hồ, mã số, I/O nguyên tử, đường dẫn kho (paths), thử lại
    ingest      nguồn, đồng bộ, live, thăm dò đủ 27 ô (fetch_results), sổ chuẩn Lottery, kiểm dữ liệu
    ensemble    neo mức, trọng số, thành phần, hiệu chỉnh, gộp ý kiến, co ngót, đa dạng đuôi
    stats       thống kê mô tả/kiểm định, ma trận, tín hiệu thống kê, động học số
    soi_cau     cầu vị trí, bảy kiểu cầu, cầu theo đường, tổng – bóng – chạm;
                gói con bridges (quét cầu ghép chéo, cổng kiểm định), features (đặc trưng cầu)
    ml          ML thành phần và Cầu Kèo: đặc trưng, huấn luyện, dự báo, thách đấu miền
    forecast    xếp chồng, dự báo đầy đủ, học trực tuyến, kho tri thức, Lô VIP (multi_hit_*);
                gói con modeling (dự đoán hằng ngày predictions_today.json), xsmb_agents (hệ ba tác tử)
    evaluation  chất lượng mô hình, sổ dự báo, độ tin cậy, bảng mô phỏng, kiểm toán vận hành
    research    phòng nghiên cứu và phép kiểm tiến cứu đã đăng ký;
                gói con ml_engine (khung học tiếp diễn), vla (phòng thử thách mô hình)
    web         shell, theme, page_output, bằng chứng, thành phần trang dùng chung;
                tài nguyên templates (mẫu HTML/CSS/JS, Jinja) và assets (tệp tĩnh, phông, biểu tượng)
    pages       trình dựng từng trang trong docs/ (build_*), README

Gói cũ đã gom (24-10-2026), không còn gì đứng riêng: `crawler` → `ingest`, `utils` → `core`;
`bridges`, `features` → gói con của `soi_cau`; `modeling`, `xsmb_agents` → gói con của `forecast`;
`ml_engine`, `vla` → gói con của `research`; `templates`, `assets` → `web/templates`, `web/assets`.
Gói cũ giữ làm GÓI CON vì tên module bên trong chung chung (`base`, `spec`, `risk`, `engine`).
Lệnh chạy ở cạnh gói chúng điều khiển: `soi_cau/bridges/run_bridge_scan.py`,
`forecast/modeling/run_daily_prediction.py`, `forecast/xsmb_agents/run_xsmb_agents.py`.

- Import: `from ensemble import ensemble_utils` hoặc `from ensemble.ensemble_utils import
  finalize_blend`. KHÔNG import theo tên phẳng cũ — chạy được khi kịch bản đứng cùng thư
  mục, hỏng ở mọi nơi khác.
- Chạy: `PYTHONPATH=src python src/<gói>/<module>.py`. Chạy bằng đường dẫn tệp thì Python
  đặt thư mục của CHÍNH tệp ấy lên `sys.path`, không phải `src`. `pipeline._child_env` tự
  đặt cho mọi bước con; job workflow nào chạy `src/<gói>/…` phải khai `PYTHONPATH` trong
  `env`.
- Đường dẫn tới gốc kho, `src/web/templates`, `src/web/assets` CHỈ qua `core.paths`
  (`REPO_ROOT`, `SRC`, `TEMPLATES`, `ASSETS`). Đừng đếm `Path(__file__).parents[...]`:
  `known_non_draw_days` đọc lịch nghỉ bằng đường dẫn ấy, và sai tầng thì lịch rỗng chứ
  không báo lỗi. Cũng đừng ghép `repo_root / "src" / …` hay `SRC / …` ngoài `core/paths.py`.
- Pack joblib ghi trước đợt gom nhắc lớp bằng tên `ml_models`; `ml/ml_models.py` đăng ký tên
  ấy trong `sys.modules`. Thiếu nó, `MODEL_LOAD_ERRORS` nuốt ImportError và bước dự báo coi
  pack là hỏng mà không báo.
- Module mới vào gói đúng chức năng, không đặt ở gốc `src/`. Gói không được phụ thuộc vòng.
- Chuyển module thì mọi lệnh chạy `src/…py` (workflow, `scripts/`, `pipeline.py`) phải trỏ tệp có
  thật: phép kiểm phụ thuộc của workflow lọc đường dẫn bằng `is_file()`, nên lệnh trỏ chỗ cũ bị bỏ
  qua lặng lẽ và chỉ hỏng khi chạy thật. Tên gói đã gom (`crawler`, `utils`, `bridges`, `features`,
  `modeling`, `ml_engine`, `vla`, `xsmb_agents`, `templates`) không được import lại.
- Bộ lọc `paths:` của workflow phải khớp tệp có thật: GitHub không báo lỗi cho bộ lọc trỏ chỗ trống,
  workflow chỉ lặng lẽ thôi chạy (`vietlott-results.yml` lọc theo ba tệp trong `web/`).
- Phép kiểm "workflow cài đủ thư viện" (`test_workflows._third_party_closure`) truy theo ĐƯỜNG DẪN
  module đầy đủ: theo tên gốc thì `from ingest.sources import …` chỉ đọc `ingest/__init__.py` và bs4
  biến mất — 23 → 24-10-2026 bốn job cần bs4 gián tiếp đã lọt khỏi phép kiểm như thế.
- `tests/repo/test_src_layout.py` canh các điều trên, mỗi luật được ghim trên mẫu dựng sẵn.

`scripts/` chia theo chức năng, bảng nhóm là `tests/test_repo_layout.SCRIPT_GROUPS`: `ops` (vận
hành CI, triển khai), `web` (công cụ dựng và hậu xử lý trang: critical CSS, khung điều hướng, CSP,
DOM; tách khỏi `ops` 24-10-2026), `browser` (kiểm trên Chromium), `reference` (đọc trang tham
chiếu), `release` (bốn kịch bản chốt phát hành), `research` (phép đo tái lập được). Script nằm
đúng hai cấp dưới gốc kho (`parents[2]`), có docstring nói nó làm gì, và mọi đường dẫn `scripts/…`
được nhắc ở đâu trong kho phải trỏ tệp có thật. 22/40 script Python không có argparse: `--help` là
chạy thật và ghi đè tệp (`extract_critical_css`, `replicate_top5_special` từng bị chạy nhầm như thế).

`tests/` chia theo chức năng (24-10-2026), bảng nhóm là `tests/repo/test_repo_layout.TEST_GROUPS`:
mười một nhóm trùng tên gói `src/` mà phép kiểm kiểm (`tests/ensemble/`, `tests/web/`…), cộng
`pipeline` (thứ tự bước của `src/pipeline.py`), `site` (bất biến trên `docs/` đã xuất bản), `worker`
(Worker và phép so Python ↔ JS), `repo` (bố cục kho, workflow, CI, tài liệu). Tên tệp giữ nguyên và
phải DUY NHẤT toàn `tests/`: không có `__init__.py`, pytest nạp phép kiểm theo tên tệp. Gốc kho trong
phép kiểm là `Path(__file__).resolve().parents[2]` (`parents[1]` chỉ để tới `tests/fixtures`):
`parents[1]` cũ trỏ vào `tests/`, `(ROOT / "docs").glob(...)` ra tập rỗng và phép kiểm tham số hoá
không chạy lần nào mà vẫn xanh. Helper dùng chung giữa các nhóm đặt ở gốc `tests/` với tên
`*_helpers.py` (`theme_palette_helpers`, `privacy_helpers`); `conftest.py` đưa `src/` và `tests/` lên
`sys.path`. Quét tệp kiểm thì dùng `rglob`: hai phép kiểm từng `glob("test_*.py")` ở gốc `tests/`.

## Khung ứng dụng

Mọi trang đi qua `page_output.write_page`, và **chỉ ở đó** khung dùng chung
được bọc vào (`_attach_shell` -> `app_shell.wrap_page`). Đừng chép khung vào
từng trình dựng: chép là để chúng trôi khỏi nhau.

    src/web/app_shell.py              dựng HTML: dải biểu tượng, dải chi tiết, thanh trên
    src/web/templates/app_shell.css   hình học và màu, theo số đo trang tham chiếu
    src/web/assets/app-shell.js       thu/mở, đổi nhóm, hai tìm kiếm độc lập
    src/web/assets/app-theme.js       khôi phục/đổi màu, OS và storage sync
    src/web/app_icons.py              SVG Lucide cho nội dung / global search
    src/web/nexlink_icons.py          SVG Nexlink gốc cho rail / sidebar / header

Điều hướng khai một lần ở `ui_theme.SITE_NAV_SECTIONS` — 8 nhóm chức năng,
chia cụm có tiêu đề. `SITE_NAV` là bản phẳng được suy ra cho các trình dựng
và tìm kiếm. Thêm mục ở `SITE_NAV_SECTIONS`, không thêm ở `app_shell.py`.

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
khối pinlight cũ. Dock chân trang đã nghỉ, không sinh lại. Bộ "Master Design System" trong lịch sử không phải nguồn chuẩn. Mười lăm
trình dựng rời (`build_docs`, `build_docs_ml`, `build_dashboard`,
`build_model_quality`, `build_confidence_page`, `build_position_bridges`,
`build_bridge_pages`,
`build_markdown_dashboard_v3`,
`build_statistics_dashboard`, `build_landing_page`, `build_fun_prediction`,
`build_research_lab`, `build_stat_pages`, `build_traditional_results`,
`build_multi_hit_page`) sinh ra 40 trang trong `docs/`, gọi từ khối `if not args.skip_docs` của
`src/pipeline.py`.

Đọc trước khi sửa frontend:

    documentation/architecture/ui-design-system.md

Stylesheet chuẩn là **`assets/ui.css`**. `assets/vla.css` là tên đã nghỉ;
`tests/site/test_published_ui_contract.py` làm đỏ trang nào còn trỏ vào nó.

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

Đổi bảng màu thì đổi ở **`src/web/ui_theme.py`** (token dùng chung) và
**`src/web/templates/ui_visual_system.css`** (lớp skin). Bốn phép kiểm canh:

- `test_every_text_token_reaches_aa_on_every_surface_it_sits_on` — mọi token
  chữ trên mọi bề mặt, cả ba khối màu.
- `test_both_dark_blocks_declare_the_same_tokens` — `@media
  prefers-color-scheme`, `.dark` và `[data-ui-theme="dark"]` phải trùng nhau.
- `test_the_three_copies_of_the_page_background_agree` và
  `test_the_first_frame_paints_the_background_from_tokens_not_a_copy` — màu nền
  từng có BỐN bản sao (`ui_theme`, module sinh ra, bản dự phòng trong
  `css_links`, và một chuỗi ghim trong `scripts/web/extract_critical_css.py`).
- `PAGE_GROUND` / `BRAND_RAMP` trong `tests/web/test_ui_design_system.py` là HỢP
  ĐỒNG: mọi chủ sở hữu style phải khai cùng một nền và cùng một dốc nhấn.

`documentation/ui/VLA_MASTER_UIUX_SPEC.md` là bản prompt thiết kế của chủ dự án,
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
  + `textContent`. Ba hàm dùng chung ở đầu `src/web/templates/stat_pages.js` —
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

Cổng thẩm định ngoài mẫu trong `src/ensemble/learn_ensemble_weights.py` chỉ đề bạt
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
(z = −2,40), bỏ sàn hơn sàn z = +2,44 (`scripts/research/benchmark_model_trust.py`). Đừng khôi phục sàn. Khi
trust = 0 mọi xác suất ML bằng nền; `ml_predict.rank_predictions` xếp hoà theo xác suất thô.

Cầu-kèo (`cau_keo_ml`, trọng số tổ hợp 0,30) dùng CÙNG luật từ 04-10-2026: cột `prob` =
`trust·thô + (1 − trust)·nền`, trust và nền học trên khối thẩm định, lưu trong gói và đọc CHỈ qua
`cau_keo_ml.trust_from_pack` — không có mặc định; gói thiếu luật tin thì học lại. `ml_prob_raw` giữ
xác suất thô cho điểm và lý do. Walk-forward 1 000 kỳ đo xác suất thô kém hằng số (Đặc Biệt
z = −2,18); `validate_cau_keo_domain` canh `prob` đúng bằng bản đã co. Dòng `p_cau` cũ trong sổ
`data/history/pred_<mode>.csv` là xác suất THÔ: sổ ghi `policy_cau` cho dòng mới, và nơi HỌC từ sổ
(trọng số, hiệu chỉnh, xếp chồng) và bảng đóng góp thành phần gọi
`availability_from_history_day(..., current_policy=True)`.
Đổi định nghĩa một thành phần thì tăng `ensemble_components.COMPONENT_POLICY`, đừng viết lại sổ.
Tác tử mẫu hình của hệ ba tác tử XSMB (`forecast.xsmb_agents.algorithms.pattern`) dùng CÙNG luật từ 20-10-2026:
`trust = model_trust(s)`, s là kỹ năng so với nền trên 30 kỳ thẩm định cuối; định nghĩa 1 trộn cố định
20% mạng dù logloss thẩm định Đặc Biệt kém nền. Mỗi định nghĩa một SỔ: họ `online.AGENT_RECIPE` =
`xsmb_three_agents_v<AGENT_POLICY>`; sổ họ cũ được `retire_superseded_ledgers` CẤT NGUYÊN thành
`data/online/agents_<mode>.<họ>.json` (không chấm lại) và sổ mới bắt đầu rỗng, để Hedge, bước chọn
η/độ quên và cổng đề bạt không thừa hưởng điểm của bộ dự báo khác. Đổi định nghĩa tác tử thì tăng
`AGENT_POLICY`, đổi họ và thêm họ cũ vào `RETIRED_AGENT_FAMILIES`.
Khung nghiên cứu `ml_engine` dùng CÙNG luật từ 20-10-2026: bandit Thompson và ngưỡng Hit-Rate 7 kỳ
đã gỡ (kém hằng số z = −3,40 trên 1 000 kỳ); nay trộn bằng trọng số mũ trên log-loss CỘNG 100 con
(`aggregation.ExponentialWeights`, η = 1 là Bayes, chia sẻ cố định α = 0,001, chốt trước khi đo) rồi
qua cổng `fallback.SafeModeController`: `trust = model_trust(kỹ năng 60 kỳ của phép trộn TRƯỚC cổng)`,
chưa đủ 30 kỳ hoặc trôi lệch/lỗi mô hình thì trust = 0 và dự báo đúng bằng nền. Ngang hằng số, hơn bản
cũ z = +3,40 (`scripts/research/benchmark_ml_engine_aggregation.py`,
`data/research/ml_engine_aggregation.json`). Đừng đo kỹ năng trên dự báo đã qua cổng: trust = 0 thì
dự báo trùng nền và cổng không bao giờ mở lại.

## Neo mức LOTO của tổ hợp — một phép chốt cho mọi nơi

`ensemble_utils.finalize_blend(p, mode)` là phép chốt của tổ hợp tuyến tính TRƯỚC hiệu chỉnh:
Đặc Biệt = `floor_distribution`; LOTO = `anchor_loto_level`, tức `Σp = 100·(1 − 0,99²⁷) ≈ 23,77`
(số con khác nhau kỳ vọng mỗi kỳ), nhân cùng một hệ số nên giữ thứ hạng. Hai nhánh cầu vị trí
thổi tổng lên 24,5 và 26,5 (lời nguyền người thắng khi chọn top quy tắc), nên trước đó tổ hợp LOTO
kém hằng số chỉ vì SAI MỨC. Mọi nơi chấm vector tổ hợp — `predict_nextday_2d`,
`learn_ensemble_weights`, `meta_predictor._baseline_validation`, `model_quality`,
`feature_attribution` — phải gọi hàm ấy; đừng chép lại `clip01`
(`tests/ensemble/test_loto_level_anchor.py`). Ngoại lệ duy nhất là dựng lại ngày ĐÃ công bố: sổ ghi
`policy_blend`, và trang Chất lượng chốt dòng cũ (không có cột) bằng `anchor_loto=False`.
Số đo: `scripts/research/benchmark_component_trust.py`,
`documentation/research/2026-10-04-ra-soat-thanh-phan-to-hop.md`.

## Chất lượng mô hình — chấm thứ đã CÔNG BỐ

Trang Chất lượng mô hình và bộ theo dõi `src/evaluation/skill_monitor.py` chấm chính
vector xác suất đã công bố trước kỳ quay
(`data/predict/predict_next_<mode>_all_<ngày>.csv`) với kết quả quay thật.
Bản dựng lại từ `data/history/pred_<mode>.csv` bỏ qua hiệu chỉnh và tầng xếp
chồng — tức chấm một mô hình KHÁC — nên chỉ dùng khi chưa đủ `MIN_DAYS` kỳ.

`skill_monitor` chạy trong job `verify-published-pages` trên mỗi commit của
pipeline và làm lượt đỏ khi kỹ năng ngoài mẫu rời vùng 0 theo HƯỚNG NÀO CŨNG
VẬY (z=3, cửa sổ 60 kỳ). Kỳ quay đã kiểm là ngẫu nhiên: tệ hơn là hồi quy,
tốt hơn thì phải kiểm lại trước khi tin. Đừng "sửa" báo động ấy bằng cách nới
ngưỡng.

Mọi sổ cái "đọc lại rồi ghi lại toàn bộ" ghi qua `src/core/atomic_io.py` (tệp tạm + `os.replace`).
Đừng quay lại `open("w")`/`to_csv(path)`: chết giữa chừng để lại sổ cụt và lần sau mất dòng cũ
(`tests/core/test_atomic_ledgers.py`).

`cleanup_artifacts` xoá artifact quá 45 ngày, nên kỹ năng từng kỳ được ghi
vào sổ cái `data/model_quality/published_skill.csv` TRƯỚC khi dọn (lần ghi đầu
giữ nguyên, không bị đè). Đừng xoá sổ ấy: nó là chuỗi đánh giá duy nhất dài
hơn hạn giữ artifact.

Sổ `data/prob_eval/ensemble_history.csv` ghi đơn vị Brier trên từng dòng (`brier_unit`): Đặc Biệt
trước 04-09-2026 là TRUNG BÌNH 100 lớp, sau đó là TỔNG — nhảy 100 lần là đổi đơn vị. Đừng sửa giá
trị cũ; nhãn được gắn bằng bất biến trong `prob_eval_history.label_brier_units`.

## Bảng mô phỏng và sổ nhật ký của nó

Bảng mô phỏng trang chủ (`build_fun_prediction.py`) rút 2 số cuối theo xác suất mô
hình; tiền tố là số ngẫu nhiên. `src/evaluation/fun_draw_ledger.py` ghi mỗi kỳ bảng đang hiện
vào `data/fun_draw/ledger.csv` và chấm với kết quả thật (Đặc Biệt trúng đúng / trúng
lộn, số vị trí LOTO có về). Bảng chỉ được ghi TRƯỚC 18:10 giờ Việt Nam của kỳ đích;
sau đó dòng ấy đóng băng. Lịch sử trước khi có sổ nạp từ git bằng đúng luật đó
(`--backfill-from-git`). Đừng xoá sổ, đừng nới giờ khoá.

## Sổ phỏng đoán trong ngày và bảng đối chiếu trang Live — 21-10-2026

`src/evaluation/prediction_board.py` (bước pipeline sau `build_fun_prediction`) chụp MỌI danh sách số các trang
công bố cho kỳ tới — tổ hợp Top 10, Cầu Kèo, ML, hệ ba tác tử, Lô VIP, xiên 2, cầu đẹp nhất, bảy trang
soi cầu, soi đường, bảng mô phỏng — vào `data/prediction_board/<kỳ>.json`; trang Live
(`src/web/assets/live-scorecard.js`) đặt từng danh sách thành hai hàng "Trước giờ quay" / "Sau giờ quay"
cạnh kết quả đang về. Sổ chỉ được ghi TRƯỚC 18:10 giờ VN của kỳ đích (`fun_draw_ledger.cutoff_utc`),
sau đó đóng băng và không tạo mới: nhiều tệp nguồn không mang ngày và bị ghi đè cho kỳ sau lúc ~19 giờ.
Nguồn nào không tự khai đúng kỳ đích thì BỎ, ghi vào `missing`. Tệp soi đường
`path_ui/predict_next_*_<ngày>.csv` mang NGÀY DỮ LIỆU (manifest `anchor_date`) và dự báo kỳ kế tiếp —
khác mọi `predict_next_*` khác (mang ngày quay); đọc theo ngày quay là chấm danh sách của kỳ trước.
Mỗi mục mang luật trúng của chính trang liệt kê nó (`rule`: LOTO tổng nháy ≥ t, xiên cần đủ số, Đặc
Biệt thuộc tập, cầu Đặc Biệt "chạm" theo chữ số) và `base` = xác suất CHÍNH XÁC của đúng sự kiện ấy khi
kỳ quay công bằng; hàng sau giờ quay chỉ "trượt" khi phần kết quả liên quan đã đủ. Kỳ đã khoá dựng lại
được bằng `--backfill-from-git` (commit cuối trước 18:10, ghi `backfilled_from`, không đè sổ đã có).
Các mục trong một danh sách thường trùng nhau (cùng chữ số chạm) nên không độc lập — đừng in "trúng
10/10" như bằng chứng. `tests/evaluation/test_prediction_board.py`, `tests/frontend/live-scorecard.test.mjs`.

## Nguồn kết quả XSMB — một chính, hai dự phòng (13-10-2026)

Theo yêu cầu chủ dự án: nguồn chính `xoso.com.vn`; dự phòng `mketqua.net` rồi
`www.minhngoc.net.vn`, CHỈ gọi khi nguồn chính gặp sự cố (`sources.primary_has_failed`:
không bóc được giá trị nào, hoặc đã quá `PRIMARY_COMPLETE_BY` = 18:40 giờ VN mà còn thiếu ô).
Khi dự phòng được gọi, chỉ dữ liệu dự phòng được hợp nhất — nguồn chính đã hỏng không cầm
phiếu. Ngưỡng đồng thuận là MỘT nhóm ở mọi nơi (`live_sync`, `fetch_results`, `sync`,
`update-data.yml`, Worker `MIN_AGREEMENT`, `production_audit`, `reconcile_live_canonical`);
hai dự phòng nói khác nhau ở một ô là thế hoà, ô ấy không được xác minh. Năm nguồn cũ đã nghỉ
vì đo trên runner là hỏng (`RETIRED_SOURCE_NAMES`, vẫn được quét riêng tư); đừng thêm lại
nguồn khi chưa đo bằng `diagnose-live-sources.yml`. Bản JS của Worker bị buộc khớp bởi
`test_worker_sources_parity`, `test_source_failover_parity`, `test_worker_snapshot_parity`.

Trước giờ quay, trang live của mọi nguồn vẫn hiện TRỌN kỳ hôm qua (đo 00:37 ngày 13-10-2026).
Nguồn mà mọi giá trị trùng đúng ô của kỳ đã lưu gần nhất bị coi là chưa có gì
(`sources.shows_previous_draw`, lỗi `StalePage`) ở `live_sync`, `ingest/fetch_results` và Worker
— thiếu chốt này, lượt thăm dò đầu khung báo kỳ hôm nay "đã xác minh" bằng số của hôm qua. Worker
lấy kỳ MỚI NHẤT trong ảnh chụp KV, khoá `previous-draw.json` và sổ chuẩn `data/xsmb.json` (khởi
động lạnh); không có gì để so thì không chốt kỳ đủ ô. Sổ chuẩn
(`Lottery.fetch`) bỏ nguồn trùng khít rồi hỏi nguồn kế tiếp, không dừng ở nguồn đầu.

Một hàng giải = dòng nhãn + các dòng NGAY SAU mà mọi mẩu là số ASCII đúng độ rộng của giải;
gặp dòng khác là hết hàng. Trước đó giải 7 (nhãn cuối bảng) vớ số của bảng lô tô, ô chọn tháng
hay liên kết ngày khi chưa quay — lỗi "trùng lặp giải 7". Mẫu trang thật: `thuc_*` trong
`tests/fixtures/prize_pages.json`. Chi tiết: `documentation/operations/live-worker.md` mục 6.

`update-data.yml` có ba chặng: `canonical` (chốt và commit kết quả chuẩn) → song song
`publish-results` (dựng trang chủ/sổ kết quả/soi cầu vị trí rồi triển khai Pages, không commit)
và `update` (pipeline đầy đủ); `deploy-pages` chờ CẢ HAI nên bản đầy đủ luôn triển khai sau cùng.
Lượt `live_verified` gọi `sync.py --cutoff 00:00` (12-10-2026 quay khống 3 phút vì mốc 18:35);
khi kỳ hôm nay đã có dự báo kỳ sau (`finalized`) nó bỏ `publish-results` và `update` nhưng VẪN
triển khai Pages và hậu kiểm lại. Đừng gộp lại thành một job: trang chủ khi ấy chờ ~5 phút
pipeline. Điều kiện `if:` của các job được ĐÁNH GIÁ (kể cả `success()` ngầm định) trong
`tests/repo/test_finalization_timing.py`; xem `documentation/operations/scheduling.md`.

## Engine Vietlott `vietlott/` — chép từ VLM, chạy riêng

Ngày 07-10-2026 chủ dự án yêu cầu VLA có ĐỦ tính năng của VLM (kho `beuvivu/VLM`,
"Vietlott Quant Engine") nhưng hai bên chạy riêng rẽ, để sau còn tách thành hai
trang. Toàn bộ VLM (bản `6bec0c9`, trừ `.github`) nằm ở `vietlott/` như một dự án
TỰ ĐỦ: `pyproject.toml`, `src/vietlott_engine`, `src/vlm`, `data/`, `scripts/`,
`tests/`, `reports/`. Đừng trộn nó vào `src/` hay `data/` của VLA, và đừng sửa
logic của nó ở đây khi không cần — engine tự tìm thư mục dự án qua `paths.py`.

- Chạy: `cd vietlott && python -m pip install -e ".[dev,crawler]" && python -m pytest`
  (369 phép kiểm). Lệnh: `vietlott`, `vlm-update`, `vlm-forecast`, `vlm-audit`.
- Workflow ở `.github/workflows/vlm-*.yml` (GitHub chỉ đọc workflow ở gốc kho),
  `working-directory: vietlott`, đường dẫn cache có tiền tố `vietlott/`. Chúng KHÔNG
  triển khai Pages; trang riêng của engine chỉ được dựng và lưu thành artifact.
  `tests/repo/test_vietlott_engine_layout.py` canh cả ba điều.
- Phép kiểm của engine tìm workflow ở cả hai bố cục (`tests/conftest.py`,
  `find_workflows`): kho riêng thì `.github/workflows/*.yml`, nằm trong VLA thì
  `../.github/workflows/vlm-*.yml`.
- Tag phát hành của engine là `vlm-v<phiên bản>`.

Trang Vietlott của site (`vietlott.html` + 7 trang sản phẩm) dựng bằng
`src/pages/build_vietlott_results.py` từ `vlm.web.dashboard.build_dashboard` của engine:
kết quả đã xác thực, bảng giải ĐÚNG mã kỳ (khuyết in "—", không mượn kỳ trước), dự
báo ghi trước kỳ + đối chiếu, kết luận e-value. Trình dựng KHÔNG in `source`,
`source_url`, `official_url` hay cảnh báo của engine (chúng nhắc tên nguồn) —
`tests/pages/test_vietlott_results.py` canh. Workflow `vietlott-results.yml` không gọi
mạng: khôi phục (chỉ đọc) cache trạng thái `vqe-state-` rồi dựng và triển khai.
Câu kết luận về độ ngẫu nhiên ở trang tổng quan in TỪ e-value của engine
(`randomness_summary`), không viết cứng: Max 3D và Max 3D Pro lệch thật ở hàng đơn vị (số 6
≈ 11%, lặp lại trên hai sản phẩm), dù mọi cửa Max 3D mà mô hình tính được vẫn có RTP < 1 (Mega/Power/Lotto không có RTP trong phân tích nên không được gộp vào câu ấy)
(`documentation/research/2026-10-07-max3d-hang-don-vi.md`).
API của engine mặc định an toàn (08-10-2026): CORS đóng, `VQE_API_TOKEN` (khi đặt) bắt mọi
POST/PUT/PATCH/DELETE và mọi `?record=` mà FastAPI đọc là True (`on`, `y`… cũng vậy, đọc bằng
chính `TypeAdapter(bool)`) gửi `Authorization: Bearer`; ba GET làm mới dự báo (`/forecast/{p}`,
`/forecast/{p}/evidence`, `/ml/forecast/{p}`) cũng là lệnh ghi. Không có token thì lệnh ghi do trình
duyệt gửi từ trang khác (`Sec-Fetch-Site`/`Origin`) bị 403; `vietlott serve` và compose chỉ nghe
`127.0.0.1`. CORS phải nằm NGOÀI middleware xác thực (thêm sau cùng). `vietlott/tests/test_api_security.py` canh; nên đưa ngược bản vá về kho VLM.
Kiểm chứng xác suất và số khớp H cho Mega/Power (13-10-2026, `vietlott/docs/VLM_HIT_BENCHMARK.md`):
`vlm.forecast.hits` (H = |vé ∩ 6 số chính| so với siêu bội C(6,h)C(N−6,6−h)/C(N,6), đơn vị KỲ, số đặc biệt
Power KHÔNG cộng vào H), `vlm.forecast.challengers`, `vlm.forecast.hit_benchmark` (giao thức `PROTOCOL` đăng ký
13-10-2026: 300 kỳ khởi động, dev 50% · validation 20% · test 30%, chọn/ablation/hiệu chuẩn chỉ trên
dev/validation, test nhìn một lần, năm điều kiện đề bạt, Holm). Đừng sửa `PROTOCOL` rồi gọi test là độc lập —
đăng ký giao thức mới. H ≥ 4 không đủ công suất để đề bạt (phát hiện ×2 cần 6.502 kỳ Mega, 14.647 kỳ Power); báo cáo nó, đừng
dùng nó. Benchmark và bảng điều khiển phải chấm ĐÚNG vé đã phát: ML là bộ đầu của `Law.top(PUBLISHED_TOP_N)` (cùng lệnh gọi với
bảng điều khiển), legacy là 6 số π cao nhất.
Checkpoint ML version 3: `pair_link`/`triple_link` không gộp tần suất của chính số ấy (bản cũ tương quan 0,99
với `lag1`). Trang Vietlott in "chọn bừa k/n" cạnh tỷ lệ trùng theo vé (`FAIR_MATCH_RATE`).
Vé công bố từ 15-10-2026 (`ticket_rule = coverage-v1`, ghi vào `pending` CÙNG lần ghi luật): năm vé RỜI NHAU
chia xoay vòng từ 30 số (Lotto: 25) có xác suất biên cao nhất (`distribution.coverage_tickets`). Luật ML gần
đều nên `Law.top` cho năm vé chung 5/6 số, và ngày 14-10-2026 hệ số nhiễu của `lag2` đẩy vé đầu Power chép
nguyên kỳ #1409. Với cùng năm vé, "ít nhất một vé trúng ≥ 2 số" lên 70,9% (Mega), 53,7% (Power), 61,1%
(Lotto) — dò cục bộ không tìm được cách xếp nào hơn; xác suất TỪNG vé không đổi, đừng nói là "tăng xác suất
trúng". Lần ghi KHÔNG có khoá ấy giữ `Law.top` (không chấm lại kỳ cũ bằng quy tắc mới); benchmark H đã đăng
ký vẫn chấm `Law.top`. Mốc in trên trang lấy từ `dashboard.coverage_summary` (`hits.any_ticket_tail`), không
viết cứng. Kỳ đã qua giờ quay mà chưa có kết quả: thẻ hiện chính bộ số đã ghi, nhãn "Đã quay, đang chờ kết
quả" (`build_vietlott_results.shown_forecast`). Kết quả Mega/Power/Lotto: chuỗi `auto` hỏi `xskt` (trang
đăng lại, đọc được từ runner) SAU bản sao NhanAZ (trễ hàng giờ); `vlm-results.yml` nhận `repository_dispatch`
`vietlott-results` và chạy sau lượt `daily-finalize` — lịch mười phút của GitHub chạy cách nhau 1–5 giờ.
Crawler Vietlott cũ (`src/vietlott_results.py`) đã nghỉ; `data/vietlott/vietlott.sqlite3`
giữ nguyên làm lưu trữ, không còn được ghi.

## Phòng thử thách mô hình `src/research/vla/`

`src/research/vla/` (đặc trưng → tiên nghiệm Dirichlet/Beta → LightGBM phần dư → hiệu chỉnh,
walk-forward, ROI) là KHUNG THÁCH ĐẤU, không nằm trong pipeline. Ngày 03-10-2026 nó không
hơn dự báo hằng số trên 1 000 kỳ và không thắng ML production, nên không được đề bạt
(`documentation/research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md`). Ý tưởng mô hình mới
phải qua `scripts/research/benchmark_probability_models.py` (kèm `--power-check`) trước; chỉ đề
bạt khi thắng CẢ hằng số LẪN mô hình đang chạy. Bộ lọc "lô nhiều nháy" `src/forecast/multi_hit_vip.py`
(08-10-2026) cũng là khung thách đấu: top-5 trúng 2,91% trên 4 228 kỳ, đúng bằng chọn bừa trên chính các kỳ ấy, nên không
vào tổ hợp xác suất; mọi xác suất/Confidence nó in ra đều suy từ walk-forward, đừng viết cứng
(`documentation/research/2026-10-08-lo-nhieu-nhay.md`). Lượt thử thứ hai (12-10-2026,
`src/forecast/multi_hit_benchmark.py`, vỏ dòng lệnh `scripts/research/benchmark_multi_hit.py`): 22 chiến lược kể cả
logistic/GBM, chọn trên giai đoạn phát triển, kiểm một lần trên 1 000 kỳ cuối — không đạt; hạng giữa
hai giai đoạn tương quan −0,02. Trang `docs/lo-vip-nhieu-nhay.html` (13-10-2026) in cả hai TỪ số đo:
`multi_hit_report.py` ghi `data/multi_hit/vip.json` mỗi ngày; `benchmark.json` là phép kiểm MỘT
lần, đóng băng ở `SECOND_ROUND_UNTIL` (12-10-2026) — đừng dời ngày ấy hay đo lại trên cửa sổ trượt
(nhìn lại cùng tập kiểm ở cùng α làm sai số loại I cộng dồn); muốn kiểm kỳ mới thì đăng ký phép kiểm
tiến cứu mới. Bộ lọc thì đo lại MỖI ngày, nên mức tin của nó dùng p luôn hợp lệ (e-process,
`multi_hit_report.anytime_p`): 2 000 lịch sử không kỹ năng xem lại sau mỗi kỳ với p thường vượt 0,05 ở
30,9%, với p luôn hợp lệ ở 3,45%. e-process CHỈ chạy trên kỳ quay sau ngày chốt của mô hình đang in
(`multi_hit_forecast.FROZEN_AT` = 15-10-2026; bộ lọc VIP cũ: `VIP_FROZEN_AT` = 12-10-2026): mô hình được
thiết kế sau khi đã xem lịch sử trước đó, nên walk-forward hồi cứu chỉ là mô tả.
Từ 15-10-2026 năm con trên trang là DỰ BÁO KỲ SAU của mô hình Lô VIP (`src/forecast/multi_hit_forecast.py`), theo
yêu cầu "dựa trên dữ liệu và kinh nghiệm cầu kèo, không phải thống kê hôm nay": đặc trưng cầu kèo của
`cau_keo_ml` (trừ 6 đặc trưng định danh/lịch), số cầu hai nháy (≥ 2 kỳ) và cầu LOTO (≥ 3 kỳ) đang chạy báo
con ấy — đếm khớp `bridge_rules.find` —, và dữ liệu nhiều nháy; logistic, C chọn bằng thẩm định trong theo
thời gian, walk-forward học lại mỗi 250 kỳ, xác suất in ra hiệu chỉnh Platt CHỈ trên lượt chọn ngoài mẫu
của các khối trước; lý do mỗi con = đóng góp dương lớn nhất. Năm con công bố do mô hình CỦA KHỐI đang chạy
chọn (`WalkForward.forecast`) — đừng học lại trên mọi kỳ để công bố: phần tiến cứu sẽ chấm năm con khác năm
con người đọc đã thấy. Kỳ được dự báo bỏ qua `known_non_draw_days` (`next_draw_date`), và đặc trưng thứ/tháng/
năm của kỳ ấy tính theo đúng ngày quay (`build_cau_keo_feature_frame(next_date=...)`). Đo đến 15-10-2026: 2,99% so với 2,92% chọn bừa
(z = +0,58), xác suất đã in TB 2,86%; kinh nghiệm cầu hai nháy ngang mức chung (0 cầu 2,94%, 1–4 cầu
2,82%, 5+ cầu 3,95% trên 481 lần) — trang in các số ấy TỪ phép đo, đừng viết "tỉ lệ cao"
(`documentation/research/2026-10-15-lo-vip-cau-keo.md`, `tests/forecast/test_multi_hit_forecast.py`). Đã nghỉ: bộ
lọc VIP (chỉ số phân tán đẩy con gan lên đầu — con 32 đứng đầu mười kỳ khi gan 10 → 19 kỳ) và luật lô rơi
(chỉ liệt kê con vừa về). `build_cau_keo_feature_frame` nhận `raw`/`two` để kiểm trên lịch sử giả định.
`build_multi_hit_page.py` suy "hơn / không hơn / chưa kết luận"
từ mức tin, ứng viên lượt hai và phép kiểm độ nhạy. Từ 13-10-2026 trang GỌN theo yêu cầu: năm con ≥ 2 nháy và
năm cặp xiên 2 (`src/forecast/multi_hit_pairs.py`: số kỳ cùng về trong 100 kỳ, luật chốt trước, mốc C(d, 2)/4 950
cùng kỳ; 4 133 kỳ trúng 5,49% so với 5,52% chọn bừa) ở trên cùng, mỗi khối MỘT dòng số đo; giải thích
thu vào «Chi tiết phép đo». Cặp không có phép kiểm độ nhạy nên chỉ được nói "chưa có bằng chứng", không
"không hơn". `benchmark.json` có phiên bản riêng (`BENCHMARK_VERSION`): đổi khuôn `vip.json`
(`MEASURE_VERSION`) không được mở lại phép kiểm một lần. `tests/forecast/test_multi_hit_page.py` dựng cả lịch sử
có cài tín hiệu để trang PHẢI nói "hơn" — đừng viết sẵn câu kết luận nào. Top-5 Đặc Biệt từng ra 7,0% chỉ vì PMI làm
trơn sai (cặp chưa có dữ liệu được PMI = log N); sửa xong còn 5,4% — đừng trích nó như tín hiệu.

## Kho tri thức và lời giải thích — 13-10-2026

`src/forecast/knowledge_base.py` (kiến trúc: `documentation/architecture/2026-10-13-he-suy-luan-va-tu-hoc.md`)
lấp phần "tự bổ sung tri thức" của yêu cầu hệ suy luận/tự học; phần bầu chọn có trọng số và tự chỉnh
trọng số ĐÃ có ở `online_learning` (Hedge hai trí nhớ, cổng đề bạt), đừng dựng bản thứ hai. Luật trễ
"a về → b về kỳ sau" được khai phá mỗi `DISCOVERY_EVERY` = 30 kỳ, ĐÓNG BĂNG khi đăng ký (định nghĩa,
ngày, số trong mẫu) và chỉ chấm trên kỳ SAU ngày đăng ký bằng e-process; "có bằng chứng" khi e đạt
ngưỡng GHI LÚC ĐĂNG KÝ: lô k được α·6/(π²k²) (`batch_alpha`), tổng mọi lô ≤ α. Đừng quay lại ngưỡng
N/α theo số luật hiện có: lô k bị xét ở α/k, tổng điều hoà không bị chặn; chỉ số lô đếm tiếp qua thí
nghiệm đã nghỉ (`batches_spent`). 15 họ của `confidence_matrix` vào kho là ẢNH CHỤP (p tính lại mỗi ngày
trên lịch sử dồn), không bao giờ "có bằng chứng"; Holm trên mọi họ chỉ phân loại. Lift trong mẫu không bao giờ là bằng chứng. Bộ nhớ ngữ cảnh (cosine, bỏ
30 kỳ chồng cửa sổ) kém hằng số trên 1 000 kỳ (z = −11,2) nên CHỈ là thông tin mô tả trong lời giải
thích, không vào tổ hợp. `explain()` in đúng xác suất đã công bố; nền + Σ đóng góp = hỗn hợp Hedge
(`tests/forecast/test_knowledge_base.py` canh). Bước pipeline chạy sau `online_learning`, `confidence_matrix` và `multi_hit_report`.
Đổi bất kỳ tham số nào trong `rule_config()` (kể cả `VERSION`, `HORIZON`, lưới cược) thì `carry_over`
cất nguyên lô cũ vào `retired` — KHÔNG chấm lại bằng luật chấm mới — và đăng ký lô mới ngay.
Ngân sách α (`alpha_budget`) chốt khi tạo kho: đổi `ALPHA` trên kho đã có bị `run` từ chối.

## Phương pháp "tổng – bóng – chạm" của chuyên mục bài dự đoán — 05-10-2026

`src/soi_cau/digit_sum_rules.py` hệ thống hoá năm quy tắc của loạt bài tuần (đầu/đuôi Đặc Biệt từ tổng
2 số cuối/đầu ĐB và bóng; chạm từ tổng 2 số cuối giải nhất; lô cặp G5; song thủ G2–G1), khớp
TỪNG con số in trong bài (`tests/soi_cau/test_digit_sum_rules.py`). Loạt bài hằng ngày không tái lập được.
Kiểm 4 225 kỳ: cả năm ngang chọn bừa; "nổ như dự đoán" là do chấm theo khung (đầu ĐB cả tuần chọn
bừa cũng nổ 78,4%). Chúng là MÔ TẢ, không vào tổ hợp xác suất. Mốc chấm LOTO là xác suất CÓ
ĐIỀU KIỆN theo số con đã về ở kỳ ấy, p Poisson-nhị thức, Holm cho năm quy tắc — khớp từng số với bộ
`xsmb_methods` chủ dự án gửi. `src/research/digit_sum_hypothesis.py` là phép kiểm TIẾN CỨU đã đăng ký
05-10-2026 (từ kỳ 06-10, 180 kỳ, α = 0,01 sau Holm), sổ cái `data/hypotheses/digit_sum_rules.csv`
giữ lần ghi đầu; KHÔNG sửa tham số. Chi tiết:
`documentation/research/2026-10-05-phuong-phap-bai-du-doan.md`; kỹ năng `soi-cau`.

## Độ tin cậy dự báo — hiệu chỉnh đa kiểm, không phải hậu nghiệm thô

`src/evaluation/confidence_matrix.py` dựng Confidence Score ba tầng (High: cả Bayes,
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

`src/research/hot_tail_test.py` là phép kiểm TIẾN CỨU đã đăng ký ngày 28-09-2026 (từ kỳ
29-09, 180 kỳ, một phía α = 0,01). KHÔNG sửa tham số của nó: muốn đổi thì đăng ký giả
thuyết mới với ngày bắt đầu mới. Sổ cái `data/hypotheses/hot_tail.csv` giữ lần ghi đầu.
Chi tiết: `documentation/research/2026-09-28-duoi-4-va-gia-thuyet-duoi-nong.md`.

## Soi cầu vị trí — đúng luật của trang tham chiếu, kèm kiểm chứng

`src/soi_cau/position_bridges.py` dò cầu trên 107 vị trí chữ số (ĐB 0–4 … G7 99–106),
`build_position_bridges.py` in `docs/soi-cau-vi-tri.html` và ô "cầu đẹp nhất"
cạnh bảng LOTO ở trang chủ (cột `.tr-day-extra` của `render_result_board`). Luật
đã đối chiếu từng con số với trang tham chiếu ngày 29-09-2026 và bị ghim trong
`tests/soi_cau/test_position_bridges.py`: lộn thì CỘNG GỘP nháy của cả hai chiều; cầu
chạy theo KỲ QUAY; số kép chỉ là một số — số bóng (44 → 99) chỉ HIỆN kèm, tính nó
vào phép trúng thì ra 64 cầu thay vì 43. Bản JS (`templates/position_bridges.js`)
tính lại cho mọi tham số và phải ra đúng từng cầu như bản Python —
`tests/frontend/position-bridges.test.mjs` so tám bộ tham số.

Cầu dài KHÔNG trúng nhiều hơn: trên 4 217 kỳ, cầu LOTO đã chạy ≥ 10 kỳ trúng tiếp
39,2% so với kỳ vọng 40,5%; nhiều cầu cùng báo một cặp cũng không hơn. Trang in
kết luận ấy TỪ SỐ ĐO (`verdict`), đừng viết cứng. Đừng thêm "điểm tin cậy" theo độ
dài cầu. Thứ tự ô "đẹp nhất" là quy tắc tự đặt (độ dài, rồi số cầu cùng báo).

### Cầu theo đường (`path_prob`, trang `soi-path-*`) — Bayes thực nghiệm, 16-10-2026

Xác suất kỳ tới của một đường cầu KHÔNG phải tỉ lệ lịch sử của nó: cầu được chọn top 300 từ ~5 671
cầu mỗi độ trễ nên tỉ lệ ấy mang lời nguyền người thắng (nhánh ổn định từng in tổng LOTO 24,40 so với
23,76). `fit_paths_with_evidence` học `BridgeEvidence` từ MỌI cầu của mọi độ trễ: `p_post` co phần
riêng theo mức chênh thật giữa các cầu (`fit_shrinkage_to_prior`, một tâm và một κ chung cho 30 độ
trễ — tâm riêng từng độ trễ là đưa cú sốc theo kỳ vào), và nhánh "đang chạy" cộng `streak_shift` —
tỉ lệ trúng tiếp theo độ dài chuỗi, co bằng DerSimonian–Laird với phương sai THEO CỤM KỲ QUAY
(`streak_experience`; phương pháp mô men không trọng số giữ 1,4 điểm % nhiễu ở nhóm ít dữ liệu,
và coi hàng nghìn cầu cùng kỳ là độc lập thì cú sốc theo kỳ thành τ² dương), đo so với tỉ lệ riêng
THÔ của từng cầu bỏ ra chuỗi đang chạy (không phải tỉ lệ chung hay `p_post`: thế là tính chất lượng
cầu hai lần). Phần riêng giữ
`N/(N + κ)` theo số lần chấm của TỪNG độ trễ; trang in phạm vi/độ trễ đúng cấu hình. Đo 15-10-2026 trên cửa sổ 2 000 kỳ của pipeline: độ tản
giữa 170 130 cầu bằng 1,00 lần nhị thức, chuỗi 0–8+ trúng tiếp 23,5–24,0% so với nền 23,8% — mọi cầu co
về nền. Walk-forward 2 000 kỳ trên cửa sổ production: nhánh LOTO ổn định mới hơn cũ z = +9,69 (tổng 24,42 → 23,84), đang chạy z = +0,22; tổ hợp không đổi (z = −0,09; +1,01) vì `finalize_blend` đã neo mức; nhánh mới ngang hằng số ở cả bốn ô (LOTO z = +0,12 / −0,62). Phép đo chạy theo phần (`--parts/--part/--merge`); bước gộp đòi cùng danh tính lượt đo. Đừng quay lại độ co đặt tay, và đừng in `p_mean` như xác suất (cột "Tỷ lệ lịch sử" là thống kê
trong mẫu). Trang in câu kết luận TỪ `bridge_evidence_<mode>.json`
(`documentation/research/2026-10-16-tran-du-bao-va-suy-luan-cau.md`, `tests/soi_cau/test_bridge_inference.py`).
Trần dự báo của cả hệ thống (lệch chữ số, phụ thuộc giữa các kỳ, mô hình tần suất gần) đo bằng
`scripts/research/audit_forecast_ceiling.py`: không có cấu trúc nào để học; kỹ năng đã công bố
không phân biệt được với 0.

### Bảy kiểu cầu của trang tham chiếu thứ hai + phôi tuần

`src/soi_cau/bridge_rules.py` + `build_bridge_pages.py` in bảy trang `docs/soi-cau-*.html`
(LOTO, hai nháy, bạch thủ, Đặc Biệt, bộ số, Đặc Biệt theo thứ, LOTO theo thứ) và
`docs/tao-phoi-tuan.html`. Mọi kiểu dùng cặp vị trí a < b, số `10·d[a]+d[b]`; chỉ
luật "bước trúng" khác nhau — ghi trong docstring và bị ghim từng ô bởi
`tests/soi_cau/test_bridge_rules.py` với `tests/fixtures/bridge_reference_2026-09-28.json`.
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
`tests/repo/test_workflow_shell_behaviour.py` chạy nguyên khối lấy từ YAML bằng
đúng lệnh shell của GitHub, chỉ thay đồng hồ, lệnh ngủ, nguồn và lệnh đẩy.
Soi chuỗi trong YAML không thấy được lỗi hệ bát phân của `$(date +%H)` hay
một vòng thử lại tự kẹt giữa rebase — cả hai đã xảy ra thật.

Số kiểm thử và bằng chứng phát hành gần nhất nằm trong PR và `documentation/qa/`.
Bốn kịch bản chốt phát hành
(`release_check.sh`, `domain_challenger_check.sh`, `number_integrity_check.sh`,
`research_release_check.sh`) cũng xanh. Đỏ một phép kiểm nghĩa là thay đổi của
bạn làm đỏ nó — không có sẵn phép kiểm đỏ nào để đổ lỗi.

## Nguồn & bằng chứng suy luận của con số — 03-10-2026

Theo yêu cầu ngày 10-10-2026, mọi trang KHÔNG hiện tooltip khi rê chuột hoặc
nhận tiêu điểm từ chuột; bỏ cả tooltip mặc định từ `title` HTML/SVG, giữ nội
dung mô tả cho trình đọc màn hình. Các ô Vietlott không gạch chân khi hover.
Mọi con số trong `#app-main` vẫn có gợi ý khi điều hướng BẰNG BÀN PHÍM (nguồn
tóm tắt, số bước, gợi ý thao tác) và ngăn kéo `<dialog>` (nhấp: ngữ cảnh, nguồn, các bước,
độ tin cậy nếu có). `src/web/assets/app-evidence.js` dùng ủy quyền sự kiện ở cấp
tài liệu nên phủ cả bảng do JS dựng sau khi tải; nhận diện "con số" bằng chữ
của phần tử (≤ 24 ký tự, khớp `NUM`), không gắn lớp sẵn cho từng ô.

- Danh mục: `src/web/evidence_catalog.py` → khối `#app-evidence-data` trong
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
  `src/web/assets/nexlink`, giữ đúng đường nét, opacity và header. Từ 05-10-2026,
  rail theo thứ tự nhóm trong `SITE_NAV`: Kết quả → Vietlott → Thống kê → Thống kê LOTO →
  Thống kê Đặc Biệt → Soi cầu → Dự báo → Nghiên cứu & công cụ. Tám nút nhóm
  có nhãn ngắn; tìm kiếm và đóng menu là hai nút riêng ngoài tablist. Không
  thêm lại hai lối tắt lặp với menu con. Mũi tên, Home/End chọn nhóm; chỉ nhóm
  đang chọn có `tabindex=0`.
  Sidebar dùng outline Flaticon Rounded chuyển nguyên hình học sang SVG.
  `nexlink_icons.py` là renderer của shell; không thay bằng Lucide tương tự.
  Lucide tại `src/web/assets/icons` chỉ còn dùng trong nội dung/global search.
  Mọi bộ icon có provenance; không vẽ lại hoặc dùng Unicode/icon font.
- Mọi bề mặt/chữ/viền/control/modal phải đọc token; màu có nghĩa dữ liệu dùng
  cặp token riêng, kiểm AA cả hai theme. Không dùng OS media riêng để bỏ qua
  lựa chọn sáng tường minh. Bản in đặt lại token sáng để chữ đọc được.
- Sửa ui_theme thì dựng ui.css, chạy `scripts/web/extract_critical_css.py`, rồi
  dựng HTML bằng process mới để không giữ module critical đã import.
- `tests/frontend` chạy bằng `npm ci --prefix tests/frontend` và
  `npm test --prefix tests/frontend`; fixture shell lấy từ generator nguồn.

Đặc tả: `documentation/architecture/2026-09-26-theme-search-icons-design.md`.
