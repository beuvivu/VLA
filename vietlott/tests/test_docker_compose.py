"""Job ``backtest`` của docker-compose phải ghi được ``./reports`` trên Docker Linux gốc.

Bind mount giữ NGUYÊN chủ và quyền của thư mục trên host (thường 0755, chủ là
người dùng host), còn image chạy ``USER vqe`` (UID 10001). Trước đây job dừng ngay
ở ``vietlott market --out /app/reports/calibration`` với ``PermissionError``. Đã
tái hiện và kiểm bản sửa trên Docker thật: job chạy bằng UID của host, và mọi thứ
khác nó ghi nằm dưới ``/tmp``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
IMAGE_OWNED = "/app"  # ``chown -R vqe:vqe /app`` trong Dockerfile: chỉ UID 10001 ghi được


def job_write_problems(service: dict) -> list[str]:
    """Lý do một job có bind mount sẽ không ghi được khi chạy bằng UID của host."""
    problems = []
    mounts = [str(v).split(":", 1)[0] for v in service.get("volumes") or []]
    if not any(m.startswith((".", "/")) for m in mounts):
        return problems  # không bind mount thư mục host: quyền của image là đủ
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
    """Ghim chính LUẬT trên bố cục cũ đã gây lỗi: quét tệp thật có thể không bao giờ đỏ."""
    original = {"environment": {"VQE_DATA_DIR": f"{IMAGE_OWNED}/jobdata"}, "volumes": ["./reports:/app/reports"]}
    assert len(job_write_problems(original)) == 3
    assert job_write_problems({"volumes": ["vqe-data:/app/data"]}) == []
