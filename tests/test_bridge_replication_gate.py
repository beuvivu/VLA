"""Cổng tái lập phải loại được đường cầu chỉ đúng ở quá khứ.

``FirewallGate`` đã chạy BH-FDR trên toàn họ và kiểm chống data snooping. Cả
hai đều cần, nhưng cả hai chấm điểm đường cầu trên CHÍNH đoạn dữ liệu đã dùng
để chọn nó. Kẽ hở ấy không phải giả định — kho đã đo được:
``randomness_report.json`` cho thấy tín hiệu duy nhất sống sót Bonferroni có
nửa đầu z = −0,40, nửa sau z = −2,50, ``replicates = False``.

Không đường cầu nào trong dữ liệu THẬT sống sót nổi đoạn phát hiện, nên đường
tái lập không thể kiểm bằng dữ liệu thật. Các phép kiểm ở đây cài tín hiệu vào
dữ liệu tổng hợp — và phép kiểm quan trọng nhất cài tín hiệu CHỈ Ở NỬA ĐẦU,
đúng thứ mà cổng này sinh ra để bắt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bridges.firewall import FirewallGate
from bridges.replication import (
    MIN_REPLICATION_DAYS,
    ReplicationGate,
    slice_tensor,
)
from bridges.scanner import BridgeScanner
from bridges.tensor import DigitTensor
from xsmb_domain import FIELD_WIDTHS

#: Bộ quét thu hẹp: một độ trễ, một loại bóng, một phép biến đổi. 11 449 giả
#: thuyết thay vì 412 164 — đủ để cổng chạy thật mà phép kiểm không mất phút.
def _scanner() -> BridgeScanner:
    return BridgeScanner(max_span=1, shadows=("thuc",), transformations=("concat",))


def _raw_frame(specials: list[int], rng: np.random.Generator) -> pd.DataFrame:
    """Bảng kết quả thô với dãy giải Đặc Biệt cho trước, các giải khác ngẫu nhiên."""
    rows = []
    for offset, special in enumerate(specials):
        row: dict[str, object] = {
            "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=offset)
        }
        for field, width in FIELD_WIDTHS:
            row[field] = (
                int(special) if field == "special"
                else int(rng.integers(0, 10**width))
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _planted_specials(n: int, rng: np.random.Generator, *, plant_until: int) -> list[int]:
    """Dãy Đặc Biệt mà hai số cuối sao chép hai số ĐẦU của kỳ trước.

    Đường cầu (vị trí 0, vị trí 1, độ trễ 1, bóng thực, ghép) vì thế trúng
    100 % ở mọi kỳ được cài, và 1 % ở các kỳ còn lại.

    ``plant_until`` cho phép cài tín hiệu chỉ ở phần đầu lịch sử — đó là ca
    dựng riêng để bắt cổng làm việc.
    """
    specials = [int(rng.integers(10_000, 100_000))]
    for t in range(1, n):
        previous = specials[-1]
        head = previous // 1000  # hai chữ số đầu của số năm chữ số
        if t < plant_until:
            specials.append(int(rng.integers(0, 1000)) * 100 + head)
        else:
            specials.append(int(rng.integers(10_000, 100_000)))
    return specials


def _tensor(n: int, *, plant_until: int, seed: int = 7) -> DigitTensor:
    rng = np.random.default_rng(seed)
    return DigitTensor.from_raw(_raw_frame(_planted_specials(n, rng, plant_until=plant_until), rng))


def _gate(**kwargs) -> ReplicationGate:
    # permutations=2 chỉ để phép kiểm data snooping chạy được đường mã; giá trị
    # thống kê của nó không phải thứ tệp này kiểm.
    kwargs.setdefault("firewall", FirewallGate(permutations=2))
    return ReplicationGate(**kwargs)


# --- Ca quyết định ---------------------------------------------------------


def test_a_signal_that_dies_after_the_split_is_rejected() -> None:
    """Đây là lý do cổng tồn tại.

    Tín hiệu được cài CHỈ ở nửa đầu. Đoạn phát hiện nhìn thấy một đường cầu
    hoàn hảo và mọi cổng thống kê trước đó đều cho qua — vì trên đoạn ấy nó
    ĐÚNG là hoàn hảo. Chỉ đoạn kiểm chứng, vốn chưa từng tham gia vào việc
    chọn, mới phát hiện ra nó đã chết.
    """
    n = 500
    tensor = _tensor(n, plant_until=int(n * 0.60))
    gate = _gate(holdout_fraction=0.40)
    verdict, found = gate.screen(tensor, _scanner(), target_type="de")

    assert verdict.conclusive
    assert found.survived > 0, "đoạn phát hiện phải thấy đường cầu đã cài"
    assert verdict.discovered > 0
    assert verdict.replicated == 0, (
        f"{verdict.replicated} đường tái lập, lẽ ra 0 — tín hiệu đã chết tại mốc cắt"
    )
    assert "KHÔNG đường nào tái lập" in verdict.describe()


def test_a_signal_present_throughout_does_replicate() -> None:
    """Cổng phải để tín hiệu THẬT đi qua, nếu không nó chỉ là cái chặn mù.

    Một cổng loại sạch mọi thứ thì "an toàn" một cách vô dụng. Ca này chứng
    minh nó phân biệt được, chứ không phải từ chối tất cả.
    """
    n = 500
    tensor = _tensor(n, plant_until=n)
    verdict, found = _gate(holdout_fraction=0.40).screen(tensor, _scanner(), target_type="de")

    assert verdict.conclusive
    assert found.survived > 0
    assert verdict.replicated > 0, "tín hiệu có mặt ở cả hai đoạn phải tái lập được"

    # Siết sang MỌI dòng, không chỉ dòng đầu: bất biến cần khoá là "không
    # đường nào được phát ra với kỹ năng âm", và một phép kiểm chỉ nhìn dòng
    # tốt nhất không nói được điều đó.
    assert (verdict.bridges["skill_replication"] > 0.0).all()
    assert (
        verdict.bridges["precision_replication"]
        > verdict.bridges["expected_rate_replication"]
    ).all()
    assert (verdict.bridges["q_value_replication"] <= verdict.alpha).all()


def test_pure_noise_yields_no_replicated_bridge() -> None:
    """Không cài gì thì không được phát ra gì."""
    n = 500
    rng = np.random.default_rng(11)
    specials = [int(rng.integers(10_000, 100_000)) for _ in range(n)]
    tensor = DigitTensor.from_raw(_raw_frame(specials, rng))

    verdict, _found = _gate(holdout_fraction=0.40).screen(tensor, _scanner(), target_type="de")
    assert verdict.conclusive
    assert verdict.replicated == 0


# --- Chống rò rỉ -----------------------------------------------------------


def test_the_holdout_half_never_influences_selection() -> None:
    """Thay TRỌN đoạn kiểm chứng không được làm đổi tập đường được chọn.

    Nếu việc chọn có nhìn trộm đoạn giữ riêng dù chỉ một chút, đổi đoạn ấy sẽ
    đổi tập sống sót. Đây là phép kiểm cấu trúc: nó chứng minh sự tách bạch,
    thay vì tin rằng mã có tách bạch.
    """
    n = 500
    base = _tensor(n, plant_until=n, seed=3)
    gate = _gate(holdout_fraction=0.40)
    split = gate.split_index(base)

    rng = np.random.default_rng(99)
    mutated_values = base.values.copy()
    mutated_values[split:] = rng.integers(0, 10, size=mutated_values[split:].shape, dtype=np.uint8)
    mutated_de = base.de_index.copy()
    mutated_de[split:] = rng.integers(0, 100, size=mutated_de[split:].shape).astype(np.int16)
    mutated_counts = base.loto_counts.copy()
    mutated_counts[split:] = 0
    mutated = DigitTensor(
        values=mutated_values,
        dates=base.dates,
        position_labels=base.position_labels,
        loto_counts=mutated_counts,
        de_index=mutated_de,
    )

    _v1, found_base = gate.screen(base, _scanner(), target_type="de")
    _v2, found_mut = gate.screen(mutated, _scanner(), target_type="de")

    columns = ["position_a", "position_b", "lag_a", "lag_b", "shadow", "transformation"]
    left = found_base.bridges[columns].sort_values(columns).reset_index(drop=True)
    right = found_mut.bridges[columns].sort_values(columns).reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


# --- Từ chối kết luận khi không đủ dữ liệu ---------------------------------


def test_a_short_holdout_is_reported_inconclusive_not_passed() -> None:
    """Đoạn kiểm chứng quá ngắn phải nói "không kết luận được", không phải "đạt".

    Một cổng im lặng cho qua khi thiếu dữ liệu còn tệ hơn không có cổng: nó
    tạo cảm giác đã kiểm trong khi chưa kiểm gì.
    """
    n = MIN_REPLICATION_DAYS + 40
    tensor = _tensor(n, plant_until=n)
    verdict, _found = _gate(holdout_fraction=0.10).screen(tensor, _scanner(), target_type="de")

    assert verdict.conclusive is False
    assert verdict.replicated == 0
    assert "KHÔNG kết luận được" in verdict.describe()


# --- Cắt lát tensor --------------------------------------------------------


def test_slicing_keeps_the_column_axis_intact() -> None:
    """Nhãn vị trí mô tả trục CỘT, không phải trục thời gian.

    Bản đầu tôi viết cắt cả nhãn vị trí theo ngày và làm vỡ bất biến của
    tensor ngay lần chạy thật đầu tiên.
    """
    tensor = _tensor(300, plant_until=300)
    piece = slice_tensor(tensor, 50, 200)

    assert piece.n_days == 150
    assert piece.position_labels == tensor.position_labels
    assert piece.n_positions == tensor.n_positions
    assert list(piece.dates) == list(tensor.dates[50:200])


@pytest.mark.parametrize("bounds", [(-1, 10), (10, 10), (0, 10_000)])
def test_an_invalid_slice_is_refused(bounds: tuple[int, int]) -> None:
    tensor = _tensor(300, plant_until=300)
    with pytest.raises(ValueError, match="không hợp lệ"):
        slice_tensor(tensor, *bounds)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [({"holdout_fraction": 0.95}, "holdout_fraction"), ({"alpha": 0.0}, "alpha")],
)
def test_invalid_configuration_is_refused(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        ReplicationGate(**kwargs)
