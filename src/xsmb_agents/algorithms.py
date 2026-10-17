"""Ba tác tử dùng cùng đặc trưng nhân quả, co Bayes và thẩm định thời gian."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from calendar_alignment import consecutive_next_pairs
from ensemble_utils import finalize_blend
from online_learning import _posterior, _prob, proper_losses
from xsmb_domain import baseline_rate

from .knowledge import KnowledgeBaseManager

LAYERS = ("statistical", "probabilistic", "pattern")
LABELS = {"statistical": "Tần suất · n-gram · nhịp",
          "probabilistic": "Bayes · Markov · đồ thị trễ",
          "pattern": "Mạng chuỗi hai tầng · ngữ cảnh",
          "constant": "Mức nền", "incumbent": "Xác suất đang công bố"}
TRAIN_WINDOW = 240
MIN_PATTERN_DRAWS = 90


@dataclass(frozen=True)
class EnsembleResult:
    """Các xác suất và chứng cứ tính toán tại thời điểm dự báo."""
    probabilities: dict[str, np.ndarray]
    diagnostics: dict


def feasible(mode: str, values: np.ndarray) -> np.ndarray:
    """Một phép chốt chuẩn của kho, giữ biên LOTO và số 0 đầu."""
    return _prob(mode, finalize_blend(np.asarray(values, dtype=float), mode))


class AlgorithmEnsemble:
    """Thống kê cấp tiên nghiệm cho xác suất và đặc trưng cho mạng mẫu hình."""

    def __init__(self, knowledge: KnowledgeBaseManager) -> None:
        self.knowledge = knowledge

    def temporal_features(self, mode: str) -> tuple[np.ndarray, np.ndarray]:
        """X[t] chỉ dùng Y[:t]; trả các kỳ học gần nhất và kỳ dự báo ở cuối.

        N-gram độ dài hai và Markov chỉ tính trên ngày lịch liên tiếp. Độ
        gan đo bằng kỳ quay, không giả rằng nghỉ lễ là một lần trượt.
        """
        y = self.knowledge.outcomes[mode]
        n = len(y)
        csum = np.vstack([np.zeros((1, 100)), y.cumsum(axis=0)])
        first = max(2, n - TRAIN_WINDOW)
        indices = np.arange(first, n + 1)
        rates = []
        for window in (10, 30, 180):
            start = np.maximum(indices - window, 0)
            span = indices - start
            rates.append((csum[indices] - csum[start] + 100 * baseline_rate(mode)) /
                         (span[:, None] + 100))
        heat = np.zeros((n + 1, 100))
        last = np.full(100, -np.inf)
        for t in range(n + 1):
            heat[t] = np.exp(-(t - last) / 30)
            if t < n:
                last[y[t] > 0] = t
        analog = np.array([self.knowledge.analog_probability(mode, int(t)) for t in indices])
        blocks = [*rates, y[indices - 1], y[indices - 2], heat[indices], analog]
        # Đồng nhất đặc trưng số qua các kỳ, không học một tham số tự do/con.
        numbers = np.arange(100)
        blocks += [np.broadcast_to(numbers // 10 / 9, rates[0].shape),
                   np.broadcast_to(numbers % 10 / 9, rates[0].shape)]
        return np.stack(blocks, axis=2), indices

    def statistical(self, mode: str) -> tuple[np.ndarray, dict]:
        """Bayes ba cửa sổ, n-gram trạng thái và hazard đã co về tiên nghiệm."""
        y = self.knowledge.outcomes[mode]
        base = np.full(100, baseline_rate(mode))
        priors = [_posterior(mode, y[-w:].sum(axis=0), min(w, len(y)), base)
                  for w in (10, 30, 180)]
        prior = np.mean(priors, axis=0)
        dates = np.array(self.knowledge.frame["date"], dtype="datetime64[D]")
        contiguous = np.diff(dates).astype(int) == 1
        ngram = prior.copy()
        if len(y) >= 3 and contiguous[-1]:
            same = ((y[:-2] == y[-2]) & (y[1:-1] == y[-1]) &
                    (contiguous[:-1] & contiguous[1:])[:, None])
            ngram = _posterior(mode, (y[2:] * same).sum(axis=0), same.sum(axis=0), prior)
        # Hazard theo nhóm độ gan tại thời điểm TRƯỚC từng nhãn; không tăng
        # xác suất đơn giản chỉ vì một con đã lâu chưa xuất hiện.
        gaps = np.zeros_like(y)
        last = np.full(100, -1)
        for t in range(len(y)):
            gaps[t] = t - last - 1
            last[y[t] > 0] = t
        edges = [0, 1, 2, 4, 8, 16, 32]
        buckets = np.digitize(gaps, edges)
        current = np.digitize(len(y) - last - 1, edges)
        matches = buckets == current
        hazard = _posterior(mode, (matches * y).sum(axis=0), matches.sum(axis=0), prior)
        p = feasible(mode, .60 * prior + .20 * ngram + .20 * hazard)
        return p, {"windows": [10, 30, 180], "ngram_order": 2,
                   "cycle": "Hazard có co Bayes theo nhóm độ gan", "history_draws": len(y)}

    def probabilistic(self, mode: str, prior: np.ndarray) -> tuple[np.ndarray, dict]:
        """Đồ thị trễ có hướng và Markov, chỉ trên cặp ngày liên tiếp."""
        y = self.knowledge.outcomes[mode]
        before, after = consecutive_next_pairs(self.knowledge.frame["date"])
        if not len(before):
            return prior.copy(), {"transitions": 0, "edges": []}
        x, target = y[before], y[after]
        support = x.sum(axis=0)
        co = x.T @ target
        conditional = (co + 100 * prior) / (support[:, None] + 100)
        active = np.flatnonzero(y[-1])
        graph = conditional[active].mean(axis=0) if len(active) else prior
        same = x == y[-1]
        markov = _posterior(mode, (same * target).sum(axis=0), same.sum(axis=0), prior)
        p = feasible(mode, .5 * markov + .5 * graph)
        gains = conditional[active] - prior
        edges = []
        if gains.size:
            for flat in np.argsort(-gains, axis=None, kind="stable")[:5]:
                a, b = divmod(int(flat), 100)
                edges.append({"from": f"{active[a]:02d}", "to": f"{b:02d}",
                              "support": int(support[active[a]]),
                              "probability": float(conditional[active[a], b]),
                              "descriptive_only": True})
        return p, {"transitions": len(before), "edges": edges,
                   "prior": "Tác tử thống kê", "shrinkage": 100}

    def pattern(self, mode: str) -> tuple[np.ndarray, dict]:
        """Mạng hai tầng ẩn; L2 chọn bằng hậu tố thời gian của tập học."""
        base = np.full(100, baseline_rate(mode))
        n = len(self.knowledge.frame)
        if n < MIN_PATTERN_DRAWS:
            return base, {"status": "insufficient_history", "draws": n,
                          "minimum": MIN_PATTERN_DRAWS}
        features, indices = self.temporal_features(mode)
        train_x = features[:-1]
        train_y = self.knowledge.outcomes[mode][indices[:-1]]
        split = len(train_x) - 30
        if split < 30 or np.unique(train_y[:split]).size < 2:
            return base, {"status": "insufficient_classes"}
        trials = []

        def fit(alpha: float, x: np.ndarray, y: np.ndarray):
            scaler = StandardScaler().fit(x.reshape(-1, x.shape[-1]))
            model = MLPClassifier(hidden_layer_sizes=(24, 12), alpha=alpha,
                                  max_iter=35, batch_size=512, shuffle=False,
                                  early_stopping=False, random_state=17)
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", ConvergenceWarning)
                model.fit(scaler.transform(x.reshape(-1, x.shape[-1])), y.reshape(-1))
            converged = not any(isinstance(w.message, ConvergenceWarning) for w in captured)
            return scaler, model, converged

        def predict(scaler, model, x: np.ndarray) -> np.ndarray:
            raw = model.predict_proba(scaler.transform(x.reshape(-1, x.shape[-1])))[:, 1]
            return np.array([feasible(mode, row) for row in raw.reshape(-1, 100)])

        for alpha in (1.0, 10.0):
            scaler, model, _ = fit(alpha, train_x[:split], train_y[:split])
            p = predict(scaler, model, train_x[split:])
            loss = np.mean([proper_losses(mode, q, y)["logloss"]
                            for q, y in zip(p, train_y[split:], strict=True)])
            trials.append((float(loss), alpha))
        loss, alpha = min(trials)
        scaler, model, converged = fit(alpha, train_x, train_y)
        raw = predict(scaler, model, features[-1:])[0]
        # Co bảo thủ; cổng tiến cứu vẫn chấm chính vector này, không vector thô.
        p = feasible(mode, .8 * base + .2 * raw)
        return p, {"status": "fitted", "hidden_layers": [24, 12], "alpha": alpha,
                   "validation_draws": 30, "validation_logloss": loss,
                   "training_draws": len(train_x), "training_until": str(self.knowledge.frame.iloc[-1]["date"]),
                   "converged": converged, "retrieval_feature": True,
                   "validation_is_prospective": False}

    def predict(self, mode: str, incumbent: np.ndarray) -> EnsembleResult:
        """Chạy ba tầng; tầng xác suất dùng tiên nghiệm từ tầng thống kê."""
        _prob(mode, incumbent)
        stat, stat_info = self.statistical(mode)
        graph, graph_info = self.probabilistic(mode, stat)
        pattern, pattern_info = self.pattern(mode)
        return EnsembleResult(dict(zip(LAYERS, (stat, graph, pattern), strict=True)),
                              dict(zip(LAYERS, (stat_info, graph_info, pattern_info), strict=True)))
