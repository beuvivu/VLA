# Soát sâu, tự sửa và tự phục hồi — 25-09-2026

Bản ghi cho chỉ thị "deep code audit, auto-fix & self-healing". Cùng nguyên
tắc với [`vla-deep-audit-report.md`](vla-deep-audit-report.md): **một phát
hiện chỉ được ghi là lỗi sau khi tái hiện được**, và **một bản vá chỉ được ghi
là xong sau khi đo lại**. Mục nào chưa đo thì ghi là chưa đo.

## 1. Trạng thái lúc bắt đầu

| | |
| --- | --- |
| `main` | `08ff523e` — cây sạch |
| Nhánh làm việc | `claude/statistical-audit-2026-09-lwfyt2`, dựng lại từ `main` (bản cũ đã trộn hết vào `main`) |
| PR đang mở | 6, đều của Dependabot (#79–#84), không đụng tới |
| Lượt chạy đỏ trong cửa sổ soát | 2: `live-results` #164 (23-09), `daily_prediction` 36037174777 (24-09) |
| Bộ kiểm trên `main` | **đỏ 2** — xem F-01. `CLAUDE.md` ghi "xanh hết" là đã cũ |

### Kiến trúc thật

Chỉ thị giả định có máy chủ, cơ sở dữ liệu, API. Kho này không có cả ba:

- **Thu thập và tính toán:** workflow GitHub Actions theo lịch
  (`daily_update`, `update-data`, `daily_prediction`, `live-results`,
  `watchdog`, `post-finalization`).
- **Lưu trữ:** JSON/CSV commit thẳng vào kho; ảnh chụp trực tiếp nằm ở nhánh
  `live` (một tệp, đẩy đè).
- **Phục vụ:** GitHub Pages tĩnh từ `docs/`, do `pages.yml` và job
  `deploy-pages` triển khai.
- **Worker:** `worker/` là một Cloudflare Worker có đồng hồ riêng — **chưa
  triển khai** (`wrangler.toml` còn `id = "THAY_BANG_ID_KV_CUA_BAN"`).

Vì thế "tự phục hồi lúc chạy" ở đây nghĩa là: lịch chạy dư, nhóm
`concurrency` xếp hàng, thử lại có giới hạn với lỗi thoáng qua, mỗi lượt
dựng SỬA được trạng thái hỏng của lượt trước, và cổng kiểm làm lượt chạy đỏ
khi đầu ra sai hình. Không có tiến trình chạy dài nào để gắn circuit breaker.

## 2. Phát hiện và bản vá

### F-01 · P1 · `docs/live.html` dày thêm một lớp khung mỗi lượt pipeline

**Tái hiện.** Đếm `class="app-rail"` qua lịch sử tệp:

| Commit | Lúc (giờ VN) | Số lớp khung |
| --- | --- | --- |
| `cf91acf0` (nhánh PR #88) | 24-09 07:13 | 1 |
| `30e0c82e` | 24-09 16:33 | 2 |
| … mỗi lượt `chore: finalize analytics` +1 … | | |
| `85f02a68` | 24-09 22:54 | **11** |

Tệp phình thêm 267 830 byte; 429 biểu tượng thay vì 39. Gọi
`ui_theme.refresh_live_page` ba lần trên bản 1 lớp cho ra 2, 3, 4 lớp.

**Nguyên nhân gốc.** `ui_theme.dock()` trả về `<nav class="ui-dock">` và
NGAY SAU là một `<script>`. `wrap_page` chỉ gỡ `<nav>`, nên thẻ `<script>` mồ
côi nằm lại **sau** đuôi khung cũ. `_DUOI_KHUNG` neo ở cuối phần thân (`\Z`),
nên bước bóc trượt, bỏ cuộc và bọc thêm lớp nữa. Hai chỗ khác chặn đường
sửa: lớp trong đã bị đổi `<main>` → `<div>` nên bước bóc không nhận ra, và
trần bóc là 8 vòng, ít hơn chính 11 lớp đo được.

**Hồi quy do đâu.** PR #88 viết lại `_DOCK_CU`. Bản cũ là
`<nav class="ui-dock".*?</nav>\s*(?:<script>.*?</script>)?` — gỡ CẢ kịch bản.
Bản mới khớp thẻ nav chặt hơn nhưng làm rơi đúng phần
`(?:<script>.*?</script>)?`. Không phép kiểm nào đỏ, vì phép kiểm bọc chồng
khi ấy không dựng kịch bản dock. Lượt pipeline đầu tiên sau khi trộn #88
(`30e0c82e`, 16:33) là lượt đầu tiên cho ra 2 lớp.

**Là tái phát.** A-01 của báo cáo trước chính là lỗi này trên chính trang
này. Phép kiểm khi ấy dựng một khung lồng có `<main>` ở lớp trong và không có
kịch bản dock, tức là một hình dạng chưa từng xảy ra.

**Cùng nguyên nhân, trên 25 trang khác:** kịch bản dock mồ côi 1 057 byte, là
mã chết (tự thoát vì không thấy `.ui-dock`, đo được 0 lỗi JS).

**Bản vá** (`src/app_shell.py`, chỗ duy nhất bọc khung):
`_DOCK_KICH_BAN` gỡ cả kịch bản đi kèm dock; bước bóc nhận cả
`<div class="app-main" id="app-main">`; `_DUOI_KHUNG` nhận `</main>` hoặc
`</div>`; trần bóc 64 vòng (mỗi vòng làm chuỗi ngắn đi nên không thể treo).

**Đo lại.** Tệp 11 lớp → 1 lớp sau một lượt, lượt thứ hai trùng từng byte;
bản sửa **trùng từng byte** bản dựng lại từ `cf91acf0` (bản 1 lớp cuối cùng
còn tốt), tức không mất nội dung. Ghi lại 29 trang: 25 trang chỉ khác đúng
đoạn kịch bản dock, `live.html` về 1 lớp, 3 trang không đổi, `docs/assets/`
không đổi. Chromium ở 1440px: 3 nút đầu dải biểu tượng đều nhận được cú bấm
(`elementFromPoint`), 0 lỗi JS.

**Phép kiểm** (`tests/test_app_shell.py`): dựng ĐÚNG hình dạng pipeline đã
tạo ở 2, 8, 11, 12 lớp; `refresh_live_page` gọi 5 lần giữ 1 lớp và trùng từng
byte; không trang xuất bản nào mang kịch bản dock. Đột biến — bỏ gỡ kịch bản,
chỉ tìm `<main>`, trần 8, đuôi chỉ `</main>` — đều làm đỏ.

**Vì sao không ai thấy suốt một ngày:** bước "Xác minh các đầu ra" của
`update-data.yml` chỉ kiểm tệp có tồn tại (`test -s`). Thêm job
`verify-published-pages`: chạy bốn tệp kiểm bất biến trang trên commit vừa
đẩy. Nó cố ý **không chặn** dữ liệu hay `deploy-pages`, chỉ làm lượt chạy đỏ.
Đã thử trong venv chỉ có `pytest` + `beautifulsoup4`: 199 xanh trên bản sửa,
**3 đỏ** trên `live.html` của `main`.

### F-02 · P1 · Một lỗi HTTP 500 giết cả khung thăm dò trực tiếp 60 phút

**Tái hiện.** `live-results` #164: `git push --force … refs/heads/live` nhận
`remote: Internal Server Error` MỘT lần; với `set -e` bước chết ngay.

**Bản vá.** `push_snapshot`: 3 lần thử, giãn cách tăng dần kèm nhiễu; hết lượt
thì KHÔNG thoát mà để vòng thăm dò kế tiếp đẩy lại. Vòng chỉ dừng khi kết quả
đã xác minh VÀ chính ảnh chụp ấy đã lên nhánh `live`. Hỏng dai dẳng thì hết
`MAX_SECONDS` rồi dừng, không lặp mãi.

Bước kích hoạt hoàn tất dữ liệu ngày cũng không thử lại: nay thử lại tối đa 4
lần **chỉ** với 5xx và lỗi mạng; 4xx (quyền, cấu hình) đỏ ngay.

### F-03 · P2 · Phép tính giờ đọc "08", "09" là hệ bát phân

`now_min=$(( $(date +%H) * 60 + $(date +%M) ))`. **Đính chính một nhận định
của chính tôi:** tôi từng viết là bước "chết lúc 18:08". Đo trên bash 5.2 thì
khác: `set -e` không bắt được lỗi này, bash bỏ ngang CẢ vòng `while` rồi chạy
tiếp. Hệ quả thật: lượt nổ lúc 17:08, 16:09 hay trong giờ 08, 09 bỏ qua bước
chờ và trần 90 phút, thăm dò ngay giờ trống, rồi hết 60 phút đúng lúc kỳ quay
bắt đầu. Trong 100 lượt gần nhất chưa lượt nào khởi động trước 18:08 (cron
trễ 2,5–6 giờ), nên lỗi đang **ngủ**. Nó sẽ thức đúng ngày đường chạy đúng giờ
được dựng. **Bản vá:** đọc đồng hồ một lần, ép cơ số `10#`.

### F-04 · P2 · Vòng đẩy lại của `daily_prediction.yml` tự kẹt

**Tái hiện.** Lượt 36037174777: lượt khác vừa đẩy dự đoán cùng kỳ,
`pull --rebase` xung đột ở `data/predictions_today.json` và để cây ở giữa
chừng; ba lần thử sau đều chết vì "unmerged files".

Hai lỗi đi kèm, cùng được sửa:
- **Dự đoán cũ đè lên dữ liệu mới.** Khi nhánh chính vừa có kỳ mới mà không
  xung đột, `pull --rebase` vui vẻ đẩy một dự đoán dựng trên dữ liệu CŨ.
- **Commit rác.** Đêm 24-09 có 8 commit "dự đoán cho kỳ 2026-09-25" chỉ khác
  dấu thời gian; hai lượt nối nhau là đủ xung đột.

**Bản vá.** Mỗi lần thử: bỏ rebase dở, `reset --hard` về đầu nhánh chính,
sinh lại dự đoán trên nền ấy. Không commit khi chỉ khác dấu thời gian.

**Bản vá chưa đủ, phát hiện SAU khi trộn PR #89.** Lượt pipeline đầu tiên sau
khi trộn vẫn cho ra commit rác `b8afdc7f`: xác suất lệch 1,08e-10 vì hai runner
khác CPU không cho kết quả trùng từng bit. Phép so "bỏ dấu thời gian rồi so
tuyệt đối" không nuốt được nó. Lần sửa thứ hai (PR sau #89) so số thực theo
**sai số tuyệt đối** 1e-8. Không dùng sai số tương đối: `lift` (xác suất trừ
đường cơ sở, cỡ 8e-4) mang nguyên nhiễu tuyệt đối nên lệch tương đối tới
1,3e-7 — bản đầu của lần sửa này dùng 1e-9 tương đối và trượt đúng ở đó; phép
kiểm tổng hợp không thấy, chỉ thử trên cặp commit thật mới lộ. Đo trên 59 cặp
commit liên tiếp của `data/predictions_today.json`: **54 là commit rác, 5 là
thay đổi thật**, và phép so mới không nuốt nhầm thay đổi thật nào.

**Phép kiểm cho F-02, F-03, F-04** (`tests/test_workflow_shell_behaviour.py`):
chạy NGUYÊN khối `run:` lấy từ YAML bằng đúng lệnh shell GitHub dùng; chỉ
thay đồng hồ, lệnh ngủ, nguồn và lệnh đẩy. Bước ghi dự đoán chạy git THẬT
trên một kho trần cục bộ. Workflow của `main` đỏ 9/20 và 3/3 phép kiểm tương
ứng. Chín đột biến (từng bản vá gỡ riêng) đều làm đỏ.

### F-05 · P3 · Kịch bản soi sổ kết quả đo một trạng thái sai

`scripts/check_traditional_results_page.py`: biến `in_range` được tính nhưng
không bao giờ kiểm (ruff F841). Thêm phép kiểm thì nó đỏ ở cả hai múi giờ:
khoảng 22→24-09 hiện 0 kỳ, vì vòng lọc thứ phía trên để bộ lọc ở thứ bảy.
Tức là phép kiểm "rỗng vì lọc thứ" trước nay vẫn xanh, nhưng trên một tiền đề
chưa từng được đo. Trả bộ lọc về "tất cả" trước khi đo khoảng thì xanh. Kèm
W605 (`\d` trong chuỗi thường).

### F-06 · Cặp số — không có lỗi, thêm phép kiểm cho cả 100 con

`77-77` thay vì `22-77`: **không tái hiện được**, như lần trước. Đo lại:
50 họ, mỗi con đúng một họ, 0 cặp tự lặp; quét `docs/` loại nhãn ngày còn đúng
năm cặp kép-bóng. Thêm phép kiểm tham số hoá trên cả 100 con (đối xứng, không
tự ghép, kép → kép bóng, còn lại → số lộn) và phép kiểm đọc chính
`window.__D_CAP50__` trên ≥10 trang xuất bản. Đột biến nguồn và đột biến
trang đều làm đỏ.

## 3. Đã kiểm, không phải lỗi

| Hạng mục | Đo được |
| --- | --- |
| Mô phỏng / vòng lặp vô hạn | Không có `while True` / `for (;;)`. Đã đọc từng vòng `while` trong `src/`, `docs/assets/`: mọi vòng đều tiến (tăng chỉ số, thêm phần tử, thu ngắn) hoặc có trần. Chỗ duy nhất trông như đứng yên — `i = end` ở nhánh chú thích `//` của `page_output` — vẫn tiến vì `end ≥ i + 2` |
| Rò rỉ thời gian | Đã có phép kiểm "đột biến tương lai không đổi quá khứ" cho đặc trưng, thống kê, điểm ứng viên, cầu. `path_backtest.py` cắt huấn luyện tới `idx_train_end`, đích đúng ngày kế — và không nơi nào gọi tới nó |
| Chọn nhanh | Dựng sẵn lúc build, không tải lúc chạy nên không có trạng thái đang tải/lỗi. 3/4 trang có 10 số; `soi-path-de-active` hiện trạng thái rỗng có giải thích (Đặc Biệt một số/ngày, chuỗi đang chạy ≥3 cực hiếm) |
| Giao diện, 29 trang × 7 bề rộng (375–1920) | 203 lượt: **0 lỗi JS**. Tràn ngang 5/203, đều ở `landing_desktop.html` dưới 1024px — trang "Mở giao diện máy tính", rộng cố ý. `live.html` 404 `data/live.json` chỉ khi phục vụ cục bộ (bản thật đọc nhánh `live`) và đã có trạng thái lỗi "Sẽ thử lại tự động" |
| Dải biểu tượng trên điện thoại | Nằm ở x = −80 trên MỌI trang, mở bằng `app-toggle` — thiết kế, không phải lỗi |
| `compileall` | sạch |
| `pip check` | "No broken requirements found" |
| `ruff check` (cấu hình kho) | 2 lỗi, cả hai trong F-05, đã sửa → sạch |

## 4. Bị chặn — cần chủ dự án

| Việc | Vì sao bị chặn | Việc cần làm |
| --- | --- | --- |
| Chạy đúng giờ | Cron của GitHub trễ 2,5–6 giờ (đo lại 24-09: lượt live nổ 19:07–22:47 giờ VN). `repository_dispatch: live-window` có **0 lượt từ trước tới nay** | Hoặc dựng bộ hẹn giờ ngoài theo `documentation/operations/on-time-trigger.md`, việc này cần PAT: theo `CLAUDE.md`, token không bao giờ đi qua phiên này. Hoặc triển khai Worker theo `documentation/operations/live-worker.md`, cần tài khoản Cloudflare |
| `github-advanced-security` | `CAPIError: 400 The requested model is not supported` — phía GitHub | Không sửa được trong kho |

## 5. Cố ý KHÔNG làm

- **Không** dựng tác tử tự sửa mã đang chạy. Chỉ thị tự nói vậy, và kho không
  có tiến trình chạy dài nào để nó sửa. Lỗi mã đi qua PR, phép kiểm, CI.
- **Không** thêm workflow tự kích hoạt chính nó.
- **Không** thêm `mypy`: kho chưa cấu hình, và chỉ thị dặn không thêm công cụ
  khi nó va với kiến trúc. **Không** chạy `ruff format` hàng loạt: 188 tệp
  lệch định dạng, `pyproject.toml` ghi rõ định dạng cố ý không chặn.
- **Không** đụng dữ liệu lịch sử, mô hình, trọng số hay phép tính thống kê.
- **Không** gỡ `ui_theme.dock()` khỏi các trình dựng. Nó đã vô hại vì
  `wrap_page` gỡ sạch; gỡ tận gốc là việc dọn riêng, lớn hơn phạm vi này.

## 6. Kết quả phép kiểm

Đo trên cây đã commit của nhánh, không đụng tới trong lúc chạy:

| | Kết quả |
| --- | --- |
| `pytest tests` | **2 104 xanh, 0 đỏ** (trên `main` trước bản vá: đỏ 2 vì F-01) |
| `release_check.sh` | xanh — dựng lại 29 trang bằng trình dựng thật: mỗi trang đúng 1 khung, 0 kịch bản dock |
| `domain_challenger_check.sh` | xanh |
| `number_integrity_check.sh` | xanh — 4 215 kỳ, 113 805 ô giải |
| `research_release_check.sh` | xanh |
| `ruff check .` (cấu hình kho) | sạch |
| `compileall` / `pip check` | sạch |

Bốn kịch bản chốt chạy trong một git worktree riêng, vì `release_check.sh`
dựng lại `docs/` — chạy chung cây với bộ kiểm là để hai lượt giẫm lên nhau.

## 7. Xác minh sau khi trộn PR #89 (`36e65445`)

| | Đo được |
| --- | --- |
| `pages.yml` #104 | xanh; triển khai `docs/` của `36e65445` — 29 trang, mỗi trang đúng 1 khung, 0 kịch bản dock |
| `update-data.yml` #589 (bị push kích hoạt) | 4/4 job xanh, **gồm cả `verify-published-pages` chạy lần đầu trên commit thật của pipeline** |
| `docs/live.html` sau lượt pipeline thật (`3a9d574b`) | **1 lớp, không đổi byte nào** — trước bản vá, mỗi lượt như thế thêm một lớp |
| `daily_prediction` sau đó (`b8afdc7f`) | còn một commit rác vì nhiễu dấu phẩy động → sửa ở PR sau, xem F-04 |

Không đọc được trang thật trên `github.io` từ môi trường phát triển (proxy trả
403), nên phép xác minh dựa vào nội dung của đúng commit đã triển khai và lượt
`pages.yml` xanh — không dựa vào việc mở trang.

## 8. Xác suất LOTO / Đặc Biệt "sai lệch khá nhiều" — đo rồi mới sửa

Yêu cầu của chủ dự án: xác suất lệch nhiều, cần đẩy mạnh ML tự học. Đo trước.

**Xác suất ĐÃ CÔNG BỐ** (`data/predict/predict_next_*_all_<ngày>.csv`, 28 kỳ
10-08 → 24-09, chấm với kết quả quay thật):

| | Kỹ năng so với cơ sở | Lớn nhất từng công bố |
| --- | --- | --- |
| Đặc Biệt | −0,03% ± 0,32% | 1,28% (cơ sở 1%) |
| LOTO | −0,013% ± 0,038% | 25,9% (cơ sở 23,8%) |

Tức là con số người xem nhận đã ở đúng mức tối ưu của một cuộc quay công bằng;
không mô hình nào nâng được xác suất trúng thật lên trên mức đó.

**Những chỗ lệch thật:**

- **F-07 · Cổng ML xếp chồng so với một đối thủ hỏng — ĐÃ SỬA.** LOTO: tổ hợp
  tuyến tính hiệu chỉnh chọn a=4,89 (làm NHỌN) trên chính ngày được khớp, cho
  logloss 1,0157 trên lát thẩm định, tệ gần gấp đôi hằng số (0,5457). Mô hình
  xếp chồng 0,5456 — hơn hằng số +0,0086% — được báo "kỹ năng 46%", bật với
  độ tin cậy 15%, và trang chủ in "ML xếp chồng đang bật". `quality_gate` nay
  đòi thắng cả dự báo hằng số, và độ tin cậy tính theo kỹ năng nhỏ hơn. Chạy
  lại trên lịch sử thật: LOTO và Đặc Biệt đều bị từ chối, trust 0.
- **Trang Chất lượng chấm một mô hình KHÁC mô hình đã công bố — CHƯA SỬA, chờ
  quyết.** Nó dựng lại tổ hợp CHƯA hiệu chỉnh, nên hiện Đặc Biệt tới 25,9% và
  kỹ năng −2,0%. Thủ phạm là hai thành phần đường cầu: `active` (kỹ năng
  −7,2%, p tới 95%) và `stable` (−29,5%). Phát lại hiệu chỉnh kiểu đi tới (mỗi
  ngày chỉ học từ quá khứ) kéo Đặc Biệt về −0,52% ± 0,52%, nhưng làm LOTO tệ
  đi chút ít và có ngày làm nhọn xác suất tới 33,6% — nên chưa đổi phương pháp
  chấm khi chưa có quyết định.
- **"Nhóm dựng lại −7,437%"** trên trang Chất lượng là các dòng lịch sử
  12-2025 → 01-2026 ghi `p_active`/`p_stable` ở thang sai (lỗi đã sửa từ
  trước, dữ liệu cũ còn nguyên). Không phải kỹ năng của mô hình hiện tại.

## 9. Trang Chất lượng chấm thứ đã công bố, và theo dõi kỹ năng liên tục

Chủ dự án chọn làm cả hai việc đề xuất ở mục 8.

- **Trang Chất lượng** nay chấm thẳng các vector đã công bố trước kỳ quay
  (`skill_monitor.published_evaluation`), không chấm bản dựng lại. Trên 28 kỳ:
  Đặc Biệt lớn nhất 1,28% (bản dựng lại in 25,9%), kỹ năng +0,002%; LOTO
  −0,014%. Thẻ "Nguồn của các con số" nói rõ nguồn chấm, khoảng ngày và kết
  luận của bộ theo dõi. Bản dựng lại chỉ còn làm phương án lùi khi chưa đủ
  `MIN_DAYS` (20) kỳ.
- **Bộ theo dõi** `src/skill_monitor.py`: 60 kỳ gần nhất, khoảng tin cậy hai
  phía z=3 (chạy mỗi ngày trên cửa sổ chồng lấn nên 1,96 sẽ báo giả vài lần
  mỗi năm), sàn hiệu ứng 0,0001%. Chạy trong job `verify-published-pages`; rời
  vùng 0 theo hướng nào cũng làm lượt đỏ. Phép kiểm dựng sẵn bắt được một lỗi
  của chính bản đầu: dự báo trùng đúng mốc cho kỹ năng ±1e-16 với sai số chuẩn
  còn nhỏ hơn, nên nó báo động giả — nay có sàn hiệu ứng.
- Phép kiểm cây import trong `test_workflows.py` không bóc nháy khỏi đặc tả gói
  (`"numpy==2.2.6"` thành tên `"numpy`); đã sửa và ghim bằng phép kiểm riêng.
- Phép kiểm sẵn có `test_quality_page_shows_skill_only_when_the_data_supports_it`
  bắt thêm một lỗi của bản đầu: thiếu `xsmb-2-digits.csv` thì
  `published_evaluation` ném ngoại lệ và làm sập cả bước chẩn đoán. Nay thiếu
  dữ liệu nghĩa là "chưa có gì để chấm" — trang lùi về bản dựng lại.
