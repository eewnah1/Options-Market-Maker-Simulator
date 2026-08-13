import math
import time
from datetime import datetime
from uuid import uuid4

from options_mm.models.common import Trade


class Order:
    def __init__(self, agent: str, side: str, price: float, qty: int, ts: float):
        self.id = str(uuid4())
        self.agent = agent
        self.side = side  # 'BUY' or 'SELL'
        self.price = price
        self.qty = qty
        self.ts = ts
        self.filled = 0

    @property
    def remaining(self) -> int:
        return self.qty - self.filled

    def __repr__(self) -> str:
        return f"Order({self.agent} {self.side} {self.remaining}@{self.price})"


class OrderBook:
    def __init__(self, instrument_id: str, tick_size: float = 0.01):
        self.instrument_id = instrument_id
        self.tick_size = tick_size
        self.bids: list[Order] = []  # sorted descending price then ascending time
        self.asks: list[Order] = []

    def _insert(self, orders: list[Order], new: Order, reverse: bool) -> None:
        idx = 0
        for i, o in enumerate(orders):
            cmp = (new.price > o.price) if reverse else (new.price < o.price)
            if cmp:
                idx = i
                break
            if new.price == o.price and new.ts < o.ts:
                idx = i
                break
            idx = i + 1
        orders.insert(idx, new)

    def add(self, agent: str, side: str, price: float, qty: int) -> Order:
        price = round(price / self.tick_size) * self.tick_size
        order = Order(agent, side, price, qty, time.time())
        if side == "BUY":
            self._insert(self.bids, order, True)
        else:
            self._insert(self.asks, order, False)
        return order

    def cancel(self, order_id: str) -> bool:
        for lst in [self.bids, self.asks]:
            for o in lst:
                if o.id == order_id:
                    lst.remove(o)
                    return True
        return False

    def cancel_by_agent(self, agent: str) -> None:
        self.bids = [o for o in self.bids if o.agent != agent]
        self.asks = [o for o in self.asks if o.agent != agent]

    def best_bid(self) -> Order | None:
        return self.bids[0] if self.bids else None

    def best_ask(self) -> Order | None:
        return self.asks[0] if self.asks else None

    def _cross(self, incoming: Order, resting: list[Order]) -> list[tuple[int, float, str, Order]]:
        fills: list[tuple[int, float, str, Order]] = []
        while incoming.remaining > 0 and resting:
            top = resting[0]
            if incoming.side == "BUY":
                if incoming.price < top.price:
                    break
            else:
                if incoming.price > top.price:
                    break
            fill_qty = min(incoming.remaining, top.remaining)
            top.filled += fill_qty
            incoming.filled += fill_qty
            fills.append((fill_qty, top.price, top.agent, top))
            if top.remaining == 0:
                resting.pop(0)
        return fills

    def market_order(
        self,
        agent: str,
        side: str,
        qty: int,
    ) -> list[Trade]:
        now = time.time()
        order = Order(agent, side, math.inf if side == "BUY" else -math.inf, qty, now)
        if side == "BUY":
            fills = self._cross(order, self.asks)
        else:
            fills = self._cross(order, self.bids)
        trades: list[Trade] = []
        for fill_qty, price, counterparty, _ in fills:
            cp = counterparty if counterparty else "MARKET"
            trades.append(
                Trade(
                    id=str(uuid4()),
                    timestamp=datetime.utcnow().isoformat(),
                    instrument_id=self.instrument_id,
                    side="BUY" if side == "BUY" else "SELL",
                    qty=fill_qty,
                    price=price,
                    counterparty=cp,
                    total=fill_qty * price,
                )
            )
        return trades

    def clear(self) -> None:
        self.bids.clear()
        self.asks.clear()


class Exchange:
    def __init__(self, tick_size: float = 0.01):
        self.tick_size = tick_size
        self.books: dict[str, OrderBook] = {}

    def book(self, instrument_id: str) -> OrderBook:
        if instrument_id not in self.books:
            self.books[instrument_id] = OrderBook(instrument_id, self.tick_size)
        return self.books[instrument_id]

    def add(self, instrument_id: str, agent: str, side: str, price: float, qty: int) -> Order:
        return self.book(instrument_id).add(agent, side, price, qty)

    def market(self, instrument_id: str, agent: str, side: str, qty: int) -> list[Trade]:
        return self.book(instrument_id).market_order(agent, side, qty)

    def cancel_agent(self, instrument_id: str, agent: str) -> None:
        self.book(instrument_id).cancel_by_agent(agent)

    def clear_all(self) -> None:
        for b in self.books.values():
            b.clear()
