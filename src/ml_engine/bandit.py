"""Multi-Armed Bandit lấy mẫu Thompson có chiết khấu.

Mô hình toán học
-----------------

Mỗi "cánh tay" (một phương pháp soi cầu: bạc nhớ, cầu vị trí, cầu nháy, tần
suất…) có một tỉ lệ trúng ẩn ``θ_i`` chưa biết. Đặt tiên nghiệm liên hợp
``θ_i ~ Beta(α₀, β₀)``; sau khi quan sát ``S_i`` lần trúng và ``F_i`` lần trượt,
hậu nghiệm là ``Beta(α₀ + S_i, β₀ + F_i)``.

Lấy mẫu Thompson chọn cánh tay bằng cách rút ``θ̃_i ~ Beta(α_i, β_i)`` cho mọi
``i`` rồi lấy ``argmax``. Đây là *xác suất khớp* (probability matching): mỗi
cánh tay được chọn đúng bằng xác suất hậu nghiệm rằng nó là cánh tay tốt nhất,
nên khai thác và thăm dò được cân bằng mà không cần tham số ``ε`` nào.

Vì sao phải chiết khấu
-----------------------

Lấy mẫu Thompson thuần giả định ``θ_i`` **cố định theo thời gian**. Trong miền
này giả định đó sai theo đúng cách nguy hiểm nhất: một đường cầu "chạy" rồi
"gãy", và một MAB không chiết khấu sẽ còn tin nó rất lâu sau khi nó gãy, vì
hàng trăm quan sát cũ áp đảo vài quan sát mới.

Chiết khấu bằng hệ số ``γ`` giải quyết điều đó::

    S_i ← γ·S_i + r,      F_i ← γ·F_i + (1 − r)

Hệ quả quan trọng nhất, và cũng là giới hạn thật của phương pháp: tổng số quan
sát hiệu dụng **bị chặn**::

    n_eff = Σ γ^k = 1/(1 − γ)

Với ``γ = 0.98`` thì ``n_eff`` bão hòa ở 50 dù đã chạy bao nhiêu ngày. Đó là
cái giá phải trả để thích ứng nhanh, và nó chặn luôn công suất thống kê: với 50
quan sát hiệu dụng quanh nền 0.2377, sai số chuẩn là 0.060, nên MAB chỉ phân
biệt được những chênh lệch rất lớn. ``power_floor()`` trả về đúng con số đó để
người gọi không nhầm dao động ngẫu nhiên với phong độ.
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
from scipy import stats

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

Policy = Literal["thompson", "ucb1"]


class BanditError(ValueError):
    """Thao tác không hợp lệ trên bandit."""


@dataclass
class ArmState:
    """Trạng thái hậu nghiệm của một cánh tay.

    Attributes:
        name: Tên phương pháp mà cánh tay đại diện.
        successes: Số lần trúng đã chiết khấu (không nguyên vì có chiết khấu).
        failures: Số lần trượt đã chiết khấu.
        pulls: Tổng số lần cánh tay được cập nhật, *không* chiết khấu.
    """

    name: str
    successes: float = 0.0
    failures: float = 0.0
    pulls: int = 0

    def posterior(self, prior_alpha: float, prior_beta: float) -> tuple[float, float]:
        """Tham số hậu nghiệm Beta hiện tại.

        Args:
            prior_alpha: Tham số ``α₀`` của tiên nghiệm.
            prior_beta: Tham số ``β₀`` của tiên nghiệm.

        Returns:
            Cặp ``(α, β)`` của phân phối hậu nghiệm.
        """
        return prior_alpha + self.successes, prior_beta + self.failures

    @property
    def effective_n(self) -> float:
        """Số quan sát hiệu dụng còn lại sau chiết khấu."""
        return self.successes + self.failures


@dataclass
class DiscountedThompsonSamplingMAB:
    """Bandit Beta–Nhị thức có chiết khấu, dùng để trộn trọng số các phương pháp.

    Ví dụ:
        >>> mab = DiscountedThompsonSamplingMAB(["bac_nho", "cau_vi_tri"], seed=0)
        >>> mab.update_reward("bac_nho", reward=1.0)
        >>> weights = mab.select_weights()
        >>> round(sum(weights.values()), 6)
        1.0

    Attributes:
        arm_names: Tên các cánh tay, theo thứ tự cố định.
        discount: Hệ số ``γ`` trong ``(0, 1]``; 1.0 là không chiết khấu.
        prior_alpha: ``α₀``, mặc định neo vào tỉ lệ nền của miền.
        prior_beta: ``β₀``.
        policy: ``"thompson"`` hoặc ``"ucb1"``.
        seed: Hạt giống sinh số ngẫu nhiên, để tái lập được.
    """

    arm_names: list[str]
    discount: float = 0.98
    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    policy: Policy = "thompson"
    seed: int = 0
    arms: dict[str, ArmState] = field(default_factory=dict)
    total_updates: int = 0
    _rng: np.random.Generator = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.arm_names:
            raise BanditError("cần ít nhất một cánh tay")
        if len(set(self.arm_names)) != len(self.arm_names):
            raise BanditError("tên cánh tay bị trùng")
        if not 0.0 < self.discount <= 1.0:
            raise BanditError(f"discount phải nằm trong (0, 1], nhận {self.discount}")
        if self.prior_alpha <= 0 or self.prior_beta <= 0:
            raise BanditError("tham số tiên nghiệm phải dương")
        if self.policy not in ("thompson", "ucb1"):
            raise BanditError(f"policy không hỗ trợ: {self.policy}")
        if not self.arms:
            self.arms = {name: ArmState(name=name) for name in self.arm_names}
        if self._rng is None:
            self._rng = np.random.default_rng(self.seed)

    # -- Tính chất -------------------------------------------------------

    @classmethod
    def with_baseline_prior(
        cls, arm_names: list[str], *, baseline: float, strength: float = 4.0, **kwargs: Any
    ) -> DiscountedThompsonSamplingMAB:
        """Dựng bandit với tiên nghiệm neo vào tỉ lệ nền của miền.

        Tiên nghiệm đều ``Beta(1, 1)`` nói rằng tỉ lệ trúng 90% cũng khả dĩ như
        24%. Trong miền này điều đó sai và sai theo hướng tốn kém: bandit sẽ
        dành nhiều lượt để bác bỏ những khả năng mà lý thuyết đã loại từ đầu.
        Neo tiên nghiệm vào nền làm cánh tay chưa có dữ liệu khởi đầu ở đúng
        mức "không biết gì ngoài nền".

        Args:
            arm_names: Tên các cánh tay.
            baseline: Tỉ lệ trúng nền của miền.
            strength: Độ mạnh tiên nghiệm, tính bằng số quan sát ảo.
            **kwargs: Chuyển tiếp cho hàm dựng.

        Returns:
            Bandit đã cấu hình tiên nghiệm.
        """
        if not 0.0 < baseline < 1.0:
            raise BanditError("baseline phải nằm trong (0, 1)")
        return cls(
            arm_names=arm_names,
            prior_alpha=baseline * strength,
            prior_beta=(1.0 - baseline) * strength,
            **kwargs,
        )

    @property
    def max_effective_n(self) -> float:
        """Trần số quan sát hiệu dụng do chiết khấu áp đặt."""
        return float("inf") if self.discount >= 1.0 else 1.0 / (1.0 - self.discount)

    def power_floor(self, baseline: float) -> float:
        """Chênh lệch tỉ lệ nhỏ nhất mà bandit này có thể phân biệt.

        Sai số chuẩn của một tỉ lệ ước lượng từ ``n_eff`` quan sát là
        ``√(p(1−p)/n_eff)``. Vì chiết khấu chặn ``n_eff`` ở ``1/(1−γ)``, con số
        này là *sàn cứng*: không có số ngày chạy nào hạ nó xuống được.

        Args:
            baseline: Tỉ lệ nền để tính sai số chuẩn.

        Returns:
            Sai số chuẩn ở trần quan sát hiệu dụng.
        """
        n = self.max_effective_n
        if not np.isfinite(n):
            return 0.0
        return float(np.sqrt(baseline * (1.0 - baseline) / n))

    # -- Cập nhật --------------------------------------------------------

    def _decay(self) -> None:
        """Chiết khấu toàn bộ cánh tay một bước.

        Chiết khấu *mọi* cánh tay chứ không riêng cánh tay vừa nhận thưởng: nếu
        chỉ chiết khấu cánh tay được cập nhật thì cánh tay lâu không dùng sẽ giữ
        nguyên độ tin cậy cũ và bandit sẽ không bao giờ thăm dò lại chúng.
        """
        if self.discount >= 1.0:
            return
        for arm in self.arms.values():
            arm.successes *= self.discount
            arm.failures *= self.discount

    def update_reward(self, arm_name: str, reward: float) -> None:
        """Cập nhật hậu nghiệm của một cánh tay bằng một tín hiệu thưởng.

        Args:
            arm_name: Tên cánh tay đã được dùng.
            reward: Phần thưởng trong ``[0, 1]``; 1 là trúng, 0 là trượt. Cho
                phép giá trị phân số để biểu diễn thưởng riêng phần (ví dụ
                trúng 2 trong 5 con gợi ý).

        Raises:
            BanditError: Khi tên cánh tay không tồn tại hoặc thưởng ngoài khoảng.
        """
        if arm_name not in self.arms:
            raise BanditError(f"cánh tay không tồn tại: {arm_name!r}")
        if not 0.0 <= reward <= 1.0:
            raise BanditError(f"reward phải nằm trong [0, 1], nhận {reward}")

        self._decay()
        arm = self.arms[arm_name]
        arm.successes += reward
        arm.failures += 1.0 - reward
        arm.pulls += 1
        self.total_updates += 1

    def update_batch(self, rewards: dict[str, float]) -> None:
        """Cập nhật nhiều cánh tay từ kết quả của cùng một ngày.

        Chiết khấu đúng **một** bước cho cả lô, không phải mỗi cánh tay một
        bước: một ngày là một đơn vị thời gian, và chiết khấu theo số cánh tay
        sẽ làm trí nhớ ngắn đi đúng bấy nhiêu lần.

        Args:
            rewards: Ánh xạ tên cánh tay sang phần thưởng của ngày đó.

        Raises:
            BanditError: Khi có tên cánh tay lạ hoặc thưởng ngoài khoảng.
        """
        unknown = set(rewards) - set(self.arms)
        if unknown:
            raise BanditError(f"cánh tay không tồn tại: {sorted(unknown)}")
        for name, reward in rewards.items():
            if not 0.0 <= reward <= 1.0:
                raise BanditError(f"reward của {name} ngoài [0, 1]: {reward}")

        self._decay()
        for name, reward in rewards.items():
            arm = self.arms[name]
            arm.successes += reward
            arm.failures += 1.0 - reward
            arm.pulls += 1
        self.total_updates += 1

    # -- Lựa chọn --------------------------------------------------------

    def sample_posteriors(self) -> dict[str, float]:
        """Rút một mẫu hậu nghiệm cho mỗi cánh tay.

        Returns:
            Ánh xạ tên cánh tay sang giá trị ``θ̃`` vừa rút.
        """
        return {
            name: float(self._rng.beta(*arm.posterior(self.prior_alpha, self.prior_beta)))
            for name, arm in self.arms.items()
        }

    def _ucb1_scores(self) -> dict[str, float]:
        """Điểm UCB1 cho từng cánh tay, dùng số quan sát đã chiết khấu."""
        total = max(sum(a.effective_n for a in self.arms.values()), 1e-9)
        scores: dict[str, float] = {}
        for name, arm in self.arms.items():
            n = arm.effective_n
            if n <= 0:
                scores[name] = float("inf")  # cánh tay chưa thử luôn được ưu tiên
                continue
            mean = arm.successes / n
            scores[name] = mean + float(np.sqrt(2.0 * np.log(total) / n))
        return scores

    def select_arm(self) -> str:
        """Chọn một cánh tay theo chính sách đang cấu hình.

        Returns:
            Tên cánh tay được chọn.
        """
        if self.policy == "ucb1":
            scores = self._ucb1_scores()
            return max(scores, key=lambda name: scores[name])
        samples = self.sample_posteriors()
        return max(samples, key=lambda name: samples[name])

    def select_weights(self, draws: int = 512) -> dict[str, float]:
        """Trọng số trộn: xác suất hậu nghiệm mỗi cánh tay là tốt nhất.

        Đây là cách dùng bandit cho bài toán *trộn* thay vì *chọn một*. Rút
        ``draws`` lần từ hậu nghiệm và đếm tần suất mỗi cánh tay thắng; kết quả
        là ước lượng Monte Carlo của ``P(cánh tay i là tốt nhất | dữ liệu)``.
        Trộn theo trọng số đó giữ nguyên tính chất khớp xác suất của lấy mẫu
        Thompson, nhưng cho dự báo trơn thay vì nhảy giữa các cánh tay.

        Args:
            draws: Số lần rút Monte Carlo.

        Returns:
            Trọng số dương, tổng bằng 1.

        Raises:
            BanditError: Khi ``draws`` không dương.
        """
        if draws < 1:
            raise BanditError("draws phải dương")
        names = list(self.arms)
        alphas = np.array(
            [self.arms[n].posterior(self.prior_alpha, self.prior_beta)[0] for n in names]
        )
        betas = np.array(
            [self.arms[n].posterior(self.prior_alpha, self.prior_beta)[1] for n in names]
        )
        samples = self._rng.beta(alphas, betas, size=(draws, len(names)))
        winners = np.argmax(samples, axis=1)
        counts = np.bincount(winners, minlength=len(names)).astype(float)
        return dict(zip(names, counts / counts.sum(), strict=True))

    def credible_interval(self, arm_name: str, level: float = 0.95) -> tuple[float, float]:
        """Khoảng tin cậy hậu nghiệm của tỉ lệ trúng một cánh tay.

        Args:
            arm_name: Tên cánh tay.
            level: Mức tin cậy trong ``(0, 1)``.

        Returns:
            Cặp ``(cận dưới, cận trên)``.

        Raises:
            BanditError: Khi cánh tay không tồn tại hoặc mức không hợp lệ.
        """
        if arm_name not in self.arms:
            raise BanditError(f"cánh tay không tồn tại: {arm_name!r}")
        if not 0.0 < level < 1.0:
            raise BanditError("level phải nằm trong (0, 1)")
        alpha, beta = self.arms[arm_name].posterior(self.prior_alpha, self.prior_beta)
        tail = (1.0 - level) / 2.0
        return float(stats.beta.ppf(tail, alpha, beta)), float(
            stats.beta.ppf(1.0 - tail, alpha, beta)
        )

    def beats_baseline(self, arm_name: str, baseline: float, level: float = 0.95) -> bool:
        """Cánh tay có vượt nền một cách đáng tin không.

        Dùng cận dưới của khoảng tin cậy chứ không dùng trung bình hậu nghiệm:
        trung bình của một cánh tay mới chỉ có vài quan sát rất dễ vượt nền do
        may rủi, còn cận dưới thì không.

        Args:
            arm_name: Tên cánh tay.
            baseline: Tỉ lệ nền của miền.
            level: Mức tin cậy.

        Returns:
            ``True`` nếu toàn bộ khoảng tin cậy nằm trên nền.
        """
        lower, _ = self.credible_interval(arm_name, level=level)
        return lower > baseline

    # -- Tuần tự hóa -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Kết xuất toàn bộ trạng thái sang cấu trúc JSON được.

        Trạng thái bộ sinh ngẫu nhiên cũng được lưu, nên nạp lại rồi chạy tiếp
        cho đúng dãy số như thể chưa từng dừng. Thiếu điều này thì mỗi lần khởi
        động lại tiến trình sẽ đổi hành vi thăm dò, và không bản chạy nào tái
        lập được.

        Returns:
            Từ điển thuần Python, an toàn cho ``json.dump``.
        """
        return {
            "version": 1,
            "arm_names": list(self.arm_names),
            "discount": self.discount,
            "prior_alpha": self.prior_alpha,
            "prior_beta": self.prior_beta,
            "policy": self.policy,
            "seed": self.seed,
            "total_updates": self.total_updates,
            "arms": {
                name: {
                    "successes": arm.successes,
                    "failures": arm.failures,
                    "pulls": arm.pulls,
                }
                for name, arm in self.arms.items()
            },
            "rng_state": json.loads(json.dumps(self._rng.bit_generator.state, default=str)),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DiscountedThompsonSamplingMAB:
        """Dựng lại bandit từ trạng thái đã kết xuất.

        Args:
            payload: Kết quả của :meth:`to_dict`.

        Returns:
            Bandit có trạng thái giống hệt lúc kết xuất.

        Raises:
            BanditError: Khi thiếu trường hoặc phiên bản không hỗ trợ.
        """
        if payload.get("version") != 1:
            raise BanditError(f"phiên bản trạng thái không hỗ trợ: {payload.get('version')!r}")
        try:
            mab = cls(
                arm_names=list(payload["arm_names"]),
                discount=float(payload["discount"]),
                prior_alpha=float(payload["prior_alpha"]),
                prior_beta=float(payload["prior_beta"]),
                policy=payload["policy"],
                seed=int(payload["seed"]),
                arms={
                    name: ArmState(
                        name=name,
                        successes=float(state["successes"]),
                        failures=float(state["failures"]),
                        pulls=int(state["pulls"]),
                    )
                    for name, state in payload["arms"].items()
                },
                total_updates=int(payload["total_updates"]),
            )
        except KeyError as error:
            raise BanditError(f"trạng thái thiếu trường {error}") from error

        state = payload.get("rng_state")
        if state:
            restored = dict(state)
            # json biến số nguyên lớn của PCG64 thành chuỗi; đổi ngược lại.
            inner = dict(restored.get("state", {}))
            for key, value in inner.items():
                if isinstance(value, str) and value.lstrip("-").isdigit():
                    inner[key] = int(value)
            restored["state"] = inner
            mab._rng.bit_generator.state = restored
        return mab

    def save_json(self, path: str | Path) -> Path:
        """Ghi trạng thái ra tệp JSON.

        Args:
            path: Đường dẫn tệp đích.

        Returns:
            Đường dẫn đã ghi.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        LOGGER.info("Đã ghi trạng thái bandit vào %s", target)
        return target

    @classmethod
    def load_json(cls, path: str | Path) -> DiscountedThompsonSamplingMAB:
        """Nạp trạng thái từ tệp JSON.

        Args:
            path: Đường dẫn tệp nguồn.

        Returns:
            Bandit đã khôi phục.

        Raises:
            BanditError: Khi tệp không tồn tại hoặc nội dung hỏng.
        """
        source = Path(path)
        if not source.exists():
            raise BanditError(f"không tìm thấy trạng thái bandit: {source}")
        try:
            return cls.from_dict(json.loads(source.read_text(encoding="utf-8")))
        except json.JSONDecodeError as error:
            raise BanditError(f"trạng thái bandit hỏng: {source}") from error

    def save_pickle(self, path: str | Path) -> Path:
        """Ghi trạng thái bằng ``pickle``.

        JSON là định dạng nên dùng để lưu lâu dài vì đọc được và không thực thi
        mã khi nạp. ``pickle`` có ở đây theo đặc tả, và chỉ nên dùng cho tệp do
        chính hệ thống sinh ra.

        Args:
            path: Đường dẫn tệp đích.

        Returns:
            Đường dẫn đã ghi.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            pickle.dump(self.to_dict(), handle, protocol=pickle.HIGHEST_PROTOCOL)
        return target

    @classmethod
    def load_pickle(cls, path: str | Path) -> DiscountedThompsonSamplingMAB:
        """Nạp trạng thái từ tệp ``pickle`` do chính hệ thống sinh ra.

        Args:
            path: Đường dẫn tệp nguồn.

        Returns:
            Bandit đã khôi phục.

        Raises:
            BanditError: Khi tệp không tồn tại hoặc nội dung hỏng.
        """
        source = Path(path)
        if not source.exists():
            raise BanditError(f"không tìm thấy trạng thái bandit: {source}")
        with source.open("rb") as handle:
            return cls.from_dict(pickle.load(handle))

    def report(self, baseline: float) -> list[dict[str, Any]]:
        """Bảng tóm tắt từng cánh tay để ghi nhật ký và hiển thị.

        Args:
            baseline: Tỉ lệ nền để so sánh.

        Returns:
            Danh sách bản ghi, sắp giảm dần theo trung bình hậu nghiệm.
        """
        rows = []
        for name, arm in self.arms.items():
            alpha, beta = arm.posterior(self.prior_alpha, self.prior_beta)
            lower, upper = self.credible_interval(name)
            rows.append(
                {
                    "arm": name,
                    "posterior_mean": alpha / (alpha + beta),
                    "credible_low": lower,
                    "credible_high": upper,
                    "effective_n": arm.effective_n,
                    "pulls": arm.pulls,
                    "beats_baseline": lower > baseline,
                }
            )
        return sorted(rows, key=lambda row: -row["posterior_mean"])
