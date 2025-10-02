from msgspec import Struct
from typing import Optional
from exchanges.structs.common import Symbol, Side, Position


class SynthPosition(Struct):
    """Trading position (for margin/futures)."""
    symbol: Symbol
    side: Side  # LONG = BUY, SHORT = SELL
    price: float
    quantity: float = 0
    quantity_filled: float = 0.0

    def __str__(self):
        return f"Synth-pos: {self.symbol} {self.side} size: {self.quantity}/{self.quantity_filled}"
