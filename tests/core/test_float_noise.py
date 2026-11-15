"""Nhiễu dấu phẩy động giữa các CPU runner không phải thay đổi (`core.float_noise`, 14-11-2026)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import pipeline
from core import stamp_only_json as S
from core.float_noise import close, same_table_up_to_float_noise, same_tree_up_to_float_noise

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "float_noise"

TABLE = (
    "mode,strategy_a,strategy_b,jaccard,phi_correlation\n"
    "loto,Chạm đuôi,Dàn đuôi,0.5,0.3000000000000001\n"
    "loto,Chạm đầu,Dàn đầu,0.5,0.3000000000000000\n"
    "loto,Bộ,Dàn tổng,0.25,0.12\n"
)


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


def test_only_floats_are_relaxed_and_only_by_noise() -> None:
    assert close(0.1, 0.1 + 2 ** -55)
    assert close(12345.678, 12345.678 * (1 + 1e-15))   # số lớn: ngưỡng tương đối
    assert close(1e-30, 1.1e-30)                 # gần 0: ngưỡng tuyệt đối
    assert not close(0.1, 0.1 * (1 + 1e-6))      # thay đổi thật
    assert close(float("nan"), float("nan"))
    assert not close(float("nan"), 0.0)
    assert close(float("inf"), float("inf")) and not close(float("inf"), 1e308)


def test_json_trees_relax_floats_and_nothing_else() -> None:
    old = {"skill": 0.1, "days": 46, "ok": True, "first": "2026-09-30", "rows": [0.2, 0.3]}
    assert same_tree_up_to_float_noise(old, {**old, "skill": 0.1 + 2 ** -55, "rows": [0.2, 0.30000000000000004]})
    for key, value in (("days", 47), ("ok", 1), ("first", "2026-10-01"), ("rows", [0.2]), ("skill", 0.11)):
        assert not same_tree_up_to_float_noise(old, {**old, key: value}), key
    assert not same_tree_up_to_float_noise({"n": 1}, {"n": 1.0})        # số nguyên không thành số thực
    assert not same_tree_up_to_float_noise(old, {**old, "new": 1})


def test_a_table_whose_near_ties_swapped_under_noise_is_the_same_table() -> None:
    swapped = TABLE.replace("loto,Chạm đuôi,Dàn đuôi,0.5,0.3000000000000001\nloto,Chạm đầu,Dàn đầu,0.5,0.3000000000000000",
                            "loto,Chạm đầu,Dàn đầu,0.5,0.30000000000000004\nloto,Chạm đuôi,Dàn đuôi,0.5,0.3")
    assert swapped != TABLE
    assert same_table_up_to_float_noise(_csv(TABLE), _csv(swapped))


@pytest.mark.parametrize("change", [
    ("0.12\n", "0.1201\n"),                                    # số thực đổi thật
    ("Bộ,Dàn tổng", "Bộ,Dàn chạm"),                            # chuỗi
    ("mode,strategy_a", "mode,chien_luoc_a"),                  # tiêu đề
    ("loto,Bộ,Dàn tổng,0.25,0.12\n", ""),                     # mất dòng
    ("0.25,0.12\n", "0.25,0.12\nloto,Bộ,Dàn bóng,0.25,0.12\n"),  # thêm dòng
])
def test_a_real_change_to_a_table_is_a_change(change: tuple[str, str]) -> None:
    assert not same_table_up_to_float_noise(_csv(TABLE), _csv(TABLE.replace(*change)))


def test_integers_codes_and_flags_are_compared_exactly() -> None:
    table = "number_str,days,flag,p\n05,47,False,0.5\n"
    for old, new in (("\n05,", "\n5,"), (",47,", ",46,"), ("False", "True")):
        assert not same_table_up_to_float_noise(_csv(table), _csv(table.replace(old, new))), old
    assert same_table_up_to_float_noise(_csv(table), _csv(table.replace("0.5", "0.5000000000000001")))
    assert same_table_up_to_float_noise(_csv("a,p\nx,nan\n"), _csv("a,p\nx,nan\n"))
    assert not same_table_up_to_float_noise(b"\xff\xfe", b"\xff\xfe")


def test_the_real_rerun_after_pr_223_is_noise_and_the_daily_run_is_not() -> None:
    """Ba bản thật của `strategy_diversity_loto.csv`: lượt hằng ngày 14-11 đổi thật so với 13-11; lượt chạy
    lại sau PR #223 trên runner khác CPU chỉ lệch phi ≤ 4·10⁻¹⁵, nhưng đổi thứ tự hai dòng gần hoà."""
    before, daily, rerun = (
        (FIXTURES / f"strategy_diversity_loto_{name}.csv").read_bytes()
        for name in ("2026-11-13", "2026-11-14_daily", "2026-11-14_rerun"))
    assert daily != rerun and daily.splitlines()[1] != rerun.splitlines()[1]   # dòng đầu đã đổi chỗ
    assert same_table_up_to_float_noise(daily, rerun)
    assert not same_table_up_to_float_noise(before, daily)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)

    git("init", "-q")
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "đầu")
    return tmp_path


def test_a_tracked_table_that_only_changed_by_noise_gets_the_committed_bytes_back(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"data/a.csv": TABLE, "data/b.csv": TABLE, "data/c.json": json.dumps({"p": 0.1}),
                            "models/train_report_loto.csv": TABLE, "docs/d.csv": TABLE})
    committed = (repo / "data/a.csv").read_bytes()
    noisy = TABLE.replace("0.12", "0.12000000000000001")
    for name in ("data/a.csv", "models/train_report_loto.csv", "docs/d.csv"):   # docs/ ngoài phạm vi
        (repo / name).write_text(noisy, encoding="utf-8")
    (repo / "data/b.csv").write_text(TABLE.replace("0.12", "0.13"), encoding="utf-8")
    (repo / "data/c.json").write_text(json.dumps({"p": 0.1 + 2 ** -55}), encoding="utf-8")
    assert S.keep_committed_tables_when_only_noise_changed(repo) == ["data/a.csv", "models/train_report_loto.csv"]
    assert (repo / "docs/d.csv").read_text(encoding="utf-8") == noisy
    assert (repo / "data/a.csv").read_bytes() == committed
    assert "0.13" in (repo / "data/b.csv").read_text(encoding="utf-8")
    assert S.keep_committed_when_only_stamps_changed(repo) == ["data/c.json"]


def test_the_pipeline_restores_noise_only_tables_after_each_step(monkeypatch) -> None:
    calls: list[str] = []
    for name in ("keep_committed_when_only_stamps_changed", "keep_committed_tables_when_only_noise_changed",
                 "keep_committed_pages_when_only_stamps_changed"):
        monkeypatch.setattr(pipeline, name, lambda root, name=name: calls.append(name) or [])
    pipeline._run([sys.executable, "-c", "pass"])
    assert "keep_committed_tables_when_only_noise_changed" in calls
