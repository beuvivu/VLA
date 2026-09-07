"""``ml_engine`` — hệ thống học tiếp diễn tự chủ cho dự đoán XSMB.

Module này gộp sáu thành phần vào một luồng có kiểm soát:

* :mod:`ml_engine.schema` — hợp đồng dữ liệu, chặn rò rỉ thời gian từ gốc.
* :mod:`ml_engine.features` — sinh đặc trưng tự động, bảo đảm chỉ dùng quá khứ.
* :mod:`ml_engine.selection` — chọn đặc trưng bằng SHAP hoặc tầm quan trọng hoán vị.
* :mod:`ml_engine.models` — cây tăng cường, LambdaMART và mô hình chuỗi sâu.
* :mod:`ml_engine.bandit` — Thompson Sampling có chiết khấu để trộn trọng số.
* :mod:`ml_engine.drift` — ADWIN và Kolmogorov–Smirnov trên chuỗi sai số.
* :mod:`ml_engine.fallback` — chuyển chế độ an toàn khi hệ thống hết đáng tin.
* :mod:`ml_engine.metrics` — quy tắc chấm điểm chặt và chỉ số kinh tế.
* :mod:`ml_engine.validation` — cuốn chiếu và dò siêu tham số tách ba đoạn thời gian.

Điểm vào vận hành là :func:`ml_engine.main_pipeline.main`.
"""

from ml_engine.bandit import ArmState, BanditError, DiscountedThompsonSamplingMAB
from ml_engine.capabilities import CAPABILITIES, Capabilities
from ml_engine.drift import ConceptDriftDetector, DriftVerdict
from ml_engine.fallback import Mode, SafeModeController
from ml_engine.features import FeatureMatrix, build_features, build_training_table
from ml_engine.metrics import EconomicModel, PerformanceReport, PerformanceTracker
from ml_engine.models import RankingBooster, TabularBooster, TemporalSequenceModel
from ml_engine.schema import BASELINE_RATE, DailyRequest, ObservationMatrix, SchemaError
from ml_engine.selection import SelectionResult, select_features
from ml_engine.validation import WalkForwardValidator

__all__ = [
    "BASELINE_RATE",
    "CAPABILITIES",
    "ArmState",
    "BanditError",
    "Capabilities",
    "ConceptDriftDetector",
    "DailyRequest",
    "DiscountedThompsonSamplingMAB",
    "DriftVerdict",
    "EconomicModel",
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
