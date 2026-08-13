import math
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np

from options_mm.market.exchange import Exchange
from options_mm.market.option_chain import build_chain, build_combos
from options_mm.models.common import (
    Combo,
    Future,
    Greeks,
    MarketState,
    Option,
    OptionType,
    PortfolioState,
    Position,
    RiskPoint,
    SimulationConfig,
    StrategyConfig,
    Trade,
    VolCurvePoint,
)
from options_mm.pricing.black_scholes import greeks, mark_option, price, vol_surface


class SimulationEngine:
    def __init__(
        self,
        spot: float = 500.0,
        r: float = 0.045,
        atm_vol: float = 0.20,
        days_to_expiry: float = 30.0,
        underlying: str = "SPY",
    ) -> None:
        self.underlying = underlying
        self.spot = spot
        self.r = r
        self.atm_vol = atm_vol
        self.skew = 0.0
        self.call_wing = 0.0
        self.put_wing = 0.0
        self.days_to_expiry = days_to_expiry
        self.market = MarketState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            spot=spot,
            r=r,
            atm_vol=atm_vol,
            days_to_expiry=days_to_expiry,
        )
        self.portfolio = PortfolioState()
        self.options: list[Option] = []
        self.combos: list[Combo] = []
        self.exchange = Exchange(tick_size=0.01)
        self.future = Future(symbol=underlying, price=spot)
        self.config = SimulationConfig()
        self.strategy = StrategyConfig()
        self.last_step_time = time.time()
        self.history_spot: list[tuple[str, float]] = []
        self.history_vol: list[tuple[str, float]] = []
        self._refresh_chain()

    def _refresh_chain(self) -> None:
        self.options = build_chain(
            spot=self.spot,
            r=self.r,
            atm_vol=self.atm_vol,
            skew=self.skew,
            call_wing=self.call_wing,
            put_wing=self.put_wing,
            days_to_expiry=self.days_to_expiry,
            underlying=self.underlying,
            min_strike=0,
            max_strike=0,
            step=10.0,
        )
        self.combos = build_combos(self.options, self.underlying)
        for opt in self.options:
            self.exchange.cancel_agent(opt.id, "USER")
            self.exchange.cancel_agent(opt.id, "BOT")
        self._quote_all()

    def _quote_all(self) -> None:
        for opt in self.options:
            bid = self._to_increment(opt.theoretical * 0.995)
            ask = self._to_increment(opt.theoretical * 1.005)
            self.exchange.add(opt.id, "USER", "BUY", bid, self.strategy.quote_size)
            self.exchange.add(opt.id, "USER", "SELL", ask, self.strategy.quote_size)

    def _to_increment(self, price: float) -> float:
        if self.market.increment_mode == "eighth":
            return round(price * 8) / 8.0
        return round(price / 0.01) * 0.01

    def _update_market_state(self) -> None:
        self.market.timestamp = datetime.now(timezone.utc).isoformat()
        self.market.spot = self.spot
        self.market.r = self.r
        self.market.atm_vol = self.atm_vol
        self.market.skew = self.skew
        self.market.call_wing = self.call_wing
        self.market.put_wing = self.put_wing
        self.market.days_to_expiry = self.days_to_expiry

    def _mark_options(self) -> None:
        T = max(0.001, self.days_to_expiry / 365.0)
        for opt in self.options:
            mark_option(opt, self.spot, self.r, T)

    def _position_key(self, instrument_id: str) -> str:
        return instrument_id

    def _apply_trade(self, t: Trade, mark_price: float, user_side: str | None = None) -> None:
        if user_side is None:
            user_side = t.side
        key = self._position_key(t.instrument_id)
        pos = self.portfolio.positions.get(key) or Position(
            instrument_id=t.instrument_id, qty=0, avg_price=0.0, market_price=mark_price
        )
        user_qty = t.qty if user_side == "BUY" else -t.qty
        old_qty = pos.qty
        new_qty = old_qty + user_qty
        total_cost = pos.avg_price * old_qty + user_qty * t.price
        if abs(new_qty) > 1e-9:
            pos.avg_price = total_cost / new_qty
        else:
            pos.avg_price = 0.0
        pos.qty = new_qty
        pos.market_price = mark_price
        # Cash changes when user pays (BUY) or receives (SELL)
        self.portfolio.cash -= user_qty * t.price
        self.portfolio.positions[key] = pos
        self.portfolio.trades.append(t)

    def _mark_portfolio(self) -> None:
        position_value = 0.0
        for pos in self.portfolio.positions.values():
            if pos.instrument_id == self.future.symbol:
                pos.market_price = self.spot
                pos.greeks = Greeks(delta=pos.qty)
                position_value += pos.qty * self.spot
            else:
                opt = next((o for o in self.options if o.id == pos.instrument_id), None)
                if opt:
                    pos.market_price = opt.theoretical
                    pos.greeks = opt.greeks.scale(pos.qty)
                    position_value += pos.qty * opt.theoretical
                else:
                    pos.greeks = Greeks()
        self.portfolio.total_greeks = sum(
            [pos.greeks for pos in self.portfolio.positions.values()],
            Greeks(),
        )
        self.portfolio.unrealized_pnl = position_value
        self.portfolio.total_pnl = self.portfolio.cash + position_value - 1_000_000.0

    def user_quote(self, instrument_id: str, bid: float, bid_qty: int, ask: float, ask_qty: int) -> None:
        book = self.exchange.book(instrument_id)
        book.cancel_by_agent("USER")
        if bid_qty > 0:
            self.exchange.add(instrument_id, "USER", "BUY", bid, bid_qty)
        if ask_qty > 0:
            self.exchange.add(instrument_id, "USER", "SELL", ask, ask_qty)

    def user_market_order(self, instrument_id: str, side: str, qty: int) -> list[Trade]:
        trades = self.exchange.market(instrument_id, "USER_TAKER", side, qty)
        for t in trades:
            self._apply_trade(t, self._mark_price(t.instrument_id))
        self._mark_portfolio()
        return trades

    def _mark_price(self, instrument_id: str) -> float:
        if instrument_id == self.future.symbol:
            return self.spot
        opt = next((o for o in self.options if o.id == instrument_id), None)
        return opt.theoretical if opt else 0.0

    def step(self) -> None:
        if not self.market.simulation.running or self.market.simulation.paused:
            return
        self._gbm_step()
        self._refresh_chain()
        self._bot_flow()
        self._simulation_counter()

    def _gbm_step(self) -> None:
        dt = 1.0 / (self.config.trading_days_per_year * self.config.trading_hours_per_day * self.config.steps_per_hour)
        dW = np.random.normal(0, math.sqrt(dt))
        drift = self.config.vol_drift * dt
        self.spot *= math.exp((drift - 0.5 * self.atm_vol**2) * dt + self.atm_vol * dW)
        self.spot = round(self.spot, 2)
        # bound spot away from zero
        self.spot = max(self.spot, 1.0)
        if np.random.rand() < self.config.shock_frequency:
            self.spot *= 1.0 + np.random.choice([-1, 1]) * np.random.uniform(0.005, 0.02)
        self.days_to_expiry = max(0.001, self.days_to_expiry - (1.0 / self.config.steps_per_hour / 24.0))
        self.history_spot.append((datetime.now(timezone.utc).isoformat(), self.spot))
        self.history_vol.append((datetime.now(timezone.utc).isoformat(), self.atm_vol))

    def _bot_flow(self) -> None:
        # Competitor tightens quotes on random strikes
        n = len(self.options)
        sample_size = min(5, n)
        for idx in np.random.choice(n, sample_size, replace=False):
            opt = self.options[idx]
            book = self.exchange.book(opt.id)
            book.cancel_by_agent("BOT")
            edge = self.strategy.quote_edge * (0.5 + np.random.rand() * 0.5)
            bid = self._to_increment(opt.theoretical * (1 - edge))
            ask = self._to_increment(opt.theoretical * (1 + edge))
            qty = int(np.random.randint(5, 25))
            self.exchange.add(opt.id, "BOT", "BUY", bid, qty)
            self.exchange.add(opt.id, "BOT", "SELL", ask, qty)

        # Customer market orders hit visible quotes
        if np.random.rand() < self.config.customer_flow_intensity and n:
            opt = self.options[int(np.random.choice(n))]
            side = np.random.choice(["BUY", "SELL"])
            qty = int(np.random.randint(1, 10))
            trades = self.exchange.market(opt.id, "CUSTOMER", side, qty)
            for t in trades:
                if t.counterparty == "USER":
                    user_side = "SELL" if t.side == "BUY" else "BUY"
                    self._apply_trade(t, opt.theoretical, user_side)
        self._mark_portfolio()
        self._update_market_state()

    def _simulation_counter(self) -> None:
        sim = self.market.simulation
        sim.step += 1
        if sim.step >= sim.total_steps - 10:
            sim.remaining_warning = True
        if sim.step >= sim.total_steps:
            sim.running = False
            sim.end_time = datetime.now(timezone.utc).isoformat()

    def start(self, total_steps: int = 44) -> None:
        self.market.simulation.running = True
        self.market.simulation.paused = False
        self.market.simulation.step = 0
        self.market.simulation.total_steps = total_steps
        self.market.simulation.start_time = datetime.now(timezone.utc).isoformat()
        self.market.simulation.remaining_warning = False
        self.exchange.clear_all()
        self._refresh_chain()

    def pause(self) -> bool:
        self.market.simulation.paused = not self.market.simulation.paused
        return self.market.simulation.paused

    def stop(self) -> None:
        self.market.simulation.running = False

    def reset(self) -> None:
        self.stop()
        self.spot = 500.0
        self.portfolio = PortfolioState()
        self.market.simulation.step = 0
        self.history_spot.clear()
        self.history_vol.clear()
        self._refresh_chain()
        self._mark_portfolio()

    def adjust_vol(self, delta: float) -> None:
        self.atm_vol = max(0.01, self.atm_vol + delta)
        self._refresh_chain()

    def adjust_skew(self, delta: float) -> None:
        self.skew = max(-0.2, min(0.2, self.skew + delta))
        self._refresh_chain()

    def adjust_wing(self, wing: str, delta: float) -> None:
        if wing == "call":
            self.call_wing = max(0.0, self.call_wing + delta)
        elif wing == "put":
            self.put_wing = max(0.0, self.put_wing + delta)
        self._refresh_chain()

    def toggle_increment(self) -> None:
        self.market.increment_mode = "eighth" if self.market.increment_mode == "penny" else "penny"
        self._refresh_chain()

    def futures_hedge(self, qty: int) -> list[Trade]:
        book = self.exchange.book(self.future.symbol)
        book.cancel_by_agent("USER")
        side = "BUY" if qty > 0 else "SELL"
        trades = self.exchange.market(self.future.symbol, "USER", side, abs(qty))
        for t in trades:
            t.instrument_id = self.future.symbol
            self._apply_trade(t, self.spot)
        self._mark_portfolio()
        return trades

    def combo_trade(self, combo_id: str, side: str, qty: int, price: float | None = None) -> list[Trade]:
        combo = next((c for c in self.combos if c.id == combo_id), None)
        if not combo:
            return []
        trades: list[Trade] = []
        for leg in combo.legs:
            opt = next((o for o in self.options if o.id == leg.instrument_id), None)
            if not opt:
                continue
            leg_qty = qty * leg.ratio
            if side == "BUY":
                t_side = "BUY" if leg_qty > 0 else "SELL"
            else:
                t_side = "SELL" if leg_qty > 0 else "BUY"
            tqty = abs(leg_qty)
            if tqty == 0:
                continue
            ts = self.exchange.market(opt.id, "USER_TAKER", t_side, tqty)
            trades.extend(ts)
        for t in trades:
            self._apply_trade(t, self._mark_price(t.instrument_id))
        self._mark_portfolio()
        return trades

    def risk_matrix(self, shocks: list[float] | None = None) -> list[RiskPoint]:
        shocks = shocks or [-0.05, -0.03, -0.01, 0.0, 0.01, 0.03, 0.05]
        points: list[RiskPoint] = []
        base_value = self._portfolio_value(self.spot, self.atm_vol)
        for shock in shocks:
            spot_shock = self.spot * (1 + shock)
            value = self._portfolio_value(spot_shock, self.atm_vol)
            g = self._portfolio_greeks_spot(spot_shock)
            points.append(
                RiskPoint(
                    shock_pct=shock,
                    spot=round(spot_shock, 2),
                    portfolio_value=round(value, 2),
                    pnl=round(value - base_value, 2),
                    delta=round(g.delta, 2),
                    gamma=round(g.gamma, 2),
                    vega=round(g.vega, 2),
                    theta=round(g.theta, 2),
                )
            )
        return points

    def _portfolio_value(self, spot: float, atm_vol: float) -> float:
        value = self.portfolio.cash + self.portfolio.realized_pnl
        T = max(0.001, self.days_to_expiry / 365.0)
        for pos in self.portfolio.positions.values():
            if pos.instrument_id == self.future.symbol:
                value += pos.qty * spot
            else:
                opt = next((o for o in self.options if o.id == pos.instrument_id), None)
                if opt:
                    value += pos.qty * price(spot, opt.strike, T, self.r, opt.implied_vol, opt.option_type)
        return value

    def _portfolio_greeks_spot(self, spot: float) -> Greeks:
        total = Greeks()
        T = max(0.001, self.days_to_expiry / 365.0)
        for pos in self.portfolio.positions.values():
            if pos.instrument_id == self.future.symbol:
                total = total + Greeks(delta=pos.qty)
            else:
                opt = next((o for o in self.options if o.id == pos.instrument_id), None)
                if opt:
                    g = greeks(spot, opt.strike, T, self.r, opt.implied_vol, opt.option_type)
                    total = total + g.scale(pos.qty)
        return total

    def vol_curve(self) -> list[VolCurvePoint]:
        T = max(0.001, self.days_to_expiry / 365.0)
        calls = [o for o in self.options if o.option_type == OptionType.CALL]
        strikes = sorted({o.strike for o in calls})
        return vol_surface(
            self.spot,
            T,
            self.atm_vol,
            self.skew,
            self.call_wing,
            self.put_wing,
            strikes,
            OptionType.CALL,
        )

    def get_state(self) -> dict[str, Any]:
        self._mark_portfolio()
        return {
            "market": self.market.model_dump(),
            "future": self.future.model_dump(),
            "portfolio": self.portfolio.model_dump(),
            "options": [o.model_dump() for o in self.options],
            "combos": [c.model_dump() for c in self.combos],
            "risk": [r.model_dump() for r in self.risk_matrix()],
            "vol_curve": [v.model_dump() for v in self.vol_curve()],
        }
