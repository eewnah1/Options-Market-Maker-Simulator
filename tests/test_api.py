import math

import pytest
from fastapi.testclient import TestClient

from options_mm.api.main import app, get_sim
from options_mm.simulation.engine import SimulationEngine


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_state(client: TestClient) -> None:
    response = client.get("/api/v1/state")
    assert response.status_code == 200
    data = response.json()
    assert "market" in data
    assert "options" in data
    assert len(data["options"]) > 0


def test_start_stop_reset(client: TestClient) -> None:
    assert client.post("/api/v1/start").status_code == 200
    assert client.post("/api/v1/stop").status_code == 200
    assert client.post("/api/v1/reset").status_code == 200


def test_quote_and_market(client: TestClient) -> None:
    sim = get_sim()
    sim.reset()
    opt = sim.options[0]
    payload = {"bid": opt.theoretical * 0.99, "bid_qty": 10, "ask": opt.theoretical * 1.01, "ask_qty": 10}
    assert client.post(f"/api/v1/quote/{opt.id}", json=payload).status_code == 200
    response = client.post(f"/api/v1/market/{opt.id}?side=BUY&qty=1")
    assert response.status_code == 200


def test_risk_matrix(client: TestClient) -> None:
    response = client.get("/api/v1/risk")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_engine_step() -> None:
    engine = SimulationEngine()
    engine.start(total_steps=5)
    for _ in range(5):
        engine.step()
    assert engine.market.simulation.step == 5
    assert not engine.market.simulation.running


def test_black_scholes_put_call_parity() -> None:
    from options_mm.models.common import OptionType
    from options_mm.pricing.black_scholes import price

    S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.2
    call = price(S, K, T, r, sigma, OptionType.CALL)
    put = price(S, K, T, r, sigma, OptionType.PUT)
    assert abs(call - put - (S - K * pow(math.e, -r * T))) < 0.01


def test_order_book_match() -> None:
    from options_mm.market.exchange import Exchange

    ex = Exchange()
    ex.add("OPT1", "USER", "BUY", 10.0, 10)
    ex.add("OPT1", "USER", "SELL", 12.0, 10)
    trades = ex.market("OPT1", "CUSTOMER", "BUY", 3)
    assert len(trades) == 1
    assert trades[0].qty == 3
    assert trades[0].price == 12.0
