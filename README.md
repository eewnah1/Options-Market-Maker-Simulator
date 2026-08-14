# Options Market Maker Simulator

An institutional-grade options market-maker simulator inspired by the Akuna
Capital in-house training tool. It simulates an option chain with live
bid/ask quoting, Black-Scholes theoreticals, Greeks, a limit-order-book
exchange, customer flow, a competitive bot, futures hedging, combo trading,
vol-surface controls, and a risk matrix.

**Live no-auth dashboard:** https://sponsors-animals-survival-few.trycloudflare.com/dashboard

## Quick start

```bash
python -m pip install -e .
python -m uvicorn options_mm.api.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/dashboard`.

## Tests and lint

```bash
python -m pytest -q
python -m ruff check .
python -m mypy options_mm
```

## Architecture

- `options_mm/pricing/` — Black-Scholes option pricing and Greeks (delta,
  gamma, vega, theta, rho, vanna, volga) and a parametric vol surface.
- `options_mm/market/` — option chain generation, listed combos, and a limit
  order book matching engine with price-time priority.
- `options_mm/simulation/` — GBM spot diffusion, customer flow, competitor
  bot, portfolio tracking, delta hedging, and risk matrix.
- `options_mm/api/` — FastAPI backend with `/state`, `/step`, `/quote`,
  `/futures/hedge`, `/combo/trade`, `/risk`, `/vol_curve`, and SSE live feed.
- `dashboard/` — dark institutional HTML/JS/CSS dashboard.

## License

Apache-2.0
