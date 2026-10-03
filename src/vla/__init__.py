"""Phòng thử thách mô hình xác suất LOTO / Đặc Biệt.

Gói này là MÔ HÌNH THÁCH ĐẤU, không phải đường dự báo production. Nó gồm:

* ``vla.features.engineer`` — ma trận đặc trưng (nhịp/gan, tần suất suy giảm,
  cầu vị trí, đồng xuất hiện PMI, cộng đồng Louvain, Markov Đặc Biệt);
* ``vla.models.bayesian_lgb`` — ba tầng: tiên nghiệm Dirichlet/Beta,
  LightGBM tăng cường từ tiên nghiệm, hiệu chỉnh Platt/isotonic;
* ``vla.backtest`` — walk-forward cửa sổ mở rộng và bộ chỉ số (logloss,
  Brier, Top-K, ROI theo luật trả thưởng).

Mô hình chỉ được đưa vào production khi thắng CẢ dự báo hằng số LẪN mô hình
đang chạy trên lát ngoài mẫu — cùng tinh thần cổng của ``meta_predictor`` và
``learn_ensemble_weights``. Kết quả đo nằm ở
``documentation/research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md``.
"""
