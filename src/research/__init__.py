"""Phòng nghiên cứu và phép kiểm tiến cứu đã đăng ký; không vào tổ hợp xác suất.

Gói con ``ml_engine``: khung học tiếp diễn (trọng số mũ trên log-loss, cổng ``SafeModeController``).
Gói con ``vla``: phòng thử thách mô hình xác suất (tiên nghiệm Dirichlet/Beta, LightGBM phần dư,
walk-forward). Cả hai là khung thách đấu, không nằm trong pipeline.
"""
