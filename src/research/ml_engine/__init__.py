"""``ml_engine`` — hệ thống học tiếp diễn tự chủ cho dự đoán XSMB.

Module này gộp các thành phần vào một luồng có kiểm soát:

* :mod:`research.ml_engine.schema` — hợp đồng dữ liệu, chặn rò rỉ thời gian từ gốc.
* :mod:`research.ml_engine.features` — sinh đặc trưng tự động, bảo đảm chỉ dùng quá khứ.
* :mod:`research.ml_engine.selection` — chọn đặc trưng bằng SHAP hoặc tầm quan trọng hoán vị.
* :mod:`research.ml_engine.models` — cây tăng cường, LambdaMART và mô hình chuỗi sâu.
* :mod:`research.ml_engine.aggregation` — trọng số mũ trên log-loss, có chia sẻ cố định.
* :mod:`research.ml_engine.drift` — ADWIN và Kolmogorov–Smirnov trên chuỗi sai số.
* :mod:`research.ml_engine.fallback` — cổng độ tin ``model_trust`` từ kỹ năng ngoài mẫu.
* :mod:`research.ml_engine.metrics` — quy tắc chấm điểm chặt và chỉ số kinh tế.
* :mod:`research.ml_engine.validation` — cuốn chiếu và dò siêu tham số tách ba đoạn thời gian.

Điểm vào vận hành là :func:`research.ml_engine.main_pipeline.main`.
"""

from research.ml_engine.aggregation import AggregationError, ExponentialWeights
from research.ml_engine.capabilities import CAPABILITIES, Capabilities
from research.ml_engine.drift import ConceptDriftDetector, DriftVerdict
from research.ml_engine.fallback import Mode, SafeModeController
from research.ml_engine.features import FeatureMatrix, build_features, build_training_table
from research.ml_engine.metrics import EconomicModel, PerformanceReport, PerformanceTracker
from research.ml_engine.models import RankingBooster, TabularBooster, TemporalSequenceModel
from research.ml_engine.schema import BASELINE_RATE, DailyRequest, ObservationMatrix, SchemaError
from research.ml_engine.selection import SelectionResult, select_features
from research.ml_engine.validation import WalkForwardValidator

__all__ = [
    "BASELINE_RATE",
    "CAPABILITIES",
    "AggregationError",
    "Capabilities",
    "ConceptDriftDetector",
    "DailyRequest",
    "DriftVerdict",
    "EconomicModel",
    "ExponentialWeights",
    "FeatureMatrix",
    "Mode",
    "ObservationMatrix",
    "PerformanceReport",
    "PerformanceTracker",
    "RankingBooster",
    "SafeModeController",
    "SchemaError",
    "SelectionResult",
    "TabularBooster",
    "TemporalSequenceModel",
    "WalkForwardValidator",
    "build_features",
    "build_training_table",
    "select_features",
]
