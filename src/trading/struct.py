from msgspec import Struct
from typing import Optional, Literal
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


# Base trading strategy states using Literal strings for optimal performance
TradingStrategyState = Literal[
    'idle',
    'executing', 
    'monitoring',
    'adjusting',
    'completed',
    'not_started',
    'cancelled',
    'paused',
    'error'
]
