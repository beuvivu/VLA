"""JSON chỉ đổi dấu giờ ghi thì trả về bản đã commit (`core.stamp_only_json`, 11-11-2026)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import pipeline
from core import stamp_only_json as S

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
    later["records"][0]["checked_at"] = "2026-11-11T09:02:00+07:00"   # dấu giờ trong danh sách
    assert S.same_but_for_stamps(REPORT, later)
    assert S.same_but_for_stamps(REPORT, dict(reversed(list(later.items()))))   # thứ tự khoá không tính
    for key, value in (("anchor_date", "2026-11-11"), ("skill", 0.1 + 2 ** -55), ("days", [1, 2, 3])):
        changed = json.loads(json.dumps(later))
        target = changed if key == "anchor_date" else changed["modes"]["de"]
        target[key] = value
        assert not S.same_but_for_stamps(REPORT, changed), key   # số thực so TỪNG BIT
    assert S.same_but_for_stamps({"p": float("nan")}, {"p": float("nan")})


def test_a_tracked_json_that_only_changed_its_stamps_gets_the_committed_bytes_back(tmp_path: Path) -> None:
    ledger = json.dumps(REPORT) + "\n"   # sổ JSON Lines một dòng: đọc được như JSON nhưng là sổ cái
    repo = _repo(tmp_path, {"data/a.json": REPORT, "data/b.json": REPORT, "data/c.csv": "x\n1\n",
                            "docs/d.json": REPORT, "data/ledger.jsonl": ledger})
    committed = (repo / "data/a.json").read_bytes()
    later = {**REPORT, "generated_at_utc": "2026-11-11T02:01:41Z"}
    _write(repo, "data/a.json", later)                                   # chỉ đổi dấu giờ
    _write(repo, "data/b.json", {**later, "anchor_date": "2026-11-11"})  # đổi thật
    (repo / "data/c.csv").write_text("x\n2\n", encoding="utf-8")          # không phải JSON
    _write(repo, "data/new.json", later)                                 # chưa được theo dõi
    _write(repo, "docs/d.json", later)                                   # ngoài phạm vi
    (repo / "data/ledger.jsonl").write_text(json.dumps(later) + "\n", encoding="utf-8")   # chỉ .json
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
    """Pipeline so sau mỗi bước; tệp đổi thật không được đọc lại ở mỗi bước, nhưng bị ghi lại thì phải so lại."""
    repo = _repo(tmp_path, {"data/a.json": REPORT})
    committed = (repo / "data/a.json").read_bytes()
    _write(repo, "data/a.json", {**REPORT, "anchor_date": "2026-11-11"})
    shown: list[tuple[str, ...]] = []
    real_git = S._git
    monkeypatch.setattr(S, "_git", lambda r, *args: (shown.append(args) if args[0] == "show" else None) or real_git(r, *args))
    assert S.keep_committed_when_only_stamps_changed(repo) == []
    assert S.keep_committed_when_only_stamps_changed(repo) == []
    assert len(shown) == 1
    _write(repo, "data/a.json", {**REPORT, "generated_at_utc": "2026-11-11T02:01:41Z"})   # bước sau ghi lại
    os.utime(repo / "data/a.json", ns=(1, 1))
    assert S.keep_committed_when_only_stamps_changed(repo) == ["data/a.json"]
    assert (repo / "data/a.json").read_bytes() == committed


@pytest.mark.parametrize("key", sorted(S.WRITE_STAMP_KEYS))
def test_every_stamp_key_is_written_by_a_tracked_data_file(key: str) -> None:
    """Khoá không còn trình ghi nào dùng thì phải gỡ: nó chỉ nới phép so mà không ai cần."""
    tracked = _git(ROOT, "ls-files", "data/*.json", "data/**/*.json").split()
    pattern = f'"{key}"'
    assert any(pattern in (ROOT / path).read_text(encoding="utf-8", errors="replace")
               for path in tracked if (ROOT / path).stat().st_size < 5_000_000), key


def test_the_pipeline_restores_stamp_only_files_right_after_each_successful_step(monkeypatch) -> None:
    """Ngay sau bước vừa ghi, không đợi cuối lượt: bước sau đọc dấu giờ ấy (mã thí nghiệm lấy ngày của
    `generated_at` trong cổng Cầu Kèo), nên dấu giờ mới sẽ lan vào tệp của bước sau."""
    restored: list[tuple[str, Path]] = []
    monkeypatch.setattr(pipeline, "keep_committed_when_only_stamps_changed",
                        lambda root: restored.append(("json", root)) or [])
    monkeypatch.setattr(pipeline, "keep_committed_pages_when_only_stamps_changed",
                        lambda root: restored.append(("html", root)) or [])
    pipeline._run([sys.executable, "-c", "pass"])
    assert restored == [("json", pipeline.ROOT), ("html", pipeline.ROOT)]
    pipeline._run([sys.executable, "-c", "raise SystemExit(3)"], allow_fail=True)
    assert len(restored) == 2   # bước hỏng không có gì để giữ


def test_a_failure_while_comparing_never_fails_the_pipeline_step(monkeypatch) -> None:
    def broken(_root: Path) -> list[str]:
        raise RuntimeError("git hỏng")

    monkeypatch.setattr(pipeline, "keep_committed_when_only_stamps_changed", broken)
    monkeypatch.setattr(pipeline, "keep_committed_pages_when_only_stamps_changed", lambda root: [])
    pipeline._run([sys.executable, "-c", "pass"])
