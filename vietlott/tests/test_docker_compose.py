from __future__ import annotations

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
IMAGE_OWNED = "/app"


def job_write_problems(service: dict) -> list[str]:
    problems = []
    mounts = [str(v).split(":", 1)[0] for v in service.get("volumes") or []]
    if not any(m.startswith((".", "/")) for m in mounts):
        return problems
    user = str(service.get("user", ""))
    if "${VQE_UID" not in user or "${VQE_GID" not in user:
        problems.append(f"user={user!r}: phải chạy bằng VQE_UID/VQE_GID của host")
    env = service.get("environment") or {}
    for key in ("VQE_DATA_DIR", "HOME"):
        value = str(env.get(key, ""))
        if not value.startswith("/tmp"):
            problems.append(f"{key}={value!r}: UID của host không ghi được ngoài /tmp")
    return problems


def test_the_backtest_job_writes_as_the_host_user() -> None:
    service = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["backtest"]
    assert job_write_problems(service) == []


def test_the_rule_itself_catches_the_original_layout() -> None:
    original = {"environment": {"VQE_DATA_DIR": f"{IMAGE_OWNED}/jobdata"}, "volumes": ["./reports:/app/reports"]}
    assert len(job_write_problems(original)) == 3
    assert job_write_problems({"volumes": ["vqe-data:/app/data"]}) == []
