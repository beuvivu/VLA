"""Các bộ học đứng sau một giao diện chung.

Vì sao cần giao diện chung
---------------------------

Tầng điều phối và tầng bandit không được biết mô hình nào đang chạy: bandit chỉ
cần một tên và một véc-tơ xác suất. Nhờ vậy thêm hoặc bỏ một họ mô hình không
chạm tới phần còn lại của hệ thống, và mọi mô hình đều bị chấm bằng đúng một
thước đo.

Ba họ được cài
---------------

* ``TabularBooster`` — cây tăng cường gradient trên đặc trưng bảng. Ưu tiên
  LightGBM, rồi CatBoost, cuối cùng ``HistGradientBoosting`` của sklearn (dùng
  cùng thuật toán lược đồ như LightGBM).
* ``RankingBooster`` — LambdaMART: mỗi ngày là một nhóm gồm 100 ứng viên, mô
  hình học *thứ tự* trong nhóm thay vì xác suất từng con.
* ``TemporalSequenceModel`` — GRU trên chuỗi véc-tơ kết quả theo ngày, nắm phụ
  thuộc thời gian mà đặc trưng cửa sổ trượt không diễn đạt được.

Về xác suất và thứ hạng
------------------------

``RankingBooster`` tối ưu một mục tiêu xếp hạng nên đầu ra **không phải xác
suất** — nó chỉ đúng về thứ tự. Trả thẳng điểm số ra ngoài sẽ phá hỏng mọi phép
đo log-loss phía sau. Vì vậy lớp này hiệu chỉnh điểm về thang xác suất bằng hồi
quy đẳng hướng khớp trên chính tập huấn luyện, và ghi rõ trong ``is_calibrated``
để tầng trên biết nó đã được hiệu chỉnh chứ không phải xác suất tự nhiên.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Protocol, runtime_checkable

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from ml_engine.capabilities import CAPABILITIES
from ml_engine.schema import BASELINE_RATE, NUMBER_SPACE

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_EPSILON: Final[float] = 1e-6


def _clip(values: np.ndarray) -> np.ndarray:
    return np.clip(values, _EPSILON, 1.0 - _EPSILON)


@runtime_checkable
class Learner(Protocol):
    """Hợp đồng tối thiểu mà tầng điều phối yêu cầu ở một bộ học."""

    name: str

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        """Khớp mô hình trên đặc trưng ``x`` và nhãn nhị phân ``y``."""
        ...

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        """Trả xác suất nhãn dương, mảng một chiều cùng số hàng với ``x``."""
        ...


class TabularBooster:
    """Cây tăng cường gradient trên đặc trưng bảng.

    Attributes:
        name: Tên hiển thị của bộ học.
        params: Siêu tham số; khóa dùng chung cho cả ba backend.
        backend: Thư viện thực sự được dùng, xác định lúc khớp.
    """

    def __init__(self, name: str = "tabular_boosting", **params: Any) -> None:
        self.name = name
        self.params: dict[str, Any] = {
            "max_depth": 3,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "l2_regularization": 1.0,
            **params,
        }
        self.backend = "chưa khớp"
        self._model: Any = None

    def _build(self) -> tuple[Any, str]:
        """Chọn cài đặt tốt nhất hiện có và dựng mô hình chưa khớp."""
        depth = int(self.params["max_depth"])
        trees = int(self.params["n_estimators"])
        rate = float(self.params["learning_rate"])
        l2 = float(self.params["l2_regularization"])

        if CAPABILITIES.lightgbm is not None:
            return (
                CAPABILITIES.lightgbm.LGBMClassifier(
                    max_depth=depth,
                    n_estimators=trees,
                    learning_rate=rate,
                    reg_lambda=l2,
                    num_leaves=max(2, 2**depth),
                    min_child_samples=int(self.params.get("min_child_samples", 40)),
                    subsample=float(self.params.get("subsample", 0.9)),
                    subsample_freq=1,
                    colsample_bytree=float(self.params.get("colsample_bytree", 0.9)),
                    random_state=0,
                    verbose=-1,
                    n_jobs=1,
                ),
                "lightgbm",
            )
        if CAPABILITIES.catboost is not None:
            return (
                CAPABILITIES.catboost.CatBoostClassifier(
                    depth=depth,
                    iterations=trees,
                    learning_rate=rate,
                    l2_leaf_reg=l2,
                    random_seed=0,
                    verbose=False,
                    thread_count=1,
                ),
                "catboost",
            )
        return (
            HistGradientBoostingClassifier(
                max_depth=depth,
                max_iter=trees,
                learning_rate=rate,
                l2_regularization=l2,
                random_state=0,
            ),
            "sklearn",
        )

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        """Khớp mô hình.

        Args:
            x: Đặc trưng ``(n, d)``.
            y: Nhãn nhị phân ``(n,)``.

        Raises:
            ValueError: Khi nhãn chỉ có một lớp — khi đó không có gì để học và
                một mô hình khớp được sẽ chỉ mã hóa hằng số.
        """
        if len(np.unique(y)) < 2:
            raise ValueError("cần cả hai lớp trong nhãn để khớp")
        self._model, self.backend = self._build()
        self._model.fit(x, y)

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        """Xác suất nhãn dương.

        Args:
            x: Đặc trưng ``(n, d)``.

        Returns:
            Mảng ``(n,)`` xác suất đã kẹp khỏi 0 và 1.

        Raises:
            RuntimeError: Khi gọi trước lúc khớp.
        """
        if self._model is None:
            raise RuntimeError(f"{self.name}: phải gọi fit() trước predict_proba()")
        return _clip(np.asarray(self._model.predict_proba(x))[:, 1])


class RankingBooster:
    """LambdaMART: học thứ tự trong nhóm 100 ứng viên của mỗi ngày.

    Attributes:
        name: Tên hiển thị.
        group_size: Số ứng viên mỗi nhóm; ở miền này luôn là 100.
        is_calibrated: Điểm xếp hạng đã được đưa về thang xác suất hay chưa.
    """

    def __init__(self, name: str = "ranking_lambdamart", **params: Any) -> None:
        self.name = name
        self.group_size = NUMBER_SPACE
        self.params: dict[str, Any] = {
            "max_depth": 3,
            "n_estimators": 200,
            "learning_rate": 0.05,
            **params,
        }
        self.is_calibrated = False
        self._model: Any = None
        self._calibrator: IsotonicRegression | None = None
        self._fallback: TabularBooster | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        """Khớp mô hình xếp hạng theo nhóm ngày.

        Args:
            x: Đặc trưng ``(n_days*100, d)``, các hàng của cùng một ngày liền kề.
            y: Nhãn nhị phân ``(n_days*100,)``.

        Raises:
            ValueError: Khi số hàng không chia hết cho kích thước nhóm.
        """
        if x.shape[0] % self.group_size != 0:
            raise ValueError(
                f"số hàng ({x.shape[0]}) phải chia hết cho kích thước nhóm ({self.group_size})"
            )
        if CAPABILITIES.lightgbm is None:
            # Không có LightGBM thì không có LambdaMART; lui về phân loại rồi
            # xếp hạng theo xác suất. Thứ tự vẫn có, chỉ là không tối ưu trực
            # tiếp cho thứ tự.
            LOGGER.warning("%s: thiếu lightgbm, lui về phân loại bảng", self.name)
            self._fallback = TabularBooster(name=f"{self.name}_fallback", **self.params)
            self._fallback.fit(x, y)
            self.is_calibrated = False
            return

        groups = [self.group_size] * (x.shape[0] // self.group_size)
        self._model = CAPABILITIES.lightgbm.LGBMRanker(
            objective="lambdarank",
            max_depth=int(self.params["max_depth"]),
            n_estimators=int(self.params["n_estimators"]),
            learning_rate=float(self.params["learning_rate"]),
            num_leaves=max(2, 2 ** int(self.params["max_depth"])),
            label_gain=[0, 1],  # nhãn nhị phân: chỉ hai mức liên quan
            random_state=0,
            verbose=-1,
            n_jobs=1,
        )
        self._model.fit(x, y, group=groups)

        # Hiệu chỉnh điểm xếp hạng về thang xác suất bằng hồi quy đẳng hướng.
        raw = np.asarray(self._model.predict(x), dtype=float)
        self._calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._calibrator.fit(raw, y.astype(float))
        self.is_calibrated = True

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        """Xác suất đã hiệu chỉnh từ điểm xếp hạng.

        Args:
            x: Đặc trưng ``(n, d)``.

        Returns:
            Mảng ``(n,)`` xác suất.

        Raises:
            RuntimeError: Khi gọi trước lúc khớp.
        """
        if self._fallback is not None:
            return self._fallback.predict_proba(x)
        if self._model is None or self._calibrator is None:
            raise RuntimeError(f"{self.name}: phải gọi fit() trước predict_proba()")
        return _clip(self._calibrator.predict(np.asarray(self._model.predict(x), dtype=float)))


class TemporalSequenceModel:
    """Mô hình chuỗi trên véc-tơ kết quả theo ngày.

    Dùng GRU khi có PyTorch. Không có thì lui về hồi quy logistic đa nhãn trên
    cửa sổ trễ — vẫn là mô hình chuỗi, chỉ là tuyến tính và không có trạng thái.

    Cảnh báo về dung lượng, và đây là điểm quan trọng nhất của lớp này: một GRU
    64 chiều trên đầu vào 100 chiều có khoảng 31 700 tham số, trong khi lịch sử
    391 kỳ chỉ cho 39 100 quan sát nhị phân. Tỉ lệ tham số trên quan sát xấp xỉ
    1:1.2. Ở tỉ lệ đó mô hình ghi nhớ tập huấn luyện chứ không học quy luật, và
    không có mức chính quy hóa nào sửa được — vấn đề nằm ở lượng thông tin trong
    dữ liệu, không phải ở siêu tham số. Lớp này giữ ``hidden_size`` nhỏ mặc định
    vì lý do đó.

    Attributes:
        name: Tên hiển thị.
        hidden_size: Số chiều trạng thái ẩn.
        lookback: Số ngày lịch sử đưa vào mỗi mẫu.
        backend: ``"torch"`` hoặc ``"linear"``.
    """

    def __init__(
        self,
        name: str = "temporal_sequence",
        *,
        hidden_size: int = 16,
        lookback: int = 14,
        epochs: int = 40,
        learning_rate: float = 0.01,
        seed: int = 0,
    ) -> None:
        self.name = name
        self.hidden_size = int(hidden_size)
        self.lookback = int(lookback)
        self.epochs = int(epochs)
        self.learning_rate = float(learning_rate)
        self.seed = int(seed)
        self.backend = "torch" if CAPABILITIES.torch is not None else "linear"
        self._model: Any = None
        self._linear_weights: np.ndarray | None = None

    @property
    def parameter_count(self) -> int:
        """Số tham số của mô hình, để so với lượng dữ liệu sẵn có."""
        if self.backend == "torch":
            gru = 3 * (self.hidden_size * (NUMBER_SPACE + self.hidden_size) + 2 * self.hidden_size)
            return int(gru + self.hidden_size * NUMBER_SPACE + NUMBER_SPACE)
        return int(self.lookback * NUMBER_SPACE + 1)

    def _windows(self, hits: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Cắt lịch sử thành các cặp (cửa sổ quá khứ, kết quả ngày kế tiếp)."""
        n = hits.shape[0]
        if n <= self.lookback:
            raise ValueError(f"cần hơn {self.lookback} ngày, chỉ có {n}")
        starts = np.arange(0, n - self.lookback)
        sequences = np.stack([hits[s : s + self.lookback] for s in starts]).astype(np.float32)
        targets = hits[self.lookback :].astype(np.float32)
        return sequences, targets

    def fit_sequence(self, hits: np.ndarray) -> None:
        """Khớp trên ma trận nhị phân theo ngày.

        Args:
            hits: Ma trận ``(n_days, 100)`` giá trị 0/1.

        Raises:
            ValueError: Khi lịch sử ngắn hơn cửa sổ nhìn lại.
        """
        sequences, targets = self._windows(hits)
        if self.backend == "torch":
            self._fit_torch(sequences, targets)
        else:
            self._fit_linear(sequences, targets)

    def _fit_torch(self, sequences: np.ndarray, targets: np.ndarray) -> None:
        """Huấn luyện GRU một lớp bằng PyTorch trên CPU."""
        torch = CAPABILITIES.torch
        assert torch is not None
        torch.manual_seed(self.seed)

        class _Net(torch.nn.Module):
            def __init__(self, hidden: int) -> None:
                super().__init__()
                self.gru = torch.nn.GRU(NUMBER_SPACE, hidden, batch_first=True)
                self.head = torch.nn.Linear(hidden, NUMBER_SPACE)

            def forward(self, batch):  # type: ignore[no-untyped-def]
                output, _ = self.gru(batch)
                return self.head(output[:, -1, :])

        model = _Net(self.hidden_size)
        optimiser = torch.optim.Adam(model.parameters(), lr=self.learning_rate)
        # KHÔNG dùng pos_weight ở đây, dù nhãn dương chỉ chiếm ~24%.
        #
        # Cân lại lớp là phản xạ đúng khi thước đo là độ chính xác hoặc F1, vì
        # khi đó mô hình có thể ăn điểm bằng cách luôn nói "không về". Nhưng
        # thước đo của hệ thống này là log-loss — một quy tắc chấm điểm *chặt*,
        # đạt cực trị khi và chỉ khi mô hình khai báo đúng xác suất thật. Dưới
        # quy tắc chặt, "luôn nói không về" không ăn được điểm nào.
        #
        # Ngược lại, pos_weight làm hỏng đúng thứ quy tắc chặt bảo vệ: bản đầu
        # tiên của lớp này khai báo xác suất trung bình 0.4892 trong khi tỉ lệ
        # về thật là 0.2377 — sai gấp đôi, và log-loss phạt rất nặng. Cân lại
        # lớp tối ưu cho một phân phối không tồn tại.
        loss_function = torch.nn.BCEWithLogitsLoss()

        x = torch.from_numpy(sequences)
        y = torch.from_numpy(targets)
        model.train()
        for _ in range(self.epochs):
            optimiser.zero_grad()
            loss = loss_function(model(x), y)
            loss.backward()
            optimiser.step()
        model.eval()
        self._model = model

    def _fit_linear(self, sequences: np.ndarray, targets: np.ndarray) -> None:
        """Đường lui: hồi quy ridge đa nhãn trên cửa sổ trễ đã làm phẳng."""
        flat = sequences.reshape(sequences.shape[0], -1)
        design = np.hstack([flat, np.ones((flat.shape[0], 1), dtype=np.float32)])
        ridge = 10.0 * np.eye(design.shape[1], dtype=np.float64)
        gram = design.T @ design + ridge
        self._linear_weights = np.linalg.solve(gram, design.T @ targets.astype(np.float64))

    def predict_sequence(self, hits: np.ndarray) -> np.ndarray:
        """Xác suất cho ngày ngay sau ``hits``.

        Args:
            hits: Ma trận ``(n_days, 100)``; chỉ ``lookback`` hàng cuối được dùng.

        Returns:
            Mảng ``(100,)`` xác suất.

        Raises:
            RuntimeError: Khi gọi trước lúc khớp.
        """
        window = hits[-self.lookback :].astype(np.float32)
        if window.shape[0] < self.lookback:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        if self.backend == "torch" and self._model is not None:
            torch = CAPABILITIES.torch
            assert torch is not None
            with torch.no_grad():
                logits = self._model(torch.from_numpy(window[None, ...]))
                return _clip(torch.sigmoid(logits).numpy().ravel())
        if self._linear_weights is not None:
            design = np.concatenate([window.ravel().astype(np.float64), [1.0]])
            return _clip(design @ self._linear_weights)
        raise RuntimeError(f"{self.name}: phải gọi fit_sequence() trước predict_sequence()")
