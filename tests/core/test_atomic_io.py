from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

import pipeline
from core import atomic_io as S
from core.atomic_io import save_xlsx, write_text_unless_only_stamps, xlsx_payload_equal

STAMP = (re.compile(r"Dựng lúc \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"),)


def test_a_text_that_differs_only_by_its_build_stamp_keeps_the_existing_file(tmp_path: Path) -> None:
    page = tmp_path / "trang.html"
    assert write_text_unless_only_stamps(page, "<p>12 · Dựng lúc 2026-11-05T11:38:57Z.</p>", STAMP)
    assert not write_text_unless_only_stamps(page, "<p>12 · Dựng lúc 2026-11-05T12:32:58Z.</p>", STAMP)
    assert page.read_text(encoding="utf-8") == "<p>12 · Dựng lúc 2026-11-05T11:38:57Z.</p>"
    assert write_text_unless_only_stamps(page, "<p>13 · Dựng lúc 2026-11-05T12:32:58Z.</p>", STAMP)
    assert page.read_text(encoding="utf-8") == "<p>13 · Dựng lúc 2026-11-05T12:32:58Z.</p>"
    assert write_text_unless_only_stamps(page, "<p>13 · Dựng lúc 2026-11-06T00:00:00Z.</p>", ())


def _utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC).replace(tzinfo=None)


def _workbook(value: int, created: datetime) -> Workbook:
    wb = Workbook()
    wb.active["A1"] = value
    wb.properties.created = created
    return wb


def test_a_workbook_whose_cells_did_not_change_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "xsmb.xlsx"
    assert save_xlsx(_workbook(7, _utc(2026, 11, 5, 11, 38)), path)
    before = path.read_bytes()
    assert not save_xlsx(_workbook(7, _utc(2026, 11, 5, 12, 32)), path)
    assert path.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".")], "không để lại tệp tạm"
    assert save_xlsx(_workbook(8, _utc(2026, 11, 5, 12, 32)), path)
    assert path.read_bytes() != before


def test_payload_comparison_ignores_only_the_core_properties(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a.xlsx", tmp_path / "b.xlsx", tmp_path / "c.xlsx"
    _workbook(7, _utc(2020, 1, 1)).save(a)
    _workbook(7, _utc(2021, 1, 1)).save(b)
    _workbook(9, _utc(2020, 1, 1)).save(c)
    assert xlsx_payload_equal(a, b)
    assert not xlsx_payload_equal(a, c)
    assert not xlsx_payload_equal(a, tmp_path / "khong-co.xlsx")


ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def _repo(tmp_path: Path, files: dict[str, object]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _git(tmp_path, "init", "-q")
    for name, payload in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload, indent=2), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "đầu")
    return tmp_path


def _write(repo: Path, name: str, payload: object) -> None:
    (repo / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


REPORT = {"generated_at_utc": "2026-11-10T11:39:20Z", "anchor_date": "2026-11-10",
          "modes": {"de": {"learned_at_utc": "2026-11-10T11:39:23Z", "skill": 0.1, "days": [1, 2]}},
          "records": [{"checked_at": "2026-11-10T18:40:00+07:00", "draw": "2026-11-10"}]}


def test_only_write_stamps_are_ignored_at_every_depth() -> None:
    later = json.loads(json.dumps(REPORT))
    later["generated_at_utc"] = "2026-11-11T02:01:41Z"
    later["modes"]["de"]["learned_at_utc"] = "2026-11-11T02:01:45Z"
    later["records"][0]["checked_at"] = "2026-11-11T09:02:00+07:00"
    assert S.same_but_for_stamps_and_noise(REPORT, later)
    assert S.same_but_for_stamps_and_noise(REPORT, dict(reversed(list(later.items()))))
    noisy = json.loads(json.dumps(later))
    noisy["modes"]["de"]["skill"] = 0.1 + 2 ** -55
    assert S.same_but_for_stamps_and_noise(REPORT, noisy)
    for key, value in (("anchor_date", "2026-11-11"), ("skill", 0.1 * (1 + 1e-6)), ("days", [1, 2, 3])):
        changed = json.loads(json.dumps(later))
        target = changed if key == "anchor_date" else changed["modes"]["de"]
        target[key] = value
        assert not S.same_but_for_stamps_and_noise(REPORT, changed), key
    assert S.same_but_for_stamps_and_noise({"p": float("nan")}, {"p": float("nan")})


def test_a_tracked_json_that_only_changed_its_stamps_gets_the_committed_bytes_back(tmp_path: Path) -> None:
    ledger = json.dumps(REPORT) + "\n"
    repo = _repo(tmp_path, {"data/a.json": REPORT, "data/b.json": REPORT, "data/c.csv": "x\n1\n",
                            "docs/d.json": REPORT, "data/ledger.jsonl": ledger})
    committed = (repo / "data/a.json").read_bytes()
    later = {**REPORT, "generated_at_utc": "2026-11-11T02:01:41Z"}
    _write(repo, "data/a.json", later)
    _write(repo, "data/b.json", {**later, "anchor_date": "2026-11-11"})
    (repo / "data/c.csv").write_text("x\n2\n", encoding="utf-8")
    _write(repo, "data/new.json", later)
    _write(repo, "docs/d.json", later)
    (repo / "data/ledger.jsonl").write_text(json.dumps(later) + "\n", encoding="utf-8")
    assert S.keep_committed_when_only_stamps_changed(repo) == ["data/a.json"]
    assert (repo / "data/a.json").read_bytes() == committed
    assert json.loads((repo / "data/b.json").read_text())["anchor_date"] == "2026-11-11"
    assert (repo / "data/c.csv").read_text() == "x\n2\n"
    assert (repo / "data/new.json").is_file()
    assert json.loads((repo / "docs/d.json").read_text())["generated_at_utc"] == "2026-11-11T02:01:41Z"
    assert json.loads((repo / "data/ledger.jsonl").read_text())["generated_at_utc"] == "2026-11-11T02:01:41Z"
    assert _git(repo, "status", "--porcelain", "data/a.json") == ""


def test_outside_a_repository_or_with_unreadable_json_nothing_is_touched(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    _write(tmp_path, "data/a.json", REPORT)
    assert S.keep_committed_when_only_stamps_changed(tmp_path) == []
    repo = _repo(tmp_path / "r", {"data/a.json": REPORT})
    (repo / "data/a.json").write_text("{hỏng", encoding="utf-8")
    assert S.keep_committed_when_only_stamps_changed(repo) == []
    assert (repo / "data/a.json").read_text(encoding="utf-8") == "{hỏng"


def test_a_real_change_is_read_once_until_the_file_is_written_again(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, {"data/a.json": REPORT})
    committed = (repo / "data/a.json").read_bytes()
    _write(repo, "data/a.json", {**REPORT, "anchor_date": "2026-11-11"})
    shown: list[tuple[str, ...]] = []
    real_git = S._git
    monkeypatch.setattr(S, "_git", lambda r, *args: (shown.append(args) if args[0] == "show" else None) or real_git(r, *args))
    assert S.keep_committed_when_only_stamps_changed(repo) == []
    assert S.keep_committed_when_only_stamps_changed(repo) == []
    assert len(shown) == 1
    _write(repo, "data/a.json", {**REPORT, "generated_at_utc": "2026-11-11T02:01:41Z"})
    os.utime(repo / "data/a.json", ns=(1, 1))
    assert S.keep_committed_when_only_stamps_changed(repo) == ["data/a.json"]
    assert (repo / "data/a.json").read_bytes() == committed


@pytest.mark.parametrize("key", sorted(S.WRITE_STAMP_KEYS))
def test_every_stamp_key_is_written_by_a_tracked_data_file(key: str) -> None:
    tracked = _git(ROOT, "ls-files", "data/*.json", "data/**/*.json").split()
    pattern = f'"{key}"'
    assert any(pattern in (ROOT / path).read_text(encoding="utf-8", errors="replace")
               for path in tracked if (ROOT / path).stat().st_size < 5_000_000), key


def test_the_pipeline_restores_stamp_only_files_right_after_each_successful_step(monkeypatch) -> None:
    restored: list[tuple[str, Path]] = []
    monkeypatch.setattr(pipeline, "keep_committed_when_only_stamps_changed",
                        lambda root: restored.append(("json", root)) or [])
    monkeypatch.setattr(pipeline, "keep_committed_tables_when_only_noise_changed",
                        lambda root: restored.append(("csv", root)) or [])
    monkeypatch.setattr(pipeline, "keep_committed_pages_when_only_stamps_changed",
                        lambda root: restored.append(("html", root)) or [])
    pipeline._run([sys.executable, "-c", "pass"])
    assert restored == [("json", pipeline.ROOT), ("csv", pipeline.ROOT), ("html", pipeline.ROOT)]
    pipeline._run([sys.executable, "-c", "raise SystemExit(3)"], allow_fail=True)
    assert len(restored) == 3


def test_a_failure_while_comparing_never_fails_the_pipeline_step(monkeypatch) -> None:
    def broken(_root: Path) -> list[str]:
        raise RuntimeError("git hỏng")

    monkeypatch.setattr(pipeline, "keep_committed_when_only_stamps_changed", broken)
    monkeypatch.setattr(pipeline, "keep_committed_tables_when_only_noise_changed", lambda root: [])
    monkeypatch.setattr(pipeline, "keep_committed_pages_when_only_stamps_changed", lambda root: [])
    pipeline._run([sys.executable, "-c", "pass"])


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
    assert S.floats_close(0.1, 0.1 + 2 ** -55)
    assert S.floats_close(12345.678, 12345.678 * (1 + 1e-15))
    assert S.floats_close(1e-30, 1.1e-30)
    assert not S.floats_close(0.1, 0.1 * (1 + 1e-6))
    assert S.floats_close(float("nan"), float("nan"))
    assert not S.floats_close(float("nan"), 0.0)
    assert S.floats_close(float("inf"), float("inf")) and not S.floats_close(float("inf"), 1e308)


def test_json_trees_relax_floats_and_nothing_else() -> None:
    old = {"skill": 0.1, "days": 46, "ok": True, "first": "2026-09-30", "rows": [0.2, 0.3]}
    assert S.same_tree_up_to_float_noise(old, {**old, "skill": 0.1 + 2 ** -55, "rows": [0.2, 0.30000000000000004]})
    for key, value in (("days", 47), ("ok", 1), ("first", "2026-10-01"), ("rows", [0.2]), ("skill", 0.11)):
        assert not S.same_tree_up_to_float_noise(old, {**old, key: value}), key
    assert not S.same_tree_up_to_float_noise({"n": 1}, {"n": 1.0})
    assert not S.same_tree_up_to_float_noise(old, {**old, "new": 1})


def test_a_table_whose_near_ties_swapped_under_noise_is_the_same_table() -> None:
    swapped = TABLE.replace("loto,Chạm đuôi,Dàn đuôi,0.5,0.3000000000000001\nloto,Chạm đầu,Dàn đầu,0.5,0.3000000000000000",
                            "loto,Chạm đầu,Dàn đầu,0.5,0.30000000000000004\nloto,Chạm đuôi,Dàn đuôi,0.5,0.3")
    assert swapped != TABLE
    assert S.same_table_up_to_float_noise(_csv(TABLE), _csv(swapped))


@pytest.mark.parametrize("change", [
    ("0.12\n", "0.1201\n"),
    ("Bộ,Dàn tổng", "Bộ,Dàn chạm"),
    ("mode,strategy_a", "mode,chien_luoc_a"),
    ("loto,Bộ,Dàn tổng,0.25,0.12\n", ""),
    ("0.25,0.12\n", "0.25,0.12\nloto,Bộ,Dàn bóng,0.25,0.12\n"),
])
def test_a_real_change_to_a_table_is_a_change(change: tuple[str, str]) -> None:
    assert not S.same_table_up_to_float_noise(_csv(TABLE), _csv(TABLE.replace(*change)))


def test_integers_codes_and_flags_are_compared_exactly() -> None:
    table = "number_str,days,flag,p\n05,47,False,0.5\n"
    for old, new in (("\n05,", "\n5,"), (",47,", ",46,"), ("False", "True")):
        assert not S.same_table_up_to_float_noise(_csv(table), _csv(table.replace(old, new))), old
    assert S.same_table_up_to_float_noise(_csv(table), _csv(table.replace("0.5", "0.5000000000000001")))
    assert S.same_table_up_to_float_noise(_csv("a,p\nx,nan\n"), _csv("a,p\nx,nan\n"))
    assert not S.same_table_up_to_float_noise(b"\xff\xfe", b"\xff\xfe")


def test_the_real_rerun_after_pr_223_is_noise_and_the_daily_run_is_not() -> None:
    before, daily, rerun = (
        (FIXTURES / f"strategy_diversity_loto_{name}.csv").read_bytes()
        for name in ("2026-11-13", "2026-11-14_daily", "2026-11-14_rerun"))
    assert daily != rerun and daily.splitlines()[1] != rerun.splitlines()[1]
    assert S.same_table_up_to_float_noise(daily, rerun)
    assert not S.same_table_up_to_float_noise(before, daily)


def test_a_tracked_table_that_only_changed_by_noise_gets_the_committed_bytes_back(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"data/a.csv": TABLE, "data/b.csv": TABLE, "data/c.json": json.dumps({"p": 0.1}),
                            "models/train_report_loto.csv": TABLE, "docs/d.csv": TABLE})
    committed = (repo / "data/a.csv").read_bytes()
    noisy = TABLE.replace("0.12", "0.12000000000000001")
    for name in ("data/a.csv", "models/train_report_loto.csv", "docs/d.csv"):
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
