"""
Example configuration for cross-exchange spot-futures arbitrage strategy.

This file shows how to configure and initialize the spot-futures arbitrage
strategy for different cross-exchange configurations. The most profitable
opportunities are typically between different exchanges (e.g., MEXC spot vs Gate.io futures).
"""

from exchanges.structs import Symbol, AssetName, ExchangeEnum
from .spot_futures_arbitrage_task import SpotFuturesArbitrageTaskContext
from trading.strategies.structs import MarketData


def create_mexc_spot_gateio_futures_config(symbol_base: str, symbol_quote: str) -> SpotFuturesArbitrageTaskContext:
    """
    Create configuration for MEXC spot vs Gate.io futures arbitrage.
    
    This is typically the most profitable cross-exchange spot-futures arbitrage setup.
    MEXC spot often has different pricing dynamics compared to Gate.io futures.
    
    Args:
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        SpotFuturesArbitrageTaskContext configured for MEXC spot vs Gate.io futures
    """
    symbol = Symbol(
        base=AssetName(symbol_base),
        quote=AssetName(symbol_quote),
        is_futures=False  # Symbol represents the underlying asset
    )
    
    return SpotFuturesArbitrageTaskContext(
        symbol=symbol,
        total_quantity=100.0,  # Total position size
        order_qty=10.0,  # Individual order size
        current_mode='enter',  # Start in entry mode
        
        # Profitability thresholds for cross-exchange arbitrage
        min_profit_margin=0.15,  # 0.15% minimum profit (higher due to transfer costs)
        max_acceptable_spread=0.3,  # 0.3% max spread (more tolerance for cross-exchange)
        
        # Cross-exchange market configurations
        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.MEXC,  # MEXC spot market
                tick_tolerance=5,
                ticks_offset=1,
                use_market=False
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures market
                tick_tolerance=5,
                ticks_offset=1,
                use_market=False
            )
        }
    )


def create_gateio_spot_futures_config(symbol_base: str, symbol_quote: str) -> SpotFuturesArbitrageTaskContext:
    """
    Create configuration for Gate.io spot vs Gate.io futures arbitrage (same exchange).
    
    This is a traditional basis arbitrage within the same exchange.
    Lower transfer costs but potentially smaller spreads.
    
    Args:
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        SpotFuturesArbitrageTaskContext configured for Gate.io same-exchange arbitrage
    """
    symbol = Symbol(
        base=AssetName(symbol_base),
        quote=AssetName(symbol_quote),
        is_futures=False
    )
    
    return SpotFuturesArbitrageTaskContext(
        symbol=symbol,
        total_quantity=100.0,  # Same exchange - standard position size
        order_qty=10.0,
        current_mode='enter',
        
        # Tighter thresholds for same-exchange arbitrage
        min_profit_margin=0.1,  # 0.1% minimum profit (lower costs)
        max_acceptable_spread=0.2,  # 0.2% max spread
        
        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.GATEIO,  # Gate.io spot
                tick_tolerance=5,
                ticks_offset=1,
                use_market=False
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures
                tick_tolerance=5,
                ticks_offset=1,
                use_market=False
            )
        }
    )


def create_binance_spot_gateio_futures_config(symbol_base: str, symbol_quote: str) -> SpotFuturesArbitrageTaskContext:
    """
    Create configuration for Binance spot vs Gate.io futures arbitrage.
    
    Another profitable cross-exchange setup. Binance often has high liquidity
    for spot markets while Gate.io futures may have different pricing.
    
    Args:
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        SpotFuturesArbitrageTaskContext configured for Binance spot vs Gate.io futures
    """
    symbol = Symbol(
        base=AssetName(symbol_base),
        quote=AssetName(symbol_quote),
    )
    
    return SpotFuturesArbitrageTaskContext(
        symbol=symbol,
        total_quantity=200.0,  # Larger position for Binance liquidity
        order_qty=20.0,
        current_mode='enter',
        
        # Cross-exchange thresholds
        min_profit_margin=0.12,  # 0.12% minimum profit
        max_acceptable_spread=0.25,  # 0.25% max spread
        
        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.BINANCE,  # Binance spot
                tick_tolerance=3,
                ticks_offset=1,
                use_market=False
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures
                tick_tolerance=5,
                ticks_offset=1,
                use_market=False
            )
        }
    )


def create_aggressive_cross_exchange_config(symbol_base: str, symbol_quote: str) -> SpotFuturesArbitrageTaskContext:
    """
    Create aggressive cross-exchange arbitrage configuration with market orders.
    
    Uses MEXC spot vs Gate.io futures with market orders for maximum speed.
    Higher risk but faster execution for profitable opportunities.
    
    Args:
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        SpotFuturesArbitrageTaskContext configured for aggressive cross-exchange trading
    """
    symbol = Symbol(
        base=AssetName(symbol_base),
        quote=AssetName(symbol_quote),
        is_futures=False
    )
    
    return SpotFuturesArbitrageTaskContext(
        symbol=symbol,
        total_quantity=150.0,  # Aggressive position size
        order_qty=30.0,  # Large individual orders
        current_mode='enter',
        
        # Aggressive margins for cross-exchange speed
        min_profit_margin=0.08,  # 0.08% minimum profit (lower for speed)
        max_acceptable_spread=0.4,  # 0.4% max spread (higher tolerance)
        
        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.MEXC,  # MEXC spot
                tick_tolerance=10,  # Allow more price movement
                ticks_offset=0,  # Top of book
                use_market=True  # Use market orders for speed
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,  # Gate.io futures
                tick_tolerance=10,
                ticks_offset=0,
                use_market=True  # Use market orders for speed
            )
        }
    )


def create_conservative_strategy_config(symbol_base: str, symbol_quote: str) -> SpotFuturesArbitrageTaskContext:
    """
    Create conservative arbitrage configuration with limit orders and wide margins.
    
    Args:
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        SpotFuturesArbitrageTaskContext configured for conservative trading
    """
    symbol = Symbol(
        base=AssetName(symbol_base),
        quote=AssetName(symbol_quote),
        is_futures=False
    )
    
    return SpotFuturesArbitrageTaskContext(
        symbol=symbol,
        total_quantity=25.0,  # Small position
        order_qty=2.5,  # Small individual orders
        current_mode='enter',
        
        # Wide margins for conservative trading
        min_profit_margin=0.25,  # 0.25% minimum profit
        max_acceptable_spread=0.1,  # 0.1% max spread (very tight)
        
        settings={
            'spot': MarketData(
                exchange=ExchangeEnum.GATEIO,
                tick_tolerance=2,  # Cancel quickly on price moves
                ticks_offset=3,  # Place orders away from best price
                use_market=False  # Always use limit orders
            ),
            'futures': MarketData(
                exchange=ExchangeEnum.GATEIO_FUTURES,
                tick_tolerance=2,
                ticks_offset=3,
                use_market=False
            )
        }
    )


# Example usage:
if __name__ == "__main__":
    # Create different cross-exchange strategy configurations
    configs = {
        'mexc_gateio_btc': create_mexc_spot_gateio_futures_config('BTC', 'USDT'),
        'binance_gateio_eth': create_binance_spot_gateio_futures_config('ETH', 'USDT'),
        'gateio_same_exchange': create_gateio_spot_futures_config('BNB', 'USDT'),
        'aggressive_cross_exchange': create_aggressive_cross_exchange_config('SOL', 'USDT'),
        'conservative_cross_exchange': create_conservative_strategy_config('ADA', 'USDT')
    }
    
    print("🚀 Cross-Exchange Spot-Futures Arbitrage Configurations")
    print("=" * 60)
    
    for name, config in configs.items():
        is_cross_exchange = config.settings['spot'].exchange != config.settings['futures'].exchange
        exchange_type = "Cross-Exchange" if is_cross_exchange else "Same Exchange"
        
        print(f"\n📊 {name.upper()} ({exchange_type}):")
        print(f"  Symbol: {config.symbol.base}/{config.symbol.quote}")
        print(f"  Total Quantity: {config.total_quantity}")
        print(f"  Min Profit Margin: {config.min_profit_margin}%")
        print(f"  Max Spread: {config.max_acceptable_spread}%")
        print(f"  Spot Exchange: {config.settings['spot'].exchange.value}")
        print(f"  Futures Exchange: {config.settings['futures'].exchange.value}")
        print(f"  Use Market Orders: {config.settings['spot'].use_market}")
        print(f"  Transfer Required: {'Yes' if is_cross_exchange else 'No'}")
        
    print(f"\n💡 Recommended for highest profitability:")
    print(f"   1. MEXC Spot vs Gate.io Futures (mexc_gateio_btc)")
    print(f"   2. Binance Spot vs Gate.io Futures (binance_gateio_eth)")
    print(f"   3. Aggressive cross-exchange for fast opportunities")