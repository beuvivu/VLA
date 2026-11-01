# Sửa tra cứu Đặc Biệt hôm sau và làm rõ các trang dự báo

Yêu cầu ngày 25-10-2026: sửa `giai-db-ngay-mai.html` theo lịch sử các lần cùng hai số cuối xuất hiện; thiết kế lại hai trang Top 10 ML và trang soi cầu vị trí để dễ xem và dễ hiểu.

Yêu cầu bổ sung trong cùng phiên: tô ba mức số đường cầu cao nhất ở `soi-cau-loto.html` và `soi-cau-hai-nhay.html`, chỉ xét từng số có hơn 7 đường cầu; đồng hạng cùng màu. Đổi bộ lọc phải tính lại màu.

Yêu cầu mở rộng tiếp theo: áp dụng cùng màu cho năm luật cầu còn lại; sửa và thiết kế lại bốn trang đường cầu active/stable và bốn trang thống kê Đặc Biệt. Tổng phạm vi cuối là 19 trang. Công việc tiếp tục trên cùng nhánh/PR; sáu trang đầu và các kiểm chứng đã có được giữ lại.

Yêu cầu tiếp nối: thiết kế lại `dau-duoi-loto.html`, `cap-lon-loto.html`, `lo-gan.html` theo cùng hướng dễ đọc. Tổng phạm vi PR sau đợt này là 22 trang; chỉ dựng thêm ba HTML này. Tiếp nhận main mới với ba tệp Vietlott không liên quan để giữ các cập nhật đã xuất bản.

## Thiết kế

- Giữ khung Nexlink và hệ màu chung; giao diện dữ liệu sáng rõ, tiêu đề gọn, không dải giới thiệu lớn hay thẻ trang trí chiếm chỗ. Màu Đặc Biệt đỏ, LOTO xanh theo token; sáng/tối đồng bộ.
- Đặc Biệt hôm sau: chọn 00–99 (mặc định hai số cuối kỳ mới nhất), toàn bộ lịch sử mặc định, liệt kê các lần cùng đuôi từ mới đến cũ. Cột giải gốc giữ đủ 5 số và nhấn đúng 2 số cuối. Cạnh nó là Đặc Biệt của ngày lịch kế tiếp và ngày tương ứng. Không lấy ngày có dữ liệu kế tiếp để thay cho một ngày bị thiếu; chưa có kết quả giữ trạng thái trống có giải thích. Bảng tần suất chỉ đếm các kết quả kế tiếp đã biết, không biến thành xác suất dự báo.
- Top 10 ML: một tiêu đề ngắn, chuyển Đặc Biệt/LOTO rõ ràng, kỳ dự báo và trạng thái mức tin, bảng xếp hạng có cột số và xác suất dễ đọc. Giữ thứ tự, số 0 đầu, xác suất đầy đủ, bằng chứng từng giá trị và ý nghĩa mức tin. Giải thích kỹ thuật đặt trong phần mở rộng.
- Soi cầu vị trí: luồng đọc "chọn điều kiện → chọn cặp số/cầu → xem từng kỳ"; hướng dẫn ngắn ngay chỗ thao tác. Dải chọn và kết quả nổi bật, bảng vị trí rõ nhãn giải/chữ số; kiểm chứng thống kê và phương pháp đặt sau phần sử dụng, có thể mở rộng. Giữ nguyên luật cầu và hợp đồng query.
- Hai bảng cầu LOTO: xếp ba mức đếm khác nhau từ cao xuống thấp, chỉ trong các số có >7 đường cầu. Nhất vàng, nhì xanh dương, ba xanh lá theo token sáng/tối; giữ màu khi chọn/rê chuột, có chú giải và nhãn truy cập. Không cộng chung số đảo và không thay đổi luật hay điểm kiểm chứng.
- Tất cả không tràn ngang toàn trang ở 390/768/1440px; bảng rộng được cuộn riêng; không tooltip từ chuột, không chuỗi HTML gán vào DOM; không lộ danh tính nguồn trên trang xuất bản.

## Phương án

Chọn chỉnh có phạm vi ở trình dựng/tài nguyên riêng: sửa đúng luồng nghiệp vụ, không ảnh hưởng các trang khác. Thay hệ CSS toàn kho hoặc thêm framework không cần thiết và làm tăng rủi ro hồi quy.

## Thực hiện và kiểm chứng

- [x] TDD cho các lần trùng đuôi, ngày kế tiếp thực, ngày thiếu/chờ, số 0 đầu, thứ tự ngược thời gian và bộ lọc; bỏ phép xếp hạng gan cũ.
- [x] Thiết kế lại ML, giữ bằng chứng, ngày và mức tin; kiểm dữ liệu không đổi và trạng thái rỗng.
- [x] Thiết kế lại soi cầu, giữ thuật toán/query và kiểm Python ↔ JS; kiểm thao tác chọn hai vị trí và đường cầu.
- [x] TDD cho màu >7 đường cầu, đồng hạng, giới hạn ba mức, đổi bộ lọc, giới hạn đúng hai trang và Python ↔ JS.
- [x] Dựng sáu trang, kiểm Chromium thực 390/768/1440px và sáng/tối, kiểm bàn phím/mobile; chụp ảnh trước/sau trong scratch.
- [x] Chạy pytest/Node/Ruff liên quan, kiểm trình duyệt và review độc lập với bằng chứng; bộ Python toàn repo chạy bổ sung.

Baseline: 168 kiểm thử ML/trang thống kê/cầu vị trí đạt trước sửa trên nhánh từ `origin/main` 9daca67.

## Phạm vi bổ sung và cách thực hiện

Giữ cùng công nghệ Python/Jinja/JavaScript/CSS viết tay và hệ màu Nexlink. Chọn thay bố cục trong từng trình dựng, không thêm framework hay thay khung trang. Các số liệu vẫn phải được đối chiếu; màu phải có chú giải về đại lượng được tô.

### 1. Màu của cả bảy luật cầu

Tệp: `src/pages/build_bridge_pages.py`, `src/web/templates/bridge_pages.js`, `tests/pages/test_bridge_rank_colors.py`, `tests/frontend/bridge-pages.test.mjs`.

- [x] Viết và chạy kiểm đỏ cho năm trang bạch thủ, LOTO theo thứ, Đặc Biệt, Đặc Biệt bộ số và Đặc Biệt theo thứ chưa có màu.
- [x] Mở phạm vi `number_ranks(counts, rule_key)` và `numberRanks(counts, ruleKey)` sang cả bảy luật; giữ ba mức đếm phân biệt, ngưỡng >7, đồng hạng và từng số riêng.
- [x] Kiểm xanh trên mặc định và query, đối chiếu Python/JS; đột biến thu phạm vi lại hai trang phải bị bắt. Dữ liệu, luật quét và số đếm không thay đổi. Chromium 28 trạng thái kiểm cả mặc định và bộ lọc một kỳ đạt.

### 2. Bốn trang đường cầu theo ngày

Tệp: `src/pages/build_docs.py`, `src/web/templates/path_ui_page.html.j2`, tài nguyên riêng cho đường cầu và các kiểm thử path tương ứng.

- [x] Tái hiện việc thiếu tương tác và kiểm vì sao Đặc Biệt active đang trống, trước khi sửa. Phân biệt không có cầu đủ điều kiện với lỗi tính toán; không hạ điều kiện ngầm.
- [x] Kiểm đỏ cho thao tác chọn cầu/số, nguồn chữ số và ngày kết quả, số 0 đầu, dữ liệu thiếu/rỗng, quan hệ ngày nguồn → ngày đích.
- [x] Làm các nhóm active/stable và LOTO/Đặc Biệt rõ ràng. Danh sách đường cầu chọn được bằng bàn phím; bằng chứng đặt cạnh đường được chọn, có vị trí giải/chữ số, hai chữ số được ghép, kết quả đích và trạng thái khớp.
- [x] Các bước trong lịch sử đi từ ngày nguồn tới đúng ngày đích theo độ trễ; không dùng kết quả tương lai làm nguồn. Hiển thị rõ kỳ tới chưa biết kết quả, giữ xác suất mô hình và ranh giới dữ liệu.
- [x] Trang active rỗng giải thích điều kiện chưa đạt và có liên kết xem lịch sử, không để ô giả nút. Kiểm xanh, kiểm đột biến lỗi ngày/chữ số và review độc lập.

### 3. Bốn trang thống kê Đặc Biệt

Tệp: `src/pages/build_stat_pages.py`, `src/web/templates/stat_pages.js`, CSS riêng, kiểm thử frontend/Python các trang `cau-giai-dac-biet`, `giai-dac-biet-theo-tong`, `cau-dac-biet-theo-bo-so`, `chu-ky-dac-biet`.

- [x] Kiểm đỏ cho bố cục mới và chú giải đại lượng màu; giữ kỳ lọc, số liệu, sắp xếp, đánh dấu ô/cặp và các trường hợp thiếu/rỗng.
- [x] Tiêu đề/điều kiện gọn, bảng số là nội dung chính, nhãn giải thích số lượt/chu kỳ/chưa về/chuyển tổng ngay tại nơi đọc. Màu phân biệt mức số liệu và có chú giải, không đổi thành lời hứa về xác suất.
- [x] Dùng `.app-specialstats-shell[data-app-workspace-guide]` để giữ hướng dẫn riêng, tránh thêm lại hero/guide lớn; kiểm hợp đồng vẫn giữ ID/control/script/liên kết, chỉ cập nhật đúng chủ sở hữu hướng dẫn.
- [x] Kiểm xanh cùng các kiểm hồi quy cũ, đối chiếu dữ liệu trước/sau và Python/JS khi liên quan.

### 4. Tích hợp và nghiệm thu

- [x] Dựng từ nguồn đúng 19 HTML yêu cầu, không dựng lại trang chủ hoặc các trang khác ngoài phạm vi.
- [x] Chromium ở 390/768/1440 px, sáng/tối; không tràn toàn trang. Kiểm riêng chọn/lọc/mở đường cầu và trạng thái active trống; kiểm màu >7 của cả bảy luật.
- [x] Chạy các bộ kiểm Python/Node/Ruff liên quan: 788 pytest, 248 Node và Ruff đạt. Bộ toàn repo đã thử nhưng chưa hoàn tất, ghi giới hạn trong QA; các kiểm hợp đồng bố cục cũ chỉ đổi phần có chủ đích, giữ bảo vệ dữ liệu.
- [x] Review độc lập, ghi bằng chứng cuối vào báo cáo QA, cập nhật PR theo toàn bộ phạm vi cuối.

### Trọng tâm review

1. Số có đúng 7 cầu không màu, đồng hạng có cùng màu và đổi query không giữ hạng cũ.
2. Cầu active Đặc Biệt trống có giải thích thật; các điều khiển vẫn dùng được và không giả tạo cầu đủ điều kiện.
3. Chữ số 0 đầu, vị trí chữ số và ngày nguồn/đích giữ đúng; kết quả chưa biết không bị tính thành sai hay đúng.
4. Màu sáng/tối, focus/hover/chọn không che màu số liệu; chú giải giúp hiểu ý nghĩa.
5. Trình dựng lũy đẳng, đủ điều khiển/bằng chứng/liên kết cũ; bố cục riêng không bị khung chung chèn lại.

## Bổ sung: ba bảng thống kê LOTO

**Mục tiêu:** giúp so sánh số và đọc đúng ý nghĩa từng bảng, nhất quán với các trang thống kê vừa chỉnh. Giữ CSS/JavaScript viết tay, khung chung và token sáng/tối.

**Tệp:** `src/pages/build_stat_pages.py`, `src/web/templates/stat_pages.js`, CSS riêng `src/web/templates/loto_stat_pages.css`, các kiểm Python/Node mới và hợp đồng hướng dẫn trong `tests/web/test_analysis_workspace.py`.

**Thiết kế:** chọn bố cục tiêu đề gọn → ba tab trang → phạm vi → số liệu → phương pháp gập. Đầu/Đuôi tổng hợp song song trên máy tính, ma trận theo kỳ có nhãn/chú giải; Cặp lộn đặt 45 cặp và 10 kép song song, cặp số nổi bật; Lô gan phân biệt rõ gan hiện tại, cực đại trong dải, cực đại toàn lịch sử và gan cặp. Không thêm hero lớn hay framework. Root `div.app-lotostats-shell[data-app-workspace-guide]` giữ quyền sở hữu bố cục của ba trang.

- [x] Chụp baseline độc lập cho các bảng, bộ lọc, ngày, số 0 đầu và đánh dấu trước sửa; bao gồm nháy lặp, ngày nghỉ, dữ liệu rỗng và chỉ một lần xuất hiện.
- [x] Viết kiểm đỏ cho bố cục/luồng và màu đúng đại lượng; triển khai phạm vi đúng ba slug. Giữ nguyên phép tính, thứ tự, khóa dấu, độ chính xác và ID điều khiển.
- [x] Kiểm xanh và đột biến có ý nghĩa. Đối chiếu DOM số liệu trước/sau; chu kỳ chưa quan sát đủ vẫn là chưa xác định, không biến thành số 0 đã đo.
- [x] Dựng ba trang qua `write_page`, kiểm Chromium 390/768/1440 px, sáng/tối và thao tác lọc/đánh dấu/cuộn riêng. Review độc lập, cập nhật QA và PR.

Điểm review: thang Đầu/Đuôi cùng đại lượng dùng cùng trần; màu các đại lượng khác nhau có chú giải riêng; các bảng max toàn lịch sử không thay theo preset; gan đếm một lần mỗi kỳ dù có nhiều nháy; 45 cặp lộn và 10 kép giữ đúng quan hệ số và thứ tự.

## Tinh chỉnh tiếp: hai khung bằng chiều cao và LOTO theo từng ngày

Yêu cầu tiếp nối cho `giai-db-ngay-mai` và bốn trang `soi-path-*`: hai khung nhìn thấy phải có cùng mép trên/dưới ở bố cục hai cột, vùng bảng trái điền đủ chiều cao khối phải khi đổi lọc hoặc chọn cầu. Trang Đặc Biệt hôm sau bổ sung LOTO của chính ngày đã về và ngày lịch kế tiếp, nằm cạnh giải Đặc Biệt tương ứng.

Hướng thực hiện: tiếp tục CSS/JS/Jinja hiện có, dùng grid/flex và vùng cuộn có phạm vi. CSS riêng phải thắng giới hạn chiều cao của lớp nền; không đặt chiều cao pixel cố định hay đổi khung chung. Trên màn hình nhỏ, xếp dọc và cho đọc đủ nội dung, không giữ containment khiến bảng mất chiều cao. Đồng bộ bằng JavaScript chỉ cần nếu CSS không đáp ứng được.

- [x] Lưu baseline dữ liệu và kích thước thật; xác định quy tắc CSS đang chặn chiều cao.
- [x] Đặc Biệt hôm sau: hai cột bằng chiều rộng/chiều cao, giữ thứ tự và khóa đánh dấu cũ; LOTO đủ 27 lượt, giữ số 0 đầu/nháy trùng, không lấy nhầm ngày hay bịa kết quả khi thiếu/chờ.
- [x] Bốn đường cầu: cân hai khung có viền, ghi chú trong khung trái, bảng cuộn điền phần còn lại; giữ query/chọn cầu/lọc/ngày và trạng thái trống hợp lệ.
- [x] Kiểm đỏ → xanh và đột biến đúng hành vi; kiểm cả trạng thái ít/nhiều/rỗng, đổi số, đổi 5/10/toàn bộ kỳ và đánh dấu.
- [x] Dựng đúng năm HTML qua nguồn và `write_page`, chốt manifest, đo Chromium ở desktop/tablet/mobile sáng/tối; review độc lập đối chiếu dữ liệu và hình học sau mỗi thao tác.
- [ ] Chạy kiểm liên quan và toàn bộ frontend, Ruff/hợp đồng trang; đưa bản sửa qua PR và chỉ hợp nhất khi CI đạt.
