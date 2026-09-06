"""Đấu trường chung cho các họ mô hình dự đoán lô tô.

Vì sao cần một đấu trường thay vì so từng bài báo cáo rời
----------------------------------------------------------

So sánh mô hình chỉ có nghĩa khi mọi mô hình nhìn thấy đúng một tập thông tin
và bị chấm bằng đúng một thước đo. Ở miền này sai lệch dễ len vào nhất qua ba
đường, nên giao thức bên dưới chặn cả ba:

1. **Rò rỉ thời gian.** Mô hình dự đoán ngày ``t`` chỉ được khớp trên
   ``counts[:t]``. Không có ngoại lệ, kể cả cho việc chuẩn hóa hay chọn siêu
   tham số — vì vậy mọi thứ đó cũng nằm trong ``fit``.
2. **Chấm điểm không đúng quy tắc.** Dùng log-loss và Brier, hai quy tắc chấm
   điểm chặt (proper scoring rules): chúng đạt cực trị khi và chỉ khi mô hình
   khai báo đúng xác suất thật. Độ chính xác thô thì không — ở nền 23.8%, một
   mô hình luôn nói "không về" đạt 76.2% "chính xác" mà không biết gì cả.
3. **So với nền sai.** Nền ở đây là xác suất biên đúng của miền, và điểm kỹ
   năng (skill) là mức cải thiện *tương đối* so với nền đó.

Mỗi mô hình khai báo xác suất cho cả 100 con mỗi ngày, nên một ngày đóng góp
100 quan sát Bernoulli. Kiểm định ghép cặp chạy trên mức ngày chứ không mức
quan sát: 100 con trong cùng một kỳ không độc lập với nhau (tổng số con về bị
ràng buộc), nên coi chúng là 100 mẫu độc lập sẽ thổi phồng bậc tự do lên 100
lần và biến nhiễu thành "có ý nghĩa thống kê".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy import stats
from scipy.special import logsumexp
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

from bridges.tensor import NUMBER_SPACE
from xsmb_domain import LOTO_BASELINE_RATE, LOTO_DRAWS_PER_DAY

#: Xác suất một con bất kỳ về ít nhất một lần trong 27 giải, nếu công bằng.
#: Lấy từ ``xsmb_domain`` chứ không tính lại — nền là định nghĩa của miền, và
#: hai bản sao rồi sẽ lệch nhau.
BASELINE_RATE: float = LOTO_BASELINE_RATE

#: Kẹp xác suất để log-loss không phân kỳ khi một mô hình khai báo chắc chắn.
_EPSILON: float = 1e-6


def _clip(probabilities: np.ndarray) -> np.ndarray:
    return np.clip(probabilities, _EPSILON, 1.0 - _EPSILON)


# --------------------------------------------------------------------------
# Giao thức
# --------------------------------------------------------------------------


class SequenceModel(Protocol):
    """Mô hình nhìn lịch sử đếm và khai báo xác suất cho ngày kế tiếp."""

    name: str
    family: str

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        """Trả mảng ``(100,)`` xác suất mỗi con về ít nhất một lần ngày kế tiếp."""
        ...


# --------------------------------------------------------------------------
# 1. Nền — mọi thứ khác phải vượt được cái này
# --------------------------------------------------------------------------


class UniformBaseline:
    """Xác suất biên của miền, không học gì cả.

    Cơ sở: nếu 27 giải là 27 lần rút độc lập đều trên 00–99 thì
    ``P(con n về) = 1 - (1 - 1/100)^27``. Đây không phải "mô hình ngây thơ" mà
    là *giả thuyết rỗng đúng của miền*. Một mô hình không vượt được nó thì
    không mang thông tin nào ngoài thứ đã biết trước khi nhìn dữ liệu.
    """

    name = "Nền đồng đều"
    family = "baseline"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        return np.full(NUMBER_SPACE, BASELINE_RATE)


# --------------------------------------------------------------------------
# 2. Tần suất và co rút Bayes
# --------------------------------------------------------------------------


class EmpiricalFrequency:
    """Ước lượng hợp lý cực đại cho từng con: tần suất về trong lịch sử.

    Đây là hình thức hóa của phương pháp "số nóng / số lạnh". Đưa vào để cho
    thấy điều xảy ra khi ước lượng 100 tham số từ 391 quan sát mỗi tham số mà
    không co rút: phương sai ước lượng lấn át hoàn toàn phần tín hiệu.
    """

    name = "Tần suất kinh nghiệm"
    family = "frequentist"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        return _clip((history > 0).mean(axis=0))


class BetaBinomialShrinkage:
    """Hậu nghiệm Beta–Nhị thức với tiên nghiệm ước lượng từ chính dữ liệu.

    Cơ sở toán học: đặt tiên nghiệm ``p_n ~ Beta(a, b)`` cho tỉ lệ về của con
    ``n``. Với ``k_n`` lần về trong ``m`` kỳ, hậu nghiệm là
    ``Beta(a + k_n, b + m - k_n)`` và trung bình hậu nghiệm

        p̂_n = (a + k_n) / (a + b + m)

    tức trung bình có trọng số giữa tần suất riêng và trung bình chung, với
    trọng số quyết định bởi ``a + b`` — độ mạnh của tiên nghiệm.

    Vì sao có thể cải thiện: ước lượng riêng từng con có phương sai
    ``p(1-p)/m``; co rút về trung bình chung đánh đổi một chút chệch lấy mức
    giảm phương sai lớn hơn nhiều. Đây chính là hiệu ứng Stein. Nếu các con
    thật sự đồng nhất, ``a + b`` ước lượng được sẽ rất lớn và mô hình tự động
    thoái hóa về nền — nó *không thể* tệ hơn nền nhiều, đó là ưu điểm chính.

    ``a`` và ``b`` lấy bằng phương pháp mô-men trên chính lịch sử đã thấy, nên
    không có siêu tham số nào phải chỉnh tay.
    """

    name = "Co rút Beta–Nhị thức"
    family = "bayesian"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = (history > 0).astype(float)
        m = hits.shape[0]
        if m < 2:
            return np.full(NUMBER_SPACE, BASELINE_RATE)
        rates = hits.mean(axis=0)
        grand = float(rates.mean())
        observed_var = float(rates.var(ddof=1))
        # Phương sai kỳ vọng nếu mọi con đồng nhất — phần "nhiễu lấy mẫu".
        sampling_var = grand * (1.0 - grand) / m
        signal_var = observed_var - sampling_var
        if signal_var <= 0:
            # Không có bằng chứng khác biệt giữa các con: co rút hoàn toàn.
            return np.full(NUMBER_SPACE, grand)
        strength = max(grand * (1.0 - grand) / signal_var - 1.0, 0.0)
        a, b = grand * strength, (1.0 - grand) * strength
        return _clip((a + hits.sum(axis=0)) / (a + b + m))


# --------------------------------------------------------------------------
# 3. Xích Markov — hình thức hóa của "bạc nhớ"
# --------------------------------------------------------------------------


class MarkovChain:
    """Xích Markov bậc nhất trên trạng thái có/không của từng con.

    Cơ sở toán học: mô hình hóa ``P(hit_t | hit_{t-1})`` bằng ma trận chuyển
    2×2. Ước lượng hợp lý cực đại là tỉ lệ đếm chuyển, có cộng giả đếm Laplace
    để hậu nghiệm xác định khi một ô trống.

    Vì sao có thể cải thiện: đây đúng là giả thuyết mà phương pháp "bạc nhớ"
    đưa ra — kết quả hôm qua mang thông tin về hôm nay. Nếu đúng thì hai hàng
    của ma trận chuyển phải khác nhau rõ rệt.

    ``order`` cho phép mở rộng lên bậc cao hơn: bậc ``k`` cần ``2^k`` trạng
    thái, tức số tham số nhân đôi mỗi bậc trong khi số quan sát mỗi trạng thái
    giảm một nửa. Đó là lý do bậc cao gần như luôn thua trên chuỗi ngắn.
    """

    family = "markov"

    def __init__(self, order: int = 1, pooled: bool = True) -> None:
        self.order = int(order)
        self.pooled = bool(pooled)
        scope = "gộp" if pooled else "riêng từng con"
        self.name = f"Xích Markov bậc {self.order} ({scope})"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = (history > 0).astype(np.int64)
        k = self.order
        if hits.shape[0] <= k + 1:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        # Mã hóa k ngày trước thành một chỉ số trạng thái trong [0, 2^k).
        windows = np.stack([hits[i : hits.shape[0] - k + i] for i in range(k)], axis=0)
        weights = (2 ** np.arange(k))[:, None, None]
        states = (windows * weights).sum(axis=0)  # (n-k, 100)
        outcomes = hits[k:]  # (n-k, 100)
        n_states = 2**k

        if self.pooled:
            # Một ma trận chuyển dùng chung cho mọi con: tối đa hóa số quan sát
            # mỗi ô, đổi lại giả định các con đồng nhất.
            successes = np.bincount(states.ravel(), weights=outcomes.ravel(), minlength=n_states)
            totals = np.bincount(states.ravel(), minlength=n_states)
            table = (successes + 1.0) / (totals + 2.0)
            current = (hits[-k:] * (2 ** np.arange(k))[:, None]).sum(axis=0)
            return _clip(table[current])

        # Ma trận riêng cho từng con: linh hoạt hơn nhưng chia nhỏ dữ liệu ra
        # 100 lần, nên cộng giả đếm neo về nền để không bùng phương sai.
        probabilities = np.empty(NUMBER_SPACE)
        prior = 4.0
        for number in range(NUMBER_SPACE):
            state_col, outcome_col = states[:, number], outcomes[:, number]
            current = int((hits[-k:, number] * (2 ** np.arange(k))).sum())
            mask = state_col == current
            total = int(mask.sum())
            successes = float(outcome_col[mask].sum())
            probabilities[number] = (successes + prior * BASELINE_RATE) / (total + prior)
        return _clip(probabilities)


# --------------------------------------------------------------------------
# 4. Mô hình nguy cơ theo khoảng cách — "nhịp gan", "điểm rơi"
# --------------------------------------------------------------------------


class GapHazard:
    """Xác suất về là hàm của số ngày đã gan.

    Cơ sở toán học: hàm nguy cơ ``h(g) = P(về hôm nay | đã gan g ngày)``. Với
    chuỗi độc lập, ``h`` là hằng số — đó là tính không nhớ của phân phối hình
    học. Mọi phương pháp "nuôi khung", "điểm rơi" đều ngầm khẳng định ``h``
    tăng theo ``g``.

    Ước lượng phi tham số bằng bảng sống (life table), gộp mọi con để có đủ
    quan sát mỗi mức gan, cộng co rút về nền theo cỡ mẫu từng ô. Nhóm đuôi lại
    vì số quan sát ở mức gan lớn rất thưa — không gộp thì các mức gan hiếm sẽ
    cho ước lượng 0 hoặc 1 và log-loss nổ.
    """

    name = "Nguy cơ theo độ gan"
    family = "survival"

    def __init__(self, max_gap: int = 12, prior: float = 40.0) -> None:
        self.max_gap = int(max_gap)
        self.prior = float(prior)

    def _current_gaps(self, hits: np.ndarray) -> np.ndarray:
        """Số ngày kể từ lần về gần nhất, tính đến hết lịch sử."""
        n = hits.shape[0]
        last = np.where(hits.any(axis=0), n - 1 - np.argmax(hits[::-1], axis=0), -1)
        return np.minimum(n - 1 - last, self.max_gap)

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = history > 0
        n = hits.shape[0]
        if n < 30:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        successes = np.zeros(self.max_gap + 1)
        totals = np.zeros(self.max_gap + 1)
        gaps = np.zeros(NUMBER_SPACE, dtype=np.int64)
        for day in range(n):
            bucket = np.minimum(gaps, self.max_gap)
            np.add.at(totals, bucket, 1)
            np.add.at(successes, bucket, hits[day].astype(float))
            gaps = np.where(hits[day], 0, gaps + 1)

        hazard = (successes + self.prior * BASELINE_RATE) / (totals + self.prior)
        return _clip(hazard[self._current_gaps(hits)])


# --------------------------------------------------------------------------
# 5. Mô hình Markov ẩn — chế độ "nóng / nguội" của cả kỳ
# --------------------------------------------------------------------------


class HiddenMarkovRegime:
    """HMM hai trạng thái trên số con phân biệt mỗi kỳ.

    Cơ sở toán học: giả định tồn tại chuỗi trạng thái ẩn ``z_t ∈ {0, 1}`` theo
    xích Markov, và quan sát ``y_t`` (số con phân biệt trong kỳ) sinh từ
    ``N(μ_{z_t}, σ²_{z_t})``. Ước lượng bằng Baum–Welch (EM): bước E chạy
    tiến–lùi để lấy ``γ_t(i) = P(z_t = i | y)``, bước M cập nhật tham số theo
    trung bình có trọng số ``γ``.

    Vì sao có thể cải thiện: nếu có "kỳ nở" và "kỳ co" thì số con phân biệt
    trong kỳ sẽ có hai chế độ, và biết đang ở chế độ nào cho phép điều chỉnh
    xác suất chung lên hoặc xuống.

    Cài bằng NumPy thuần, có chuẩn hóa theo thang log để không tràn số dưới —
    tích của 391 xác suất nhỏ hơn 1 sẽ về 0 trong dấu phẩy động nếu nhân trực
    tiếp.
    """

    name = "HMM hai chế độ"
    family = "state-space"

    def __init__(self, iterations: int = 30, seed: int = 0) -> None:
        self.iterations = int(iterations)
        self.seed = int(seed)

    @staticmethod
    def _forward_backward(
        log_emission: np.ndarray, log_transition: np.ndarray, log_start: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        n, k = log_emission.shape
        log_alpha = np.empty((n, k))
        log_alpha[0] = log_start + log_emission[0]
        for t in range(1, n):
            log_alpha[t] = log_emission[t] + logsumexp(
                log_alpha[t - 1][:, None] + log_transition, axis=0
            )
        log_beta = np.zeros((n, k))
        for t in range(n - 2, -1, -1):
            log_beta[t] = logsumexp(log_transition + log_emission[t + 1] + log_beta[t + 1], axis=1)
        log_gamma = log_alpha + log_beta
        log_gamma -= logsumexp(log_gamma, axis=1, keepdims=True)
        return np.exp(log_gamma), log_alpha

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        observations = (history > 0).sum(axis=1).astype(float)
        n = observations.size
        if n < 40 or observations.std() < 1e-9:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        rng = np.random.default_rng(self.seed)
        mu = np.array(
            [observations.mean() - observations.std(), observations.mean() + observations.std()]
        )
        sigma = np.full(2, max(observations.std(), 1e-3))
        transition = np.array([[0.8, 0.2], [0.2, 0.8]])
        start = np.array([0.5, 0.5])

        for _ in range(self.iterations):
            log_emission = np.stack(
                [stats.norm.logpdf(observations, mu[i], sigma[i]) for i in range(2)], axis=1
            )
            gamma, _ = self._forward_backward(log_emission, np.log(transition), np.log(start))
            weights = gamma.sum(axis=0)
            if np.any(weights < 1e-8):
                break
            mu = (gamma * observations[:, None]).sum(axis=0) / weights
            sigma = np.sqrt((gamma * (observations[:, None] - mu) ** 2).sum(axis=0) / weights)
            sigma = np.maximum(sigma, 1e-3)
            # Cập nhật ma trận chuyển từ xác suất cặp xấp xỉ bằng tích gamma —
            # đủ cho hai trạng thái và rẻ hơn nhiều so với xi đầy đủ.
            joint = gamma[:-1, :, None] * gamma[1:, None, :]
            transition = joint.sum(axis=0)
            transition /= np.maximum(transition.sum(axis=1, keepdims=True), 1e-12)
            start = gamma[0] / gamma[0].sum()
            _ = rng  # giữ chữ ký tất định; không cần ngẫu nhiên sau khởi tạo

        log_emission = np.stack(
            [stats.norm.logpdf(observations, mu[i], sigma[i]) for i in range(2)], axis=1
        )
        gamma, _ = self._forward_backward(log_emission, np.log(transition), np.log(start))
        # Chế độ dự báo cho ngày kế tiếp, rồi quy ra kỳ vọng số con phân biệt.
        next_state = gamma[-1] @ transition
        expected_distinct = float(next_state @ mu)
        return np.full(
            NUMBER_SPACE, float(np.clip(expected_distinct / NUMBER_SPACE, _EPSILON, 1 - _EPSILON))
        )


# --------------------------------------------------------------------------
# 6. Phân cụm — nhóm các con có hành vi giống nhau
# --------------------------------------------------------------------------


class ClusterRate:
    """Gộp các con thành cụm theo hồ sơ hành vi, rồi dùng tỉ lệ của cụm.

    Cơ sở: nếu các con không đồng nhất nhưng chia thành vài nhóm, thì ước lượng
    ở mức nhóm có phương sai thấp hơn nhiều so với mức từng con, trong khi vẫn
    giữ được phần khác biệt. Hồ sơ gồm tỉ lệ về, độ gan trung bình và tỉ lệ ra
    hai nháy; phân cụm bằng k-means.

    Đây là dạng co rút có cấu trúc — nằm giữa "mọi con như nhau" và "mỗi con
    một tham số". Nếu bác bỏ được tính đồng nhất thì nó phải thắng cả hai.
    """

    family = "clustering"

    def __init__(self, n_clusters: int = 4, seed: int = 0) -> None:
        self.n_clusters = int(n_clusters)
        self.seed = int(seed)
        self.name = f"Phân cụm k-means (k={self.n_clusters})"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = history > 0
        n = hits.shape[0]
        if n < 60:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        rate = hits.mean(axis=0)
        double_rate = (history >= 2).mean(axis=0)
        gaps = np.array(
            [
                np.diff(np.flatnonzero(hits[:, i])).mean() if hits[:, i].sum() >= 2 else float(n)
                for i in range(NUMBER_SPACE)
            ]
        )
        profile = np.stack([rate, double_rate, gaps / n], axis=1)
        profile = (profile - profile.mean(axis=0)) / np.maximum(profile.std(axis=0), 1e-9)

        labels = KMeans(n_clusters=self.n_clusters, n_init=4, random_state=self.seed).fit_predict(
            profile
        )
        probabilities = np.empty(NUMBER_SPACE)
        for cluster in range(self.n_clusters):
            mask = labels == cluster
            # Co rút tỉ lệ cụm về nền theo số quan sát của cụm.
            observations = mask.sum() * n
            cluster_rate = float(hits[:, mask].mean()) if mask.any() else BASELINE_RATE
            weight = observations / (observations + 2000.0)
            probabilities[mask] = weight * cluster_rate + (1 - weight) * BASELINE_RATE
        return _clip(probabilities)


# --------------------------------------------------------------------------
# 7. Học máy có giám sát trên đặc trưng công phu
# --------------------------------------------------------------------------


def build_features(history: np.ndarray, day: int) -> np.ndarray:
    """Đặc trưng cho từng con tại thời điểm ``day``, chỉ dùng dữ liệu trước đó.

    Trả mảng ``(100, d)``. Mọi cột đều là hàm của ``history[:day]`` — không có
    cột nào chạm tới ``history[day]``, và đó là bất biến duy nhất thực sự quan
    trọng ở đây.
    """
    past = history[:day] > 0
    if past.shape[0] < 30:
        return np.zeros((NUMBER_SPACE, 8))

    windows = (10, 30, 90)
    columns = [past[-w:].mean(axis=0) for w in windows]

    last_seen = np.where(past.any(axis=0), past.shape[0] - 1 - np.argmax(past[::-1], axis=0), -1)
    gap = past.shape[0] - 1 - last_seen
    columns.append(np.minimum(gap, 30) / 30.0)
    columns.append(past[-1].astype(float))
    columns.append(past[-2].astype(float) if past.shape[0] >= 2 else np.zeros(NUMBER_SPACE))
    columns.append((history[:day][-30:] >= 2).mean(axis=0))
    # Tổng chữ số: đặc trưng miền, kiểm tra xem cấu trúc chữ số có mang tin không.
    columns.append(np.array([(n // 10 + n % 10) / 18.0 for n in range(NUMBER_SPACE)]))
    return np.stack(columns, axis=1)


class SupervisedModel:
    """Bao chung cho mọi bộ phân loại scikit-learn trên đặc trưng ở trên.

    Khớp lại mỗi ``refit_every`` ngày chứ không mỗi ngày: khớp lại hằng ngày
    tốn 290 lần khớp mà thay đổi giữa hai ngày liên tiếp là không đáng kể, và
    kết quả đo được không khác biệt.
    """

    family = "supervised"

    def __init__(self, name: str, factory, refit_every: int = 14, window: int = 240) -> None:
        self.name = name
        self._factory = factory
        self.refit_every = int(refit_every)
        self.window = int(window)
        self._model = None
        self._fitted_at = -1

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        n = history.shape[0]
        if n < 90:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        if self._model is None or n - self._fitted_at >= self.refit_every:
            start = max(30, n - self.window)
            rows, targets = [], []
            for day in range(start, n):
                rows.append(build_features(history, day))
                targets.append((history[day] > 0).astype(int))
            x = np.concatenate(rows, axis=0)
            y = np.concatenate(targets, axis=0)
            if len(np.unique(y)) < 2:
                return np.full(NUMBER_SPACE, BASELINE_RATE)
            self._model = self._factory()
            self._model.fit(x, y)
            self._fitted_at = n

        return _clip(self._model.predict_proba(build_features(history, n))[:, 1])


def gradient_boosting(refit_every: int = 14) -> SupervisedModel:
    """Cây tăng cường gradient — đại diện cho họ XGBoost/LightGBM/CatBoost.

    ``HistGradientBoostingClassifier`` dùng cùng thuật toán lược đồ (histogram)
    như LightGBM; trên tập vài chục nghìn hàng, chênh lệch giữa các cài đặt là
    nhiễu so với chênh lệch giữa mô hình và nền.
    """
    return SupervisedModel(
        "Cây tăng cường gradient",
        lambda: HistGradientBoostingClassifier(
            max_depth=3,
            max_iter=120,
            learning_rate=0.05,
            l2_regularization=1.0,
            random_state=0,
        ),
        refit_every=refit_every,
    )


def high_capacity_network(refit_every: int = 30) -> SupervisedModel:
    """Mạng nơ-ron nhiều tham số — đại diện cho họ LSTM/GRU.

    Không có PyTorch trong môi trường này, nhưng điều cần chứng minh không phụ
    thuộc vào kiến trúc hồi tiếp: đó là chuyện gì xảy ra khi số tham số vượt xa
    lượng thông tin trong dữ liệu. Mạng hai lớp 64 nút có khoảng 4 700 tham số
    trên 39 100 quan sát nhị phân; một GRU 64 chiều còn nhiều hơn thế.
    """
    return SupervisedModel(
        "Mạng nơ-ron dung lượng cao",
        lambda: MLPClassifier(
            hidden_layer_sizes=(64, 64), max_iter=300, random_state=0, alpha=1e-4
        ),
        refit_every=refit_every,
    )


# --------------------------------------------------------------------------
# Đánh giá cuốn chiếu
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Evaluation:
    """Điểm của một mô hình trên tập đánh giá."""

    name: str
    family: str
    days: int
    logloss: float
    brier: float
    baseline_logloss: float
    baseline_brier: float
    paired_t: float
    hit_at_27: float
    baseline_hit_at_27: float
    calibration_error: float

    @property
    def logloss_skill(self) -> float:
        return (self.baseline_logloss - self.logloss) / self.baseline_logloss

    @property
    def brier_skill(self) -> float:
        return (self.baseline_brier - self.brier) / self.baseline_brier

    @property
    def beats_baseline(self) -> bool:
        """Vượt nền *và* chênh lệch đủ lớn so với nhiễu ngày qua ngày."""
        return self.logloss_skill > 0 and self.paired_t > 1.96

    def describe(self) -> str:
        verdict = "VƯỢT nền" if self.beats_baseline else "không vượt nền"
        return (
            f"{self.name:<30} kỹ năng={self.logloss_skill:>+9.5f}  "
            f"t={self.paired_t:>+6.2f}  trúng@27={self.hit_at_27:>5.2f}  "
            f"lệch hiệu chuẩn={self.calibration_error:.4f}  {verdict}"
        )


def _calibration_error(probabilities: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    """Sai số hiệu chuẩn kỳ vọng: |xác suất khai báo − tần suất thật| bình quân.

    Một mô hình có thể xếp hạng tốt mà hiệu chuẩn tệ, và ngược lại. Với bài
    toán này hiệu chuẩn quan trọng hơn: người dùng đọc con số như một xác suất.
    """
    edges = np.quantile(probabilities, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    total = 0.0
    for i in range(bins):
        mask = (probabilities > edges[i]) & (probabilities <= edges[i + 1])
        if mask.sum() == 0:
            continue
        total += mask.mean() * abs(probabilities[mask].mean() - outcomes[mask].mean())
    return float(total)


def walk_forward(counts: np.ndarray, model: SequenceModel, *, warmup: int = 120) -> Evaluation:
    """Chấm một mô hình bằng đánh giá cuốn chiếu ngày qua ngày.

    Với mỗi ngày ``t ≥ warmup``, mô hình chỉ thấy ``counts[:t]`` và khai báo
    xác suất cho cả 100 con của ngày ``t``. Không có bước nào nhìn về phía
    trước, kể cả trong việc chọn tham số.
    """
    n = counts.shape[0]
    daily_logloss, daily_baseline, rows = [], [], []
    hit_at_27, baseline_hit = [], []

    for day in range(warmup, n):
        probabilities = np.asarray(model.predict_next(counts[:day]), dtype=float)
        outcome = (counts[day] > 0).astype(float)
        p = _clip(probabilities)

        daily_logloss.append(-float(np.mean(outcome * np.log(p) + (1 - outcome) * np.log1p(-p))))
        b = BASELINE_RATE
        daily_baseline.append(-float(np.mean(outcome * np.log(b) + (1 - outcome) * np.log1p(-b))))
        rows.append((p, outcome))
        # Xếp hạng: chọn 27 con có xác suất cao nhất, đếm số trúng.
        top = np.argsort(-p)[:LOTO_DRAWS_PER_DAY]
        hit_at_27.append(float(outcome[top].sum()))
        baseline_hit.append(float(outcome.sum()) * LOTO_DRAWS_PER_DAY / NUMBER_SPACE)

    model_scores = np.array(daily_logloss)
    baseline_scores = np.array(daily_baseline)
    difference = baseline_scores - model_scores  # dương = mô hình tốt hơn
    t_stat = (
        float(difference.mean() / (difference.std(ddof=1) / np.sqrt(difference.size)))
        if difference.std(ddof=1) > 0
        else 0.0
    )

    all_p = np.concatenate([p for p, _ in rows])
    all_y = np.concatenate([y for _, y in rows])
    return Evaluation(
        name=model.name,
        family=model.family,
        days=int(model_scores.size),
        logloss=float(model_scores.mean()),
        brier=float(np.mean((all_p - all_y) ** 2)),
        baseline_logloss=float(baseline_scores.mean()),
        baseline_brier=float(np.mean((BASELINE_RATE - all_y) ** 2)),
        paired_t=t_stat,
        hit_at_27=float(np.mean(hit_at_27)),
        baseline_hit_at_27=float(np.mean(baseline_hit)),
        calibration_error=_calibration_error(all_p, all_y),
    )


def default_models() -> list[SequenceModel]:
    """Đủ một đại diện cho mỗi họ thuật toán được đề xuất."""
    return [
        UniformBaseline(),
        EmpiricalFrequency(),
        BetaBinomialShrinkage(),
        MarkovChain(order=1, pooled=True),
        MarkovChain(order=2, pooled=True),
        MarkovChain(order=1, pooled=False),
        GapHazard(),
        HiddenMarkovRegime(),
        ClusterRate(n_clusters=4),
        gradient_boosting(),
        high_capacity_network(),
    ]


__all__ = [
    "BASELINE_RATE",
    "BetaBinomialShrinkage",
    "ClusterRate",
    "EmpiricalFrequency",
    "Evaluation",
    "GapHazard",
    "HiddenMarkovRegime",
    "LogisticRegression",
    "MarkovChain",
    "SequenceModel",
    "SupervisedModel",
    "UniformBaseline",
    "build_features",
    "default_models",
    "gradient_boosting",
    "high_capacity_network",
    "walk_forward",
]


# --------------------------------------------------------------------------
# 8. Kết hợp có kiểm soát — kiến trúc đề xuất
# --------------------------------------------------------------------------


class ShrinkageEnsemble:
    """Trung bình hóa mô hình theo bằng chứng, mặc định rơi về nền.

    Đây là hạt nhân của kiến trúc đề xuất, và điểm mấu chốt nằm ở *mặc định*.
    Một chồng mô hình (stacking) thông thường chuẩn hóa trọng số sao cho tổng
    bằng 1 giữa các mô hình thành phần — nghĩa là luôn có một mô hình được
    trọng số cao nhất, kể cả khi mọi mô hình đều vô dụng. Cấu trúc đó không có
    cách nào diễn đạt câu "không cái nào đáng tin".

    Ở đây nền là một thành phần đặc biệt: nó giữ toàn bộ trọng số cho tới khi
    một mô hình chứng minh được điều ngược lại. Về mặt Bayes, đây là trung bình
    hóa mô hình với tiên nghiệm spike-and-slab đặt khối lượng dương tại "không
    có hiệu ứng".

    Trọng số của mô hình ``i`` lấy từ bằng chứng cuốn chiếu của chính nó:

        w_i ∝ max(0, t_i - t_ngưỡng)²

    với ``t_i`` là thống kê t ghép cặp ở mức ngày của kỹ năng log-loss trên cửa
    sổ đánh giá vừa qua. Bình phương phần vượt ngưỡng, chứ không dùng trực tiếp
    ``t``, làm trọng số tắt trơn về 0 tại ngưỡng thay vì nhảy bậc — một mô hình
    dao động quanh ngưỡng sẽ không làm dự báo giật.

    ``t_ngưỡng`` đã hiệu chỉnh đa kiểm định: thử ``k`` mô hình thì ngưỡng là
    phân vị ``1 - α/(2k)``. Không hiệu chỉnh thì với 10 mô hình, xác suất có ít
    nhất một mô hình vượt ngưỡng 1.96 hoàn toàn do may rủi là khoảng 40%.
    """

    name = "Kết hợp co rút"
    family = "ensemble"

    def __init__(
        self,
        models: list[SequenceModel] | None = None,
        *,
        evidence_window: int = 90,
        alpha: float = 0.05,
        revalidate_every: int = 14,
    ) -> None:
        self.models = (
            models
            if models is not None
            else [
                BetaBinomialShrinkage(),
                MarkovChain(order=1, pooled=True),
                GapHazard(),
                gradient_boosting(),
            ]
        )
        self.evidence_window = int(evidence_window)
        self.alpha = float(alpha)
        self.revalidate_every = int(revalidate_every)
        self._weights: np.ndarray | None = None
        self._validated_at = -1

    @property
    def threshold(self) -> float:
        """Ngưỡng t đã hiệu chỉnh Bonferroni cho số mô hình đang xét."""
        return float(stats.norm.isf(self.alpha / (2 * max(len(self.models), 1))))

    def _evidence(self, history: np.ndarray) -> np.ndarray:
        """Thống kê t ghép cặp của từng mô hình trên cửa sổ bằng chứng gần nhất."""
        window = min(self.evidence_window, history.shape[0] // 2)
        start = history.shape[0] - window
        statistics = np.zeros(len(self.models))
        for index, model in enumerate(self.models):
            differences = []
            for day in range(start, history.shape[0]):
                p = _clip(np.asarray(model.predict_next(history[:day]), dtype=float))
                outcome = (history[day] > 0).astype(float)
                model_loss = -np.mean(outcome * np.log(p) + (1 - outcome) * np.log1p(-p))
                b = BASELINE_RATE
                baseline_loss = -np.mean(outcome * np.log(b) + (1 - outcome) * np.log1p(-b))
                differences.append(baseline_loss - model_loss)
            values = np.asarray(differences)
            spread = values.std(ddof=1)
            statistics[index] = (
                values.mean() / (spread / np.sqrt(values.size)) if spread > 0 else 0.0
            )
        return statistics

    def weights(self, history: np.ndarray) -> np.ndarray:
        """Trọng số hiện hành; phần tử cuối là trọng số của nền."""
        if self._weights is None or history.shape[0] - self._validated_at >= self.revalidate_every:
            excess = np.maximum(self._evidence(history) - self.threshold, 0.0) ** 2
            total = excess.sum()
            # Nền nhận toàn bộ phần trọng số không mô hình nào giành được.
            self._weights = np.append(excess / (total + 1.0), 1.0 / (total + 1.0))
            self._validated_at = history.shape[0]
        return self._weights

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        if history.shape[0] < self.evidence_window * 2:
            return np.full(NUMBER_SPACE, BASELINE_RATE)
        weights = self.weights(history)
        stacked = np.stack(
            [np.asarray(m.predict_next(history), dtype=float) for m in self.models]
            + [np.full(NUMBER_SPACE, BASELINE_RATE)]
        )
        return _clip(weights @ stacked)


__all__ += ["ShrinkageEnsemble"]
