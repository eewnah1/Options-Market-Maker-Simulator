import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from options_mm.config import settings
from options_mm.simulation.engine import SimulationEngine

sim: SimulationEngine | None = None


def get_sim() -> SimulationEngine:
    global sim
    if sim is None:
        sim = SimulationEngine()
    return sim


async def _simulation_loop() -> None:
    while True:
        await asyncio.sleep(1.0)
        s = get_sim()
        if s.market.simulation.running and not s.market.simulation.paused:
            s.step()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_sim()
    task = asyncio.create_task(_simulation_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title=settings.project_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


try:
    app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")
except RuntimeError:
    pass


class QuoteRequest(BaseModel):
    bid: float
    bid_qty: int
    ask: float
    ask_qty: int


class FuturesHedgeRequest(BaseModel):
    qty: int


class ComboTradeRequest(BaseModel):
    combo_id: str
    side: str = Field(pattern="^(BUY|SELL)$")
    qty: int
    price: float | None = None


class MarketOrderRequest(BaseModel):
    instrument_id: str
    side: str = Field(pattern="^(BUY|SELL)$")
    qty: int


class VolAdjustRequest(BaseModel):
    delta: float


class SkewAdjustRequest(BaseModel):
    delta: float


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/state")
async def state() -> dict[str, Any]:
    return get_sim().get_state()


@app.post("/api/v1/start")
async def start() -> dict[str, str]:
    get_sim().start()
    return {"status": "started"}


@app.post("/api/v1/pause")
async def pause() -> dict[str, bool]:
    return {"paused": get_sim().pause()}


@app.post("/api/v1/stop")
async def stop() -> dict[str, str]:
    get_sim().stop()
    return {"status": "stopped"}


@app.post("/api/v1/reset")
async def reset() -> dict[str, str]:
    get_sim().reset()
    return {"status": "reset"}


@app.post("/api/v1/step")
async def step() -> dict[str, Any]:
    get_sim().step()
    return get_sim().get_state()


@app.post("/api/v1/quote/{instrument_id}")
async def quote(instrument_id: str, req: QuoteRequest) -> dict[str, str]:
    get_sim().user_quote(instrument_id, req.bid, req.bid_qty, req.ask, req.ask_qty)
    return {"status": "ok"}


@app.post("/api/v1/market/{instrument_id}")
async def market_order(instrument_id: str, side: str, qty: int) -> dict[str, Any]:
    trades = get_sim().user_market_order(instrument_id, side.upper(), qty)
    return {"trades": [t.model_dump() for t in trades]}


@app.post("/api/v1/market/order")
async def market_order_body(req: MarketOrderRequest) -> dict[str, Any]:
    trades = get_sim().user_market_order(req.instrument_id, req.side.upper(), req.qty)
    return {"trades": [t.model_dump() for t in trades]}


@app.post("/api/v1/futures/hedge")
async def futures_hedge(req: FuturesHedgeRequest) -> dict[str, Any]:
    trades = get_sim().futures_hedge(req.qty)
    return {"trades": [t.model_dump() for t in trades]}


@app.post("/api/v1/combo/trade")
async def combo_trade(req: ComboTradeRequest) -> dict[str, Any]:
    trades = get_sim().combo_trade(req.combo_id, req.side.upper(), req.qty, req.price)
    return {"trades": [t.model_dump() for t in trades]}


@app.post("/api/v1/vol")
async def adjust_vol(req: VolAdjustRequest) -> dict[str, float]:
    get_sim().adjust_vol(req.delta)
    return {"atm_vol": get_sim().atm_vol}


@app.post("/api/v1/skew")
async def adjust_skew(req: SkewAdjustRequest) -> dict[str, float]:
    get_sim().adjust_skew(req.delta)
    return {"skew": get_sim().skew}


@app.post("/api/v1/wing/{wing}")
async def adjust_wing(wing: str, req: VolAdjustRequest) -> dict[str, float]:
    if wing not in {"call", "put"}:
        raise HTTPException(status_code=400, detail="wing must be call or put")
    get_sim().adjust_wing(wing, req.delta)
    return {wing: getattr(get_sim(), f"{wing}_wing")}


@app.post("/api/v1/increment/toggle")
async def toggle_increment() -> dict[str, str]:
    get_sim().toggle_increment()
    return {"mode": get_sim().market.increment_mode}


@app.get("/api/v1/risk")
async def risk(shocks: str = "-5,-3,-1,0,1,3,5") -> list[dict[str, Any]]:
    try:
        shock_list = [float(x) / 100.0 for x in shocks.split(",") if x]
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid shocks")
    return [r.model_dump() for r in get_sim().risk_matrix(shock_list)]


@app.get("/api/v1/vol_curve")
async def vol_curve() -> list[dict[str, Any]]:
    return [v.model_dump() for v in get_sim().vol_curve()]


async def state_generator() -> AsyncGenerator[str, None]:
    while True:
        await asyncio.sleep(1.0)
        data = get_sim().get_state()
        yield f"data: {json.dumps(data)}\n\n"


@app.get("/api/v1/sse")
async def sse() -> StreamingResponse:
    return StreamingResponse(state_generator(), media_type="text/event-stream")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})
