# Kiểm chứng ba tác tử XSMB — 17-10-2026

## Phạm vi đã triển khai

`KnowledgeBaseManager`, `AlgorithmEnsemble`, `MetaLearner`, `PredictiveEngine`
trong `src/xsmb_agents/`. Ba lớp dùng chung tiền tố và lõi tự học hiện hữu;
profile mới không sửa sổ bảy chuyên gia cũ. Pipeline cập nhật các chẩn đoán
và kho tri thức trước khi đóng băng snapshot tác tử, kể cả `--skip-docs`.

Kỳ khởi tạo: dữ liệu đến **16-10-2026**, dự báo **17-10-2026**. Hai sổ mới
có **0 kỳ tiến cứu đã chấm**. Hệ thống chạy, truy xuất và tự học ở chế độ
shadow; vector sản xuất không bị ghi đè. Trang `do-tin-cay.html#app-agents`
phân biệt xác suất công bố/ứng viên, có căn cứ, sai số, rủi ro và tệp JSON
của đủ 100 số cho mỗi mục tiêu.

## Kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| `PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest tests -q` | 3.686 qua, 9 bỏ qua; 500,06 giây |
| Bộ liên quan chạy lại sau thay đổi cuối về pipeline/giao diện | 312 qua; 54,48 giây |
| `npm test --prefix tests/frontend` | 161 qua |
| `python -m ruff check src tests` | Qua |
| `python -m compileall -q src tests` | Qua |
| Chromium 140, 1440 và 390 px, sáng/tối | 4 cấu hình qua; không lỗi JS, không tràn trang, không tooltip title |
| Chi tiết và tải JSON | Mở được; tải đúng `xsmb-agents.json` |

Đã xem ảnh render thật ở desktop/mobile. Bảng 3 cột mới bỏ sàn chiều rộng
680 px của bảng nghiên cứu rộng; trên mobile bảng rộng 324 px, cạnh phải
cột xác suất ở 357 px trong viewport 390 px. Phần giải thích nằm ngoài bảng
để không ép cột số thành chữ dọc hoặc bị cắt khi mở chi tiết.

Kiểm thử mới được chạy đỏ trước khi triển khai/sửa: profile, tiền tố nhân
quả (gồm mạng MLP), xác suất hai miền, truy xuất, idempotence, không đổi
vector công bố, lỗi checksum, replay không đọc kỳ chưa chốt, bộ nhớ dài,
cutoff sau chờ khóa/huấn luyện, pipeline, báo cáo cũ và benchmark chẩn đoán.

## Review và quyết định kỹ thuật

Review độc lập đọc toàn bộ thay đổi, không sửa mã. Hai lỗi quan trọng đã
được tái hiện bằng test đỏ rồi sửa:

1. Replay cắt cả bộ nhớ dài còn 180 kỳ. Nay chỉ điểm CHỌN siêu tham số dùng
   180 kỳ cuối; trạng thái và trọng số cuối dùng toàn bộ kỳ đã chốt.
2. Đồng hồ lấy trước khóa/huấn luyện có thể vượt cutoff mà vẫn ghi giờ cũ.
   Nay đọc giờ thật sau khóa, sau huấn luyện và trước ghi sổ mới.

Review cũng chỉ ra snapshot luật lấy từ lượt trước. Đã chuyển chẩn đoán và
knowledge ingestion thành pha dữ liệu trước tác tử, không phụ thuộc dựng
HTML. Test gọi pipeline thật với bộ ghi lệnh xác nhận thứ tự và không chạy
trùng các producer.

Không thêm dịch vụ DB hoặc dependency mới: bộ nhớ cosine, luật, checksum,
khóa và ghi nguyên tử đang có đủ cho quy mô dữ liệu này. Đổi sang Qdrant,
pgvector hoặc Neo4j là hướng mở rộng, chưa được triển khai.

## Chẩn đoán hồi cứu 60 kỳ

Lệnh tái lập:

```bash
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python src/xsmb_agents/run_xsmb_agents.py --benchmark-last 60
```

Fingerprint và số đo đầy đủ ở `data/forecast/agents/benchmark.json`. Đối chứng đương
nhiệm có artifact của 46/60 kỳ; 14 kỳ còn lại dùng hằng số và được ghi rõ.
Mỗi kỳ chỉ học trên tiền tố trước đích. Không bản ghi giả nào được đưa vào
sổ thật: `prospective_draws=0`, `promotion_allowed=false`.

| Mục tiêu | Logloss hằng số | Logloss tổ hợp mới | Brier hằng số | Brier tổ hợp mới |
| --- | ---: | ---: | ---: | ---: |
| Đặc Biệt | 4,605170 | 4,600817 | 0,495000 | 0,494956 |
| LOTO | 0,547016 | 0,547022 | 0,180569 | 0,180571 |

Chênh lệch rất nhỏ và không đồng đều. Đây là hồi cứu sau khi chọn kiến trúc,
không đủ chứng minh lợi thế dự báo. Vì thế giữ shadow và tiếp tục chấm từng
kỳ công bố thật. MLP kỳ đầu chưa hội tụ trong giới hạn epoch; cờ này được
ghi vào diagnostics và rủi ro hiển thị. Không có cam kết trúng hoặc phần
trăm tin cậy mô hình dựng sẵn. Khoảng hiệu chuẩn chỉ xuất hiện sau đủ 60 kỳ
có kết quả, là xấp xỉ theo nhóm với SE khối, không bảo đảm riêng một số.
