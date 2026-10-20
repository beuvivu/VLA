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
from ml_train import model_trust
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
#: Định nghĩa đang chạy của tác tử mẫu hình. Sổ tiến cứu ``agents_<mode>.json`` ghi số này
#: trên từng bản ghi mới (``agent_policy``); bản ghi cũ không có trường là định nghĩa 1 và
#: KHÔNG bị viết lại — chúng là dự báo đã đóng băng.
#:
#: 1 (17-10-2026): trộn cố định ``0,8·nền + 0,2·mạng`` bất kể khối thẩm định nói gì.
#: 2 (20-10-2026): ``trust = ml_train.model_trust(kỹ năng thẩm định)``, cùng luật mọi thành
#:    phần ML của kho — không có kỹ năng thì không tin. Ba kỳ đầu của sổ, mạng Đặc Biệt có
#:    logloss thẩm định 4,6146 / 4,6121 / 4,6112, đều kém mức nền log 100 = 4,6052, mà vẫn
#:    được trộn 20%.
AGENT_POLICY = 2


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
        """Mạng hai tầng ẩn; L2 chọn bằng hậu tố thời gian của tập học.

        Vector phát ra là ``trust·mạng + (1 − trust)·nền`` với
        ``trust = ml_train.model_trust(s_logloss, s_brier)``, s là kỹ năng của mạng so với
        nền trên 30 kỳ thẩm định cuối của tập học (định nghĩa ``AGENT_POLICY`` = 2).
        """
        base = np.full(100, baseline_rate(mode))
        n = len(self.knowledge.frame)
        if n < MIN_PATTERN_DRAWS:
            return base, {"status": "insufficient_history", "draws": n,
                          "minimum": MIN_PATTERN_DRAWS, "trust": 0.0, "policy": AGENT_POLICY}
        features, indices = self.temporal_features(mode)
        train_x = features[:-1]
        train_y = self.knowledge.outcomes[mode][indices[:-1]]
        split = len(train_x) - 30
        if split < 30 or np.unique(train_y[:split]).size < 2:
            return base, {"status": "insufficient_classes", "trust": 0.0, "policy": AGENT_POLICY}
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

        def scored(p: np.ndarray) -> dict[str, float]:
            losses = [proper_losses(mode, q, y) for q, y in zip(p, train_y[split:], strict=True)]
            return {name: float(np.mean([row[name] for row in losses])) for name in ("logloss", "brier")}

        for alpha in (1.0, 10.0):
            scaler, model, _ = fit(alpha, train_x[:split], train_y[:split])
            trials.append((scored(predict(scaler, model, train_x[split:])), alpha))
        measured, alpha = min(trials, key=lambda row: (row[0]["logloss"], row[1]))
        # Kỹ năng thẩm định so với NỀN trên đúng 30 kỳ ấy, rồi luật tin chung của kho: kém
        # hơn trong logloss/Brier, trust = clip(20·s, 0, 1). Khối này cũng đã chọn α (hai
        # ứng viên) nên s hơi lạc quan — lệch về phía TIN, không bao giờ về phía bịa tín hiệu.
        reference = scored(np.tile(base, (len(train_y) - split, 1)))
        skill = {name: (reference[name] - measured[name]) / reference[name] for name in measured}
        trust = model_trust(skill["logloss"], skill["brier"])
        scaler, model, converged = fit(alpha, train_x, train_y)
        raw = predict(scaler, model, features[-1:])[0]
        # Không có kỹ năng thì không tin: trust = 0 phát đúng mức nền. Cổng tiến cứu chấm
        # chính vector này, không vector thô.
        p = feasible(mode, trust * raw + (1.0 - trust) * base)
        return p, {"status": "fitted", "hidden_layers": [24, 12], "alpha": alpha,
                   "validation_draws": 30, "validation_logloss": measured["logloss"],
                   "validation_brier": measured["brier"],
                   "baseline_validation_logloss": reference["logloss"],
                   "baseline_validation_brier": reference["brier"],
                   "validation_skill": skill, "trust": trust, "policy": AGENT_POLICY,
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
