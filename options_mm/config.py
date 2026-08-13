from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMM_")

    project_name: str = "Options Market Maker Simulator"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    data_dir: Path = Path("data")

    # Default simulation parameters
    default_underlying: str = "SPY"
    default_spot: float = 500.0
    default_volatility: float = 0.20
    default_risk_free_rate: float = 0.045
    default_dividend_yield: float = 0.0
    tick_size: float = 0.01
    lot_size: int = 1

    # Time parameters
    trading_days_per_year: int = 252
    trading_hours_per_day: float = 6.5
    steps_per_hour: int = 12


settings = Settings()
