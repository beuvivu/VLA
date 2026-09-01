from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from validate_data import FIELD_WIDTHS, main


def _write_data(root: Path, dates: list[str]) -> None:
    rows = []
    for d in dates:
        row = {"date": d}
        row.update({field: 0 for field in FIELD_WIDTHS})
        rows.append(row)
    pd.DataFrame(rows).to_csv(root / "xsmb.csv", index=False)

    sparse_rows = []
    for d in dates:
        row = {"date": d, **{str(i): 0 for i in range(100)}}
        for i in range(27):
            row[str(i)] = 1
        sparse_rows.append(row)
    pd.DataFrame(sparse_rows).to_csv(root / "xsmb-sparse.csv", index=False)


def test_full_history_gap_fails_even_outside_lookback(tmp_path: Path, monkeypatch):
    _write_data(tmp_path, ["2026-01-01", "2026-01-03"])
    out = tmp_path / "health.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_data.py",
            "--data-dir",
            str(tmp_path),
            "--lookback-days",
            "0",
            "--out",
            str(out),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["missing_count"] == 0
    assert payload["full_missing_count"] == 1
    assert payload["full_missing_dates"] == ["2026-01-02"]
    assert payload["ok"] is False


def test_contiguous_history_passes(tmp_path: Path, monkeypatch):
    _write_data(tmp_path, ["2026-01-01", "2026-01-02", "2026-01-03"])
    out = tmp_path / "health.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_data.py", "--data-dir", str(tmp_path), "--out", str(out)],
    )
    main()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["full_missing_count"] == 0
