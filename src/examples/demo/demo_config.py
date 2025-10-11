"""
Configuration for optimal threshold demo.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName


@dataclass
class DemoConfig:
    """Configuration for optimal threshold calculation demo."""
    
    # Trading parameters
    symbol_base: str = "LUNC"
    symbol_quote: str = "USDT" 
    spot_exchange: str = "MEXC_SPOT"
    futures_exchange: str = "GATEIO_FUTURES"
    
    # Data parameters
    days_back: int = 2
    limit: int = 10000
    end_date: Optional[datetime] = None
    
    # Optimization parameters
    max_positions: int = 5
    min_liquidity: float = 1000.0
    alignment_tolerance: int = 1
    optimization_target: str = "total_profit"
    
    def __post_init__(self):
        """Set default end_date if not provided."""
        if self.end_date is None:
            self.end_date = datetime(2025, 10, 11, 16, 15, 0, tzinfo=timezone.utc)
    
    @property
    def symbol(self) -> Symbol:
        """Get Symbol object."""
        return Symbol(base=AssetName(self.symbol_base), quote=AssetName(self.symbol_quote))
    
    @property
    def start_date(self) -> datetime:
        """Calculate start date based on end_date and days_back."""
        return self.end_date - timedelta(days=self.days_back)
    
    @property
    def symbol_pair_str(self) -> str:
        """Get symbol pair as string."""
        return f"{self.symbol_base}/{self.symbol_quote}"