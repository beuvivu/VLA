from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prob_eval_history import evaluate_latest_emitted


def _history(day: str, *, mode: str) -> pd.DataFrame:
    y = np.zeros(100, dtype=int)
    if mode == "de":
        y[17] = 1
    else:
        y[[1, 3, 8, 17, 42]] = 1
    return pd.DataFrame(
        {
            "target_date": [day] * 100,
            "number": np.arange(100),
            "y": y,
            # Deliberately include components that would have allowed the old
            # 40/30/30 reconstruction. The evaluator must ignore them.
            "p_ml": np.full(100, 0.2),
            "p_active": np.full(100, 0.2),
            "p_stable": np.full(100, 0.2),
        }
    )


def _prediction(day: str, *, mode: str) -> pd.DataFrame:
    if mode == "de":
        p = np.full(100, 0.005)
        p[17] = 0.505
        p = p / p.sum()
    else:
        p = np.full(100, 0.20)
        p[[1, 3, 8, 17, 42]] = 0.30
    return pd.DataFrame(
        {
            "target_date": [day] * 100,
            "number": np.arange(100),
            "prob": p,
        }
    )


def test_missing_exact_artifact_never_reconstructs_from_components(tmp_path: Path) -> None:
    day = "2026-08-31"
    history_path = tmp_path / "pred_loto.csv"
    _history(day, mode="loto").to_csv(history_path, index=False)
    result = evaluate_latest_emitted(
        mode="loto",
        history_path=history_path,
        predict_dir=tmp_path / "predict",
    )
    assert result is None


def test_exact_emitted_artifact_is_evaluated(tmp_path: Path) -> None:
    day = "2026-08-31"
    history_path = tmp_path / "pred_de.csv"
    predict_dir = tmp_path / "predict"
    predict_dir.mkdir()
    _history(day, mode="de").to_csv(history_path, index=False)
    _prediction(day, mode="de").to_csv(
        predict_dir / f"predict_next_de_all_{day}.csv", index=False
    )

    result = evaluate_latest_emitted(
        mode="de",
        history_path=history_path,
        predict_dir=predict_dir,
    )
    assert result is not None
    assert result["target_date"] == day
    assert result["evaluation_source"] == "exact_emitted_prediction_artifact"
    assert float(result["logloss"]) >= 0.0
    assert float(result["brier"]) >= 0.0


def test_stale_internal_target_date_invalidates_artifact(tmp_path: Path) -> None:
    day = "2026-08-31"
    history_path = tmp_path / "pred_loto.csv"
    predict_dir = tmp_path / "predict"
    predict_dir.mkdir()
    _history(day, mode="loto").to_csv(history_path, index=False)
    pred = _prediction("2026-08-30", mode="loto")
    pred.to_csv(predict_dir / f"predict_next_loto_all_{day}.csv", index=False)

    result = evaluate_latest_emitted(
        mode="loto",
        history_path=history_path,
        predict_dir=predict_dir,
    )
    assert result is None


def _emit(tmp_path: Path, day: str, mode: str) -> None:
    history_dir = tmp_path / "history"
    predict_dir = tmp_path / "predict"
    history_dir.mkdir(exist_ok=True)
    predict_dir.mkdir(exist_ok=True)
    _history(day, mode=mode).to_csv(history_dir / f"pred_{mode}.csv", index=False)
    _prediction(day, mode=mode).to_csv(predict_dir / f"predict_next_{mode}_all_{day}.csv", index=False)


def test_every_written_row_names_its_brier_unit(tmp_path: Path, monkeypatch) -> None:
    """Đọc tệp thô phải thấy ngay đơn vị: Đặc Biệt cũ là trung bình, mới là tổng.

    Sổ cũ chưa có cột; lần ghi kế tiếp phải gắn nhãn cả dòng cũ, nhận ra dòng
    thang cũ bằng bất biến chứ không bằng ngày, và không đè nhãn đã có.
    """
    import prob_eval_history

    out = tmp_path / "ensemble_history.csv"
    pd.DataFrame(
        {
            "mode": ["de", "de", "loto", "de"],
            "target_date": ["2026-08-01", "2026-08-02", "2026-08-01", "2026-08-03"],
            "logloss": [4.65, 4.65, 0.55, 4.60],
            # Thang cũ (~0,0099), thang mới (~0,99), LOTO, thang cũ.
            "brier": [0.0099, 0.9905, 0.18, 0.0101],
            "updated_at_utc": ["2026-09-30T00:00:00Z"] * 4,
        }
    ).to_csv(out, index=False)
    for mode in ("de", "loto"):
        _emit(tmp_path, "2026-09-10", mode)
        monkeypatch.setattr(
            sys, "argv",
            ["prob_eval_history.py", "--mode", mode, "--history-dir", str(tmp_path / "history"),
             "--predict-dir", str(tmp_path / "predict"), "--out", str(out)],
        )
        prob_eval_history.main()

    frame = pd.read_csv(out, dtype={"target_date": str})
    assert list(frame.columns).index("brier_unit") == list(frame.columns).index("brier") + 1
    unit = frame.set_index(["mode", "target_date"])["brier_unit"]
    # Ngày ghi của dòng cũ cố ý là SAU bản sửa: luật theo ngày sẽ gắn sai.
    assert unit[("de", "2026-08-01")] == "mean_100_classes"
    assert unit[("de", "2026-08-02")] == "sum_100_classes"
    assert unit[("loto", "2026-08-01")] == "mean_100_bernoulli"
    assert unit[("de", "2026-09-10")] == "sum_100_classes"
    assert unit[("loto", "2026-09-10")] == "mean_100_bernoulli"
    assert unit[("de", "2026-08-03")] == "mean_100_classes"

    # Nhãn đã ghi thì giữ nguyên.
    kept = prob_eval_history.label_brier_units(frame.assign(brier_unit=frame["brier_unit"].where(
        frame["target_date"] != "2026-08-03", "ghi_tay")))
    assert kept.set_index(["mode", "target_date"])["brier_unit"][("de", "2026-08-03")] == "ghi_tay"


def test_the_repository_ledger_labels_every_brier_with_a_consistent_unit() -> None:
    """Sổ thật: mỗi dòng có nhãn, và nhãn khớp độ lớn của chính con số.

    Brier Đặc Biệt theo quy ước trung bình không vượt 2/100 (tổng bình phương của
    một phân phối và một one-hot tối đa là 2); quy ước tổng thì thoả cận dưới
    ``(1 − e^−logloss)²``.
    """
    from backfill_baseline_skill import brier_is_comparable

    path = Path(__file__).resolve().parents[1] / "data" / "prob_eval" / "ensemble_history.csv"
    frame = pd.read_csv(path, dtype={"target_date": str})
    assert len(frame) > 0
    allowed = {("loto", "mean_100_bernoulli"), ("de", "mean_100_classes"), ("de", "sum_100_classes")}
    for row in frame.itertuples(index=False):
        assert (row.mode, row.brier_unit) in allowed, (row.mode, row.target_date, row.brier_unit)
        if row.brier_unit == "mean_100_classes":
            assert row.brier <= 0.02, (row.target_date, row.brier)
        if row.brier_unit == "sum_100_classes":
            assert brier_is_comparable("de", row.logloss, row.brier), (row.target_date, row.brier)
