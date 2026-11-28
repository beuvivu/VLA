from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from soi_cau.bridges.firewall import FirewallGate, SurvivorSet
from soi_cau.bridges.scanner import BridgeScanner, _tail_probability, baseline_rate_table
from soi_cau.bridges.scanner import DigitTensor
from stats.statistical_corrections import benjamini_hochberg as bh_fdr

IDENTITY_COLUMNS: Final[tuple[str, ...]] = (
    "position_a", "position_b", "lag_a", "lag_b", "shadow", "transformation",
)

DEFAULT_HOLDOUT_FRACTION: Final[float] = 0.40
DEFAULT_ALPHA: Final[float] = 0.05
MIN_REPLICATION_DAYS: Final[int] = 120


@dataclass(frozen=True)
class ReplicationVerdict:

    bridges: pd.DataFrame
    discovered: int
    discovery_days: int
    replication_days: int
    split_date: str
    alpha: float
    conclusive: bool

    @property
    def replicated(self) -> int:
        return int(len(self.bridges))

    @property
    def is_empty(self) -> bool:
        return self.replicated == 0

    def describe(self) -> str:
        if not self.conclusive:
            return (
                f"Cổng tái lập KHÔNG kết luận được: đoạn kiểm chứng chỉ "
                f"{self.replication_days} kỳ, dưới ngưỡng {MIN_REPLICATION_DAYS}."
            )
        if self.discovered == 0:
            return "Không đường cầu nào bước vào cổng tái lập (đoạn phát hiện đã loại hết)."
        if self.is_empty:
            return (
                f"KHÔNG đường nào tái lập: {self.discovered:,} đường qua được đoạn "
                f"phát hiện ({self.discovery_days} kỳ) đều không giữ được kỹ năng "
                f"trên {self.replication_days} kỳ kiểm chứng sau {self.split_date}."
            )
        return (
            f"{self.replicated:,}/{self.discovered:,} đường tái lập được trên "
            f"{self.replication_days} kỳ kiểm chứng sau {self.split_date} "
            f"(BH-FDR q={self.alpha:g} trên chính tập đã sống sót)."
        )


def slice_tensor(tensor: DigitTensor, start: int, stop: int) -> DigitTensor:
    if not 0 <= start < stop <= tensor.n_days:
        raise ValueError(f"lát [{start}, {stop}) không hợp lệ với {tensor.n_days} kỳ")
    return DigitTensor(
        values=tensor.values[start:stop],
        dates=tensor.dates[start:stop],
        position_labels=tensor.position_labels,
        loto_counts=tensor.loto_counts[start:stop],
        de_index=tensor.de_index[start:stop],
    )


class ReplicationGate:

    def __init__(
        self,
        *,
        holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
        alpha: float = DEFAULT_ALPHA,
        firewall: FirewallGate | None = None,
    ) -> None:
        if not 0.1 <= holdout_fraction <= 0.9:
            raise ValueError("holdout_fraction phải nằm trong [0.1, 0.9]")
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha phải nằm trong (0, 1)")
        self.holdout_fraction = float(holdout_fraction)
        self.alpha = float(alpha)
        self.firewall = firewall or FirewallGate()

    def split_index(self, tensor: DigitTensor) -> int:
        return int(round(tensor.n_days * (1.0 - self.holdout_fraction)))

    def screen(
        self,
        tensor: DigitTensor,
        scanner: BridgeScanner,
        *,
        target_type: str,
    ) -> tuple[ReplicationVerdict, SurvivorSet]:
        split = self.split_index(tensor)
        warmup = scanner.start_index
        replication_days = tensor.n_days - split

        if split <= warmup or replication_days < MIN_REPLICATION_DAYS:
            empty = pd.DataFrame(columns=[*IDENTITY_COLUMNS])
            return (
                ReplicationVerdict(
                    bridges=empty,
                    discovered=0,
                    discovery_days=max(0, split),
                    replication_days=max(0, replication_days),
                    split_date="",
                    alpha=self.alpha,
                    conclusive=False,
                ),
                self.firewall.screen(scanner.scan(tensor, target_type=target_type), tensor, scanner),
            )

        discovery = slice_tensor(tensor, 0, split)
        replication = slice_tensor(tensor, split - warmup, tensor.n_days)

        found = self.firewall.screen(
            scanner.scan(discovery, target_type=target_type), discovery, scanner
        )
        split_date = str(pd.Timestamp(tensor.dates[split]).date())

        if found.is_empty:
            return (
                ReplicationVerdict(
                    bridges=found.bridges,
                    discovered=0,
                    discovery_days=split,
                    replication_days=replication_days,
                    split_date=split_date,
                    alpha=self.alpha,
                    conclusive=True,
                ),
                found,
            )

        scored = self._score_on_holdout(found.bridges, replication, scanner, target_type)
        scored["q_value_replication"] = bh_fdr(scored["p_value_replication"].to_numpy(dtype=float))
        replicated = scored[
            (scored["q_value_replication"] <= self.alpha)
            & (scored["precision_replication"] > scored["expected_rate_replication"])
        ].copy()
        replicated = replicated.sort_values(["q_value_replication", "p_value_replication"])

        return (
            ReplicationVerdict(
                bridges=replicated,
                discovered=int(len(found.bridges)),
                discovery_days=split,
                replication_days=replication_days,
                split_date=split_date,
                alpha=self.alpha,
                conclusive=True,
            ),
            found,
        )

    def _score_on_holdout(
        self,
        survivors: pd.DataFrame,
        replication: DigitTensor,
        scanner: BridgeScanner,
        target_type: str,
    ) -> pd.DataFrame:
        rebuilt, target = scanner.rebuild_hits(replication, survivors, target_type=target_type)
        hits = rebuilt.hits_for(target, target_type)

        rate_table = baseline_rate_table(target_type)
        day_rate = rate_table[rebuilt.sizes]
        successes = hits.sum(axis=0).astype(float)
        trials = float(hits.shape[0])
        expected = day_rate.sum(axis=0)
        variance = np.maximum((day_rate * (1.0 - day_rate)).sum(axis=0), 1e-9)

        p_value = _tail_probability(successes, expected, variance, day_rate)

        out = survivors.copy()
        out["trials_replication"] = int(trials)
        out["successes_replication"] = successes.astype(int)
        out["precision_replication"] = successes / trials
        out["expected_rate_replication"] = expected / trials
        out["skill_replication"] = (successes - expected) / trials
        out["p_value_replication"] = np.asarray(p_value, dtype=float)
        return out
