# Chính sách và mô hình bảo mật

## Báo cáo lỗ hổng

Không công bố dữ liệu nhạy cảm hoặc mã khai thác trong issue công khai. Hãy dùng
[GitHub Security Advisories](https://github.com/beuvivu/VLA/security/advisories/new)
và cung cấp phiên bản/commit, điều kiện tái hiện, ảnh hưởng và bản vá đề xuất nếu
có. Không gửi khóa, cookie hay thông tin đăng nhập thật.

## Ranh giới tin cậy

- HTML/JSON từ các trang kết quả là **dữ liệu không tin cậy**. Bộ thu thập chỉ
  chấp nhận chữ số ASCII nguyên đúng độ rộng giải và không tự “sửa” token lạ.
- Kết quả gần nhất chỉ được đưa vào lịch sử chuẩn sau khi toàn bộ 27 ô vượt kiểm
  tra miền dữ liệu và có đồng thuận từ ít nhất hai nhóm nhà cung cấp độc lập.
- `xsmb.csv`, `xsmb.json` và `xsmb-sparse.csv` phải có ngày duy nhất, đúng định
  dạng, cùng trục ngày, đủ lược đồ và chỉ chứa số nguyên hữu hạn hợp lệ.
- Dữ liệu chèn vào trang tĩnh được escape khi tuần tự hóa JSON; giao diện dùng
  `textContent`/DOM node thay cho HTML động. Trang sinh mới có CSP tự chứa và
  chính sách không gửi referrer.
- Feature sản xuất là allowlist trong mã nguồn. Model pack không được tự thêm
  cột; metadata, xác suất, trọng số, calibration và output model đều phải hữu hạn
  và đúng miền trước khi được dùng.
- GitHub Actions chỉ nhận quyền ghi ở job cần ghi. Tệp tạm được tạo ngẫu nhiên
  trong thư mục tạm của runner, không dùng tên chung có thể bị ghi đè.

## Artifact mô hình

`joblib` dùng định dạng dựa trên pickle và **có thể thực thi mã khi giải tuần tự**.
Chỉ tải model do workflow tin cậy của chính repository tạo ra và đã được review.
Không tải model từ URL, issue, pull request không tin cậy hoặc tệp người dùng gửi.
Kiểm tra schema sau `joblib.load` bảo vệ tính tương thích/allowlist, nhưng không
biến một tệp pickle thù địch thành an toàn.

## Thu thập dữ liệu công khai

Collector chỉ gửi HTTP thông thường tới trang công khai. Không dùng thư viện né
anti-bot, không vượt CAPTCHA, không dùng API riêng và không lưu cookie đăng nhập.
Nguồn chặn truy cập phải được ghi nhận là không khả dụng thay vì tìm cách vượt
kiểm soát của họ.

## Bí mật và quyền vận hành

- Cấu hình mặc định không cần secret riêng; `GITHUB_TOKEN` do Actions cấp chỉ dùng
  trong đúng job và đúng permission khai báo.
- `.env`, log và cache cục bộ không được commit. Không ghi token vào artifact,
  dashboard, exception hoặc output kiểm thử.
- Nhánh `live` là ảnh chụp một tệp và được force-push có chủ đích. Không áp dụng
  cơ chế này cho `main`.
- Dependabot theo dõi cả pip và GitHub Actions. Mọi nâng cấp phụ thuộc vẫn phải
  qua CI và review.

## Kiểm tra trước phát hành

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
bash scripts/number_integrity_check.sh
bash scripts/domain_challenger_check.sh
bash scripts/research_release_check.sh
```

`scripts/release_check.sh` là cổng tích hợp đầy đủ, bao gồm kiểm tra dữ liệu,
artifact, rò rỉ thời gian và production audit.

## Giới hạn đã biết

- CSP của trang tĩnh vẫn cần `'unsafe-inline'` cho JavaScript/CSS tự chứa. Vì vậy
  escape dữ liệu và tránh DOM HTML sink vẫn là lớp bảo vệ bắt buộc.
- Các action hiện được khóa theo phiên bản lớn và cập nhật bằng Dependabot, chưa
  khóa theo commit SHA bất biến.
- Thay đổi cấu trúc HTML của nguồn công khai có thể làm parser mất dữ liệu. Thiết
  kế hiện tại fail-closed và cần kiểm toán nguồn định kỳ.
