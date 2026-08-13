from options_mm.models.common import OptionType, VolCurvePoint
from options_mm.pricing.black_scholes import greeks


def parametric_vol(
    moneyness: float,
    atm_vol: float,
    skew: float = 0.0,
    call_wing: float = 0.0,
    put_wing: float = 0.0,
) -> float:
    vol = atm_vol + skew * (moneyness - 1.0)
    if moneyness > 1.0:
        vol += call_wing * (moneyness - 1.0) ** 2
    if moneyness < 1.0:
        vol += put_wing * (1.0 - moneyness) ** 2
    return max(0.01, min(2.0, vol))


def build_vol_surface(
    spot: float,
    T: float,
    r: float,
    atm_vol: float,
    skew: float,
    call_wing: float,
    put_wing: float,
    strikes: list[float],
) -> list[VolCurvePoint]:
    points: list[VolCurvePoint] = []
    for K in strikes:
        m = K / spot
        vol = parametric_vol(m, atm_vol, skew, call_wing, put_wing)
        for ot in [OptionType.CALL, OptionType.PUT]:
            g = greeks(spot, K, T, r, vol, ot)
            points.append(
                VolCurvePoint(
                    delta=round(g.delta, 4),
                    vol=round(vol, 4),
                    strike=K,
                    option_type=ot,
                )
            )
    return points
