"""
Market Data Generator for Trading Task Tests

Specialized helper for generating realistic market data scenarios including
price movements, spreads, and volatility patterns for testing trading tasks.
"""

import time
import math
from typing import List, Dict, Tuple, Optional
from enum import Enum

from exchanges.structs import Symbol, BookTicker, SymbolInfo
from exchanges.structs.common import AssetName
from .test_data_factory import TestDataFactory


class MarketCondition(Enum):
    """Market condition types for testing."""
    STABLE = "stable"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    VOLATILE = "volatile"
    LOW_LIQUIDITY = "low_liquidity"
    HIGH_SPREAD = "high_spread"


class PriceMovementPattern(Enum):
    """Price movement patterns for testing."""
    GRADUAL = "gradual"
    SUDDEN_SPIKE = "sudden_spike"
    SUDDEN_DROP = "sudden_drop"
    OSCILLATING = "oscillating"
    BREAKOUT = "breakout"


class MarketDataGenerator:
    """Generator for creating realistic market data scenarios for testing."""
    
    def __init__(self, base_price: float = 50000.0):
        self.base_price = base_price
        self.timestamp_counter = int(time.time() * 1000)
    
    def generate_arbitrage_opportunity(self, symbol: Symbol,
                                     profit_margin: float = 100.0,
                                     spread_width: float = 1.0) -> Dict[str, BookTicker]:
        """Generate market data showing arbitrage opportunity."""
        buy_exchange_price = self.base_price
        sell_exchange_price = self.base_price + profit_margin
        
        buy_ticker = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=buy_exchange_price - spread_width/2,
            ask_price=buy_exchange_price + spread_width/2,
            timestamp=self._get_next_timestamp()
        )
        
        sell_ticker = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=sell_exchange_price - spread_width/2,
            ask_price=sell_exchange_price + spread_width/2,
            timestamp=self._get_next_timestamp()
        )
        
        return {
            'buy_exchange': buy_ticker,
            'sell_exchange': sell_ticker,
            'profit_potential': profit_margin - spread_width
        }
    
    def generate_price_movement_sequence(self, symbol: Symbol,
                                       pattern: PriceMovementPattern,
                                       duration_seconds: int = 60,
                                       update_interval: int = 1) -> List[BookTicker]:
        """Generate sequence of price movements following a pattern."""
        tickers = []
        steps = duration_seconds // update_interval
        
        for i in range(steps + 1):
            progress = i / steps if steps > 0 else 1.0
            price = self._calculate_price_for_pattern(pattern, progress)
            
            ticker = TestDataFactory.create_book_ticker(
                symbol=symbol,
                bid_price=price - 0.5,
                ask_price=price + 0.5,
                timestamp=self._get_next_timestamp()
            )
            tickers.append(ticker)
        
        return tickers
    
    def generate_volatile_market(self, symbol: Symbol,
                               volatility_percentage: float = 5.0,
                               updates_count: int = 20) -> List[BookTicker]:
        """Generate volatile market with random price swings."""
        tickers = []
        current_price = self.base_price
        
        for i in range(updates_count):
            # Random price change within volatility range
            max_change = self.base_price * (volatility_percentage / 100)
            price_change = (2 * (i % 2) - 1) * max_change * (0.5 + 0.5 * math.sin(i))
            current_price = max(self.base_price + price_change, 1.0)
            
            ticker = TestDataFactory.create_book_ticker(
                symbol=symbol,
                bid_price=current_price - 1.0,
                ask_price=current_price + 1.0,
                timestamp=self._get_next_timestamp()
            )
            tickers.append(ticker)
        
        return tickers
    
    def generate_spread_scenarios(self, symbol: Symbol) -> Dict[str, BookTicker]:
        """Generate various spread scenarios for testing."""
        scenarios = {}
        
        # Normal spread
        scenarios['normal'] = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price - 0.5,
            ask_price=self.base_price + 0.5,
            timestamp=self._get_next_timestamp()
        )
        
        # Wide spread (low liquidity)
        scenarios['wide'] = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price - 25.0,
            ask_price=self.base_price + 25.0,
            timestamp=self._get_next_timestamp()
        )
        
        # Tight spread (high liquidity)
        scenarios['tight'] = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price - 0.1,
            ask_price=self.base_price + 0.1,
            timestamp=self._get_next_timestamp()
        )
        
        # Crossed spread (error condition)
        scenarios['crossed'] = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price + 1.0,
            ask_price=self.base_price - 1.0,
            timestamp=self._get_next_timestamp()
        )
        
        return scenarios
    
    def generate_dual_exchange_price_divergence(self, symbol: Symbol,
                                              divergence_amount: float = 200.0,
                                              convergence_steps: int = 10) -> List[Dict[str, BookTicker]]:
        """Generate price divergence and convergence between two exchanges."""
        sequence = []
        
        for i in range(convergence_steps + 1):
            progress = i / convergence_steps if convergence_steps > 0 else 1.0
            current_divergence = divergence_amount * (1.0 - progress)
            
            exchange1_price = self.base_price
            exchange2_price = self.base_price + current_divergence
            
            exchange1_ticker = TestDataFactory.create_book_ticker(
                symbol=symbol,
                bid_price=exchange1_price - 0.5,
                ask_price=exchange1_price + 0.5,
                timestamp=self._get_next_timestamp()
            )
            
            exchange2_ticker = TestDataFactory.create_book_ticker(
                symbol=symbol,
                bid_price=exchange2_price - 0.5,
                ask_price=exchange2_price + 0.5,
                timestamp=self._get_next_timestamp()
            )
            
            sequence.append({
                'exchange1': exchange1_ticker,
                'exchange2': exchange2_ticker,
                'divergence': current_divergence
            })
        
        return sequence
    
    def generate_market_condition_scenario(self, symbol: Symbol,
                                         condition: MarketCondition) -> Dict[str, any]:
        """Generate market data representing specific market conditions."""
        if condition == MarketCondition.STABLE:
            return self._generate_stable_market(symbol)
        elif condition == MarketCondition.TRENDING_UP:
            return self._generate_trending_market(symbol, direction=1)
        elif condition == MarketCondition.TRENDING_DOWN:
            return self._generate_trending_market(symbol, direction=-1)
        elif condition == MarketCondition.VOLATILE:
            return self._generate_volatile_condition(symbol)
        elif condition == MarketCondition.LOW_LIQUIDITY:
            return self._generate_low_liquidity(symbol)
        elif condition == MarketCondition.HIGH_SPREAD:
            return self._generate_high_spread(symbol)
        else:
            return self._generate_stable_market(symbol)
    
    def generate_symbol_info_variations(self, symbol: Symbol) -> Dict[str, SymbolInfo]:
        """Generate symbol info with different trading parameters."""
        variations = {}
        
        # Standard trading pair
        variations['standard'] = TestDataFactory.create_symbol_info(
            symbol=symbol,
            min_base_quantity=0.001,
            min_quote_quantity=10.0,
            tick=0.01
        )
        
        # High minimum requirements
        variations['high_minimums'] = TestDataFactory.create_symbol_info(
            symbol=symbol,
            min_base_quantity=0.1,
            min_quote_quantity=1000.0,
            tick=1.0
        )
        
        # Micro trading (very small minimums)
        variations['micro'] = TestDataFactory.create_symbol_info(
            symbol=symbol,
            min_base_quantity=0.0001,
            min_quote_quantity=1.0,
            tick=0.001
        )
        
        # Futures contract
        variations['futures'] = TestDataFactory.create_symbol_info(
            symbol=symbol,
            min_base_quantity=1.0,
            min_quote_quantity=100.0,
            tick=0.1,
            is_futures=True,
            quanto_multiplier=0.01
        )
        
        return variations
    
    def _calculate_price_for_pattern(self, pattern: PriceMovementPattern, progress: float) -> float:
        """Calculate price based on movement pattern and progress."""
        if pattern == PriceMovementPattern.GRADUAL:
            return self.base_price + (progress * 100)
        elif pattern == PriceMovementPattern.SUDDEN_SPIKE:
            return self.base_price + (500 if progress > 0.8 else 0)
        elif pattern == PriceMovementPattern.SUDDEN_DROP:
            return self.base_price - (500 if progress > 0.8 else 0)
        elif pattern == PriceMovementPattern.OSCILLATING:
            return self.base_price + (100 * math.sin(progress * 4 * math.pi))
        elif pattern == PriceMovementPattern.BREAKOUT:
            if progress < 0.7:
                return self.base_price + (10 * math.sin(progress * 10 * math.pi))
            else:
                return self.base_price + 300
        else:
            return self.base_price
    
    def _generate_stable_market(self, symbol: Symbol) -> Dict[str, any]:
        """Generate stable market conditions."""
        ticker = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price - 0.5,
            ask_price=self.base_price + 0.5,
            bid_quantity=10.0,
            ask_quantity=10.0
        )
        return {'condition': MarketCondition.STABLE, 'ticker': ticker}
    
    def _generate_trending_market(self, symbol: Symbol, direction: int) -> Dict[str, any]:
        """Generate trending market (direction: 1 for up, -1 for down)."""
        trend_amount = 200 * direction
        ticker = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price + trend_amount - 1.0,
            ask_price=self.base_price + trend_amount + 1.0
        )
        return {'condition': MarketCondition.TRENDING_UP if direction > 0 else MarketCondition.TRENDING_DOWN, 
                'ticker': ticker}
    
    def _generate_volatile_condition(self, symbol: Symbol) -> Dict[str, any]:
        """Generate volatile market conditions."""
        # Wide spread with frequent updates
        ticker = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price - 10.0,
            ask_price=self.base_price + 10.0,
            bid_quantity=0.5,
            ask_quantity=0.5
        )
        return {'condition': MarketCondition.VOLATILE, 'ticker': ticker}
    
    def _generate_low_liquidity(self, symbol: Symbol) -> Dict[str, any]:
        """Generate low liquidity conditions."""
        ticker = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price - 2.0,
            ask_price=self.base_price + 2.0,
            bid_quantity=0.1,  # Very low quantities
            ask_quantity=0.1
        )
        return {'condition': MarketCondition.LOW_LIQUIDITY, 'ticker': ticker}
    
    def _generate_high_spread(self, symbol: Symbol) -> Dict[str, any]:
        """Generate high spread conditions."""
        ticker = TestDataFactory.create_book_ticker(
            symbol=symbol,
            bid_price=self.base_price - 50.0,
            ask_price=self.base_price + 50.0
        )
        return {'condition': MarketCondition.HIGH_SPREAD, 'ticker': ticker}
    
    def _get_next_timestamp(self) -> int:
        """Get next timestamp for sequence generation."""
        self.timestamp_counter += 1000  # 1 second increment
        return self.timestamp_counter
    
    def reset_timestamp(self):
        """Reset timestamp counter for new test."""
        self.timestamp_counter = int(time.time() * 1000)