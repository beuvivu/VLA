from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from soi_cau.bridges.scanner import BridgeScanner, BridgeScanResult
from soi_cau.bridges.scanner import DigitTensor
from stats.statistical_corrections import benjamini_hochberg as bh_fdr

DEFAULT_Q_VALUE: Final[float] = 0.05
DEFAULT_PERMUTATIONS: Final[int] = 30
DEFAULT_SEED: Final[int] = 20260906
_MIN_SHIFT: Final[int] = 5


@dataclass(frozen=True)
class SurvivorSet:

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
        frame = result.frame
        tested = int(len(frame))
        q = bh_fdr(frame["p_value"].to_numpy(dtype=float))
        survivors = frame.assign(q_value_fdr=q)
        survivors = survivors[survivors["q_value_fdr"] <= self.q_value].copy()
        survivors = survivors.sort_values(["q_value_fdr", "p_value"])

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
        del survivors
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
            shifted = np.roll(target, int(shift), axis=0)
            null_max[index] = scanner.family_max_skill(tensor, shifted, result.target_type)

        exceed = int(np.sum(null_max >= observed - 1e-12))
        return {
            "observed_max_skill": observed,
            "null_max_skill_p95": float(np.quantile(null_max, 0.95)),
            "reality_check_p_value": float((exceed + 1) / (len(shifts) + 1)),
            "permutations": int(len(shifts)),
        }
