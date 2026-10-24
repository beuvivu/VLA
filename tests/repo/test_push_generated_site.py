"""Hai bot ghi vào remote git thật phải giữ cả nội dung lẫn manifest chung."""

import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest

from web.site_assets import check_site, refresh_site

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("push_generated_site", ROOT / "scripts/ops/push_generated_site.py")
PUSH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUSH)


def git(repo, *args, check=True):
    return subprocess.run(["git", *args], cwd=repo, check=check, capture_output=True, text=True)


def commit(repo, filename, value, *, finalize=True):
    (repo / "docs" / filename).write_text(f"<!doctype html><p>{value}</p>", encoding="utf-8")
    if finalize:
        refresh_site(repo / "docs")
    git(repo, "add", "docs")
    git(repo, "commit", "-qm", value)


@pytest.fixture
def writers(tmp_path):
    remote, first, second = (tmp_path / name for name in ("remote.git", "first", "second"))
    git(tmp_path, "init", "--bare", "-q", "--initial-branch=main", str(remote))
    git(tmp_path, "clone", "-q", str(remote), str(first))
    for repo in (first,):
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
    (first / "docs/assets").mkdir(parents=True)
    (first / "docs/assets/app.js").write_text("/* mã nguồn */", encoding="utf-8")
    for name in ("left.html", "right.html", "same.html", "race.html"):
        (first / "docs" / name).write_text("<!doctype html><p>Ban đầu</p>", encoding="utf-8")
    (first / "src" / "web").mkdir(parents=True)
    shutil.copyfile(ROOT / "src/web/site_assets.py", first / "src/web/site_assets.py")
    refresh_site(first / "docs")
    git(first, "add", ".")
    git(first, "commit", "-qm", "Ban đầu")
    git(first, "push", "-q", "origin", "main")
    git(tmp_path, "clone", "-q", str(remote), str(second))
    git(second, "config", "user.name", "Fixture")
    git(second, "config", "user.email", "fixture@example.test")
    return remote, first, second


def assert_remote(remote, tmp_path):
    target = tmp_path / "published"
    git(tmp_path, "clone", "-q", str(remote), str(target))
    assert check_site(target / "docs") == []
    return target


def test_two_finalized_writers_merge_manifest_and_keep_both_pages(writers, tmp_path):
    remote, first, second = writers
    commit(first, "left.html", "Bot thứ nhất")
    commit(second, "right.html", "Bot thứ hai")
    git(second, "push", "-q", "origin", "main")
    PUSH.push_generated_site(first, "main")
    published = assert_remote(remote, tmp_path)
    assert "Bot thứ nhất" in (published / "docs/left.html").read_text()
    assert "Bot thứ hai" in (published / "docs/right.html").read_text()
    assert git(first, "status", "--porcelain").stdout == ""


def test_clean_rebase_refinalizes_combined_tree(writers, tmp_path):
    remote, first, second = writers
    commit(first, "left.html", "Bot thứ nhất")
    commit(second, "right.html", "Bot cũ chưa chốt", finalize=False)
    git(second, "push", "-q", "origin", "main")
    PUSH.push_generated_site(first, "main")
    published = assert_remote(remote, tmp_path)
    assert "Bot cũ chưa chốt" in (published / "docs/right.html").read_text()


def test_multiple_local_commits_replay_every_manifest_conflict(writers, tmp_path):
    remote, first, second = writers
    commit(first, "left.html", "Bot một lượt đầu")
    commit(first, "race.html", "Bot một lượt sau")
    commit(second, "right.html", "Bot hai")
    git(second, "push", "-q", "origin", "main")
    PUSH.push_generated_site(first, "main")
    published = assert_remote(remote, tmp_path)
    for name, text in (("left.html", "Bot một lượt đầu"), ("race.html", "Bot một lượt sau"), ("right.html", "Bot hai")):
        assert text in (published / "docs" / name).read_text()


def test_manifest_repair_commit_can_become_empty_after_replay(writers, tmp_path):
    remote, first, second = writers
    (first / "docs/assets/release.json").write_text("{}\n", encoding="utf-8")
    git(first, "add", "docs")
    git(first, "commit", "-qm", "Manifest cũ chưa chốt")
    git(first, "push", "-q", "origin", "main")
    git(second, "fetch", "-q", "origin", "main")
    git(second, "reset", "--hard", "origin/main")
    refresh_site(first / "docs")
    git(first, "add", "docs")
    git(first, "commit", "-qm", "Chỉ sửa manifest dẫn xuất")
    commit(second, "right.html", "Remote đã chốt cả gói")
    git(second, "push", "-q", "origin", "main")
    PUSH.push_generated_site(first, "main")
    published = assert_remote(remote, tmp_path)
    assert "Remote đã chốt cả gói" in (published / "docs/right.html").read_text()
    assert git(first, "status", "--porcelain").stdout == ""


def test_push_race_replays_an_empty_generated_correction_safely(writers, tmp_path, monkeypatch):
    remote, first, second = writers
    commit(first, "left.html", "Trang của bot một")
    commit(second, "right.html", "Remote chưa chốt", finalize=False)
    git(second, "push", "-q", "origin", "main")
    original, attempts, skipped = PUSH._git, [], []
    def competing_push(repo, *args, **kwargs):
        if args[:2] == ("rebase", "--skip"):
            skipped.append(1)
        if args[0] == "push":
            attempts.append(1)
            if len(attempts) == 1:
                # Helper vừa tạo commit chỉ sửa manifest sau lần rebase sạch.
                assert "chốt gói trang" in git(first, "log", "-1", "--format=%s").stdout
                commit(second, "right.html", "Remote cập nhật lần hai")
                git(second, "push", "-q", "origin", "main")
        return original(repo, *args, **kwargs)
    monkeypatch.setattr(PUSH, "_git", competing_push)
    PUSH.push_generated_site(first, "main")
    published = assert_remote(remote, tmp_path)
    assert len(attempts) == 2
    assert skipped, "Commit sửa manifest đã trở thành rỗng phải được bỏ an toàn"
    assert "Trang của bot một" in (published / "docs/left.html").read_text()
    assert "Remote cập nhật lần hai" in (published / "docs/right.html").read_text()
    assert git(first, "status", "--porcelain").stdout == ""


def test_conflict_outside_manifest_stops_without_changing_remote(writers):
    remote, first, second = writers
    commit(first, "same.html", "Nội dung bên một")
    original_head = git(first, "rev-parse", "HEAD").stdout
    commit(second, "same.html", "Nội dung bên hai")
    git(second, "push", "-q", "origin", "main")
    before = git(remote, "rev-parse", "main").stdout
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        PUSH.push_generated_site(first, "main")
    assert git(remote, "rev-parse", "main").stdout == before
    assert git(first, "rev-parse", "HEAD").stdout == original_head
    assert git(first, "status", "--porcelain").stdout == ""
    assert "Nội dung bên một" in (first / "docs/same.html").read_text()


def test_dirty_tree_is_rejected_before_fetch_or_push(writers):
    remote, first, _ = writers
    (first / "docs/left.html").write_text("Chưa commit", encoding="utf-8")
    before = git(remote, "rev-parse", "main").stdout
    with pytest.raises(RuntimeError, match="chưa sạch"):
        PUSH.push_generated_site(first, "main")
    assert git(remote, "rev-parse", "main").stdout == before
    assert (first / "docs/left.html").read_text() == "Chưa commit"


@pytest.mark.parametrize("races", [1, 3])
def test_push_race_retries_only_three_times(writers, tmp_path, monkeypatch, races):
    remote, first, second = writers
    commit(first, "left.html", "Thay đổi cần giữ")
    original, attempts = PUSH._git, []
    def competing_push(repo, *args, **kwargs):
        if args[0] == "push":
            attempts.append(1)
            if len(attempts) <= races:
                git(second, "fetch", "-q", "origin", "main")
                git(second, "reset", "--hard", "origin/main")
                commit(second, "race.html", f"Lượt chen {len(attempts)}")
                git(second, "push", "-q", "origin", "main")
        return original(repo, *args, **kwargs)
    monkeypatch.setattr(PUSH, "_git", competing_push)
    if races == 3:
        with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
            PUSH.push_generated_site(first, "main")
        assert len(attempts) == 3
    else:
        PUSH.push_generated_site(first, "main")
        assert len(attempts) == 2
        published = assert_remote(remote, tmp_path)
        assert "Thay đổi cần giữ" in (published / "docs/left.html").read_text()
        assert "Lượt chen 1" in (published / "docs/race.html").read_text()


def test_push_failure_without_remote_advancement_is_not_retried(writers, monkeypatch):
    remote, first, _ = writers
    commit(first, "left.html", "Thay đổi")
    original, attempts = PUSH._git, []
    def unavailable(repo, *args, **kwargs):
        if args[0] == "push":
            attempts.append(1)
            return subprocess.CompletedProcess(["git", *args], 128, "", "network failed")
        return original(repo, *args, **kwargs)
    monkeypatch.setattr(PUSH, "_git", unavailable)
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        PUSH.push_generated_site(first, "main")
    assert len(attempts) == 1


def test_auth_failure_is_not_retried_even_when_remote_advances(writers, monkeypatch):
    remote, first, second = writers
    commit(first, "left.html", "Thay đổi")
    original, attempts = PUSH._git, []
    def denied(repo, *args, **kwargs):
        if args[0] == "push":
            attempts.append(1)
            commit(second, "right.html", "Remote tiến lên")
            git(second, "push", "-q", "origin", "main")
            return subprocess.CompletedProcess(["git", *args], 128, "", "Authentication failed")
        return original(repo, *args, **kwargs)
    monkeypatch.setattr(PUSH, "_git", denied)
    with pytest.raises(subprocess.CalledProcessError):
        PUSH.push_generated_site(first, "main")
    assert len(attempts) == 1


def test_shallow_clone_can_rebase_onto_advanced_remote(writers, tmp_path):
    remote, first, second = writers
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth=1", remote.as_uri(), str(shallow))
    git(shallow, "config", "user.name", "Fixture")
    git(shallow, "config", "user.email", "fixture@example.test")
    assert git(shallow, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    commit(shallow, "left.html", "Bot shallow")
    commit(second, "right.html", "Bot remote")
    git(second, "push", "-q", "origin", "main")
    PUSH.push_generated_site(shallow, "main")
    published = assert_remote(remote, tmp_path)
    assert "Bot shallow" in (published / "docs/left.html").read_text()
    assert "Bot remote" in (published / "docs/right.html").read_text()
