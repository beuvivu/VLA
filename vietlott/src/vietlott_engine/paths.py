"""Where the project lives on disk.

Settings use paths relative to the project folder (``data/``, ``data/seed``, ``reports/``). The
``vietlott`` command can be started from anywhere: it moves to the project folder first, found as

1. ``VQE_HOME`` if set;
2. the current folder or one of its parents that holds the project (``pyproject.toml``,
   ``data/seed`` and ``src/vietlott_engine``);
3. the folder the package was installed from (``pip install -e .``), when it is the project.

Otherwise it stays where it is (a container sets absolute ``VQE_*`` paths instead).
"""

from __future__ import annotations

import os
from pathlib import Path


def _is_project(d: Path) -> bool:
    return (d / "data" / "seed").is_dir() and (d / "pyproject.toml").is_file() and (d / "src" / "vietlott_engine").is_dir()


def project_root() -> Path | None:
    env = os.environ.get("VQE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        if _is_project(d):
            return d
    installed = Path(__file__).resolve().parents[2]  # src/vietlott_engine/paths.py → project folder
    return installed if _is_project(installed) else None


def enter_project() -> Path:
    """chdir to the project folder when one is found; returns the working folder."""
    root = project_root()
    if root is not None and root != Path.cwd().resolve():
        os.chdir(root)
    return Path.cwd()
