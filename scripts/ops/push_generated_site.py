"""Đẩy trang dẫn xuất, chỉ tự dựng lại manifest khi hai bot cùng cập nhật."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

MANIFEST = "docs/assets/release.json"


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=check, capture_output=True, text=True,
        env={**os.environ, "GIT_EDITOR": "true", "GIT_TERMINAL_PROMPT": "0"},
    )


def _raise(result: subprocess.CompletedProcess[str]) -> None:
    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)


def _refresh(root: Path) -> None:
    subprocess.run(
        [sys.executable, "src/site_assets.py", "--refresh", "docs", "--check"],
        cwd=root, check=True,
    )


def _stage(root: Path) -> None:
    _git(root, "add", "--", "docs/*.html", "docs/assets")


def _fetch(root: Path, branch: str) -> str:
    _git(root, "fetch", "--no-tags", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}")
    return _git(root, "rev-parse", f"refs/remotes/origin/{branch}").stdout.strip()


def _rebase(root: Path, branch: str) -> None:
    result = _git(root, "rebase", f"refs/remotes/origin/{branch}", check=False)
    while result.returncode:
        unresolved = set(filter(None, _git(root, "diff", "--name-only", "--diff-filter=U", "-z").stdout.split("\0")))
        if unresolved != {MANIFEST}:
            _git(root, "rebase", "--abort")
            raise RuntimeError("Dừng hợp nhất: xung đột không chỉ ở manifest: " + ", ".join(sorted(unresolved)))
        try:
            _refresh(root)
            _stage(root)
            # Chỉ bỏ commit dẫn xuất khi sau dựng lại, index thật sự rỗng.
            empty = _git(root, "diff", "--cached", "--quiet", check=False).returncode == 0
            result = _git(root, "rebase", "--skip" if empty else "--continue", check=False)
        except Exception:
            _git(root, "rebase", "--abort")
            raise


def push_generated_site(root: Path, branch: str) -> None:
    """Chốt gói sau rebase; chỉ thử lại tối đa ba lần khi remote tiến lên."""
    root = root.resolve()
    _git(root, "check-ref-format", f"refs/heads/{branch}")
    if _git(root, "status", "--porcelain").stdout:
        raise RuntimeError("Cây làm việc chưa sạch; cần commit trước khi đẩy gói trang.")
    for state in ("rebase-merge", "rebase-apply", "MERGE_HEAD"):
        location = _git(root, "rev-parse", "--git-path", state).stdout.strip()
        if (root / location).exists():
            raise RuntimeError("Đang có thao tác git chưa hoàn tất: " + state)
    if _git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        # Checkout một commit chưa có đủ tổ tiên để xác định đúng điểm rebase.
        _git(root, "fetch", "--no-tags", "--unshallow", "origin", branch)
    for attempt in range(3):
        before = _fetch(root, branch)
        _rebase(root, branch)
        # Một lần ghép sạch vẫn có thể giữ manifest của một cây chưa ghép.
        _refresh(root)
        _stage(root)
        if _git(root, "diff", "--cached", "--quiet", check=False).returncode:
            _git(root, "commit", "-m", "chore: chốt gói trang sau hợp nhất")
        pushed = _git(root, "push", "--porcelain", "origin", f"HEAD:refs/heads/{branch}", check=False)
        if pushed.returncode == 0:
            return
        # Lỗi mạng, xác thực và hook không phải tín hiệu để thử lại.
        rejected = "[rejected]" in pushed.stdout and any(
            reason in pushed.stdout for reason in ("(fetch first)", "(non-fast-forward)")
        )
        if not rejected:
            _raise(pushed)
        after = _fetch(root, branch)
        advanced = after != before and _git(root, "merge-base", "--is-ancestor", before, after, check=False).returncode == 0
        if not advanced or attempt == 2:
            _raise(pushed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()
    try:
        root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip())
        push_generated_site(root, args.branch)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        parser.exit(1, (detail or str(exc)) + "\n")


if __name__ == "__main__":
    main()
