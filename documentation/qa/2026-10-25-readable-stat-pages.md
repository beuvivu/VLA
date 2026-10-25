# Kiểm chứng 22 trang thống kê và đường cầu, 25-10-2026

Phạm vi cuối theo [kế hoạch](../plans/2026-10-25-readable-stat-pages.md): một trang Đặc Biệt hôm sau, hai bảng ML, một trang cầu vị trí, bảy luật cầu có màu, bốn trang đường cầu, bốn bảng thống kê Đặc Biệt và ba bảng LOTO. Giữ tất cả yêu cầu bổ sung trong cùng phiên.

## Hành vi đã đối chiếu

- Đặc Biệt hôm sau mặc định số cuối kỳ mới nhất, liệt kê các lần trùng hai số cuối từ mới đến cũ, giữ đủ năm chữ số. Kết quả bên cạnh thuộc đúng ngày lịch kế tiếp; ngày thiếu không được thay bằng kỳ có dữ liệu sau đó. Chỉ kết quả kế tiếp đã biết được đưa vào mẫu số tần suất. Dữ liệu thật: 26/09/2026 có 18132, ngày 27/09/2026 có 55473; 24/10/2026 có 45932 và kết quả hôm sau đang chờ.
- Hai trang ML giữ nguyên mười số, thứ tự, số 0 đầu, toàn bộ xác suất và bằng chứng JSON so với `origin/main` tại 9daca67; chỉ bố cục thay đổi. Ngày dự báo, mức tin và chuyển loại luôn nhìn thấy. Mỗi bằng chứng vẫn mở bằng bàn phím và đóng bằng Escape.
- Cầu vị trí giữ luật, 107 vị trí chữ số và tham số URL. Luồng ba bước cho phép lọc cặp số, chọn cầu rồi xem từng kỳ; nhãn vị trí ghi rõ giải/chữ số. Liên kết cầu đang chọn hiện rõ cả khi URL chưa có hash.
- Bảy luật cầu dùng số đường cầu của từng số, độc lập với cặp đảo. Ví dụ đếm 20,20,12,9,8,7 cho các số khác nhau tạo hạng 1,1,2,3,không màu,không màu. Mức 7 không đủ điều kiện, mức 8 có thể vào hạng; chỉ ba mức đếm cao nhất được tô. Đổi bộ lọc tính lại màu. Nhất vàng, nhì xanh dương, ba xanh lá; đồng hạng cùng màu.
- Màu là số đường cầu, không phải xác suất dự báo. Bộ lọc hai nháy mặc định hiện chưa có số nào trên 7 cầu, nên bảng không ép tạo màu. Đổi độ dài tối thiểu còn một kỳ tạo đủ mẫu để kiểm ba màu thực tế.
- Bốn bảng thống kê Đặc Biệt: 98 ca đối chiếu độc lập trước/sau trên dữ liệu thật, 420 kỳ dựng sẵn có ngày thiếu/số 0 đầu và dữ liệu rỗng. Giữ số lượt, gan, chuyển tiếp đúng ngày lịch, thứ tự, khóa ô, phạm vi, ba kỳ gần nhất và chu trình đánh dấu → lọc → xóa. Khác biệt duy nhất của văn bản ô là thêm rõ `0 lần` vào ô ma trận chưa xuất hiện; chỉ chuẩn hóa chính xác trường hợp đó khi so sánh.
- Mỗi thang màu có chú giải theo trần riêng: lượt từng số, lượt cặp đảo, lượt tổng và lượt chuyển tổng. Số kỳ chưa về dùng cam; chẵn/lẻ có nhãn và màu riêng. Điều kiện ở trước bảng, phương pháp gập phía sau.
- Bốn trang đường cầu trước đây không có JavaScript chọn/lọc, “Chọn nhanh” chỉ là ô hiển thị. Nay số và đường cầu là nút thật, có lọc 00–99, số kỳ đối chiếu và URL lưu lựa chọn. Hiện ngày nguồn = ngày đích − độ trễ, hai vị trí giải/chữ số, số ghép và kết quả thực tế. Nút chọn đưa focus/vùng nhìn tới căn cứ, chừa header cố định.
- Đối chiếu độc lập 600 đường/6.600 ô (6.000 lịch sử + 600 kỳ tới) với CSV và dữ liệu gốc: số ghép, nháy, ngày và trạng thái đúng; xác suất giữ nguyên. Kỳ tới không đọc kết quả sau ngày neo. Thiếu nguồn/kết quả/số/cờ lịch sử ghi chưa đủ dữ liệu; NaN không làm hỏng trình dựng. Chế độ Đặc Biệt vẫn ghi đúng Đặc Biệt nếu thiếu cờ phân loại phụ.
- Đặc Biệt đang chạy thực sự có 0 cầu đạt ba kỳ liên tiếp ở ngày hiện tại. Trang giải thích điều kiện chưa đạt, có liên kết sang nhóm từng có chuỗi; giữ nguyên ngưỡng. Số hỗ trợ trên toàn bộ cầu đủ điều kiện được phân biệt với danh sách 200 đường đang hiển thị.

## Kiểm tra trên trình duyệt

Chromium 153 chạy bản HTML dựng từ nguồn cuối, không sửa tay tệp xuất bản.

| Kiểm tra | Kết quả |
| --- | --- |
| 19 trang × 390/768/1440 px × sáng/tối | 114 trạng thái đạt, không lỗi JavaScript/tràn toàn trang, một H1/khung nội dung |
| Ba trang LOTO bổ sung × 390/768/1440 px × sáng/tối | 18 trạng thái đạt |
| Tương tác ba trang LOTO × 390/1440 px × sáng/tối | 12 trạng thái đạt: lọc, ngày, đánh dấu, xóa dấu, cỡ số và màu hover |
| Cặp lộn/ma trận ĐB/Tổng ở 390/768/1024/1100/1101/1440 px, sáng/tối | 36 trạng thái hồi quy đạt trên HTML đã dựng, không thay CSS khi chạy |
| Kiểm lại chín trang sau sửa chú giải/nhãn | 54 trạng thái đạt |
| Kiểm lại bốn path sau sửa focus và màu số | 24 trạng thái đạt; màu số đồng nhất ở chọn nhanh/danh sách/căn cứ |
| Tương tác bốn trang thiết kế lại × 390/1440 px | 8 trường hợp đạt |
| Tương tác tám trang bổ sung × 390/1440 px | 16 trường hợp đạt |
| Bảy trang màu × 390/1440 px × sáng/tối | 28 trạng thái đạt, cả mặc định và bộ lọc một kỳ |
| Tương phản ba màu ở hai chế độ | Tất cả đạt ít nhất 4,5:1 |
| Rê chuột, focus và chọn số có hạng | Giữ nền hạng, thêm viền chọn |

Đã xem ảnh desktop/mobile, sáng/tối; ma trận rộng cuộn trong khung riêng. Kiểm tương tác chọn số Đặc Biệt, trở về số mới nhất, dải 30/toàn bộ; mở bằng chứng ML; lọc/chọn đường cầu, chế độ Đặc Biệt; đổi số kỳ để tạo/xóa màu cầu.

Đã tái hiện trên điện thoại: chọn đường thứ hai cập nhật căn cứ nhưng tiêu đề ở y≈−2125 px. Sau sửa, focus ở tiêu đề căn cứ và y≈100 px, dưới header. Kiểm Enter, lọc có/không có kết quả, đổi số kỳ, tải lại URL, trở về toàn bộ và liên kết từ trang active rỗng sang lịch sử.

## Kiểm thử tự động

- 796 kiểm thử Python liên quan đạt trên nguồn cuối, gồm trình dựng, lịch sử Đặc Biệt, ML, các luật/đường cầu, hợp đồng bố cục, ba bảng LOTO và danh mục bằng chứng.
- Toàn bộ 257 kiểm thử frontend Node đạt.
- Ruff toàn bộ `src tests` và `git diff --check` đạt.
- Các kiểm thử mới đã thất bại trước khi sửa. Đột biến lấy kỳ có dữ liệu kế tiếp thay vì ngày lịch kế tiếp, đảo thứ tự lịch sử, sai ngưỡng 7/8, phá đồng hạng, bỏ cập nhật màu theo bộ lọc và mở màu sang trang khác đều bị kiểm thử bắt.
- Các đột biến sai ngày nguồn/đích, đọc kết quả tương lai, đổi xác suất và bỏ thao tác mở căn cứ cũng bị bắt. Kiểm hợp đồng cũ chỉ đổi phần bố cục có chủ đích; vẫn giữ ID/control/script/liên kết, một hướng dẫn duy nhất và tính lũy đẳng.
- Review độc lập đối chiếu dữ liệu ML, 98 ca thống kê, toàn bộ ô đường cầu, hợp đồng URL và màu. Các thiếu sót chú giải/NaN/nhãn được sửa và kiểm lại.
- Bộ Python toàn repo đã chạy bổ sung nhưng chưa hoàn tất trong phiên: lượt cuối không tiến thêm sau 734 ca ở nhóm mô hình dự báo. Ca được xác định chạy riêng đạt trong 0,35 giây; chưa xác định nguyên nhân chậm của lượt toàn bộ. Không công bố bộ toàn repo đã đạt và không sửa mô hình để né kiểm tra; CI của PR tiếp tục là kiểm tích hợp.

Baseline: 168 kiểm thử liên quan đạt trước thay đổi. Tài nguyên khung trang dùng chung, trang chủ, dữ liệu quay và mô hình ML được giữ nguyên.

## Bổ sung ba trang LOTO và khắc phục hồi quy CI

- `dau-duoi-loto`, `cap-lon-loto`, `lo-gan`: tiêu đề/tab/phạm vi gọn, bảng ở trước và phương pháp gập sau. Đầu/Đuôi có cùng thang màu để đối chiếu; 45 cặp và 10 kép song song từ 1024 px, nhãn số luôn ≥24 px; gan hiện tại, chu kỳ và số lượt dùng thang có tên/đơn vị riêng. Chu kỳ chưa đủ hai lần xuất hiện vẫn là dấu `—`, không biến thành 0 kỳ đã đo.
- Baseline độc lập gồm 178 kịch bản trên dữ liệu thật, hai bộ 420 kỳ có nháy lặp, bảy kỳ thưa ngày và dữ liệu rỗng. Sau dựng, toàn bộ văn bản ô/thứ tự/khóa/ngày chọn/dấu chọn khớp chính xác; chỉ chuẩn hóa khoảng trắng từ đầu. Oracle độc lập xác nhận đủ 27 nháy, tổng modulo 10, gan đếm theo Set mỗi kỳ và hai nửa max dùng toàn lịch sử.
- Năm đột biến bị bắt: nhầm cycle/gap, dùng sai trần màu, sai modulo tổng, bỏ kép khi chọn trần chung và thêm điều khiển cặp không có tác dụng ở Đầu/Đuôi. Review độc lập không có blocker.
- CI của `7e9c155` đã đạt job Python/AI-ML và CodeQL nhưng thất bại ở `check_detail_tables` do hồi quy CSS Đặc Biệt: khung cao 639 px, nội dung 690 px; chữ số 22/18 px. Đã trả ma trận về đủ mười hàng (view=full=714 px), chữ số/ô 0/cặp đảo 24 px trước và sau chọn. Checker kiểm thêm mép hàng cuối; kiểm bố cục Tổng dùng đúng wrapper và breakpoint mới, vẫn giữ chia cột/cỡ chữ/clipping. Đã tái hiện đỏ trước sửa và kiểm xanh 36 trạng thái sau dựng. CI của đầu nhánh mới tiếp tục là kiểm tích hợp cuối.
- Tiếp nhận ba tệp cập nhật Vietlott từ main `fe053ec`; không đổi chúng ngoài nội dung main đã có, không đổi dữ liệu XSMB. Chỉ dựng thêm ba trang LOTO và dựng lại bốn trang Đặc Biệt dùng CSS vừa sửa.

## Hai khung bằng chiều cao và LOTO theo từng ngày

- Phạm vi: `giai-db-ngay-mai` và bốn trang `soi-path-{loto,de}-{active,stable}`. Giới hạn chiều cao của bảng trái được thay bằng vùng cuộn nhận chiều cao tự nhiên của khung phải. Hai khung có cùng mép trên/dưới khi nằm cạnh nhau; ở ngưỡng xếp dọc, trả bảng về kích thước nội dung và giữ cuộn riêng để xem hàng cuối. Không đồng bộ chiều cao bằng JavaScript.
- Trang Đặc Biệt hôm sau có năm cột: ngày về, Đặc Biệt nguồn, LOTO cùng ngày, Đặc Biệt ngày lịch kế tiếp, LOTO ngày kế tiếp. LOTO gom các số trùng thành nhãn `×n`, giữ đủ 27 lượt, số `00` và khóa đánh dấu Đặc Biệt cũ. Ngày thiếu/chờ không được thay bằng kỳ có dữ liệu kế tiếp; không tạo LOTO giả từ giá trị trống hoặc sai định dạng.
- Baseline độc lập: 30 tổ hợp trang/kích thước/theme và 54 ảnh. Nguyên nhân trang hôm sau là selector nền chèn sau thắng CSS riêng; đường cầu còn trần 38rem và hai khung không stretch. Sau sửa, 30 tổ hợp và 54 ảnh được đối chiếu lại: sai lệch mép trên/dưới và chiều cao desktop là **0px**. Tại 1440px, hai khung hôm sau đều 628 × 1257,19px; cả năm cột vừa vùng bảng 626px. Hai ca vuốt cảm ứng 390px đạt, không tràn ngang trang.
- Đối chiếu độc lập toàn bộ 4.245 ngày/114.615 đuôi giải với CSV chuẩn; 20 kịch bản thật/giả lập, 155 lần về và 310 ô LOTO đều đúng. 303 ô đủ 27 lượt; bảy ô thiếu/chờ giữ trống. Hai ca di chuyển khóa đánh dấu đạt. Dữ liệu nhúng cả năm trang giống từng byte so với baseline trước sửa; phép tính tần suất và mô hình dự báo không đổi.
- 194 kiểm tra tương tác đạt, không lỗi JavaScript: đổi dải/số, đánh dấu, đổi 5/10/toàn bộ kỳ, chọn bằng Enter, lọc có/rỗng/reset, cuộn tới hàng/cột cuối, sáng/tối và breakpoint. Trường hợp Đặc Biệt đang chạy có 0 cầu là dữ liệu hợp lệ; fixture có cầu bảo đảm nhánh bố cục này vẫn được kiểm thật.
- Kiểm đỏ → xanh và đột biến: 14 đột biến ở trang hôm sau và bốn đột biến bố cục đường cầu đều bị bắt. Guard Chromium của CI được mở rộng để đo viền khung, tăng chiều cao theo số thẻ, khả năng tới nội dung cuối, đúng ngày và số nháy LOTO; không chỉ tìm chuỗi CSS. Bộ bridge giữ nguyên 72 trường hợp cũ và đạt **104/104** sau bổ sung.
- Toàn bộ **279/279** kiểm thử frontend đạt; Ruff toàn bộ `src tests scripts` đạt. Review độc lập đã đối chiếu dữ liệu, kích thước và ảnh thực tế. Lỗi nhô số Đặc Biệt 1,42px ở 1100px đã được sửa bằng padding riêng, giữ nguyên cỡ số và kiểm lại.
- Nguyên bộ kiểm thống kê Chromium của CI đạt **242/242** trạng thái, không lỗi. Guard đáy nội dung phải bổ sung sau đó đạt 18 trạng thái hẹp; mutation chỉ bỏ containment bị bắt với khoảng trắng thừa 7.574,69px. Ba mutation cap chiều cao/tỷ lệ cột/align cũng bị bắt, tránh trường hợp hai khung bằng nhau nhưng đều bị kéo quá dài.
- Bản phát hành dựng trên main `0e84d918`, giữ các cập nhật dữ liệu/mô hình tự động mới nhất. Chỉ dựng lại đúng năm trang và chốt `docs/assets/release.json`; cổng `web.site_assets --refresh docs --check` đạt. CI của PR là cổng tích hợp bắt buộc trước hợp nhất.
- Bộ Python toàn repo đạt **4.017 lượt kiểm, 0 lỗi**, mười lượt bỏ qua do kiểm browser tùy chọn chưa có Chromium mặc định ở local (JUnit: 4.027 lượt, gồm hai lượt bỏ qua khi collection). Bốn ca browser đường cầu mới chạy thật bằng executable local và đạt. Sau đồng bộ main, kiểm liên quan/bố cục/chỉ mục tài liệu đạt; đối chiếu release thêm 14 tổ hợp browser không lỗi, payload năm trang giống main `0e84d918` từng byte.
- CI đầu nhánh `b306f91` đạt cả Python, Chromium (gồm bộ stat/bridge mới) và CodeQL. Main đồng thời cập nhật Vietlott tới `63c26d4`, gây xung đột duy nhất ở manifest. Đồng bộ giữ nguyên ba tệp Vietlott của main, chốt lại manifest cho cả bản mới và năm trang đã sửa; mã nguồn và năm HTML đã kiểm chứng giữ nguyên từng byte. CI chạy lại trên đầu nhánh đã đồng bộ trước hợp nhất.
