"""Real-time arbitrage monitoring with signal generation."""

import asyncio
from typing import Optional, Deque, Dict
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np

from trading.analysis.arbitrage_signals import calculate_arb_signals, ArbSignal
from trading.analysis.structs import Signal
from infrastructure.logging import HFTLoggerInterface


@dataclass
class ArbMonitor:
    """Monitor arbitrage spreads and generate trading signals."""
    
    logger: HFTLoggerInterface
    history_size: int = 1000
    mexc_vs_gateio_history: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    gateio_spot_vs_futures_history: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    last_signal: Optional[Signal] = None
    signal_callback: Optional[callable] = None
    
    def __post_init__(self):
        """Initialize with correct history size."""
        self.mexc_vs_gateio_history = deque(maxlen=self.history_size)
        self.gateio_spot_vs_futures_history = deque(maxlen=self.history_size)
    
    def update_spreads(
        self, 
        mexc_spot_bid: float,
        mexc_spot_ask: float,
        gateio_futures_bid: float,
        gateio_futures_ask: float,
        gateio_spot_bid: float,
        gateio_spot_ask: float
    ) -> Optional[ArbSignal]:
        """
        Update spread history and generate signals.
        
        Args:
            mexc_spot_bid: MEXC spot bid price
            mexc_spot_ask: MEXC spot ask price
            gateio_futures_bid: Gate.io futures bid price
            gateio_futures_ask: Gate.io futures ask price
            gateio_spot_bid: Gate.io spot bid price
            gateio_spot_ask: Gate.io spot ask price
            
        Returns:
            ArbSignal if signal changed, None otherwise
        """
        # Calculate spreads (using mid prices for simplicity)
        mexc_mid = (mexc_spot_bid + mexc_spot_ask) / 2
        gateio_futures_mid = (gateio_futures_bid + gateio_futures_ask) / 2
        gateio_spot_mid = (gateio_spot_bid + gateio_spot_ask) / 2
        
        # Calculate arbitrage spreads as percentages
        mexc_vs_gateio_futures_spread = (mexc_mid - gateio_futures_mid) / gateio_futures_mid
        gateio_spot_vs_futures_spread = (gateio_spot_mid - gateio_futures_mid) / gateio_futures_mid
        
        # Add to history
        self.mexc_vs_gateio_history.append(mexc_vs_gateio_futures_spread)
        self.gateio_spot_vs_futures_history.append(gateio_spot_vs_futures_spread)
        
        # Need minimum history before generating signals
        if len(self.mexc_vs_gateio_history) < 100:
            return None
        
        # Calculate signal
        result = calculate_arb_signals(
            list(self.mexc_vs_gateio_history),
            list(self.gateio_spot_vs_futures_history),
            mexc_vs_gateio_futures_spread,
            gateio_spot_vs_futures_spread
        )
        
        # Check if signal changed
        if result.signal != self.last_signal:
            self.last_signal = result.signal
            self._log_signal_change(result)
            
            # Call callback if provided
            if self.signal_callback:
                asyncio.create_task(self.signal_callback(result))
            
            return result
        
        return None
    
    def _log_signal_change(self, signal: ArbSignal):
        """Log signal changes."""
        if signal.signal == Signal.ENTER:
            self.logger.info(
                "🟢 ENTER SIGNAL - Start arbitrage",
                mexc_vs_gateio=f"{signal.mexc_vs_gateio_futures.current:.4f}",
                threshold=f"{signal.mexc_vs_gateio_futures.min_25pct:.4f}",
                reason=signal.reason
            )
        elif signal.signal == Signal.EXIT:
            self.logger.info(
                "🔴 EXIT SIGNAL - Close arbitrage",
                gateio_spot_vs_futures=f"{signal.gateio_spot_vs_futures.current:.4f}",
                threshold=f"{signal.gateio_spot_vs_futures.max_25pct:.4f}",
                reason=signal.reason
            )
        else:
            self.logger.debug(
                "⏸️ HOLD - No action",
                mexc_vs_gateio=f"{signal.mexc_vs_gateio_futures.current:.4f}",
                gateio_spot_vs_futures=f"{signal.gateio_spot_vs_futures.current:.4f}"
            )
    
    def get_statistics(self) -> Dict:
        """Get current statistics for monitoring."""
        if len(self.mexc_vs_gateio_history) == 0:
            return {"status": "No data"}
        
        return {
            "history_size": len(self.mexc_vs_gateio_history),
            "last_signal": self.last_signal.value if self.last_signal else "None",
            "mexc_vs_gateio": {
                "current": self.mexc_vs_gateio_history[-1] if self.mexc_vs_gateio_history else 0,
                "mean": np.mean(list(self.mexc_vs_gateio_history)),
                "std": np.std(list(self.mexc_vs_gateio_history)),
                "min": min(self.mexc_vs_gateio_history),
                "max": max(self.mexc_vs_gateio_history)
            },
            "gateio_spot_vs_futures": {
                "current": self.gateio_spot_vs_futures_history[-1] if self.gateio_spot_vs_futures_history else 0,
                "mean": np.mean(list(self.gateio_spot_vs_futures_history)),
                "std": np.std(list(self.gateio_spot_vs_futures_history)),
                "min": min(self.gateio_spot_vs_futures_history),
                "max": max(self.gateio_spot_vs_futures_history)
            }
        }
    
    def reset_history(self):
        """Reset spread history."""
        self.mexc_vs_gateio_history.clear()
        self.gateio_spot_vs_futures_history.clear()
        self.last_signal = None