from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

import pandas as pd
import yaml

from core.excel_export import export_excel_outputs

ROOT = Path(__file__).resolve().parents[2]
OTHER_WORKBOOKS = ("excel/statistics_matrices.xlsx",)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def _produced_workbooks(tmp_path: Path) -> list[str]:
    prizes = [c for c in pd.read_csv(ROOT / "data" / "xsmb.csv", nrows=0).columns if c != "date"]
    raw = pd.DataFrame([{"date": "2026-08-11", **{c: 7 for c in prizes}}])
    two = raw.copy()
    sparse = pd.DataFrame([{"date": "2026-08-11", **{str(i): 0 for i in range(100)}}])
    export_excel_outputs(raw_df=raw, two_digit_df=two, sparse_df=sparse, data_dir=tmp_path,
                         latest_daily_only=True)
    produced = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.xlsx"))
    assert len(produced) >= 4, produced
    return [*produced, *OTHER_WORKBOOKS]


def test_every_workbook_the_export_writes_stays_out_of_git(tmp_path: Path) -> None:
    for relative in _produced_workbooks(tmp_path):
        path = f"data/{relative}"
        assert _git("check-ignore", "-q", path).returncode == 0, f"{path} phải nằm trong .gitignore"
    tracked = _git("ls-files", "data/excel").stdout.split()
    assert not [path for path in tracked if path.endswith(".xlsx")], tracked
    assert "data/excel/integrity.json" in tracked


def test_the_pipeline_run_uploads_every_workbook(tmp_path: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/update-data.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["update"]["steps"]
    pipeline = next(i for i, step in enumerate(steps) if "src/pipeline.py" in step.get("run", ""))
    patterns = [
        pattern
        for step in steps[pipeline + 1:]
        if str(step.get("uses", "")).startswith("actions/upload-artifact@") and step.get("if") == "always()"
        for pattern in step["with"]["path"].split()
    ]
    for relative in _produced_workbooks(tmp_path):
        path = PurePosixPath(f"data/{relative}")
        assert any(path.full_match(pattern) for pattern in patterns), f"{path} không lên artifact"


def test_the_pipeline_rebuilds_the_workbooks_before_checking_them() -> None:
    source = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    sync = source.index('"src/ingest/sync.py"')
    check = source.index('"src/ingest/validate_excel_integrity.py"')
    assert sync < check
    sync_source = (ROOT / "src" / "ingest" / "sync.py").read_text(encoding="utf-8")
    no_new_dates = sync_source[sync_source.index("if not missing:"):sync_source.index("return []")]
    assert re.search(r"lottery\.dump\(\)", no_new_dates), "lượt không có kỳ mới cũng phải dựng lại XLSX"
