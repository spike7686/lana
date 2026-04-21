from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Lana Project API"
    app_env: str = "dev"
    debug: bool = True
    database_url: str = "postgresql+psycopg://lana:lana@localhost:5432/lana_dev"
    binance_fapi_base_url: str = "https://fapi.binance.com"
    binance_http_timeout_seconds: float = 20.0
    coingecko_api_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_http_timeout_seconds: float = 20.0
    scheduler_enabled: bool = True
    scheduler_timezone: str = "UTC"
    scheduler_interval_minutes: int = 15
    scheduler_run_on_startup: bool = False
    scheduler_step_retry_count: int = 2
    scheduler_step_retry_delay_seconds: float = 1.5
    gap_check_enabled: bool = True
    gap_check_hours: int = 24
    gap_check_max_symbols: int = 300
    gap_check_hour: int = 0
    gap_check_minute: int = 20
    auto_pool_binance_min_quote_volume: float = 10_000_000
    auto_pool_candidate_max_from_sources: int = 100
    auto_pool_cooldown_hours: int = 24
    auto_init_new_symbols: bool = True
    auto_init_days: int = 30
    auto_init_max_symbols_per_cycle: int = 5
    cors_allow_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
