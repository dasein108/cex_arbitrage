"""
Signal Types - Enum definitions for arbitrage signals_v2.

Centralized signal type definitions to avoid circular imports.
"""

from enum import Enum


class Signal(Enum):
    """Trading signal enumeration."""
    ENTER = "enter"
    EXIT = "exit" 
    HOLD = "hold"