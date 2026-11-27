from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed"


def test_project_root_is_found_from_anywhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vietlott_engine.paths import enter_project, project_root

    monkeypatch.delenv("VQE_HOME", raising=False)
    monkeypatch.chdir(ROOT / "tests")
    assert project_root() == ROOT
    monkeypatch.chdir(tmp_path)
    assert project_root() == ROOT
    assert enter_project() == ROOT and Path.cwd() == ROOT
    monkeypatch.setenv("VQE_HOME", str(tmp_path))
    assert project_root() == tmp_path.resolve()


def test_version_and_help() -> None:
    from vietlott_engine import __version__
    from vietlott_engine.cli import build_parser

    text = build_parser().format_help()
    assert __version__ == "4.0.0" and "init" in text and "doctor" in text and "forecast" in text
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["--version"])
    assert e.value.code == 0


def test_local_runs_keep_their_own_ledger() -> None:
    assert "\nVQE_FORECAST_DIR=data/local/forecast\n" in (ROOT / ".env.example").read_text(encoding="utf-8")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/local/" in ignored and "!data/forecast/ledger.jsonl" in ignored


def test_workflows_reference_real_commands(workflow_files: dict[str, Path]) -> None:
    yaml = pytest.importorskip("yaml")
    wf = {name: yaml.safe_load(p.read_text(encoding="utf-8")) for name, p in workflow_files.items()}
    assert {"ci.yml", "update.yml"} <= set(wf)
    names = [s.get("name", "") for s in wf["update.yml"]["jobs"]["update"]["steps"]]
    assert names.index("Ghi sổ dự báo vào repo") < names.index("Dựng trang")
    steps = " ".join(str(s.get("run", "")) for job in wf["update.yml"]["jobs"].values() for s in job.get("steps", []))
    for command in ("vietlott init", "vietlott sync", "vietlott products sync", "vietlott forecast next", "scripts/build_site.py"):
        assert command in steps
    assert (ROOT / "scripts" / "build_site.py").exists()


def test_site_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vietlott_engine.forecast.data import load_series
    from vietlott_engine.forecast.engine import Forecaster, record, state_path

    fdir = tmp_path / "forecast"
    for code in ("max3dpro", "lotto535"):
        f = Forecaster(code)
        f.update(load_series(code, seed_dir=SEED))
        f.save(state_path(fdir, f.product))
        if code == "max3dpro":
            record(fdir, f.forecast())
    out = tmp_path / "site"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py"), "--out", str(out), "--dir", str(fdir)], capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")])})
    assert r.returncode == 0, r.stderr
    page = (out / "forecast.html").read_text(encoding="utf-8")
    assert '<html lang="vi">' in page and "Max 3D Pro" in page and "Lotto 5/35" in page
    assert (out / "index.html").exists() and (out / "data" / "dashboard.json").exists()
    summary = json.loads((out / "data" / "summary.json").read_text(encoding="utf-8"))
    assert [p["product"] for p in summary["products"]] == ["lotto535", "max3dpro"]
    assert summary["products"][1]["evidence_found"] is True
    assert (out / "data" / "ledger.jsonl").exists() and (out / "data" / "forecast" / "max3dpro.json").exists() and (out / ".nojekyll").exists()


def test_serve_refuses_more_than_one_worker(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import uvicorn

    from vietlott_engine import cli

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: pytest.fail("không được khởi động server"))
    assert cli.main(["serve", "--workers", "2"]) == 2
    assert "--workers phải là 1" in capsys.readouterr().err
    started = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(k["workers"]))
    assert cli.main(["serve"]) == 0 and started == [1]


def test_audit_resolves_defaults_inside_the_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vlm.tools import gap_analyzer

    seen: dict[str, Path] = {}

    async def fake_run(args):  # type: ignore[no-untyped-def]
        seen["cwd"] = Path.cwd()
        seen["seed"] = args.seed_dir.resolve()
        return 0

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VQE_HOME", str(ROOT))
    monkeypatch.setattr(gap_analyzer, "_run", fake_run)
    assert gap_analyzer.main(["--game", "mega645"]) == 0
    assert seen["cwd"] == ROOT.resolve() and seen["seed"] == SEED.resolve()


def _requirement_lines(path: Path) -> list[str]:
    lines = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("-r")]


def test_requirements_files_say_the_same_as_pyproject() -> None:
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert _requirement_lines(ROOT / "requirements.txt") == project["dependencies"]
    assert _requirement_lines(ROOT / "requirements-dev.txt") == project["optional-dependencies"]["dev"]
