"""Kiểm định cuốn chiếu và dò siêu tham số, không rò rỉ thời gian.

Vì sao không dùng ``train_test_split`` hay ``KFold``
-----------------------------------------------------

Chia ngẫu nhiên trên chuỗi thời gian cho mô hình thấy ngày mai để dự đoán hôm
nay. ``KFold`` cũng vậy. Sai lầm này không hiện ra thành lỗi — nó hiện ra thành
kết quả *đẹp*, nên rất khó phát hiện nếu không chặn từ thiết kế.

Ba tầng thời gian
------------------

Rò rỉ tinh vi nhất không nằm ở vòng huấn luyện mà ở **việc dò siêu tham số**:
chọn tham số bằng cách nhìn điểm trên tập đánh giá rồi báo cáo chính điểm đó là
một dạng rò rỉ, dù mỗi lần khớp riêng lẻ đều sạch. Vì vậy lịch sử chia làm ba
đoạn không chồng lấn, theo đúng thứ tự thời gian::

    [0 ────────── warmup) [warmup ────────── tune_end) [tune_end ────────── n)
       khởi động             dò siêu tham số              đánh giá cuối

Optuna chỉ nhìn thấy đoạn giữa. Đoạn cuối chỉ được chạm đúng một lần, sau khi
tham số đã chốt.

Cửa sổ trượt
-------------

Mỗi lần khớp chỉ dùng ``window`` ngày gần nhất chứ không dùng toàn bộ quá khứ.
Lý do thuộc về miền: nếu quy luật đổi thì dữ liệu cũ không chỉ vô ích mà còn có
hại. Đây là cùng một lập luận đứng sau hệ số chiết khấu của bandit, và cũng
mang cùng cái giá — cửa sổ ngắn thì thích ứng nhanh nhưng phương sai ước lượng
cao hơn.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from ml_engine.capabilities import CAPABILITIES
from ml_engine.features import build_features, build_training_table
from ml_engine.metrics import PerformanceReport, PerformanceTracker
from ml_engine.models import Learner, TabularBooster
from ml_engine.schema import BASELINE_RATE, NUMBER_SPACE

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

#: Không gian siêu tham số mặc định, cố ý hẹp.
#:
#: Hẹp là có chủ đích: không gian rộng trên dữ liệu gần như ngẫu nhiên chỉ làm
#: tăng số giả thuyết được thử, và giá trị tốt nhất tìm được sẽ phản ánh may rủi
#: của quá trình tìm kiếm chứ không phải cấu trúc trong dữ liệu.
DEFAULT_SEARCH_SPACE: Final[dict[str, tuple[Any, ...]]] = {
    "max_depth": ("int", 2, 5),
    "n_estimators": ("int", 80, 320),
    "learning_rate": ("float", 0.01, 0.12),
    "l2_regularization": ("float", 0.1, 10.0),
}


@dataclass(frozen=True)
class Split:
    """Một lát cắt cuốn chiếu.

    Attributes:
        train_start: Ngày đầu của cửa sổ huấn luyện, đã bao gồm.
        train_stop: Ngày cuối của cửa sổ huấn luyện, không bao gồm.
        predict_day: Ngày được dự đoán; luôn bằng ``train_stop``.
    """

    train_start: int
    train_stop: int
    predict_day: int

    def __post_init__(self) -> None:
        if self.train_start >= self.train_stop:
            raise ValueError("cửa sổ huấn luyện rỗng")
        if self.predict_day != self.train_stop:
            raise ValueError("ngày dự đoán phải ngay sau cửa sổ huấn luyện")


class WalkForwardValidator:
    """Đánh giá cuốn chiếu với cửa sổ trượt và dò siêu tham số tách biệt.

    Attributes:
        counts: Ma trận đếm toàn lịch sử.
        window: Số ngày trong cửa sổ huấn luyện trượt.
        warmup: Số ngày đầu chỉ dùng để tích lũy, không đánh giá.
        refit_every: Khớp lại sau mỗi bấy nhiêu ngày.
    """

    def __init__(
        self,
        counts: np.ndarray,
        *,
        window: int = 240,
        warmup: int = 120,
        refit_every: int = 14,
    ) -> None:
        if counts.ndim != 2 or counts.shape[1] != NUMBER_SPACE:
            raise ValueError(f"counts phải có dạng (n, {NUMBER_SPACE})")
        if warmup < 60:
            raise ValueError("warmup phải ít nhất 60 ngày để đặc trưng có nghĩa")
        if window < 30:
            raise ValueError("window phải ít nhất 30 ngày")
        if refit_every < 1:
            raise ValueError("refit_every phải dương")
        if counts.shape[0] <= warmup:
            raise ValueError(f"cần hơn {warmup} ngày, chỉ có {counts.shape[0]}")

        self.counts = counts
        self.window = int(window)
        self.warmup = int(warmup)
        self.refit_every = int(refit_every)

    def splits(self, start: int, stop: int) -> Iterator[Split]:
        """Sinh các lát cắt cuốn chiếu trong khoảng ``[start, stop)``.

        Args:
            start: Ngày đầu tiên được dự đoán.
            stop: Ngày cuối, không bao gồm.

        Yields:
            Lát cắt cho từng ngày.
        """
        for day in range(start, stop):
            yield Split(
                train_start=max(self.warmup - self.window, max(0, day - self.window)),
                train_stop=day,
                predict_day=day,
            )

    def evaluate(
        self,
        model_factory: Callable[[], Learner],
        *,
        start: int,
        stop: int,
        feature_filter: list[str] | None = None,
    ) -> PerformanceReport:
        """Chấm một họ mô hình bằng cuốn chiếu trên ``[start, stop)``.

        Args:
            model_factory: Hàm không đối số trả về bộ học chưa khớp. Nhận
                factory chứ không nhận thể hiện: mỗi lần khớp lại phải là một mô
                hình mới, nếu không trạng thái của lần trước sẽ rò sang lần sau.
            start: Ngày đầu tiên được dự đoán.
            stop: Ngày cuối, không bao gồm.
            feature_filter: Nếu đặt, chỉ dùng các cột đặc trưng này.

        Returns:
            Báo cáo hiệu năng trên khoảng đã cho.

        Raises:
            ValueError: Khi khoảng ngày không hợp lệ.
        """
        if not self.warmup <= start < stop <= self.counts.shape[0]:
            raise ValueError(
                f"khoảng [{start}, {stop}) phải nằm sau warmup={self.warmup} "
                f"và trong {self.counts.shape[0]} ngày"
            )

        tracker = PerformanceTracker()
        model: Learner | None = None
        fitted_at = -1

        for split in self.splits(start, stop):
            if model is None or split.predict_day - fitted_at >= self.refit_every:
                x, y, names = build_training_table(
                    self.counts, start=split.train_start, stop=split.train_stop
                )
                if feature_filter:
                    keep = [names.index(name) for name in feature_filter if name in names]
                    x = x[:, keep]
                if len(np.unique(y)) < 2:
                    model = None
                else:
                    model = model_factory()
                    model.fit(x, y)
                    fitted_at = split.predict_day

            if model is None:
                probabilities = np.full(NUMBER_SPACE, BASELINE_RATE)
            else:
                matrix = build_features(self.counts, split.predict_day)
                features = matrix.values
                if feature_filter:
                    keep = [matrix.names.index(n) for n in feature_filter if n in matrix.names]
                    features = features[:, keep]
                probabilities = model.predict_proba(features)

            tracker.add(probabilities, (self.counts[split.predict_day] > 0).astype(float))

        return tracker.report()

    def tune(
        self,
        *,
        tune_start: int,
        tune_stop: int,
        n_trials: int = 30,
        search_space: dict[str, tuple[Any, ...]] | None = None,
        seed: int = 0,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Dò siêu tham số trên đoạn giữa, không chạm đoạn đánh giá.

        Args:
            tune_start: Ngày đầu của đoạn dò.
            tune_stop: Ngày cuối của đoạn dò, không bao gồm. Đoạn đánh giá cuối
                phải bắt đầu từ đây trở đi.
            n_trials: Số lần thử.
            search_space: Không gian tham số; mặc định là ``DEFAULT_SEARCH_SPACE``.
            seed: Hạt giống, để tái lập được.
            timeout: Giới hạn giây cho toàn bộ quá trình dò.

        Returns:
            Bộ tham số tốt nhất tìm được.
        """
        space = search_space or DEFAULT_SEARCH_SPACE
        if CAPABILITIES.optuna is None:
            LOGGER.warning("Thiếu optuna — chuyển sang dò ngẫu nhiên có kiểm soát hạt giống")
            return self._random_search(
                tune_start=tune_start,
                tune_stop=tune_stop,
                n_trials=n_trials,
                search_space=space,
                seed=seed,
            )

        optuna = CAPABILITIES.optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial: Any) -> float:
            params = self._suggest(trial, space)
            report = self.evaluate(
                lambda: TabularBooster(**params), start=tune_start, stop=tune_stop
            )
            # Tối thiểu hóa log-loss. Không tối ưu Hit-Rate: nó không phải quy
            # tắc chấm điểm chặt, nên chọn tham số theo nó sẽ chọn ra mô hình
            # xếp hạng hơi tốt hơn mà xác suất tệ hơn hẳn.
            return report.logloss

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=seed),
            # Cắt tỉa theo trung vị: bỏ sớm những lần thử đang tệ hơn trung vị,
            # nên phần lớn ngân sách dồn cho vùng tham số đáng quan tâm.
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=0),
        )
        study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=False)

        LOGGER.info(
            "Optuna: %d lần thử, log-loss tốt nhất %.6f (nền %.6f)",
            len(study.trials),
            study.best_value,
            -np.log(BASELINE_RATE) * BASELINE_RATE - np.log1p(-BASELINE_RATE) * (1 - BASELINE_RATE),
        )
        return dict(study.best_params)

    @staticmethod
    def _suggest(trial: Any, space: dict[str, tuple[Any, ...]]) -> dict[str, Any]:
        """Dịch mô tả không gian tham số sang lời gọi Optuna."""
        params: dict[str, Any] = {}
        for name, spec in space.items():
            kind, low, high = spec[0], spec[1], spec[2]
            if kind == "int":
                params[name] = trial.suggest_int(name, int(low), int(high))
            elif kind == "float":
                params[name] = trial.suggest_float(name, float(low), float(high), log=False)
            else:
                raise ValueError(f"kiểu tham số không hỗ trợ: {kind}")
        return params

    def _random_search(
        self,
        *,
        tune_start: int,
        tune_stop: int,
        n_trials: int,
        search_space: dict[str, tuple[Any, ...]],
        seed: int,
    ) -> dict[str, Any]:
        """Đường lui khi không có Optuna: dò ngẫu nhiên với hạt giống cố định."""
        rng = np.random.default_rng(seed)
        best_params: dict[str, Any] = {}
        best_loss = float("inf")
        for _ in range(n_trials):
            params: dict[str, Any] = {}
            for name, spec in search_space.items():
                kind, low, high = spec[0], spec[1], spec[2]
                params[name] = (
                    int(rng.integers(int(low), int(high) + 1))
                    if kind == "int"
                    else float(rng.uniform(float(low), float(high)))
                )
            report = self.evaluate(
                lambda: TabularBooster(**params), start=tune_start, stop=tune_stop
            )
            if report.logloss < best_loss:
                best_loss, best_params = report.logloss, params
        return best_params
