"""Bảng nghiên cứu đầy đủ ra khỏi git; git giữ bản cắt (phương án 3, 07 → 11-11-2026).

Đợt đầu (07-11) là `crosslag_rules.csv` (5 832 quy tắc) và `loto_nextday_given_special_long.csv`
(10 000 ô): đo ngày 06-11-2026 chúng chiếm 24% phần tăng của kho. Đợt hai (11-11) là năm bảng chẩn đoán
không trang nào đọc: tường lửa nghiên cứu (hai chế độ), dòng thời gian đường cầu (hai chế độ) và bảng cặp
của `legacy_extensions` (`documentation/plans/2026-11-05-dung-luong-kho.md`). Gần như mọi số trong các
bảng ấy đổi mỗi kỳ, nên git không lấy được delta.

Chúng vẫn được ghi ra đĩa và lên artifact của `update-data.yml`, nhưng nằm trong `.gitignore`. Danh sách
khai MỘT lần ở `core.table_cuts.FULL_TABLE_CUTS`. Các phép dưới đây buộc:
- trang dựng từ bản cắt trùng trang dựng từ bảng đầy đủ;
- bản cắt giữ mọi dòng đáng xem và là một phần của đúng bảng đầy đủ;
- mỗi trình ghi ghi đúng cặp tệp đã khai, qua chính lối vào mà pipeline gọi;
- `.gitignore` bỏ qua đúng các bảng đầy đủ đã khai, không hơn không kém;
- workflow lưu đúng các bảng đầy đủ đã khai.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from core.path_models import FIELD_WIDTHS
from core.table_cuts import FULL_TABLE_CUTS
from pages.build_research_lab import _conditional_table, _crosslag_table, build
from research import (
    conditional_nextday,
    crosslag_positional_lab as crosslag,
    research_firewall,
    research_legacy_extensions as legacy_extensions,
)
from soi_cau import path_timeline_evidence

ROOT = Path(__file__).resolve().parents[2]
CROSS_DIR = Path("data/research/crosslag_positional")
CONDITIONAL_DIR = Path("data/stats/conditional")
FULL_TABLES = tuple(Path("data") / full for full in FULL_TABLE_CUTS)
CUT_TABLES = tuple(Path("data") / cut for cut in FULL_TABLE_CUTS.values())


def _rules(n: int, seed: int, gate: int = 0) -> pd.DataFrame:
    """Bảng quy tắc giả, đủ cột cho trang và cho bản cắt; độ nâng làm tròn để có nhiều dòng hoà."""
    rng = np.random.default_rng(seed)
    table = pd.DataFrame({
        "rule": [f"r{i:05d}" for i in range(n)],
        "operator": rng.choice(["concat", "lon", "bo", "cham", "tong"], n),
        "position_a_name": [f"a{i % 27}" for i in range(n)],
        "position_b_name": [f"b{i % 13}" for i in range(n)],
        "lag_a_days": 1,
        "lag_b_days": rng.choice([1, 2], n),
        "holdout_lift": rng.normal(1, 0.1, n).round(2),
        "validation_lift": rng.normal(1, 0.1, n).round(2),
        "train_p_value": rng.uniform(0, 1, n),
        "train_q_value_fdr": rng.uniform(0, 1, n).round(1),
        "research_gate_pass": np.arange(n) < gate,
        "production_eligible": False,
    })
    return table.sample(frac=1, random_state=seed).reset_index(drop=True)


def _long(seed: int) -> pd.DataFrame:
    """Bảng dài giả 100 × 100, làm tròn để có dòng hoà như bảng thật (cùng trials, cùng hits)."""
    rng = np.random.default_rng(seed)
    special, number = np.meshgrid(np.arange(100), np.arange(100), indexing="ij")
    hits = rng.integers(0, 20, special.size)
    trials = np.repeat(rng.integers(30, 60, 100), 100)
    p_eb = ((hits + 60 * 0.24) / (trials + 60)).round(3)
    return pd.DataFrame({
        "special": special.ravel(), "number": number.ravel(), "trials": trials, "hits": hits,
        "p_raw": hits / trials, "p_eb": p_eb, "q_value_fdr": rng.uniform(0.5, 1, special.size).round(2),
        "fdr_05": False, "prior_strength": 60.0,
    })


def test_the_crosslag_page_reads_the_same_rows_from_the_cut() -> None:
    for seed in range(5):
        full = _rules(2_000, seed)
        assert _crosslag_table(crosslag.cut_table(full)) == _crosslag_table(full), seed


def test_the_cut_keeps_every_gate_pass_and_the_strongest_training_rules() -> None:
    """Quy tắc qua cổng giữ hết, kể cả khi nhiều hơn `CUT_ROWS`; p huấn luyện nhỏ nhất cũng giữ,
    dù chúng nằm sâu trong thứ tự của trang."""
    full = _rules(2_000, seed=7, gate=crosslag.CUT_ROWS + 50)
    full.loc[full["research_gate_pass"], "holdout_lift"] = 0.5   # qua cổng nhưng đứng cuối mọi thứ khác
    cut = set(crosslag.cut_table(full)["rule"])
    assert set(full.loc[full["research_gate_pass"], "rule"]) <= cut
    strongest = full.sort_values("train_p_value", kind="stable")["rule"].head(crosslag.CUT_ROWS)
    assert set(strongest) <= cut
    assert len(cut) <= 3 * crosslag.CUT_ROWS + 50


def test_the_crosslag_writer_puts_the_page_rows_in_the_tracked_file(tmp_path: Path) -> None:
    full = _rules(800, seed=3)
    out = tmp_path / "data" / CROSS_DIR.relative_to("data")
    full_path, cut_path, report_path = crosslag.write_outputs(full, {"hypotheses": len(full)}, out)
    assert cut_path.name == crosslag.CUT_TABLE
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["cut_rows"] == len(pd.read_csv(cut_path)) < len(full)
    full_path.unlink()   # bản checkout không có bảng đầy đủ: trang phải dựng từ tệp git theo dõi
    page = build(tmp_path / "data", tmp_path / "docs").read_text(encoding="utf-8")
    assert _crosslag_table(full) in page


def test_the_conditional_page_reads_the_same_rows_from_the_current_cut(tmp_path: Path) -> None:
    """Trang chỉ hiện trạng thái Đặc Biệt hiện tại; bản cắt của trạng thái ấy cho đúng 10 dòng ấy."""
    long_df = _long(seed=11)
    for special in (0, 7, 77, 99):
        cut = conditional_nextday.current_special_rows(long_df, special, 20)
        assert _conditional_table(cut, f"{special:02d}") == _conditional_table(long_df, f"{special:02d}")
    out = tmp_path / "data" / CONDITIONAL_DIR.relative_to("data")
    written = conditional_nextday.write_tables(long_df, out_dir=out, anchor_date="2026-11-06",
                                               current_special=77, top=20, prior_learned=False)
    (long_path,) = [path for path in written if path.name == conditional_nextday.LONG_TABLE]
    long_path.unlink()   # bản checkout không có bảng dài: trang phải dựng từ tệp git theo dõi
    page = build(tmp_path / "data", tmp_path / "docs").read_text(encoding="utf-8")
    assert _conditional_table(long_df, "77") in page


class _History:
    """Sổ kết quả giả, đủ ba dạng mà các trình ghi hỏi `Lottery`; ngày liền nhau, 27 giải mỗi kỳ."""

    def __init__(self, days: int, seed: int) -> None:
        rng = np.random.default_rng(seed)
        dates = pd.date_range("2025-01-01", periods=days, freq="D")
        fields = [field for field, _width in FIELD_WIDTHS]
        self.raw = pd.DataFrame({"date": dates} | {
            field: rng.integers(0, 10 ** width, days) for field, width in FIELD_WIDTHS})
        self.two = self.raw.copy()
        self.two[fields] = self.two[fields] % 100
        counts = np.zeros((days, 100), dtype=int)
        np.add.at(counts, (np.repeat(np.arange(days), len(fields)), self.two[fields].to_numpy().ravel()), 1)
        self.sparse = pd.DataFrame(counts, columns=[str(i) for i in range(100)])
        self.sparse.insert(0, "date", dates)

    def load(self) -> None:
        return None

    def get_raw_data(self) -> pd.DataFrame:
        return self.raw.copy()

    def get_2_digits_data(self) -> pd.DataFrame:
        return self.two.copy()

    def get_sparse_data(self) -> pd.DataFrame:
        return self.sparse.copy()


def _position_evidence(n: int, seed: int) -> pd.DataFrame:
    """Bảng đường cầu giả cho `path_timeline_evidence`: `n` cặp vị trí khác nhau, điểm quy tắc có dòng hoà."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "rule_kind": "active", "lag_days": 1,
        "pos_i_index": np.arange(n) % 107, "pos_j_index": (np.arange(n) * 7 + 3) % 107,
        "path_line": [f"L{i}" for i in range(n)],
        "rule_score": rng.integers(0, 12, n), "p_mean": rng.uniform(0.2, 0.3, n).round(2),
        "current_streak": rng.integers(0, 5, n), "max_streak": rng.integers(5, 9, n),
    })


@pytest.fixture(scope="module")
def written(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Thư mục `data/` tạm mà MỌI trình ghi đã ghi vào, qua chính lối vào mà pipeline gọi.

    Ba trình ghi của đợt 11-11 chạy cả lượt (`main`, `run`, `run_extensions`) trên sổ giả: phép kiểm phải đỏ
    khi lối vào thôi gọi hàm ghi cặp tệp, không chỉ khi hàm ghi sai tên.
    """
    data = tmp_path_factory.mktemp("written") / "data"
    history = _History(days=240, seed=5)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(research_firewall, "Lottery", lambda: history)
        patch.setattr(sys, "argv", ["research_firewall.py", "--out-dir", str(data / "research"),
                                    "--permutations", "15", "--max-reality-days", "120"])
        research_firewall.main()

        patch.setattr(path_timeline_evidence, "Lottery", lambda: history)
        evidence = data / "ai_ml"
        evidence.mkdir(parents=True)
        for seed, mode in enumerate(("loto", "de")):
            rows = path_timeline_evidence.CUT_ROWS + 30
            _position_evidence(rows, seed).to_csv(evidence / f"cau_position_evidence_{mode}.csv", index=False)
        path_timeline_evidence.run(evidence_dir=evidence, out_dir=data / "research" / "path_timelines")

    legacy_extensions.run_extensions(history.raw, history.two, history.sparse,
                                     out_dir=data / "research" / "legacy_extensions")
    rules = _rules(800, seed=3)
    crosslag.write_outputs(rules, {"hypotheses": len(rules)}, data / CROSS_DIR.relative_to("data"))
    conditional_nextday.write_tables(_long(seed=11), out_dir=data / CONDITIONAL_DIR.relative_to("data"),
                                     anchor_date="2026-11-06", current_special=77, top=20, prior_learned=False)
    return data


def test_every_writer_writes_the_full_table_and_the_cut_the_registry_declares(written: Path) -> None:
    """Bảng khai là nguồn duy nhất: trình ghi đổi tên tệp, hay bảng khai thêm một cặp không ai ghi, đều đỏ."""
    assert len(FULL_TABLE_CUTS) >= 7
    assert not set(FULL_TABLE_CUTS) & set(FULL_TABLE_CUTS.values())
    for full, cut in FULL_TABLE_CUTS.items():
        assert (written / full).is_file(), f"không trình ghi nào ghi bảng đầy đủ {full}"
        assert (written / cut).is_file(), f"không trình ghi nào ghi bản cắt {cut}"
        assert 0 < (written / cut).stat().st_size < (written / full).stat().st_size, (full, cut)
    # Mọi tệp `*_top.csv` các trình ghi sinh ra đều là bản cắt ĐÃ KHAI: bản cắt chưa khai thì bảng đầy đủ
    # của nó không được `.gitignore` bỏ qua và cũng không lên artifact.
    cuts = {path.relative_to(written).as_posix() for path in written.rglob("*_top.csv")}
    assert cuts <= set(FULL_TABLE_CUTS.values()), cuts - set(FULL_TABLE_CUTS.values())


def test_the_firewall_cut_keeps_every_eligible_rule_and_the_strongest_training_rules(written: Path) -> None:
    key = ["rule", "position_i", "position_j"]
    for mode in ("loto", "de"):
        full = pd.read_csv(written / "research" / research_firewall.FULL_TABLE.format(mode=mode))
        cut = pd.read_csv(written / "research" / research_firewall.CUT_TABLE.format(mode=mode))
        assert len(full) == 27 * 27 * 2
        assert cut[key].values.tolist() == research_firewall.cut_table(full)[key].values.tolist()
        assert cut[key].values.tolist()[:10] == full[key].values.tolist()[:10]
        strongest = full.sort_values("train_p_value", kind="stable").head(research_firewall.CUT_ROWS)
        assert set(map(tuple, strongest[key].values)) <= set(map(tuple, cut[key].values))
        report = json.loads((written / "research" / "research_firewall_report.json").read_text(encoding="utf-8"))
        assert report["modes"][mode]["cut_rows"] == len(cut) < len(full)
    # Giả thuyết đủ điều kiện vận hành giữ hết, kể cả khi nhiều hơn `CUT_ROWS` (sổ giả không có dòng nào).
    eligible = research_firewall.CUT_ROWS + 40
    table = full.assign(production_eligible=np.arange(len(full))[::-1] < eligible)
    kept = research_firewall.cut_table(table)
    assert int(kept["production_eligible"].sum()) == eligible


def test_the_timeline_and_pair_cuts_are_the_head_of_the_full_table(written: Path) -> None:
    timelines = written / "research" / "path_timelines"
    manifest = json.loads((timelines / "manifest.json").read_text(encoding="utf-8"))
    for mode in ("loto", "de"):
        full = pd.read_csv(timelines / path_timeline_evidence.FULL_TABLE.format(mode=mode))
        cut = pd.read_csv(timelines / path_timeline_evidence.CUT_TABLE.format(mode=mode))
        assert len(cut) == path_timeline_evidence.CUT_ROWS < len(full)
        assert cut.equals(full.head(len(cut)))
        assert manifest["modes"][mode]["cut_output"] == path_timeline_evidence.CUT_TABLE.format(mode=mode)
        assert manifest["modes"][mode]["cut_rows"] == len(cut)
        assert manifest["modes"][mode]["rows"] == len(full)

    legacy = written / "research" / "legacy_extensions"
    full = pd.read_csv(legacy / legacy_extensions.PAIR_FULL_TABLE)
    cut = pd.read_csv(legacy / legacy_extensions.PAIR_CUT_TABLE)
    assert len(cut) == legacy_extensions.PAIR_CUT_ROWS < len(full)
    assert cut.equals(full.head(len(cut)))
    manifest = json.loads((legacy / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pair_recency_cut_rows"] == len(cut)
    assert manifest["rows"][legacy_extensions.PAIR_FULL_TABLE] == len(full)


def _ignored_tables() -> set[str]:
    """Các dòng `.gitignore` gọi đích danh một CSV trong `data/` (không ký tự đại diện)."""
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines
            if line.startswith("data/") and line.strip().endswith(".csv") and "*" not in line}


def test_the_full_tables_stay_out_of_git_and_the_cuts_stay_in() -> None:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)

    assert len(FULL_TABLES) == len(CUT_TABLES) >= 7
    for path in FULL_TABLES:
        assert git("check-ignore", "-q", str(path)).returncode == 0, f"{path} phải nằm trong .gitignore"
        assert git("ls-files", "--error-unmatch", str(path)).returncode != 0, f"{path} vẫn được git theo dõi"
    for path in CUT_TABLES:
        assert git("check-ignore", "-q", str(path)).returncode != 0, f"{path} không được bị bỏ qua"
        assert git("ls-files", "--error-unmatch", str(path)).returncode == 0, f"{path} phải được git theo dõi"
    # Chiều ngược lại: bảng bị bỏ qua mà không khai thì không trình ghi nào bị buộc ghi bản cắt cho nó
    # và workflow không lưu nó — dữ liệu biến mất lặng lẽ.
    assert _ignored_tables() == {str(path) for path in FULL_TABLES}


def test_the_pipeline_run_uploads_every_full_table() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/update-data.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["update"]["steps"]
    pipeline = next(i for i, step in enumerate(steps) if "src/pipeline.py" in step.get("run", ""))
    full = {str(path) for path in FULL_TABLES}
    uploads = [step for step in steps[pipeline + 1:]
               if str(step.get("uses", "")).startswith("actions/upload-artifact@")
               and full & set(step["with"]["path"].split())]
    assert len(uploads) == 1
    (upload,) = uploads
    assert upload.get("if") == "always()"
    assert set(upload["with"]["path"].split()) == full
    # Bước nghiên cứu được phép hỏng: thiếu tệp không được làm đỏ lượt chốt kết quả.
    assert upload["with"]["if-no-files-found"] == "ignore"
