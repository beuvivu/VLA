"""Mặc định an toàn của API: CORS đóng, lệnh ghi cần token khi được đặt, cổng chỉ ở loopback.

Trước đây CORS là "*" và không có xác thực nào, nên bất kỳ trang web nào người dùng
đang mở cũng gọi được /sync, /fit hay ?record=true vào API chạy trên máy họ. Với
?record=true và POST thân rỗng, CORS chặt cũng không đủ: trình duyệt vẫn GỬI một
"simple request" dù không cho đọc phản hồi. Đầu mục Authorization buộc preflight.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from vietlott_engine.api.main import create_app
from vietlott_engine.core.config import Settings
from vietlott_engine.core.games import MEGA_645
from vietlott_engine.core.models import Draw
from vietlott_engine.crawler.storage import InMemoryRepository
from tests.conftest import make_history

TOKEN = "s3cret-token-for-tests"
EVIL = "https://evil.example"


def _repo() -> InMemoryRepository:
    repo = InMemoryRepository()
    h = make_history(MEGA_645, 120, seed=5)
    repo.upsert(
        Draw(game=MEGA_645.code, draw_id=i + 1, draw_date=str(h.dates[i]), numbers=tuple(int(x) for x in h.numbers[i]))
        for i in range(len(h))
    )
    return repo


@pytest.fixture()
def guarded() -> TestClient:
    with TestClient(create_app(Settings(storage_backend="memory", api_token=TOKEN), repository=_repo())) as c:
        yield c


@pytest.fixture()
def default() -> TestClient:
    with TestClient(create_app(Settings(storage_backend="memory"), repository=_repo())) as c:
        yield c


EV = ("/games/mega645/ev", {"ticket": [3, 17, 22, 35, 41, 44], "jackpot1": 45e9})


def test_without_a_configured_token_requests_behave_as_before(default: TestClient) -> None:
    assert default.post(EV[0], json=EV[1]).status_code == 200


def test_with_a_token_writes_need_it_and_reads_do_not(guarded: TestClient) -> None:
    assert guarded.get("/health").status_code == 200
    assert guarded.post(EV[0], json=EV[1]).status_code == 401
    assert guarded.post(EV[0], json=EV[1], headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert guarded.post(EV[0], json=EV[1], headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_record_true_is_a_write_even_though_it_is_a_get(guarded: TestClient) -> None:
    assert guarded.get("/forecast/mega645?record=true").status_code == 401
    assert guarded.get("/forecast/mega645?record=TRUE").status_code == 401


def test_a_bodyless_cross_site_post_to_sync_is_refused(guarded: TestClient) -> None:
    response = guarded.post("/games/mega645/prizes/sync", headers={"Origin": EVIL})
    assert response.status_code == 401


def test_cors_is_closed_by_default(default: TestClient) -> None:
    response = default.get("/health", headers={"Origin": EVIL})
    assert "access-control-allow-origin" not in response.headers


def test_cors_opens_only_to_configured_origins() -> None:
    settings = Settings(storage_backend="memory", cors_origins=["https://ok.example"])
    with TestClient(create_app(settings, repository=_repo())) as c:
        assert c.get("/health", headers={"Origin": "https://ok.example"}).headers.get(
            "access-control-allow-origin") == "https://ok.example"
        assert "access-control-allow-origin" not in c.get("/health", headers={"Origin": EVIL}).headers


def test_docker_publishes_the_api_on_loopback_only() -> None:
    compose = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8"))
    ports = [str(p) for p in compose["services"]["api"]["ports"]]
    assert ports and all(p.startswith("127.0.0.1:") for p in ports), ports
