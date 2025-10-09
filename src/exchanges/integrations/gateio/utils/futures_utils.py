"""
Gate.io futures utility functions for position analysis and calculations.

This module provides utilities for position analysis, side detection, value calculations,
and other futures-related operations while maintaining HFT performance requirements.
"""

import time
from typing import List, Optional
from decimal import Decimal

from exchanges.structs.common import Position, Symbol, Side


def detect_side_from_size(size: float) -> Side:
    """
    Determine position side from size value.
    
    Args:
        size: Position size (negative for short, positive for long)
        
    Returns:
        Side.BUY for long positions, Side.SELL for short positions
    """
    return Side.BUY if size >= 0 else Side.SELL


def format_contract_size(size: float, side: Side) -> int:
    """
    Format position size for Gate.io futures API.
    
    Args:
        size: Absolute position size
        side: Position side
        
    Returns:
        Signed integer size for API (negative for short, positive for long)
        
    Notes:
        - Gate.io futures API expects integer contract sizes
        - Sign indicates direction: positive = long, negative = short
    """
    abs_size = abs(size)
    return int(abs_size) if side == Side.BUY else -int(abs_size)


def calculate_position_value(size: float, mark_price: float, quanto_multiplier: Optional[float] = None) -> float:
    """
    Calculate position value in quote currency.
    
    Args:
        size: Position size in contracts
        mark_price: Current mark price
        quanto_multiplier: Contract multiplier (default 1.0)
        
    Returns:
        Position value in quote currency
    """
    multiplier = quanto_multiplier or 1.0
    return abs(size) * mark_price * multiplier


def calculate_unrealized_pnl(
    size: float, 
    entry_price: float, 
    mark_price: float, 
    side: Side,
    quanto_multiplier: Optional[float] = None
) -> float:
    """
    Calculate unrealized PnL for futures position.
    
    Args:
        size: Position size in contracts
        entry_price: Entry price
        mark_price: Current mark price
        side: Position side
        quanto_multiplier: Contract multiplier (default 1.0)
        
    Returns:
        Unrealized PnL in quote currency
    """
    multiplier = quanto_multiplier or 1.0
    price_diff = mark_price - entry_price
    
    if side == Side.SELL:
        price_diff = -price_diff
    
    return abs(size) * price_diff * multiplier


def is_position_profitable(position: Position) -> bool:
    """
    Check if position is currently profitable.
    
    Args:
        position: Position object
        
    Returns:
        True if position has positive unrealized PnL
    """
    return position.unrealized_pnl > 0


def get_position_margin_ratio(position: Position) -> Optional[float]:
    """
    Calculate position margin ratio.
    
    Args:
        position: Position object
        
    Returns:
        Margin ratio if margin and mark_price are available, else None
    """
    if not position.margin or not position.mark_price:
        return None
        
    position_value = position.size * position.mark_price
    if position_value == 0:
        return None
        
    return position.margin / position_value


def filter_active_positions(positions: List[Position], min_size: float = 0.0) -> List[Position]:
    """
    Filter positions to include only active ones above minimum size.
    
    Args:
        positions: List of positions
        min_size: Minimum position size to include
        
    Returns:
        Filtered list of active positions
    """
    return [pos for pos in positions if pos.size > min_size]