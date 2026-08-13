from typing import Any

from options_mm.models.common import Greeks, Trade


def risk_attribution(
    greeks: Greeks,
    spot_shock: float,
    vol_shock: float,
    time_shock: float = 1.0 / 365.0,
) -> dict[str, float]:
    delta_pnl = greeks.delta * spot_shock
    gamma_pnl = 0.5 * greeks.gamma * spot_shock**2
    vega_pnl = greeks.vega * vol_shock
    theta_pnl = greeks.theta * time_shock
    return {
        "delta_pnl": delta_pnl,
        "gamma_pnl": gamma_pnl,
        "vega_pnl": vega_pnl,
        "theta_pnl": theta_pnl,
        "total": delta_pnl + gamma_pnl + vega_pnl + theta_pnl,
    }


def markout(trade: Trade, fair_price: float, mark_lag: int = 1) -> dict[str, Any]:
    if trade.side == "BUY":
        pnl = (fair_price - trade.price) * trade.qty
    else:
        pnl = (trade.price - fair_price) * trade.qty
    return {
        "trade_id": trade.id,
        "markout_pnl": pnl,
        "adverse": pnl < 0,
        "mark_lag": mark_lag,
    }


def var_cvar(returns: list[float], percentile: float = 0.05) -> dict[str, float]:
    if not returns:
        return {"var": 0.0, "cvar": 0.0}
    sorted_r = sorted(returns)
    idx = int(len(sorted_r) * percentile)
    idx = max(0, min(idx, len(sorted_r) - 1))
    var = sorted_r[idx]
    tail = sorted_r[: idx + 1]
    cvar = sum(tail) / len(tail) if tail else 0.0
    return {"var": var, "cvar": cvar}
