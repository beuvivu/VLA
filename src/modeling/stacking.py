"""Mô hình xếp chồng cho lô tô và Đặc Biệt.

Bố cục dữ liệu theo đúng hợp đồng mà kho đang dùng trong ``data/history/``: mỗi
hàng là một cặp (ngày, con số), nhãn là "con đó có về ở ngày kế tiếp không". Nhờ
vậy lô tô là bài toán phân loại nhị phân đa nhãn còn ĐB là phân loại một-trong-
trăm, và cả hai dùng chung một đường đặc trưng.

Chống học thuộc: mọi phép chia đều theo thời gian. ``TimeSeriesSplit`` sinh dự
đoán ngoài mẫu để huấn luyện lớp meta, nên lớp meta không bao giờ nhìn thấy dự
đoán mà lớp cơ sở đưa ra trên chính dữ liệu nó đã học.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit

from bridges.tensor import NUMBER_SPACE, DigitTensor
from features import FeatureContext, FeatureMatrix, FeatureRegistry, default_registry
from xsmb_domain import baseline_rate

_EPS: Final[float] = 1e-9
MIN_UNIFORM_SHARE: Final[float] = 1e-4


@dataclass(frozen=True)
class TrainingData:
    """Ma trận đặc trưng, nhãn và chỉ số ngày cho một dải lịch sử."""

    features: np.ndarray
    labels: np.ndarray
    day_index: np.ndarray
    columns: tuple[str, ...]
    groups: dict[str, tuple[int, int]]

    @property
    def n_days(self) -> int:
        return int(len(np.unique(self.day_index)))


def build_training_data(
    tensor: DigitTensor,
    *,
    mode: str = "loto",
    warmup_days: int = 180,
    registry: FeatureRegistry | None = None,
    last_anchor: int | None = None,
) -> TrainingData:
    """Dựng ma trận huấn luyện, nhãn lấy từ ngày kế tiếp ngày neo.

    Nhãn luôn đến từ ``anchor + 1`` còn đặc trưng luôn dừng ở ``anchor``, nên
    khoảng cách một ngày giữa hai bên là bất biến của hàm này chứ không phải quy
    ước mà nơi gọi phải nhớ.
    """
    if mode not in {"loto", "de"}:
        raise ValueError("mode phải là 'loto' hoặc 'de'")
    registry = registry or default_registry()
    stop = tensor.n_days - 1 if last_anchor is None else last_anchor + 1
    if stop <= warmup_days:
        raise ValueError("lịch sử quá ngắn so với warmup_days")

    hits = tensor.loto_hits()
    blocks, labels, days = [], [], []
    columns: tuple[str, ...] = ()
    groups: dict[str, tuple[int, int]] = {}

    for anchor in range(warmup_days, stop):
        matrix = registry.build_matrix(FeatureContext(tensor=tensor, anchor_index=anchor))
        if not columns:
            columns, groups = matrix.columns, matrix.groups
        blocks.append(matrix.values)
        if mode == "de":
            target = np.zeros(NUMBER_SPACE, dtype=np.int8)
            target[int(tensor.de_index[anchor + 1])] = 1
        else:
            target = hits[anchor + 1].astype(np.int8)
        labels.append(target)
        days.append(np.full(NUMBER_SPACE, anchor, dtype=np.int32))

    return TrainingData(
        features=np.vstack(blocks),
        labels=np.concatenate(labels),
        day_index=np.concatenate(days),
        columns=columns,
        groups=groups,
    )


def _base_learners() -> list[tuple[str, object]]:
    """Lớp cơ sở dùng thư viện đã có trong kho, không thêm phụ thuộc nặng.

    ``HistGradientBoostingClassifier`` là boosting theo histogram của
    scikit-learn; trên dữ liệu bảng cỡ này nó tương đương XGBoost/LightGBM mà
    không kéo theo ba phụ thuộc mới vào CI.
    """
    return [
        (
            "boosting",
            HistGradientBoostingClassifier(
                max_depth=3,
                max_iter=120,
                learning_rate=0.05,
                l2_regularization=1.0,
                early_stopping=False,
                random_state=20260906,
            ),
        ),
        (
            "linear",
            LogisticRegression(max_iter=1000, C=0.5, random_state=20260906),
        ),
    ]


@dataclass
class StackedEnsemble:
    """Xếp chồng: vài lớp cơ sở, một lớp meta học trên dự đoán ngoài mẫu."""

    mode: str = "loto"
    n_splits: int = 4
    name: str = "stacked_ensemble"
    description: str = "Boosting + tuyến tính, xếp chồng bằng chia theo thời gian"
    base_learners: list[tuple[str, object]] = field(default_factory=_base_learners)
    meta_learner: object = field(
        default_factory=lambda: LogisticRegression(max_iter=1000, random_state=20260906)
    )
    columns: tuple[str, ...] = ()
    groups: dict[str, tuple[int, int]] = field(default_factory=dict)
    _fitted: bool = False

    def fit(self, data: TrainingData) -> StackedEnsemble:
        """Huấn luyện lớp cơ sở rồi lớp meta trên dự đoán ngoài mẫu."""
        if len(np.unique(data.labels)) < 2:
            raise ValueError("nhãn chỉ có một lớp; không huấn luyện được")
        self.columns, self.groups = data.columns, data.groups

        # Chia theo thời gian trên NGÀY, không trên hàng: cắt giữa một ngày sẽ
        # để 99 con của ngày đó ở tập huấn luyện và 1 con ở tập kiểm.
        unique_days = np.unique(data.day_index)
        splitter = TimeSeriesSplit(n_splits=self.n_splits)
        meta_features = np.zeros((len(data.labels), len(self.base_learners)))

        for train_days, test_days in splitter.split(unique_days):
            train = np.isin(data.day_index, unique_days[train_days])
            test = np.isin(data.day_index, unique_days[test_days])
            if len(np.unique(data.labels[train])) < 2:
                continue
            for column, (_, learner) in enumerate(self.base_learners):
                fold_model = _clone(learner)
                fold_model.fit(data.features[train], data.labels[train])
                meta_features[test, column] = fold_model.predict_proba(data.features[test])[:, 1]

        scored = meta_features.any(axis=1)
        if scored.sum() == 0 or len(np.unique(data.labels[scored])) < 2:
            raise ValueError("không sinh được dự đoán ngoài mẫu để học lớp meta")
        self.meta_learner.fit(meta_features[scored], data.labels[scored])

        # Lớp cơ sở cuối cùng học trên toàn bộ dữ liệu; chỉ lớp meta cần ngoài mẫu.
        for _, learner in self.base_learners:
            learner.fit(data.features, data.labels)
        self._fitted = True
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Xác suất nổ cho từng hàng."""
        if not self._fitted:
            raise RuntimeError("mô hình chưa được huấn luyện")
        stacked = np.column_stack(
            [learner.predict_proba(features)[:, 1] for _, learner in self.base_learners]
        )
        return self.meta_learner.predict_proba(stacked)[:, 1]

    def predict_day(self, matrix: FeatureMatrix) -> np.ndarray:
        """Phân phối xác suất trên 100 con cho một ngày.

        Với ĐB phải là phân phối phân loại tổng bằng 1, và luôn giữ lại một phần
        nền đều: không mô hình nào được phép tuyên bố một con là bất khả thi, vì
        xác suất 0 mà con đó về sẽ cho log-loss bùng nổ.
        """
        raw = self.predict_proba(matrix.values)
        if self.mode != "de":
            return np.clip(raw, _EPS, 1.0 - _EPS)
        total = raw.sum()
        shaped = raw / total if total > _EPS else np.full(NUMBER_SPACE, 1.0 / NUMBER_SPACE)
        blended = (1.0 - MIN_UNIFORM_SHARE) * shaped + MIN_UNIFORM_SHARE / NUMBER_SPACE
        return blended / blended.sum()

    @property
    def baseline(self) -> float:
        return baseline_rate(self.mode)


def _clone(estimator: object) -> object:
    from sklearn.base import clone

    return clone(estimator)


class LotoModel(StackedEnsemble):
    """Dự đoán lô tô — đa nhãn, mỗi con một xác suất độc lập."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(mode="loto", **kwargs)  # type: ignore[arg-type]


class DeModel(StackedEnsemble):
    """Dự đoán Đặc Biệt — phân loại một-trong-trăm, tổng xác suất bằng 1."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(mode="de", **kwargs)  # type: ignore[arg-type]
