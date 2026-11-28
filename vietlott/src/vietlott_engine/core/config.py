from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VQE_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    duckdb_file: str = "vietlott.duckdb"
    parquet_subdir: str = "parquet"

    http_backend: Literal["httpx", "curl_cffi"] = "httpx"
    source: Literal["github_mirror", "vietlott", "file", "nhanaz", "xskt", "v130", "auto"] = "github_mirror"
    github_mirror_base_url: str = "https://raw.githubusercontent.com/vietvudanh/vietlott-data/main/data"
    prize_winners_base_url: str = "https://raw.githubusercontent.com/Compal123/vietlot-ai/main/data"
    prize_power_history_url: str = "https://raw.githubusercontent.com/leoodz/vn-vietlott/main/results/power6x55.json"
    vietlott_base_url: str = "https://www.vietlott.vn"
    vietlott_cookie_bootstrap: bool = True
    canonical_base_url: str = "https://raw.githubusercontent.com/pqminh-4/vietlott-data/main/data/canonical"
    product_mirror_base_url: str = "https://raw.githubusercontent.com/vietvudanh/vietlott-data/main/data"
    nhanaz_base_url: str = "https://raw.githubusercontent.com/NhanAZ-Data/vietlott-data-collector/datasets/datasets"
    xskt_base_url: str = "https://xskt.com.vn"
    nhanaz_dir: Path | None = None
    v130_dir: Path | None = None
    fallback_order: list[str] = ["vietlott", "nhanaz", "xskt", "github_mirror", "v130"]
    http_timeout_s: float = 20.0
    max_retries: int = 5
    backoff_base_s: float = 0.5
    backoff_max_s: float = 30.0
    rate_limit_per_s: float = 2.0
    rate_limit_burst: int = 2
    max_concurrency: int = 4
    official_max_pages: int = 400
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) VietlottQuantEngine/1.0"

    default_decay: float = 1.0
    monte_carlo_sims: int = 1000
    random_seed: int = 20260930

    quick_pick_share: float = Field(default=0.35, ge=0.0, le=1.0)
    default_tickets_sold: int = 1_500_000
    calibration_dir: Path = Path("data/calibration")
    anchors_file: Path = Path("data/seed/jackpot_anchors.json")
    forecast_dir: Path | None = None
    product_seed_dir: Path = Path("data/seed")
    product_sync_max_pages: int = 50

    api_title: str = "Vietlott Quant Engine"
    cors_origins: list[str] = []
    api_token: str | None = None
    max_backtest_strategies: int = 8
    max_backtest_tickets: int = 50
    sync_on_startup: bool = False
    auto_update_enabled: bool = True
    auto_update_timeout_s: float = Field(default=180, gt=0)
    auto_update_dir: Path | None = None
    source_timeout_s: float = Field(default=20, gt=0)
    archive_timeout_s: float = Field(default=90, gt=0)
    ml_auto_update_enabled: bool = True
    ml_bootstrap: int = Field(default=1000, ge=1, le=1000)
    ml_learning_timeout_s: float = Field(default=180, gt=0)
    ml_tree_every: int = Field(default=64, ge=1, le=1000)
    ml_search_nodes: int = Field(default=1000, ge=1, le=20000)
    ml_backends: list[Literal['rf', 'xgb', 'lgb']] = ['rf']
    ml_adaptive: bool = False
    ml_multi_agent: bool = True
    ml_patterns: bool = False
    storage_backend: Literal["duckdb", "memory"] = "duckdb"
    seed_file_dir: Path | None = None
    log_level: str = "INFO"
    log_json: bool = False

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / self.duckdb_file

    @property
    def parquet_dir(self) -> Path:
        return self.data_dir / self.parquet_subdir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
