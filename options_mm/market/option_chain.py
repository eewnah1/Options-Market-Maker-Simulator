import uuid
from datetime import datetime, timedelta

from options_mm.models.common import Combo, ComboLeg, Option, OptionType
from options_mm.pricing.black_scholes import mark_option


def _expiry_str(days: int) -> str:
    return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")


def build_chain(
    spot: float,
    r: float,
    atm_vol: float,
    skew: float,
    call_wing: float,
    put_wing: float,
    days_to_expiry: float,
    underlying: str = "SPY",
    min_strike: float = 0.0,
    max_strike: float = 0.0,
    step: float = 10.0,
) -> list[Option]:
    T = days_to_expiry / 365.0
    if min_strike == 0:
        min_strike = int(spot * 0.7 / step) * step
    if max_strike == 0:
        max_strike = int(spot * 1.3 / step) * step + step
    strikes = [round(k, 2) for k in range(int(min_strike), int(max_strike) + 1, int(step))]
    expiry = _expiry_str(int(days_to_expiry))
    options: list[Option] = []
    for K in strikes:
        for ot in [OptionType.CALL, OptionType.PUT]:
            m = K / spot
            vol = atm_vol + skew * (m - 1.0)
            if ot == OptionType.CALL and m > 1.0:
                vol += call_wing * (m - 1.0) ** 2
            if ot == OptionType.PUT and m < 1.0:
                vol += put_wing * (1.0 - m) ** 2
            vol = max(0.05, min(2.0, vol))
            opt = Option(
                id=f"{underlying}_{expiry}_{ot.value}_{int(K)}",
                name=f"{underlying} {expiry} {K} {ot.value}",
                expiry=expiry,
                strike=K,
                option_type=ot,
                underlying=underlying,
                tte=T,
                implied_vol=vol,
            )
            mark_option(opt, spot, r, T)
            options.append(opt)
    return options


def _combo(
    name: str,
    legs: list[tuple[str, int]],
    options: list[Option],
    underlying: str,
) -> Combo:
    leg_models = [ComboLeg(instrument_id=oid, ratio=ratio) for oid, ratio in legs]
    return Combo(
        id=f"{underlying}_{uuid.uuid4().hex[:6]}",
        name=name,
        legs=leg_models,
    )


def build_combos(options: list[Option], underlying: str = "SPY") -> list[Combo]:
    calls = {o.strike: o for o in options if o.option_type == OptionType.CALL}
    puts = {o.strike: o for o in options if o.option_type == OptionType.PUT}
    strikes = sorted(calls.keys())
    combos: list[Combo] = []
    if len(strikes) < 5:
        return combos
    atm = strikes[len(strikes) // 2]
    k_lo = strikes[len(strikes) // 4]
    k_hi = strikes[3 * len(strikes) // 4]

    combos.append(_combo("ATM Straddle", [(calls[atm].id, 1), (puts[atm].id, 1)], options, underlying))
    combos.append(_combo("Call Spread", [(calls[k_lo].id, 1), (calls[k_hi].id, -1)], options, underlying))
    combos.append(_combo("Put Spread", [(puts[k_lo].id, -1), (puts[k_hi].id, 1)], options, underlying))
    combos.append(_combo("Risk Reversal", [(calls[k_hi].id, 1), (puts[k_lo].id, -1)], options, underlying))
    combos.append(_combo("Collar", [(calls[k_hi].id, -1), (puts[k_lo].id, 1), (underlying, -1)], options, underlying))
    combos.append(
        _combo("Call Fly", [(calls[k_lo].id, 1), (calls[atm].id, -2), (calls[k_hi].id, 1)], options, underlying)
    )
    return combos
