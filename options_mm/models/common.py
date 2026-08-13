from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Side(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class Greeks(BaseModel):
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    rho: float = 0.0
    vanna: float = 0.0
    volga: float = 0.0

    def scale(self, qty: float) -> "Greeks":
        return Greeks(
            delta=self.delta * qty,
            gamma=self.gamma * qty,
            vega=self.vega * qty,
            theta=self.theta * qty,
            rho=self.rho * qty,
            vanna=self.vanna * qty,
            volga=self.volga * qty,
        )

    def __add__(self, other: "Greeks") -> "Greeks":
        return Greeks(
            delta=self.delta + other.delta,
            gamma=self.gamma + other.gamma,
            vega=self.vega + other.vega,
            theta=self.theta + other.theta,
            rho=self.rho + other.rho,
            vanna=self.vanna + other.vanna,
            volga=self.volga + other.volga,
        )


class Quote(BaseModel):
    bid: float = 0.0
    bid_qty: int = 0
    ask: float = 0.0
    ask_qty: int = 0
    spread: float = 0.0
    mid: float = 0.0


class Instrument(BaseModel):
    id: str
    name: str
    expiry: str
    strike: float
    option_type: OptionType
    underlying: str = "SPY"


class Option(Instrument):
    tte: float = 0.0  # years
    theoretical: float = 0.0
    implied_vol: float = 0.0
    quote: Quote = Field(default_factory=Quote)
    user_bid: float = 0.0
    user_ask: float = 0.0
    user_bid_qty: int = 0
    user_ask_qty: int = 0
    market_bid: float = 0.0
    market_ask: float = 0.0
    market_bid_qty: int = 0
    market_ask_qty: int = 0
    position: int = 0
    greeks: Greeks = Field(default_factory=Greeks)


class Future(BaseModel):
    symbol: str = "SPY"
    price: float = 500.0
    quote: Quote = Field(default_factory=Quote)


class Position(BaseModel):
    instrument_id: str
    qty: int = 0
    avg_price: float = 0.0
    market_price: float = 0.0
    unrealized_pnl: float = 0.0
    greeks: Greeks = Field(default_factory=Greeks)


class Trade(BaseModel):
    id: str
    timestamp: str
    instrument_id: str
    side: str  # BUY / SELL
    qty: int
    price: float
    counterparty: str
    total: float = 0.0
    pnl_impact: float = 0.0


class ComboLeg(BaseModel):
    instrument_id: str
    ratio: int = 1  # positive long, negative short


class Combo(BaseModel):
    id: str
    name: str
    legs: list[ComboLeg]
    theoretical: float = 0.0
    quote: Quote = Field(default_factory=Quote)


class SimulationState(BaseModel):
    running: bool = False
    paused: bool = False
    step: int = 0
    total_steps: int = 44
    start_time: str | None = None
    end_time: str | None = None
    remaining_warning: bool = False


class VolCurvePoint(BaseModel):
    delta: float
    vol: float
    strike: float
    option_type: OptionType


class MarketState(BaseModel):
    timestamp: str = ""
    spot: float = 500.0
    r: float = 0.045
    atm_vol: float = 0.20
    skew: float = 0.0
    call_wing: float = 0.0
    put_wing: float = 0.0
    days_to_expiry: float = 30.0
    increment_mode: str = "penny"  # penny or eighth
    simulation: SimulationState = Field(default_factory=SimulationState)


class PortfolioState(BaseModel):
    cash: float = 1_000_000.0
    margin: float = 0.0
    positions: dict[str, Position] = Field(default_factory=dict)
    trades: list[Trade] = Field(default_factory=list)
    total_greeks: Greeks = Field(default_factory=Greeks)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0


class RiskPoint(BaseModel):
    shock_pct: float
    spot: float
    portfolio_value: float
    pnl: float
    delta: float
    gamma: float
    vega: float
    theta: float


class StrategyConfig(BaseModel):
    quote_edge: float = 0.05
    quote_size: int = 26
    skew_limit: int = 3
    delta_hedge_threshold: float = 50.0
    auto_hedge: bool = False
    adverse_selection_model: bool = False


class SimulationConfig(BaseModel):
    total_steps: int = 44
    step_delay_ms: int = 1000
    vol_drift: float = 0.0
    shock_frequency: float = 0.05
    customer_flow_intensity: float = 0.3
    competitor_sharpness: float = 0.5
    tick_size: float = 0.01
    trading_days_per_year: int = 252
    trading_hours_per_day: float = 6.5
    steps_per_hour: int = 12


__all__ = [
    "Side",
    "OptionType",
    "Greeks",
    "Quote",
    "Instrument",
    "Option",
    "Future",
    "Position",
    "Trade",
    "ComboLeg",
    "Combo",
    "SimulationState",
    "VolCurvePoint",
    "MarketState",
    "PortfolioState",
    "RiskPoint",
    "StrategyConfig",
    "SimulationConfig",
]
