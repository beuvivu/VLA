# Cài đặt Vietlott

Mã Vietlott là một phần của kho VLA, nằm ở thư mục `vietlott/` với bố cục gói riêng. Lệnh dưới chạy trong thư mục ấy.

**Cần:** Python 3.11 trở lên, khoảng 1 GB đĩa, mạng tới pypi.org cho lần cài đầu. Dữ liệu lịch sử đi kèm (`data/seed`), nên phân tích và dự báo chạy được cả khi không có mạng.

## 1. Cài gói

```bash
cd vietlott
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,crawler]"
vietlott init                                       # nạp dữ liệu đi kèm, học bộ dự báo, kiểm tra
python -m pytest                                    # bộ kiểm của Vietlott
```

Gói được cài editable: kéo mã mới về không cần cài lại. Lệnh luôn chạy trên thư mục dự án; nếu cần, đặt `VQE_HOME=/đường/dẫn/vietlott`.

Trên GitHub, các workflow `.github/workflows/vlm-*.yml` ở gốc kho chạy trong thư mục này: đồng bộ kết quả, học kỳ mới, ghi sổ dự báo và lưu dữ liệu vào kho; trang Vietlott của site do `vietlott-results.yml` dựng.

## 2. Docker

```bash
docker compose up -d                                  # API + bộ lập lịch
make docker-job                                      # chạy một lần toàn bộ báo cáo, bằng UID của bạn
# Không có make: Docker Desktop (Windows/macOS) chạy thẳng lệnh dưới;
# Linux thêm VQE_UID=$(id -u) VQE_GID=$(id -g) phía trước để ghi được ./reports.
docker compose --profile jobs run --rm backtest
```

API ở http://localhost:8000/docs. Bộ lập lịch đồng bộ 6 giờ/lần rồi gọi `/forecast/<sản phẩm>?record=true`: mô hình tự học kỳ mới và ghi dự báo vào sổ (chỉ khi kỳ đó chưa quay). Dữ liệu nằm trong volume `vqe-data`.

## 3. Lệnh thường dùng

| Lệnh | Việc |
|---|---|
| `vietlott init` | nạp dữ liệu đi kèm, học bộ dự báo, kiểm tra |
| `vietlott doctor` | kiểm tra Python, gói, dữ liệu, kho, bộ dự báo, mạng |
| `vietlott forecast next` | học kỳ mới, dự báo kỳ tới, ghi sổ nếu kỳ chưa quay |
| `vietlott forecast update` | sau kỳ quay: học kỳ mới, chấm các dự báo đã ghi |
| `vietlott forecast scoreboard` | thành tích thật của các dự báo ghi trước kỳ quay |
| `vietlott sync --game all --source auto` | đồng bộ Mega, Power, Lotto |
| `vietlott products sync` | đồng bộ Keno, Bingo18, Max 3D, Max 3D Pro |
| `vietlott serve` | API tại http://127.0.0.1:8000/docs |
| `python scripts/build_site.py` | dựng trang tĩnh của engine vào `site/` để kiểm |

Danh sách đầy đủ: `vietlott --help`, và README mục 3.

## 4. Sự cố thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| "cần Python 3.11 trở lên" | cài Python 3.11 trở lên; kho VLA chạy bản ghi trong `.python-version` |
| `pip install` lỗi mạng | mạng công ty: đặt `HTTPS_PROXY`, rồi chạy lại lệnh cài |
| `doctor` báo vietlott.vn HTTP 403 hoặc Cloudflare | bình thường khi ở ngoài Việt Nam hoặc khi trang yêu cầu xác minh người dùng; `--source auto` dùng nguồn dự phòng. Muốn đối chiếu với trang chính thức: README mục 1.8 |
| "không ghi vào sổ: …" | kỳ được dự báo đã hoặc sắp quay theo lịch, hoặc dữ liệu chưa đủ: đồng bộ (`vietlott sync --game all --source auto`, `vietlott products sync`) rồi chạy lại. Ngay sau khi cài, dữ liệu đi kèm thường đã cũ vài ngày nên lần đầu sẽ gặp thông báo này. Keno/Bingo18 chỉ ghi trong khoảng 22:15–05:55 |
| Lỗi khi chạy `vietlott serve` cùng lúc với lệnh khác | DuckDB chỉ cho một tiến trình ghi một tệp kho: dừng `serve` trước, hoặc gọi API thay cho lệnh |
| Chữ tiếng Việt bị lỗi khi chuyển đầu ra sang tệp | lệnh `vietlott` tự ghi UTF-8; mở tệp bằng trình soạn thảo hỗ trợ UTF-8 |

**Dọn máy:** xóa `.venv`, `data/local` (sổ dự báo và bộ dự báo đã học trên máy này; giữ lại nếu muốn giữ sổ), `.env` và `data/*.duckdb*`.
