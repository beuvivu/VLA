from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vietlott_engine.core import config as _config
from vietlott_engine.core.games import MEGA_645, POWER_655, GameSpec
from vietlott_engine.core.history import DrawHistory


@pytest.fixture(scope="session", autouse=True)
def _ignore_local_dotenv():  # type: ignore[no-untyped-def]
    """Disable installer .env files before module-scoped clients are created."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(_config.Settings.model_config, "env_file", None)
        # Offline tests opt out of the production background crawler.
        patch.setenv('VQE_AUTO_UPDATE_ENABLED', 'false')
        patch.setenv('VQE_ML_AUTO_UPDATE_ENABLED', 'false')
        _config.get_settings.cache_clear()
        yield
        _config.get_settings.cache_clear()


PROJECT = Path(__file__).resolve().parents[1]


def find_workflows(project: Path = PROJECT) -> dict[str, Path]:
    """Workflow của engine theo TÊN GỐC (``ci.yml``, ``update.yml``…), ở cả hai cách bố trí.

    * Kho riêng: ``<dự án>/.github/workflows/*.yml``.
    * Nằm trong kho khác (VLA chép engine vào thư mục con ``vietlott/``): GitHub chỉ
      đọc workflow ở gốc kho, nên chúng nằm ở ``<kho>/.github/workflows/vlm-*.yml``;
      bỏ tiền tố ``vlm-`` để các phép kiểm vẫn hỏi đúng tên gốc.
    """
    own = project / ".github" / "workflows"
    if own.is_dir():
        return {p.name: p for p in own.glob("*.yml")}
    host = project.parent / ".github" / "workflows"
    return {p.name.removeprefix("vlm-"): p for p in host.glob("vlm-*.yml")}


@pytest.fixture
def workflow_files() -> dict[str, Path]:
    return find_workflows()


def make_history(spec: GameSpec, draws: int, seed: int = 0, weights: np.ndarray | None = None) -> DrawHistory:
    """Synthetic history; ``weights`` (n,) plants a per-number bias (Plackett–Luce sampling)."""
    rng = np.random.default_rng(seed)
    n, k = spec.pool_size, spec.pick
    if weights is None:
        nums = np.argpartition(rng.random((draws, n)), k, axis=1)[:, :k] + 1
    else:
        g = np.log(weights)[None, :] + rng.gumbel(size=(draws, n))
        nums = np.argpartition(-g, k, axis=1)[:, :k] + 1
    bonus = None
    if spec.separate_special:
        bonus = rng.integers(1, int(spec.bonus_pool_size or 1) + 1, draws)
    elif spec.has_bonus:
        bonus = np.array([rng.choice(np.setdiff1d(np.arange(1, n + 1), row)) for row in nums])
    return DrawHistory.from_arrays(spec, nums, bonus=bonus)


@pytest.fixture
def mega_history() -> DrawHistory:
    return make_history(MEGA_645, 800, seed=1)


@pytest.fixture
def power_history() -> DrawHistory:
    return make_history(POWER_655, 800, seed=2)
