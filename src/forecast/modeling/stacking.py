"""Mô hình xếp chồng cho LOTO và Đặc Biệt.

Bố cục dữ liệu theo đúng hợp đồng mà kho đang dùng trong ``data/evaluation/history/``: mỗi
hàng là một cặp (ngày, con số), nhãn là "con đó có về ở ngày kế tiếp không". Nhờ
vậy LOTO là bài toán phân loại nhị phân đa nhãn còn Đặc Biệt là phân loại một-trong-
trăm, và cả hai dùng chung một đường đặc trưng.

Chống học thuộc: mọi phép chia đều theo thời gian. ``TimeSeriesSplit`` sinh dự
đoán ngoài mẫu để huấn luyện lớp meta, nên lớp meta không bao giờ nhìn thấy dự
đoán mà lớp cơ sở đưa ra trên chính dữ liệu nó đã học.

Từ 15-11-2026 module này mang luôn giải thích Shapley (`explain.py`), bộ lọc rủi ro (`risk.py`) và gói
dự đoán `predictions_today.json` (`bundle.py`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from math import factorial
from pathlib import Path
from typing import Any, Final

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit

from core.number_reference import normalize_two_digit
from core.time_policy import iso_local
from core.xsmb_domain import baseline_rate
from soi_cau.bridges.scanner import NUMBER_SPACE, DigitTensor
from soi_cau.features import FeatureContext, FeatureMatrix, FeatureRegistry, PatternMemoryExtractor, default_registry


# --- Xếp chồng (trước 15-11-2026: modeling/stacking.py) -------------------------------------------
#
# Mô hình xếp chồng cho LOTO và Đặc Biệt.
#
# Bố cục dữ liệu theo đúng hợp đồng mà kho đang dùng trong ``data/evaluation/history/``: mỗi
# hàng là một cặp (ngày, con số), nhãn là "con đó có về ở ngày kế tiếp không". Nhờ
# vậy LOTO là bài toán phân loại nhị phân đa nhãn còn Đặc Biệt là phân loại một-trong-
# trăm, và cả hai dùng chung một đường đặc trưng.
#
# Chống học thuộc: mọi phép chia đều theo thời gian. ``TimeSeriesSplit`` sinh dự
# đoán ngoài mẫu để huấn luyện lớp meta, nên lớp meta không bao giờ nhìn thấy dự
# đoán mà lớp cơ sở đưa ra trên chính dữ liệu nó đã học.

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

        Với Đặc Biệt phải là phân phối phân loại tổng bằng 1, và luôn giữ lại một phần
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
    """Dự đoán LOTO — đa nhãn, mỗi con một xác suất độc lập."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(mode="loto", **kwargs)  # type: ignore[arg-type]


class DeModel(StackedEnsemble):
    """Dự đoán Đặc Biệt — phân loại một-trong-trăm, tổng xác suất bằng 1."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(mode="de", **kwargs)  # type: ignore[arg-type]


# --- Giải thích Shapley (trước 15-11-2026: modeling/explain.py) -----------------------------------
#
# Đóng góp của từng nhóm đặc trưng vào một dự đoán cụ thể.
#
# Với bốn nhóm đặc trưng, giá trị Shapley tính được **chính xác** chứ không cần
# xấp xỉ: chỉ có 2^4 = 16 liên minh, và mỗi liên minh là một lượt dự đoán trên
# 100 hàng. Đây là điểm khác biệt đáng kể so với xấp xỉ lấy mẫu — con số báo ra là
# phân bổ Shapley thật, không phải ước lượng có sai số không nêu.
#
# Cách "tắt" một nhóm là thay các cột của nó bằng trung vị trên toàn tập huấn
# luyện, tức đưa nhóm đó về mức "không mang thông tin gì Đặc Biệt về con này".
# Đây là quy ước phải nêu rõ: Shapley luôn được định nghĩa tương đối với một nền
# tham chiếu, và chọn nền khác sẽ cho phân bổ khác.

_SHAPLEY_EPS = 1e-12


@dataclass
class Explainer:
    """Phân bổ Shapley chính xác ở cấp nhóm đặc trưng."""

    model: StackedEnsemble
    reference: np.ndarray

    @classmethod
    def from_training(cls, model: StackedEnsemble, features: np.ndarray) -> Explainer:
        """Lấy nền tham chiếu là trung vị từng cột trên tập huấn luyện."""
        return cls(model=model, reference=np.median(features, axis=0))

    @property
    def group_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.model.groups))

    def _masked(self, values: np.ndarray, active: frozenset[str]) -> np.ndarray:
        """Bản sao ma trận với các nhóm ngoài ``active`` đưa về nền tham chiếu."""
        out = values.copy()
        for name, (start, stop) in self.model.groups.items():
            if name not in active:
                out[:, start:stop] = self.reference[start:stop]
        return out

    def contributions(self, matrix: FeatureMatrix) -> dict[str, np.ndarray]:
        """Giá trị Shapley của mỗi nhóm cho cả 100 con, tính chính xác."""
        names = self.group_names
        n = len(names)
        if n == 0:
            return {}

        # Một lượt dự đoán cho mỗi liên minh, dùng lại cho mọi nhóm.
        values: dict[frozenset[str], np.ndarray] = {}
        for size in range(n + 1):
            for subset in combinations(names, size):
                active = frozenset(subset)
                values[active] = self.model.predict_proba(self._masked(matrix.values, active))

        shapley = {name: np.zeros(matrix.values.shape[0]) for name in names}
        for name in names:
            others = [x for x in names if x != name]
            for size in range(len(others) + 1):
                weight = factorial(size) * factorial(n - size - 1) / factorial(n)
                for subset in combinations(others, size):
                    active = frozenset(subset)
                    shapley[name] += weight * (values[active | {name}] - values[active])
        return shapley

    def group_shares(self, matrix: FeatureMatrix, row: int) -> dict[str, float]:
        """Đóng góp của mỗi nhóm cho một con, chuẩn hóa thành phần trăm.

        Chuẩn hóa theo tổng trị tuyệt đối để nhóm kéo xác suất *xuống* vẫn hiện
        ra thay vì bị triệt tiêu lặng lẽ bởi nhóm kéo lên.
        """
        contributions = self.contributions(matrix)
        magnitudes = {name: abs(float(v[row])) for name, v in contributions.items()}
        total = sum(magnitudes.values())
        if total <= _SHAPLEY_EPS:
            return dict.fromkeys(magnitudes, 0.0)
        return {
            name: float(contributions[name][row]) / total
            for name in sorted(magnitudes, key=lambda k: -magnitudes[k])
        }

    def top_reasons(self, matrix: FeatureMatrix, row: int, k: int = 3) -> list[tuple[str, float]]:
        """``k`` nhóm đóng góp mạnh nhất cho một con, kèm tỉ trọng có dấu."""
        shares = self.group_shares(matrix, row)
        ordered = sorted(shares.items(), key=lambda item: -abs(item[1]))
        return ordered[:k]


# --- Lọc rủi ro (trước 15-11-2026: modeling/risk.py) ----------------------------------------------
#
# Bộ lọc rủi ro: chặn bẫy lô gan.
#
# Một con càng lâu không về càng dễ trông như "sắp phải về". Với xổ số công bằng
# thì niềm tin đó sai — mỗi kỳ độc lập với kỳ trước, nên khoảng cách dài không làm
# tăng xác suất. Bộ lọc này không sửa xác suất theo hướng nào cả; nó chỉ **đánh
# dấu** các con đã vượt ngưỡng nhịp gan để phần trình bày nói rõ ra, và tùy chọn
# loại chúng khỏi danh sách gợi ý.

DEFAULT_GAN_THRESHOLD_DAYS = 15


@dataclass
class GanFilter:
    """Đánh dấu và (tùy chọn) loại các con có nhịp gan vượt ngưỡng."""

    threshold_days: int = DEFAULT_GAN_THRESHOLD_DAYS
    exclude: bool = False

    def gaps(self, ctx: FeatureContext) -> np.ndarray:
        """Số ngày kể từ lần về gần nhất, cho cả 100 con."""
        block = PatternMemoryExtractor().extract(ctx)
        return block[:, 2]

    def flagged(self, ctx: FeatureContext) -> list[str]:
        gaps = self.gaps(ctx)
        return [normalize_two_digit(int(n)) for n in np.flatnonzero(gaps > self.threshold_days)]

    def apply(self, probabilities: np.ndarray, ctx: FeatureContext) -> np.ndarray:
        """Trả về xác suất đã lọc; giữ nguyên nếu chỉ ở chế độ cảnh báo.

        Khi loại, phần xác suất bị lấy đi được chia lại cho các con còn lại nếu
        đầu vào là phân phối tổng bằng 1 — bỏ qua bước đó sẽ tạo ra một phân
        phối hụt, và mọi phép chấm log-loss phía sau sẽ sai lệch.
        """
        if probabilities.shape != (NUMBER_SPACE,):
            raise ValueError(f"xác suất phải là vector {NUMBER_SPACE} phần tử")
        if not self.exclude:
            return probabilities

        keep = self.gaps(ctx) <= self.threshold_days
        if not keep.any():
            return probabilities
        filtered = np.where(keep, probabilities, 0.0)
        total = float(probabilities.sum())
        if abs(total - 1.0) < 1e-6:
            return filtered / max(filtered.sum(), 1e-12)
        return filtered


# --- Gói dự đoán (trước 15-11-2026: modeling/bundle.py) -------------------------------------------
#
# Gói dự đoán và schema JSON đầu ra.
#
# Bổ sung cho ``picks_loto.json`` / ``picks_de.json`` chứ không thay thế — các
# trang trong ``docs/`` đang đọc hai tệp đó.
#
# Mọi con số đưa ra đều mang theo bối cảnh của nó: xác suất đi kèm đường cơ sở,
# danh sách cầu đi kèm số giả thuyết đã thử. Một xác suất 0,26 không có đường cơ
# sở 0,2377 bên cạnh sẽ được đọc là "cao", và đó là cách trình bày sai lệch nhất
# có thể ở miền này.

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class NumberPick:
    """Một con số kèm xác suất và lý do đóng góp."""

    number: str
    probability: float
    baseline: float
    lift: float
    contribution_reasons: dict[str, float]
    gan_days: int
    gan_flagged: bool


@dataclass(frozen=True)
class PredictionBundle:
    """Đầu ra hằng ngày, ghi ra ``data/predictions_today.json``."""

    date: str
    generated_at_local: str
    generated_at_utc: str
    top_lo_to: list[NumberPick]
    top_dac_biet: dict[str, Any]
    active_bridges: list[dict[str, Any]]
    disclaimer: str
    schema_version: str = SCHEMA_VERSION
    evidence: dict[str, Any] = field(default_factory=dict)
    gan_flagged: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["top_lo_to"] = [asdict(pick) for pick in self.top_lo_to]
        return payload

    def to_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def build_picks(
    probabilities: np.ndarray,
    *,
    baseline: float,
    gaps: np.ndarray,
    gan_threshold: int,
    reasons: dict[int, dict[str, float]],
    top_k: int = 10,
    max_per_tail: int | None = None,
) -> list[NumberPick]:
    """Lấy ``top_k`` con có xác suất cao nhất, kèm bối cảnh đầy đủ.

    ``max_per_tail`` giới hạn số con cùng đuôi (xem ``pick_diversity``);
    None giữ thứ tự xác suất thuần.
    """
    if max_per_tail is None:
        order = np.lexsort((np.arange(len(probabilities)), -probabilities))[:top_k]
    else:
        from ensemble.pick_diversity import diversified_order

        order = diversified_order(probabilities, top_k, max_per_tail=max_per_tail)
    return [
        NumberPick(
            number=normalize_two_digit(int(n)),
            probability=float(probabilities[n]),
            baseline=float(baseline),
            lift=float(probabilities[n] - baseline),
            contribution_reasons={k: round(v, 4) for k, v in reasons.get(int(n), {}).items()},
            gan_days=int(gaps[n]),
            gan_flagged=bool(gaps[n] > gan_threshold),
        )
        for n in order
    ]


def utc_stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_stamp() -> str:
    """Dấu thời gian theo giờ Việt Nam, dùng lại chính sách múi giờ của kho."""
    return iso_local()
