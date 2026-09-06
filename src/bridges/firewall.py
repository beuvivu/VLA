"""Cổng bắt buộc giữa việc quét cầu và việc dùng cầu.

Không có lớp này, bộ quét là một cỗ máy sinh phát hiện giả. Với 412.164 giả
thuyết trên 386 ngày, kỳ vọng có khoảng 104.000 đường cầu "đang chạy 5 nhịp"
ngay cả khi dữ liệu hoàn toàn không mang tín hiệu — chúng trông y hệt cầu thật:
cùng chuỗi thắng, cùng bảng thống kê.

Hai lớp sàng, theo đúng giao thức mà ``research_firewall`` đã thiết lập cho lớp
nghiên cứu của kho:

1. **Benjamini-Hochberg** trên *toàn bộ* họ đã thử, không phải trên phần đã lọc.
   Lọc trước rồi mới chỉnh đa kiểm định chính là cách con số giả sống sót.
2. **Max-statistic circular shift**: dịch vòng chuỗi kết quả để phá liên kết
   ngày–kết quả mà vẫn giữ nguyên cấu trúc tự tương quan, rồi hỏi xem đường cầu
   mạnh nhất trong họ có mạnh hơn đường mạnh nhất của các họ đã bị phá liên kết
   hay không. Đây là phép kiểm chống data snooping ở cấp họ, không phải cấp
   từng giả thuyết.

Vì các phép biến đổi ``reverse_pair`` và ``bo`` đặt cược nhiều con, phép kiểm
thực tế chạy trên ma trận trúng dựng lại chứ không trên chỉ số con — bản dùng
chỉ số con trong ``research_firewall`` chỉ đúng cho giả thuyết một con.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from bridges.scanner import BridgeScanner, BridgeScanResult
from bridges.tensor import DigitTensor
from research_diagnostics import bh_fdr

DEFAULT_Q_VALUE: Final[float] = 0.05
#: Mỗi lần dịch tốn một lượt quét đầy đủ họ giả thuyết (khoảng 6 giây
#: trên 412.164 giả thuyết), nên mặc định thấp và có thể nâng khi cần.
DEFAULT_PERMUTATIONS: Final[int] = 30
DEFAULT_SEED: Final[int] = 20260906
_MIN_SHIFT: Final[int] = 5


@dataclass(frozen=True)
class SurvivorSet:
    """Kết quả sàng lọc — kể cả khi không đường cầu nào sống sót.

    ``tested`` luôn được mang theo. Báo cáo "tìm được 12 đường cầu" mà không nói
    đã thử bao nhiêu giả thuyết là cách trình bày sai lệch nhất có thể ở đây.
    """

    bridges: pd.DataFrame
    tested: int
    q_value: float
    observed_max_skill: float
    null_max_skill_p95: float
    reality_check_p_value: float
    permutations: int

    @property
    def survived(self) -> int:
        return int(len(self.bridges))

    @property
    def is_empty(self) -> bool:
        return self.survived == 0

    @property
    def passed_reality_check(self) -> bool:
        """Họ giả thuyết có vượt được phép kiểm chống data snooping không."""
        if not np.isfinite(self.reality_check_p_value):
            return False
        return self.reality_check_p_value <= self.q_value

    def describe(self) -> str:
        if self.is_empty:
            return (
                f"Không đường cầu nào sống sót: đã thử {self.tested:,} giả thuyết, "
                f"BH-FDR q={self.q_value:g} loại toàn bộ."
            )
        verdict = "ĐẠT" if self.passed_reality_check else "KHÔNG ĐẠT"
        return (
            f"{self.survived:,}/{self.tested:,} giả thuyết qua BH-FDR q={self.q_value:g}; "
            f"kiểm chống data snooping {verdict} "
            f"(kỹ năng quan sát {self.observed_max_skill:+.4f} so với "
            f"p95 của giả thuyết rỗng {self.null_max_skill_p95:+.4f}, "
            f"p={self.reality_check_p_value:.4f}, {self.permutations} lần dịch)"
        )


class FirewallGate:
    """Sàng một :class:`BridgeScanResult` xuống tập được phép dùng tiếp."""

    def __init__(
        self,
        *,
        q_value: float = DEFAULT_Q_VALUE,
        permutations: int = DEFAULT_PERMUTATIONS,
        seed: int = DEFAULT_SEED,
    ) -> None:
        if not 0.0 < q_value < 1.0:
            raise ValueError("q_value phải nằm trong khoảng (0, 1)")
        self.q_value = float(q_value)
        self.permutations = int(permutations)
        self.seed = int(seed)

    def screen(
        self,
        result: BridgeScanResult,
        tensor: DigitTensor,
        scanner: BridgeScanner,
    ) -> SurvivorSet:
        """Chạy BH-FDR trên toàn họ rồi kiểm chống data snooping trên phần sống sót."""
        frame = result.frame
        tested = int(len(frame))
        q = bh_fdr(frame["p_value"].to_numpy(dtype=float))
        survivors = frame.assign(q_value_fdr=q)
        survivors = survivors[survivors["q_value_fdr"] <= self.q_value].copy()
        survivors.sort_values(["q_value_fdr", "p_value"], inplace=True)

        if survivors.empty:
            return SurvivorSet(
                bridges=survivors,
                tested=tested,
                q_value=self.q_value,
                observed_max_skill=float("nan"),
                null_max_skill_p95=float("nan"),
                reality_check_p_value=float("nan"),
                permutations=0,
            )

        check = self._reality_check(survivors, result, tensor, scanner)
        return SurvivorSet(
            bridges=survivors,
            tested=tested,
            q_value=self.q_value,
            **check,
        )

    def _reality_check(
        self,
        survivors: pd.DataFrame,
        result: BridgeScanResult,
        tensor: DigitTensor,
        scanner: BridgeScanner,
    ) -> dict[str, float | int]:
        """Max-statistic circular shift trên TOÀN họ giả thuyết.

        Phân phối rỗng phải lấy trên đúng không gian tìm kiếm đã sinh ra giá trị
        quan sát. Lấy nó trên riêng tập đã sàng lọc — vốn được chọn *vì* mạnh —
        sẽ hạ thấp phân phối rỗng một cách giả tạo và cho gần như mọi tập sống
        sót đều "đạt". Cái giá là mỗi lần dịch tốn một lượt quét đầy đủ, nên số
        lần dịch mặc định thấp hơn hẳn các phép kiểm rẻ tiền khác.
        """
        del survivors  # phân phối rỗng lấy trên toàn họ, không trên phần sống sót
        target = scanner._target_for(tensor, result.target_type)
        n_days = target.shape[0]
        observed = scanner.family_max_skill(tensor, target, result.target_type)

        valid_shifts = np.arange(_MIN_SHIFT, max(_MIN_SHIFT + 1, n_days - _MIN_SHIFT))
        if n_days < 30 or valid_shifts.size == 0:
            return {
                "observed_max_skill": observed,
                "null_max_skill_p95": float("nan"),
                "reality_check_p_value": float("nan"),
                "permutations": 0,
            }

        rng = np.random.default_rng(self.seed)
        shifts = rng.choice(
            valid_shifts,
            size=max(1, self.permutations),
            replace=valid_shifts.size < self.permutations,
        )
        null_max = np.empty(len(shifts), dtype=float)
        for index, shift in enumerate(shifts):
            # Dịch vòng kết quả, giữ nguyên ứng viên: phá liên kết ngày–kết quả
            # mà không phá cấu trúc tự tương quan của cả hai chuỗi.
            shifted = np.roll(target, int(shift), axis=0)
            null_max[index] = scanner.family_max_skill(tensor, shifted, result.target_type)

        exceed = int(np.sum(null_max >= observed - 1e-12))
        return {
            "observed_max_skill": observed,
            "null_max_skill_p95": float(np.quantile(null_max, 0.95)),
            "reality_check_p_value": float((exceed + 1) / (len(shifts) + 1)),
            "permutations": int(len(shifts)),
        }
