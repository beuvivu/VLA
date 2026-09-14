"""Gộp thông tin có phân cấp: học độ co ngót thay vì đặt tay.

Vì sao đây là hướng DUY NHẤT nâng được công suất
================================================
``data/research/randomness_report.json`` đo được: với 100 giả thuyết độc lập
(một cho mỗi con số), hiệu ứng tối thiểu phát hiện được là +15,8 % tương đối;
với một giả thuyết duy nhất, chỉ +10,3 %. Khoảng cách ấy là cái giá của việc
ước lượng 100 tham số rời rạc.

Mô hình phân cấp không thêm sức chứa — nó **bớt** đi. Mỗi con số vay mượn
thông tin từ 99 con còn lại, nên số tham số HIỆU DỤNG nằm giữa 1 và 100 thay vì
đúng bằng 100. Ít tham số hiệu dụng nghĩa là ngưỡng phát hiện thấp hơn. Đó là
lý do mọi kiến trúc "thêm tầng" đi ngược hướng, còn cái này đi đúng hướng.

Quan hệ với mã hiện có
======================
``statistical_signal.py`` VỐN ĐÃ là Beta-Binomial phân cấp: nó dựng tiên nghiệm
Beta quanh tần suất nền với ``prior_strength = 80``. Vấn đề duy nhất là con số
80 được đặt tay. Module này ước lượng nó từ chính dữ liệu bằng phương pháp
Bayes thực nghiệm, và trả về kèm mọi con số cần để kiểm chứng lựa chọn ấy.

Điều quan trọng phải nói trước: nếu các con số thực sự đồng nhất — tức không có
con nào "về nhiều hơn" con nào ngoài dao động ngẫu nhiên — thì ước lượng đúng
là co ngót GẦN NHƯ HOÀN TOÀN về trung bình chung. Đó không phải mô hình thất
bại; đó là mô hình nói đúng sự thật, và nó tốt hơn hẳn việc giữ 100 ước lượng
rời rạc mỗi cái đầy nhiễu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

#: Trên ngưỡng này coi như co ngót hoàn toàn. Không phải để làm đẹp số: với
#: κ lớn hơn vài nghìn lần số kỳ, hậu nghiệm của mọi con số đã trùng nhau tới
#: mức không phân biệt được bằng số thực dấu chấm động.
MAX_PRIOR_STRENGTH: Final[float] = 1e6
MIN_NUMBERS: Final[int] = 3


@dataclass(frozen=True)
class PoolingFit:
    """Kết quả gộp, kèm mọi con số cần để KIỂM CHỨNG lựa chọn.

    ``fully_pooled`` là kết luận đáng chú ý nhất: nó nói rằng dữ liệu không
    phân biệt được các con số với nhau, và mọi bảng xếp hạng theo tần suất
    riêng của từng con đều đang xếp hạng nhiễu.
    """

    pooled_rate: float
    prior_strength: float
    shrinkage: float
    effective_parameters: float
    between_variance: float
    within_variance: float
    n_units: int
    n_trials: float

    @property
    def fully_pooled(self) -> bool:
        return self.prior_strength >= MAX_PRIOR_STRENGTH

    def describe(self) -> str:
        if self.fully_pooled:
            return (
                f"Co ngót HOÀN TOÀN: {self.n_units} đơn vị không phân biệt được nhau "
                f"trên {self.n_trials:.0f} kỳ (phương sai giữa các đơn vị {self.between_variance:.3e} "
                f"không vượt phương sai trong nội bộ {self.within_variance:.3e}). "
                # In số THẬT chứ không in cứng "1,00": ở mức trần κ vẫn còn một
                # phần tự do nhỏ (κ/(κ+n) < 1), và thông điệp nói khác con số
                # thật là cách một sai lệch nhỏ sống sót qua mọi lần đọc.
                f"Tham số hiệu dụng: {self.effective_parameters:.2f} trên {self.n_units}."
            )
        return (
            f"Co ngót {self.shrinkage:.1%} về trung bình chung {self.pooled_rate:.4f} "
            f"(κ = {self.prior_strength:.1f} trên {self.n_trials:.0f} kỳ). "
            f"Tham số hiệu dụng: {self.effective_parameters:.2f} trên {self.n_units}."
        )


def fit_pooling(successes: np.ndarray, trials: np.ndarray | float) -> PoolingFit:
    """Ước lượng độ co ngót bằng Bayes thực nghiệm (phương pháp mô men).

    Ý tưởng, phát biểu bằng phương sai:

    * Nếu mọi đơn vị có cùng tỉ lệ thật, thì tỉ lệ QUAN SÁT của chúng vẫn khác
      nhau — nhưng chỉ khác đúng bằng dao động nhị thức ``m(1-m)/n``.
    * Phần phương sai VƯỢT quá mức ấy mới là bằng chứng các đơn vị thật sự khác
      nhau. Không có phần vượt thì không có gì để phân biệt.

    Khi phần vượt ``≤ 0``, hàm trả về co ngót hoàn toàn thay vì một κ âm vô
    nghĩa. Đây là trường hợp thường gặp nhất với dữ liệu ở đây, và nó là câu
    trả lời ĐÚNG chứ không phải trường hợp suy biến cần né.
    """
    counts = np.asarray(successes, dtype=float).reshape(-1)
    n_units = counts.size
    if n_units < MIN_NUMBERS:
        raise ValueError(f"cần ít nhất {MIN_NUMBERS} đơn vị để ước lượng độ co ngót")
    n = np.asarray(trials, dtype=float)
    if n.ndim == 0:
        n = np.full(n_units, float(n))
    if n.shape != counts.shape:
        raise ValueError("successes và trials phải cùng hình dạng")
    if np.any(n <= 0):
        raise ValueError("mọi đơn vị phải có ít nhất một phép thử")
    # Dung sai cho sai số cộng dấu chấm động.
    #
    # Với số lần thành công CÓ TRỌNG SỐ, ``counts`` và ``trials`` được cộng
    # theo hai thứ tự khác nhau, nên một đơn vị trúng MỌI kỳ có thể cho
    # ``counts`` nhỉnh hơn ``trials`` ở chữ số cuối. Đó là đầu vào hoàn toàn
    # hợp lệ, và từ chối nó là từ chối nhầm — phép kiểm chọn chu kỳ bán rã đã
    # nổ đúng vì chuyện này.
    tolerance = 1e-9 * np.maximum(np.abs(n), 1.0)
    if np.any(counts < -tolerance) or np.any(counts > n + tolerance):
        raise ValueError("số lần thành công phải nằm trong [0, số phép thử]")
    # Kẹp này là phòng thủ và KHÔNG quan sát được từ bên ngoài — đã kiểm ngược:
    # gỡ nó đi không phép kiểm nào đỏ. Lý do là chốt ``pooled <= 0 or pooled >= 1``
    # phía dưới đã bắt cùng một biên, nên một giá trị lệch 1e-15 vẫn rơi vào
    # nhánh co ngót hoàn toàn y hệt. Giữ lại để ``rates`` không mang giá trị vô
    # nghĩa nếu ai đó thêm phép tính khác vào giữa; ghi rõ ở đây rằng phép kiểm
    # không tách được dòng này.
    counts = np.clip(counts, 0.0, n)

    rates = counts / n
    # Trung bình CÓ TRỌNG SỐ theo số phép thử: đơn vị được thử nhiều hơn mang
    # nhiều thông tin hơn, và trung bình thường sẽ để một đơn vị hiếm kéo lệch.
    pooled = float(counts.sum() / n.sum())
    harmonic_n = float(n_units / np.sum(1.0 / n))

    observed_variance = float(np.var(rates, ddof=1))
    within = float(pooled * (1.0 - pooled) / harmonic_n)
    between = observed_variance - within

    if not np.isfinite(between) or between <= 0.0 or pooled <= 0.0 or pooled >= 1.0:
        kappa = MAX_PRIOR_STRENGTH
    else:
        kappa = float(pooled * (1.0 - pooled) / between - 1.0)
        kappa = float(np.clip(kappa, 1e-6, MAX_PRIOR_STRENGTH))

    shrinkage = float(kappa / (kappa + harmonic_n))
    return PoolingFit(
        pooled_rate=pooled,
        prior_strength=kappa,
        shrinkage=shrinkage,
        # Một tham số chung, cộng phần tự do còn lại của các đơn vị sau co ngót.
        effective_parameters=1.0 + (n_units - 1.0) * (1.0 - shrinkage),
        between_variance=max(between, 0.0),
        within_variance=within,
        n_units=n_units,
        n_trials=float(np.mean(n)),
    )


def pooled_posterior(
    successes: np.ndarray, trials: np.ndarray | float, fit: PoolingFit
) -> np.ndarray:
    """Hậu nghiệm Beta-Binomial của từng đơn vị dưới độ co ngót đã học."""
    counts = np.asarray(successes, dtype=float).reshape(-1)
    n = np.asarray(trials, dtype=float)
    if n.ndim == 0:
        n = np.full(counts.size, float(n))
    a0 = fit.prior_strength * fit.pooled_rate
    b0 = fit.prior_strength * (1.0 - fit.pooled_rate)
    return (a0 + counts) / (a0 + b0 + n)


def fit_shrinkage_to_prior(
    successes: np.ndarray,
    trials: np.ndarray | float,
    prior_mean: np.ndarray | float,
) -> float:
    """Học κ khi TÂM co ngót đã cho trước theo từng đơn vị.

    ``fit_pooling`` giả định mọi đơn vị co về một tỉ lệ chung duy nhất. Năm
    ước lượng có điều kiện trong ``number_dynamics`` không như vậy: chúng co
    về đường nền RIÊNG của từng con số. Câu hỏi ở đây khác hẳn — không phải
    "các con số có khác nhau không" mà "điều kiện hoá có dịch chuyển được con
    số khỏi đường nền của chính nó không".

    Vẫn là phương pháp mô men, chỉ đổi tâm:

    * Nếu điều kiện hoá không mang thông tin, độ lệch ``rᵢ - mᵢ`` chỉ phản ánh
      dao động nhị thức ``mᵢ(1-mᵢ)/nᵢ``.
    * Phần vượt quá mức ấy mới là bằng chứng điều kiện hoá có tác dụng.

    Không có phần vượt thì trả ``MAX_PRIOR_STRENGTH`` — nghĩa là bỏ hẳn ước
    lượng có điều kiện và giữ nguyên đường nền. Đó là câu trả lời đúng chứ
    không phải trường hợp suy biến.

    Đơn vị không có phép thử nào bị loại: chúng không nói được gì, và để
    chúng vào thì ``0/0`` sẽ giả vờ là một độ lệch bằng không.
    """
    counts = np.asarray(successes, dtype=float).reshape(-1)
    n = np.asarray(trials, dtype=float)
    if n.ndim == 0:
        n = np.full(counts.size, float(n))
    n = n.reshape(-1)
    m = np.asarray(prior_mean, dtype=float)
    if m.ndim == 0:
        m = np.full(counts.size, float(m))
    m = m.reshape(-1)
    if n.shape != counts.shape or m.shape != counts.shape:
        raise ValueError("successes, trials và prior_mean phải cùng hình dạng")

    usable = np.isfinite(counts) & np.isfinite(n) & np.isfinite(m) & (n > 0)
    if int(usable.sum()) < MIN_NUMBERS:
        return MAX_PRIOR_STRENGTH

    counts = counts[usable]
    n = n[usable]
    m = np.clip(m[usable], 1e-9, 1.0 - 1e-9)
    counts = np.clip(counts, 0.0, n)

    rates = counts / n
    deviation = float(np.mean((rates - m) ** 2))
    within = float(np.mean(m * (1.0 - m) / n))
    between = deviation - within

    centre = float(np.mean(m))
    if not np.isfinite(between) or between <= 0.0:
        return MAX_PRIOR_STRENGTH
    kappa = centre * (1.0 - centre) / between - 1.0
    if not np.isfinite(kappa):
        return MAX_PRIOR_STRENGTH
    return float(np.clip(kappa, 1e-6, MAX_PRIOR_STRENGTH))


def fit_shrinkage_to_prior_rows(
    successes: np.ndarray,
    trials: np.ndarray,
    prior_mean: np.ndarray,
) -> np.ndarray:
    """Như ``fit_shrinkage_to_prior`` nhưng học κ RIÊNG cho từng hàng.

    Vì sao phải tách hàng, nói bằng con số đã đo: ma trận chuyển trạng thái có
    100×100 ô. Gộp cả 10 000 ô vào một κ duy nhất thì một quan hệ TẤT ĐỊNH
    12 → 34 chỉ là 1 phần 10 000 của mô men bậc hai — nó chìm nghỉm, κ sập về
    co ngót hoàn toàn, và tín hiệu thật bị xoá sạch. Một phép kiểm tiêm tín
    hiệu đã bắt đúng chuyện này.

    Tách theo hàng nguồn thì cùng quan hệ ấy là 1 phần 100, đủ để nhô lên khỏi
    dao động nhị thức. Câu hỏi cũng đúng hơn về mặt thống kê: mỗi hàng là một
    câu hỏi riêng — "con số này về thì nó kéo theo gì" — nên nó phải có độ co
    ngót riêng.

    ``successes`` hình ``(n_rows, n_units)``; ``trials`` hình ``(n_rows,)``
    hoặc ``(n_rows, n_units)``; ``prior_mean`` hình ``(n_units,)``.
    """
    counts = np.asarray(successes, dtype=float)
    if counts.ndim != 2:
        raise ValueError("successes phải có hai chiều (n_rows, n_units)")
    n_rows, n_units = counts.shape
    n = np.asarray(trials, dtype=float)
    if n.ndim == 1:
        n = np.broadcast_to(n[:, None], counts.shape)
    if n.shape != counts.shape:
        raise ValueError("trials phải phát sóng được về hình của successes")
    m = np.asarray(prior_mean, dtype=float).reshape(-1)
    if m.size != n_units:
        raise ValueError("prior_mean phải cùng số đơn vị với successes")
    m = np.clip(m, 1e-9, 1.0 - 1e-9)

    out = np.full(n_rows, MAX_PRIOR_STRENGTH, dtype=float)
    usable = np.isfinite(counts) & np.isfinite(n) & (n > 0)
    enough = usable.sum(axis=1) >= MIN_NUMBERS
    if not np.any(enough):
        return out

    safe_n = np.where(usable, n, 1.0)
    rates = np.where(usable, np.clip(counts, 0.0, safe_n) / safe_n, 0.0)
    dev = np.where(usable, (rates - m[None, :]) ** 2, 0.0)
    within_cell = np.where(usable, m[None, :] * (1.0 - m[None, :]) / safe_n, 0.0)
    k = usable.sum(axis=1)
    k_safe = np.maximum(k, 1)

    between = dev.sum(axis=1) / k_safe - within_cell.sum(axis=1) / k_safe
    centre = np.where(
        k > 0, (np.where(usable, m[None, :], 0.0)).sum(axis=1) / k_safe, 0.5
    )
    good = enough & np.isfinite(between) & (between > 0.0)
    kappa = np.divide(
        centre * (1.0 - centre),
        np.where(good, between, 1.0),
        out=np.full(n_rows, np.inf),
        where=good,
    ) - 1.0
    out[good] = np.clip(kappa[good], 1e-6, MAX_PRIOR_STRENGTH)
    out[~np.isfinite(out)] = MAX_PRIOR_STRENGTH
    return out
