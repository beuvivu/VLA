# Vietlott: đo lại chuyên gia mẫu hình sau khi ghép với main (01-11-2026)

Đo lại lượt [24-10-2026](../pattern-learning-2026-10-24/README.md) trên mã đã ghép PR #190 với `main` ngày
01-11-2026. Khác biệt duy nhất về mô hình là bộ chữ số (Lotto đặc biệt, Max 3D/3D+, Max 3D Pro, Bingo18) nay có
chuyên gia hỗn hợp Bayes (`vlm.forecast.bayes_expert`, checkpoint version 5, 31-10-2026). Giao thức, dữ liệu seed,
cấu hình và cửa sổ 200 kỳ giữ nguyên lượt trước; không chọn lại tham số nào sau khi xem kết quả.

**Kết luận không đổi: chưa có bằng chứng nhóm mẫu hình cải thiện dự báo. `patterns=False` vẫn là mặc định.**

## 1. Tắt mẫu hình thì bản ghép trùng `main` từng bit

Nhánh hiện hành chạy hai lần trên cùng seed và cấu hình (`multi_agent=True`, `patterns=False`): một lần bằng mã
`main`, một lần bằng mã đã ghép. Trên cả 7 sản phẩm × 200 kỳ, mọi trường của từng kỳ (`gain_nats`, `brier`,
`brier_fair`, `hits`, `expected_hits`, `ticket`) và hash dữ liệu trùng nhau tuyệt đối
(`comparison.json` → `patterns_off_identical_to_main`). Ghép PR này không đổi xác suất hay vé đang phát hành.

Checkpoint production v5 (không có khoá `patterns`) nạp được nguyên vẹn và cho luật trùng từng bit:
`test_a_production_v5_checkpoint_without_pattern_keys_loads_and_publishes_the_same_law`.

## 2. Kết quả

Điểm: trung bình log P(mô hình) − log P(công bằng), nats/kỳ; dương là tốt hơn. Chênh lệch ghép cặp = mẫu hình −
hiện hành; CI 95% theo sai số chuẩn HAC; p một phía Diebold–Mariano; q hiệu chỉnh BH trên 14 phép so thăm dò.

| Sản phẩm | Hiện hành so công bằng | Mẫu hình so công bằng | Mẫu hình − hiện hành | CI 95% | q so hiện hành | q so công bằng |
|---|---:|---:|---:|---|---:|---:|
| Mega 6/45 | −0,000184 | −0,000839 | −0,000655 | [−0,005004; +0,003693] | 0,9937 | 0,9937 |
| Power 6/55 | −0,000295 | −0,000440 | −0,000145 | [−0,000563; +0,000272] | 0,9937 | 0,9937 |
| Lotto 5/35 | −0,000482 | −0,001165 | −0,000683 | [−0,001889; +0,000523] | 0,9937 | 0,9937 |
| Keno | −0,000580 | −0,000536 | +0,000044 | [−0,000292; +0,000379] | 0,9937 | 0,9937 |
| Bingo18 | −0,000284 | +0,000050 | +0,000334 | [−0,001720; +0,002387] | 0,9937 | 0,9937 |
| Max 3D / 3D+ | +0,002123 | +0,004005 | +0,001882 | [−0,011049; +0,014813] | 0,9937 | 0,9937 |
| Max 3D Pro | −0,003040 | −0,002956 | +0,000085 | [−0,004147; +0,004316] | 0,9937 | 0,9937 |

Mọi CI ghép cặp đều chứa 0.

- Mega/Power/Keno: trùng lượt 24-10, vì bộ số không đổi.
- Max 3D: nhánh hiện hành từ −0,001874 lên **+0,002123**, nhờ chuyên gia Bayes bắt được độ lệch chữ số 6 hàng
  đơn vị. Phần hơn của mẫu hình vì thế thu từ +0,004763 xuống +0,001882 nats/kỳ. Phần lớn "lợi thế" của lượt
  trước chính là độ lệch mà chuyên gia Bayes nay đã học.
- Lotto, Bingo18, Max 3D Pro: đổi nhẹ theo cùng lý do.

## 3. Giới hạn

Đây là đánh giá hồi cứu thăm dò trên seed (đến 30-09 → 02-10-2026 tùy sản phẩm), không đọc journal mới hơn, checkpoint
hay sổ live, và không thay giao thức benchmark đã đăng ký. Môi trường: Python 3.11.15, numpy 2.2.6, scipy 1.17.1,
scikit-learn 1.9.1, pydantic 2.11.4, lightgbm 4.7.0; mỗi nhánh ~6 phút khi hai tiến trình chạy song song.

## 4. Tái lập

Chạy từ `vietlott/`:

```bash
PYTHONPATH=src python scripts/evaluate_adaptive.py --seed-dir data/seed --output reports/vlm/pattern-learning-2026-11-01/baseline.json.gz --label current-multi-agent --multi-agent --draws 600 --initial-draws 400
PYTHONPATH=src python scripts/evaluate_adaptive.py --seed-dir data/seed --output reports/vlm/pattern-learning-2026-11-01/patterns.json.gz --label pattern-challenger --multi-agent --patterns --draws 600 --initial-draws 400
```

So ghép cặp bằng `vlm.forecast.evaluation.compare_runs`. Mốc công bằng là cùng báo cáo với `gain_nats = 0`. BH trên
14 p bằng `vietlott_engine.analytics.stats.benjamini_hochberg`. Kết quả nằm ở [comparison.json](comparison.json).
