# Rà soát toàn kho sau PR #191 — 25-10-2026

## Hợp nhất và phạm vi

PR #191 đã hợp nhất vào `main` ở `ef7cef6143526f251f9cd7b2f11cd731b2172d5a`, sau khi CI trên đúng HEAD `0335aabcfed9192fc83c506108d0d43551af6662` hoàn tất xanh. Lượt push thực chạy là [40160152307](https://github.com/beuvivu/VLA/actions/runs/40160152307): Python/AI/ML cùng bốn cổng phát hành, Chromium sáng/tối/mobile đều đạt. Các job PR bị skip là bản sự kiện trùng được route bỏ qua, không dùng làm bằng chứng kiểm. CodeQL cũng đạt. [Triển khai Pages của commit hợp nhất](https://github.com/beuvivu/VLA/actions/runs/40161564015) đã thành công.

Rà soát độc lập core/ingest/forecast/evaluation/research, workflow/pipeline, web và engine Vietlott. Đây là kiểm đúng/sai và hồi quy chức năng; không phải một cam kết rằng phần mềm không còn lỗi.

- 50 HTML × 2 kích thước (390/1440) × sáng/tối: 200 trạng thái Chromium; không lỗi JavaScript, thiếu tài nguyên nội bộ hay tràn trang ngoài bố cục `landing_desktop` chủ ý.
- 8.331 liên kết/tài nguyên nội bộ đã kiểm; không xác nhận lỗi liên kết mới.
- 4.245 kỳ raw/two/sparse/JSON cùng ngày; 27 giải và số đếm khớp; không raw tương lai. Hai sổ dự báo mỗi mode 269 ngày: không trùng khoá ngày/số, không nhãn kết quả lệch sổ chuẩn; picks và Top 10 đang công bố khớp nhau.

## Mười lỗi xác nhận và bản sửa

| Lỗi | Tái hiện trên bản trước sửa | Hành vi sau sửa |
| --- | --- | --- |
| Hiệu chỉnh mô hình hằng | `p=0,5`, tỷ lệ thật 20%: mất mọi bin, reliability=0, Brier nhóm=0 | Một nhóm đủ quan sát; reliability=0,09, Brier=0,25, phần dư=0; gồm cả p=0/1 và nền Đặc Biệt |
| Giám sát nuốt dữ liệu hỏng | Vector Đặc Biệt toàn 0 sinh NaN, trạng thái `vung_0`, không báo động; giá trị NaN có thể lưu lần đầu vào sổ | Artifact/sổ/đầu vào và thống kê tràn bị từ chối; CLI lỗi rõ ràng, không ghi sổ hỏng |
| Workflow thu thập thiếu quyền | Job dùng `github.token` gọi workflow dispatch nhưng chỉ có `contents: read` | Chỉ job cần kích hoạt được cấp thêm `actions: write`; kiểm effective permissions và job override |
| Workflow dự báo nuốt lỗi thật | Stub Python exit 1/2/124 vẫn làm bước predict/retry xanh | Chỉ mã 3 biểu thị chưa sẵn sàng; lỗi thật giữ nguyên mã khác 0 ở cả hai nhánh |
| Live hiện số cũ ở kỳ mới | Sau đổi ngày/trạng thái chờ, timer cũ hiện lại 26 ô dù bộ đếm 0/27 | Huỷ timer và hàng đợi snapshot cũ; sau 5,2 giây vẫn 0 ô; sparse/complete tiếp theo vẫn đúng |
| Ma trận thêm ngày ngoài dải lịch sử | Chọn 01–10/01/2015 vẫn thêm hàng/cột chờ của hôm nay | Chỉ thêm kỳ chờ trong ngữ cảnh dải tới dữ liệu mới nhất; kiểm cả hôm nay đã có kết quả và bộ lọc thứ |
| Gan cực đại lệch một kỳ | Hai kỳ liên tiếp cùng về 00 vẫn báo gan 1; cả 100 số lệch popup chu kỳ | Đếm kỳ không về giữa hai lần xuất hiện, đúng 0; thiếu hai lần xuất hiện vẫn là `—`; áp dụng cả 50 cặp |
| Power coverage bỏ số đặc biệt | 5 chính + bonus không được chấm jackpot2; xác suất bỏ mất 6 trường hợp | Generator, ma trận thắng và random baseline cùng xét bóng từ phần còn lại; `P(JP1 hoặc JP2)=7/C(55,6)` |
| Max 3D Pro gán hạng cho số đơn | Một bộ ba thuộc nhóm Đặc biệt bị gọi là vé trúng hạng dù chưa có vé cặp | Chỉ đếm số lần/nhóm trùng; hiện «Chưa phân hạng: cần vé cặp» ở engine, dashboard riêng và VLA; Max 3D thường giữ nguyên |
| Xác suất biên Keno mất ổn định | 1.000 kỳ hợp lệ có số 1 luôn về: mô hình trả p≈6.670,78, tổng biên≈6.689,81 | Thay chia đa thức triệt tiêu bằng DP log và truyền khối xác suất ngược; p≈0,96593, tổng=20; không clip/chuẩn hoá để che lỗi |

## Bằng chứng bản sửa

Mọi lỗi có RED → GREEN và phép đảo hành vi bắt được hồi quy; không nới ngưỡng kiểm định hay chấm lại lịch sử đã công bố.

- Evaluation: 170 kiểm liên quan đạt trước bổ sung bốn ca tràn; lượt cuối hai tệp 48 đạt. Tám phép đột biến chặn bin hằng, artifact/sổ NaN, status, CLI và thống kê tràn.
- Ops: 346 kiểm repo/pipeline/CLI đạt; bốn phép đột biến quyền, nuốt lỗi hai nhánh và mã skip đều bị bắt.
- Web: 72 Node và 223 Python liên quan đạt; tám phép đột biến bị bắt. Chromium sau sửa 12/12 trạng thái cho ba trang, đối chiếu đủ 100 số/50 cặp ở toàn lịch sử và 30 kỳ; kiểm Live độc lập cũng đạt.
- Vietlott: 41 kiểm coverage và 69 kiểm forecast/evaluation/ML liên quan đạt; sáu phép đột biến bị bắt. Review độc lập đối chiếu 15.680 vé/kỳ Power trên lồng nhỏ và 270 trường hợp biên trọng số với liệt kê tổ hợp, sai số biên lớn nhất 2,08×10⁻¹³.
- Toàn bộ Python VLA, Node và Python Vietlott đang chạy lại trên bản sửa; kết quả cuối cập nhật trước chốt PR. Ruff đầy đủ hai dự án, compile và diff-check đã đạt.

Chỉ dựng lại trang/tài nguyên bị ảnh hưởng. Ba trang thống kê giữ nguyên 4.245 kỳ và timestamp nguồn. Trang Vietlott phải giữ dữ liệu/analysis đã công bố khi máy phát triển không có checkpoint cache; không thay bằng báo cáo seed cũ hơn.

## Lỗi lịch nghỉ quay còn mở

**P2 có điều kiện, chưa gây sai số liệu kỳ hiện tại.** `forecast.daily_forecast` yêu cầu kỳ quay tiếp theo (bỏ ngày nghỉ), trong khi ensemble, lịch sử thành phần và nhiều producer vẫn dùng ngày lịch tiếp theo. Với neo 15-02-2026 và nghỉ 16–19/02, kỳ quay đúng 20/02 nhưng picks mang ngày 16/02 bị thẻ từ chối; component đúng ngày 20/02 bị ensemble coi là stale.

Các điểm liên quan: `predict_nextday_2d`, `record_pred_history`, `ml_predict`, `cau_keo_ml`, `statistical_signal`, `run_path_ui`, `xsmb_agents.engine`. `online_learning` còn kiểm ngày neo+1 trong validator, advance và đường tìm artifact; sổ cũ có settlement `non_draw`. Đổi riêng ngày producer hoặc nới validator sẽ phá hợp đồng sổ. Giữ loader từ chối an toàn; cần chuyển chính sách có phiên bản, giữ sổ/artefact cũ nguyên vẹn và kiểm trước–trong–sau nghỉ, cutoff, khởi động lại, settlement, tái lập. Không ép thẻ hiển thị dự báo sai ngày.

Giới hạn số học riêng: `Law.__init__` vẫn có thể underflow trước hàm biên khi người gọi truyền trọng số cực đoan kiểu 10³⁰⁸/10⁻³⁰⁸. Các producer hiện tại dùng trọng số có chặn và không sinh miền ấy; bản sửa Keno đã kiểm hàm biên trên trọng số hữu hạn cực đoan nhưng không thay toàn bộ phép chuẩn hoá/sampling của `Law`.
