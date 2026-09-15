"""Cổng TÁI LẬP: bắt một đường cầu chứng minh lại mình trên dữ liệu chưa từng thấy.

Vì sao cần lớp này khi đã có firewall
=====================================
``FirewallGate`` chạy BH-FDR trên toàn họ rồi kiểm chống data snooping bằng
max-statistic circular shift. Cả hai đều đúng và đều cần thiết. Nhưng cả hai
đánh giá đường cầu trên CHÍNH đoạn dữ liệu đã dùng để chọn nó.

Đó là kẽ hở cuối cùng, và nó không phải giả định — kho đã đo được nó:
``data/research/randomness_report.json`` cho thấy tín hiệu duy nhất sống sót
Bonferroni có nửa đầu z = −0,40 và nửa sau z = −2,50, tức ``replicates = False``.
Một phát hiện qua được mọi cổng thống kê vẫn có thể không tái lặp.

Cách chữa duy nhất là tách bạch theo thời gian:

    ngày 0 ─────── PHÁT HIỆN ───────┊─────── KIỂM CHỨNG ─────── ngày N
                                    ┊
              quét + BH-FDR +       ┊   chỉ đánh giá các đường
              kiểm data snooping    ┊   đã sống sót, KHÔNG chọn lại
                                    ┊
    Đoạn kiểm chứng chưa từng tham gia vào việc CHỌN, nên kết quả trên nó là
    ngoài mẫu thật, không phải ngoài mẫu trên danh nghĩa.

Lưu ý về độ trễ: để đánh giá ngày ``t`` trong đoạn kiểm chứng, đường cầu đọc
các ngày ``t - lag``, có thể rơi vào đoạn phát hiện. Đó KHÔNG phải rò rỉ — tại
thời điểm dự đoán ngày ``t``, mọi ngày trước ``t`` đều đã biết. Rò rỉ là dùng
kết quả TƯƠNG LAI, không phải dùng quá khứ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from bridges.firewall import FirewallGate, SurvivorSet
from bridges.scanner import BridgeScanner, _tail_probability, baseline_rate_table
from bridges.tensor import DigitTensor
from research_diagnostics import bh_fdr

#: Các cột nhận diện duy nhất một giả thuyết trong họ cầu ghép chéo.
IDENTITY_COLUMNS: Final[tuple[str, ...]] = (
    "position_a", "position_b", "lag_a", "lag_b", "shadow", "transformation",
)

DEFAULT_HOLDOUT_FRACTION: Final[float] = 0.40
DEFAULT_ALPHA: Final[float] = 0.05
#: Dưới ngưỡng này thì đoạn kiểm chứng quá ngắn để kết luận bất cứ điều gì, và
#: một cổng không kết luận được phải nói thế chứ không được cho qua.
MIN_REPLICATION_DAYS: Final[int] = 120


@dataclass(frozen=True)
class ReplicationVerdict:
    """Kết quả của cổng tái lập, kể cả khi không đường nào sống sót.

    Giống ``SurvivorSet``, mọi mẫu số đều được mang theo: báo "3 đường tái lập"
    mà không nói đã có bao nhiêu đường bước vào là cách trình bày sai lệch.
    """

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
    """Cắt một lát ngày liên tục, giữ nguyên mọi bất biến của tensor."""
    if not 0 <= start < stop <= tensor.n_days:
        raise ValueError(f"lát [{start}, {stop}) không hợp lệ với {tensor.n_days} kỳ")
    return DigitTensor(
        values=tensor.values[start:stop],
        dates=tensor.dates[start:stop],
        # Nhãn vị trí KHÔNG cắt theo ngày: chúng mô tả trục cột, không phải
        # trục thời gian. Cắt nhầm chúng sẽ làm vỡ bất biến của tensor.
        position_labels=tensor.position_labels,
        loto_counts=tensor.loto_counts[start:stop],
        de_index=tensor.de_index[start:stop],
    )


class ReplicationGate:
    """Chọn trên đoạn đầu, kiểm chứng trên đoạn sau — không bao giờ ngược lại."""

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
        """Quét đoạn phát hiện, rồi kiểm các đường sống sót trên đoạn giữ riêng."""
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
        # Đoạn kiểm chứng mang theo ``warmup`` kỳ tiền tố để các độ trễ có dữ
        # liệu; ``rebuild_hits`` bỏ đúng ngần ấy kỳ đầu nên phần được CHẤM ĐIỂM
        # bắt đầu chính xác tại mốc cắt.
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
        # Tập đã sống sót là nhỏ và ĐƯỢC ĐĂNG KÝ TRƯỚC khi chạm đoạn kiểm chứng,
        # nên hiệu chỉnh đa kiểm định ở đây chạy trên đúng số đường ấy, không
        # phải trên 412 nghìn giả thuyết ban đầu.
        scored["q_value_replication"] = bh_fdr(scored["p_value_replication"].to_numpy(dtype=float))
        # Điều kiện kỹ năng dương là DƯ THỪA với phép kiểm hiện tại và điều đó
        # đã được kiểm ngược: ``_tail_probability`` là đuôi MỘT PHÍA phía trên,
        # nên q nhỏ đã hàm ý số lần trúng vượt kỳ vọng. Đột biến gỡ dòng ấy
        # không làm phép kiểm nào đỏ.
        #
        # Vẫn giữ, vì nó là chốt duy nhất còn lại nếu ai đó đổi hàm đuôi sang
        # hai phía — khi ấy một đường cầu TỆ BẤT THƯỜNG cũng sẽ có q nhỏ và sẽ
        # được phát ra như một "phát hiện". Ghi rõ ở đây rằng phép kiểm không
        # tách được dòng này, để không ai tưởng nó đã được khoá.
        replicated = scored[
            (scored["q_value_replication"] <= self.alpha)
            & (scored["precision_replication"] > scored["expected_rate_replication"])
        ].copy()
        replicated.sort_values(["q_value_replication", "p_value_replication"], inplace=True)

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
        """Chấm điểm các đường đã chọn trên đoạn giữ riêng, không chọn lại gì."""
        rebuilt, target = scanner.rebuild_hits(replication, survivors, target_type=target_type)
        hits = rebuilt.hits_for(target, target_type)

        rate_table = baseline_rate_table(target_type)
        day_rate = rate_table[rebuilt.sizes]
        successes = hits.sum(axis=0).astype(float)
        trials = float(hits.shape[0])
        expected = day_rate.sum(axis=0)
        variance = np.maximum((day_rate * (1.0 - day_rate)).sum(axis=0), 1e-9)

        # DÙNG LẠI hàm đuôi của bộ quét, không viết lại.
        #
        # Bản đầu tôi viết ở đây chỉ dùng xấp xỉ chuẩn. Với LOTO (tỉ lệ nền
        # 0,24) thì đúng, nhưng với ĐỀ (tỉ lệ nền ~0,01) đó là vùng biến cố
        # hiếm, nơi xấp xỉ chuẩn thổi phồng đuôi và biến dao động thường thành
        # "tái lập". Hàm gốc tự chuyển sang Poisson đúng ở chế độ ấy — và một
        # cổng gác cổng mà lại dễ dãi hơn bộ quét nó gác thì vô nghĩa.
        p_value = _tail_probability(successes, expected, variance, day_rate)

        out = survivors.copy()
        out["trials_replication"] = int(trials)
        out["successes_replication"] = successes.astype(int)
        out["precision_replication"] = successes / trials
        out["expected_rate_replication"] = expected / trials
        out["skill_replication"] = (successes - expected) / trials
        out["p_value_replication"] = np.asarray(p_value, dtype=float)
        return out
