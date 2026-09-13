"""Kết quả cổng tái lập phải đi được tới tận đầu ra dự đoán.

Một cổng chạy đúng nhưng không ai nhìn thấy kết quả thì không đổi được gì. Tệp
này khoá đường đi của con số:

    run_bridge_scan  ->  bridge_scan_summary.json  ->  bằng chứng của dự đoán

và đòi mẫu số luôn đi kèm: "3 đường tái lập" mà không nói đã quét bao nhiêu
giả thuyết là cách trình bày sai lệch nhất có thể ở đây.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import run_bridge_scan
from run_daily_prediction import _research_evidence
from xsmb_domain import FIELD_WIDTHS


def _tiny_raw(days: int = 400, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for offset in range(days):
        row: dict[str, object] = {
            "date": pd.Timestamp("2021-01-01") + pd.Timedelta(days=offset)
        }
        for field, width in FIELD_WIDTHS:
            row[field] = int(rng.integers(0, 10**width))
        rows.append(row)
    return pd.DataFrame(rows)


def test_the_scan_summary_carries_the_replication_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chạy thật bộ quét thu hẹp và đòi khối tái lập có mặt, đủ trường."""
    monkeypatch.setattr(run_bridge_scan, "TARGET_TYPES", ("de",))
    raw = tmp_path / "xsmb.csv"
    _tiny_raw().to_csv(raw, index=False)

    summary = run_bridge_scan.run(
        raw, tmp_path / "out", max_span=1, q_value=0.05, permutations=2
    )

    assert "holdout_fraction" in summary
    block = summary["modes"]["de"]["replication"]
    for key in (
        "conclusive", "discovered_on_discovery_half", "replicated",
        "discovery_days", "replication_days", "split_date", "verdict",
    ):
        assert key in block, key
    assert block["conclusive"] is True
    assert block["discovery_days"] + block["replication_days"] <= 400
    assert block["replicated"] <= block["discovered_on_discovery_half"]

    # Mẫu số phải đi cùng: số giả thuyết đã quét nằm ngay cạnh.
    assert summary["modes"]["de"]["hypotheses"] > 0

    written = json.loads(
        (tmp_path / "out" / "bridge_scan_summary.json").read_text(encoding="utf-8")
    )
    assert written["modes"]["de"]["replication"]["conclusive"] is True


def test_noise_produces_no_replicated_bridge_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Không có gì tái lập thì KHÔNG được ghi tệp — tệp rỗng trông như dữ liệu."""
    monkeypatch.setattr(run_bridge_scan, "TARGET_TYPES", ("de",))
    raw = tmp_path / "xsmb.csv"
    _tiny_raw().to_csv(raw, index=False)

    summary = run_bridge_scan.run(
        raw, tmp_path / "out", max_span=1, q_value=0.05, permutations=2
    )
    assert summary["modes"]["de"]["replication"]["replicated"] == 0
    assert not (tmp_path / "out" / "bridge_replicated_de.csv").exists()


def test_prediction_evidence_surfaces_replication_with_its_denominator(
    tmp_path: Path,
) -> None:
    """Bằng chứng kèm dự đoán phải mang cả con số tái lập lẫn mẫu số của nó."""
    research = tmp_path / "research"
    research.mkdir()
    (research / "bridge_scan_summary.json").write_text(
        json.dumps({
            "modes": {
                "loto": {
                    "hypotheses": 412164,
                    "running_at_least_5_unscreened": 104000,
                    "survived_fdr": 7,
                    "replication": {"conclusive": True, "replicated": 0},
                }
            }
        }),
        encoding="utf-8",
    )

    evidence = _research_evidence(research)["bridge_scan"]["loto"]
    assert evidence["hypotheses"] == 412164
    assert evidence["survived_fdr"] == 7
    assert evidence["replicated_out_of_sample"] == 0
    assert evidence["replication_conclusive"] is True


def test_prediction_evidence_survives_an_older_summary_without_replication(
    tmp_path: Path,
) -> None:
    """Bản tóm tắt cũ chưa có khối tái lập không được làm đổ quy trình.

    Tệp này do một bộ quét chạy TAY sinh ra, nên bản cũ vẫn nằm trong kho một
    thời gian sau khi mã đổi. Đọc nó phải ra `None`, không phải KeyError.
    """
    research = tmp_path / "research"
    research.mkdir()
    (research / "bridge_scan_summary.json").write_text(
        json.dumps({
            "modes": {"loto": {"hypotheses": 1000, "survived_fdr": 0}}
        }),
        encoding="utf-8",
    )
    evidence = _research_evidence(research)["bridge_scan"]["loto"]
    assert evidence["replicated_out_of_sample"] is None
    assert evidence["replication_conclusive"] is None
