"""Phát hiện trôi lệch khái niệm trên chuỗi sai số dự đoán.

Bài toán
---------

Một đường cầu "gãy" không báo trước. Nếu hệ thống chỉ nhìn tỉ lệ trúng trung
bình toàn lịch sử thì phải rất lâu sau mới thấy, vì hàng trăm quan sát cũ pha
loãng vài chục quan sát mới. Phát hiện trôi lệch trả lời câu hỏi hẹp hơn và trả
lời nhanh hơn: *phân phối sai số gần đây có khác phân phối trước đó không?*

Hai phương pháp, hai vai trò
-----------------------------

**ADWIN** (Adaptive Windowing) giữ một cửa sổ các quan sát gần nhất và xét mọi
cách cắt đôi cửa sổ đó. Nếu tồn tại một điểm cắt mà trung bình hai nửa lệch
nhau quá chặn Hoeffding, ADWIN kết luận có trôi lệch và **vứt bỏ nửa cũ**. Ưu
điểm quyết định: kích thước cửa sổ tự điều chỉnh, không có tham số "dùng bao
nhiêu ngày" nào phải chọn tay — và tham số đó chính là thứ dễ bị chỉnh cho tới
khi ra kết quả mong muốn.

**Kiểm định Kolmogorov–Smirnov** so toàn bộ *hình dạng* phân phối chứ không chỉ
trung bình. Cần cả hai vì chúng bắt hai kiểu trôi khác nhau: một mô hình có thể
giữ nguyên sai số trung bình trong khi phương sai bung ra — ADWIN không thấy,
KS thấy.

Cảnh báo về giá trị p của KS trên chuỗi thời gian
--------------------------------------------------

Kiểm định KS giả định các quan sát độc lập. Sai số dự đoán theo ngày thường tự
tương quan, nên giá trị p danh nghĩa sẽ **lạc quan quá mức** — nó báo có trôi
lệch thường xuyên hơn thực tế. Vì vậy ngưỡng mặc định ở đây đặt chặt hơn thông
lệ (0.01 thay vì 0.05), và lớp này trả về cả thống kê lẫn giá trị p để người
gọi tự quyết định thay vì chỉ nhận một chữ "có/không".
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import numpy as np
from scipy import stats

from ml_engine.capabilities import CAPABILITIES

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

DriftMethod = Literal["adwin", "ks", "both"]


@dataclass(frozen=True)
class DriftVerdict:
    """Kết luận của một lần kiểm tra trôi lệch.

    Attributes:
        drifted: Có kết luận trôi lệch hay không.
        method: Phương pháp đã phát hiện ra, hoặc ``"none"``.
        statistic: Thống kê kiểm định (KS) hoặc chênh lệch trung bình (ADWIN).
        p_value: Giá trị p nếu phương pháp có, ngược lại ``None``.
        window_size: Kích thước cửa sổ ADWIN sau khi xử lý.
        detail: Thông tin bổ sung để ghi nhật ký.
    """

    drifted: bool
    method: str
    statistic: float
    p_value: float | None
    window_size: int
    detail: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        """Câu mô tả ngắn để ghi nhật ký."""
        if not self.drifted:
            return f"không trôi lệch (cửa sổ {self.window_size})"
        p_text = "" if self.p_value is None else f", p={self.p_value:.4g}"
        return f"TRÔI LỆCH qua {self.method} (thống kê={self.statistic:.4g}{p_text})"


class _PureAdwin:
    """Cài đặt ADWIN gọn bằng NumPy, dùng khi không có ``river``.

    Giữ nguyên ý tưởng gốc: xét mọi điểm cắt và so chênh lệch trung bình hai nửa
    với chặn Hoeffding có hiệu chỉnh đa kiểm định theo số điểm cắt.

    Điểm cắt lấy trên lưới cấp số nhân chứ không phải mọi vị trí, đúng theo tinh
    thần cấu trúc "bucket" của ADWIN2. Đây không phải tối ưu tốc độ mà là vấn đề
    **công suất thống kê**: xét cả ``n`` điểm cắt buộc phải hiệu chỉnh đa kiểm
    định theo ``δ/n``, làm chặn rộng đến mức bản đầu tiên của lớp này chậm hơn
    ADWIN của ``river`` khoảng 190 quan sát trên cùng một dữ liệu. Lưới cấp số
    nhân chỉ xét ``O(log n)`` điểm cắt, nên hiệu chỉnh nhẹ hơn nhiều trong khi
    vẫn phủ mọi thang thời gian — một điểm đổi chế độ luôn nằm gần một điểm cắt
    trong lưới, sai khác nhiều nhất là hệ số hai.
    """

    def __init__(self, delta: float = 0.002, max_window: int = 512) -> None:
        if not 0.0 < delta < 1.0:
            raise ValueError("delta phải nằm trong (0, 1)")
        self.delta = float(delta)
        self.window: deque[float] = deque(maxlen=int(max_window))
        self.drift_detected = False
        self.last_difference = 0.0

    @staticmethod
    def _candidate_cuts(n: int) -> np.ndarray:
        """Điểm cắt trên lưới cấp số nhân, tính từ cả hai đầu cửa sổ.

        Lấy từ hai đầu vì một điểm đổi chế độ có thể nằm sát đầu cửa sổ (đã cũ)
        hoặc sát cuối (vừa xảy ra), và lưới một phía sẽ thưa đúng ở phía kia.

        Args:
            n: Kích thước cửa sổ hiện tại.

        Returns:
            Mảng điểm cắt tăng dần, mỗi điểm trong ``[1, n)``.
        """
        offsets = 2 ** np.arange(int(np.log2(max(n - 1, 1))) + 1)
        cuts = np.unique(np.concatenate([offsets, n - offsets, [n // 2]]))
        return cuts[(cuts >= 1) & (cuts < n)]

    def _bound(self, n0: int, n1: int, variance: float, *, n_cuts: int) -> float:
        """Chặn Hoeffding có hiệu chỉnh cho số điểm cắt thực sự đã xét.

        Args:
            n0: Cỡ nửa cũ.
            n1: Cỡ nửa mới.
            variance: Phương sai của toàn cửa sổ.
            n_cuts: Số điểm cắt được xét ở lần này — đây là số giả thuyết cần
                hiệu chỉnh, không phải kích thước cửa sổ.

        Returns:
            Ngưỡng chênh lệch trung bình để kết luận trôi lệch.
        """
        m = 1.0 / (1.0 / max(n0, 1) + 1.0 / max(n1, 1))
        delta_prime = self.delta / max(n_cuts, 1)
        log_term = np.log(2.0 / delta_prime)
        return float(np.sqrt(2.0 / m * variance * log_term) + 2.0 / (3.0 * m) * log_term)

    def update(self, value: float) -> bool:
        """Thêm một quan sát và kiểm tra trôi lệch.

        Args:
            value: Quan sát mới (sai số, hoặc 0/1 trúng-trượt).

        Returns:
            ``True`` nếu phát hiện trôi lệch ở lần thêm này.
        """
        self.window.append(float(value))
        self.drift_detected = False
        n = len(self.window)
        if n < 16:
            return False

        values = np.fromiter(self.window, dtype=float, count=n)
        variance = float(values.var())
        prefix = np.cumsum(values)
        total = prefix[-1]

        cuts = self._candidate_cuts(n)
        left_n, right_n = cuts, n - cuts
        left_mean = prefix[cuts - 1] / left_n
        right_mean = (total - prefix[cuts - 1]) / right_n
        differences = np.abs(left_mean - right_mean)
        bounds = np.array(
            [
                self._bound(int(a), int(b), variance, n_cuts=cuts.size)
                for a, b in zip(left_n, right_n, strict=True)
            ]
        )

        exceeded = np.flatnonzero(differences > bounds)
        if exceeded.size == 0:
            self.last_difference = float(differences.max()) if differences.size else 0.0
            return False

        cut = int(cuts[exceeded[np.argmax(differences[exceeded])]])
        self.last_difference = float(differences[exceeded].max())
        # Vứt nửa cũ: đó là toàn bộ ý nghĩa của "adaptive windowing".
        for _ in range(cut):
            self.window.popleft()
        self.drift_detected = True
        return True


class ConceptDriftDetector:
    """Theo dõi chuỗi sai số và báo khi phân phối đổi.

    Ví dụ:
        >>> detector = ConceptDriftDetector(method="adwin")
        >>> for _ in range(60):
        ...     _ = detector.update(0.0)
        >>> verdict = None
        >>> for _ in range(60):
        ...     verdict = detector.update(1.0)
        >>> verdict.drifted
        True

    Attributes:
        method: ``"adwin"``, ``"ks"`` hoặc ``"both"``.
        delta: Mức tin cậy của ADWIN; nhỏ hơn nghĩa là thận trọng hơn.
        ks_alpha: Ngưỡng giá trị p cho kiểm định KS.
        reference_size: Số quan sát giữ làm phân phối tham chiếu.
        recent_size: Số quan sát gần nhất đem so với tham chiếu.
    """

    def __init__(
        self,
        *,
        method: DriftMethod = "both",
        delta: float = 0.002,
        ks_alpha: float = 0.01,
        reference_size: int = 90,
        recent_size: int = 30,
        prefer_river: bool = True,
    ) -> None:
        if method not in ("adwin", "ks", "both"):
            raise ValueError(f"method không hỗ trợ: {method}")
        if recent_size < 8 or reference_size < 8:
            raise ValueError("cửa sổ tham chiếu và cửa sổ gần đây phải có ít nhất 8 quan sát")
        if not 0.0 < ks_alpha < 1.0:
            raise ValueError("ks_alpha phải nằm trong (0, 1)")

        self.method = method
        self.delta = delta
        self.ks_alpha = ks_alpha
        self.reference_size = int(reference_size)
        self.recent_size = int(recent_size)

        river = CAPABILITIES.river if prefer_river else None
        if river is not None:
            try:
                self._adwin: Any = river.drift.ADWIN(delta=delta)
                self.backend = "river"
            except Exception as error:  # pragma: no cover - phụ thuộc phiên bản
                LOGGER.warning("Không dùng được ADWIN của river (%s); dùng bản tự cài", error)
                self._adwin = _PureAdwin(delta=delta)
                self.backend = "pure"
        else:
            self._adwin = _PureAdwin(delta=delta)
            self.backend = "pure"

        self._history: deque[float] = deque(maxlen=self.reference_size + self.recent_size)
        self.drift_count = 0

    # -- Nội bộ ----------------------------------------------------------

    def _adwin_update(self, value: float) -> tuple[bool, float, int]:
        """Đẩy một quan sát vào ADWIN, che khác biệt giữa hai bản cài."""
        if self.backend == "river":
            self._adwin.update(value)
            return (
                bool(self._adwin.drift_detected),
                float(getattr(self._adwin, "estimation", 0.0)),
                int(getattr(self._adwin, "width", 0)),
            )
        drifted = self._adwin.update(value)
        return drifted, self._adwin.last_difference, len(self._adwin.window)

    def _ks_check(self) -> tuple[bool, float, float | None]:
        """So phân phối tham chiếu với phân phối gần đây bằng kiểm định KS."""
        if len(self._history) < self.reference_size + self.recent_size:
            return False, 0.0, None
        values = np.fromiter(self._history, dtype=float, count=len(self._history))
        reference, recent = values[: -self.recent_size], values[-self.recent_size :]
        if np.allclose(reference, reference[0]) and np.allclose(recent, recent[0]):
            # Hai chuỗi hằng: KS không xác định. Coi là trôi lệch khi hai hằng
            # số khác nhau, và không trôi khi bằng nhau.
            return not np.isclose(reference[0], recent[0]), 0.0, None
        result = stats.ks_2samp(reference, recent)
        return bool(result.pvalue < self.ks_alpha), float(result.statistic), float(result.pvalue)

    # -- API công khai ---------------------------------------------------

    def update(self, error_value: float) -> DriftVerdict:
        """Nạp một quan sát sai số và trả kết luận trôi lệch.

        Args:
            error_value: Sai số của ngày (ví dụ ``1 - trúng``), hoặc bất kỳ đại
                lượng nào mà việc phân phối của nó đổi là điều đáng biết.

        Returns:
            Kết luận cho lần cập nhật này.

        Raises:
            ValueError: Khi giá trị không hữu hạn.
        """
        value = float(error_value)
        if not np.isfinite(value):
            raise ValueError(f"error_value phải hữu hạn, nhận {error_value!r}")
        self._history.append(value)

        adwin_drift, adwin_statistic, width = False, 0.0, len(self._history)
        if self.method in ("adwin", "both"):
            adwin_drift, adwin_statistic, width = self._adwin_update(value)

        ks_drift, ks_statistic, ks_p = False, 0.0, None
        if self.method in ("ks", "both"):
            ks_drift, ks_statistic, ks_p = self._ks_check()

        if adwin_drift:
            self.drift_count += 1
            return DriftVerdict(
                drifted=True,
                method=f"adwin/{self.backend}",
                statistic=adwin_statistic,
                p_value=None,
                window_size=width,
                detail={"ks_statistic": ks_statistic, "ks_p_value": ks_p},
            )
        if ks_drift:
            self.drift_count += 1
            return DriftVerdict(
                drifted=True,
                method="ks",
                statistic=ks_statistic,
                p_value=ks_p,
                window_size=width,
                detail={"reference": self.reference_size, "recent": self.recent_size},
            )
        return DriftVerdict(
            drifted=False,
            method="none",
            statistic=ks_statistic,
            p_value=ks_p,
            window_size=width,
        )

    def update_many(self, values: list[float] | np.ndarray) -> list[DriftVerdict]:
        """Nạp một dãy quan sát theo thứ tự thời gian.

        Args:
            values: Dãy sai số, sắp theo thời gian tăng dần.

        Returns:
            Danh sách kết luận, mỗi quan sát một kết luận.
        """
        return [self.update(float(value)) for value in np.asarray(values, dtype=float)]

    def reset(self) -> None:
        """Xóa toàn bộ trạng thái, dùng sau khi đã tái hiệu chỉnh mô hình."""
        if self.backend == "river" and CAPABILITIES.river is not None:
            self._adwin = CAPABILITIES.river.drift.ADWIN(delta=self.delta)
        else:
            self._adwin = _PureAdwin(delta=self.delta)
        self._history.clear()
