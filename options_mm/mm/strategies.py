from options_mm.models.common import Greeks, Option


def simple_skew(
    option: Option,
    inventory_delta: float,
    edge: float,
    inventory_skew: float = 0.002,
    tick: float = 0.01,
    mode: str = "penny",
) -> tuple[float, float, int, int]:
    size = 26
    adj = -inventory_skew * inventory_delta / max(1.0, abs(inventory_delta))
    bid = option.theoretical * (1 - edge + adj)
    ask = option.theoretical * (1 + edge + adj)
    if mode == "eighth":
        bid = round(bid * 8) / 8.0
        ask = round(ask * 8) / 8.0
    else:
        bid = round(bid / tick) * tick
        ask = round(ask / tick) * tick
    return bid, ask, size, size


class StrategyRegistry:
    @staticmethod
    def default_bid_ask(
        option: Option,
        greeks: Greeks,
        quote_edge: float = 0.005,
        quote_size: int = 26,
    ) -> tuple[float, float, int, int]:
        bid = round(option.theoretical * (1 - quote_edge), 2)
        ask = round(option.theoretical * (1 + quote_edge), 2)
        return bid, ask, quote_size, quote_size
