import math

from scipy.stats import norm

from options_mm.models.common import Greeks, Option, OptionType, VolCurvePoint


def d1d2(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> tuple[float, float]:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0, 0.0
    sig_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / sig_sqrt_t
    d2 = d1 - sig_sqrt_t
    return d1, d2


def price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0,
) -> float:
    d1, d2 = d1d2(S, K, T, r, sigma, q)
    if option_type == OptionType.CALL:
        return float(S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    return float(K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1))


def greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0,
) -> Greeks:
    d1, d2 = d1d2(S, K, T, r, sigma, q)
    nd1 = norm.cdf(d1)
    nd2 = norm.cdf(d2)
    pdf_d1 = norm.pdf(d1)

    if option_type == OptionType.CALL:
        delta = math.exp(-q * T) * nd1
    else:
        delta = math.exp(-q * T) * (nd1 - 1)

    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return Greeks()

    gamma = math.exp(-q * T) * pdf_d1 / (S * sigma * math.sqrt(T))
    vega = math.exp(-q * T) * S * pdf_d1 * math.sqrt(T) / 100.0
    theta_q = (
        -math.exp(-q * T) * S * pdf_d1 * sigma / (2 * math.sqrt(T))
        - r * K * math.exp(-r * T) * nd2
        + q * S * math.exp(-q * T) * nd1
    ) / 365.0
    if option_type == OptionType.PUT:
        theta_q = (
            -math.exp(-q * T) * S * pdf_d1 * sigma / (2 * math.sqrt(T))
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
            - q * S * math.exp(-q * T) * norm.cdf(-d1)
        ) / 365.0
    rho = K * T * math.exp(-r * T) * nd2 / 100.0
    if option_type == OptionType.PUT:
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0

    vanna = vega / S * (1 - d1 / (sigma * math.sqrt(T)))
    volga = vega * d1 * d2 / sigma

    return Greeks(
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta_q,
        rho=rho,
        vanna=vanna,
        volga=volga,
    )


def implied_vol(
    target_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType,
    q: float = 0.0,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    if T <= 0 or target_price <= 0:
        return 0.0
    sigma_low, sigma_high = 0.001, 5.0
    for _ in range(max_iter):
        sigma_mid = (sigma_low + sigma_high) / 2.0
        price_mid = price(S, K, T, r, sigma_mid, option_type, q)
        if abs(price_mid - target_price) < tol:
            return sigma_mid
        if price_mid > target_price:
            sigma_high = sigma_mid
        else:
            sigma_low = sigma_mid
    return (sigma_low + sigma_high) / 2.0


def vol_surface(
    S: float,
    T: float,
    atm_vol: float,
    skew: float,
    call_wing: float,
    put_wing: float,
    strikes: list[float],
    option_type: OptionType,
) -> list[VolCurvePoint]:
    points: list[VolCurvePoint] = []
    for K in strikes:
        m = K / S
        vol = atm_vol + skew * (m - 1.0)
        if option_type == OptionType.CALL and m > 1.0:
            vol += call_wing * (m - 1.0) ** 2
        if option_type == OptionType.PUT and m < 1.0:
            vol += put_wing * (1.0 - m) ** 2
        vol = max(0.01, min(2.0, vol))
        g = greeks(S, K, T, 0.045, vol, option_type)
        points.append(
            VolCurvePoint(
                delta=round(g.delta, 4),
                vol=round(vol, 4),
                strike=K,
                option_type=option_type,
            )
        )
    return points


def mark_option(opt: Option, S: float, r: float, T: float) -> Option:
    if T <= 0:
        T = 0.001
    opt.tte = T
    opt.theoretical = price(S, opt.strike, T, r, opt.implied_vol, opt.option_type)
    opt.greeks = greeks(S, opt.strike, T, r, opt.implied_vol, opt.option_type)
    return opt
