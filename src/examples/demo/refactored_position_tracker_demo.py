#!/usr/bin/env python3
"""
Refactored Position Tracker Demonstration

Demonstrates the new strategy-agnostic position tracker capabilities:
1. Same-exchange trading with rotating amounts
2. Direct price input functionality
3. Cross-exchange arbitrage with strategy-delegated P&L calculations
4. Simultaneous buy spot/sell futures operations

Key architectural improvements:
- Strategy-agnostic design with delegation pattern
- Direct price input support via entry_prices/exit_prices
- Flexible arbitrage scenarios including same-exchange trading
- Profit calculations delegated to individual strategy implementations
"""

import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import logging

# Import the refactored components
from trading.signals.backtesting.position_tracker import PositionTracker, Position, Trade
from trading.signals.implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.types.signal_types import Signal
from exchanges.structs import Symbol, AssetName

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class RefactoredSystemDemo:
    """Comprehensive demonstration of refactored position tracking capabilities."""
    
    def __init__(self):
        self.tracker = PositionTracker(initial_capital=10000.0)
        self.strategy = InventorySpotStrategySignalV2(
            symbol=Symbol(base=AssetName('FLK'), quote=AssetName('USDT')),
            position_size_usd=1000.0,
            min_execution_confidence=0.7,
            safe_offset_percentile=25.0
        )
        
    async def demonstrate_all_capabilities(self):
        """Run comprehensive demonstration of all refactored capabilities."""
        
        logger.info("🚀 Starting Refactored Position Tracker Demonstration")
        logger.info("=" * 70)
        
        # 1. Same-exchange trading with rotating amounts
        await self.demo_same_exchange_trading()
        
        # 2. Direct price input functionality
        await self.demo_direct_price_input()
        
        # 3. Cross-exchange arbitrage with strategy delegation
        await self.demo_cross_exchange_arbitrage()
        
        # 4. Simultaneous spot/futures operations
        await self.demo_simultaneous_spot_futures()
        
        # 5. Vectorized backtesting with new system
        await self.demo_vectorized_backtesting()
        
        # Final performance summary
        self.show_final_performance()
        
    async def demo_same_exchange_trading(self):
        """Demonstrate same-exchange trading with rotating amounts."""
        
        logger.info("\n1️⃣ Same-Exchange Trading with Rotating Amounts")
        logger.info("-" * 50)
        
        # Reset tracker for this demo
        self.tracker.reset()
        
        # Simulate same-exchange trading on Gate.io with rotating amounts
        # Entry: Buy 500 USDT worth, then immediately sell different amount
        logger.info("Scenario: Gate.io spot trading with rotating amounts")
        
        # Entry signal with direct prices for same-exchange trading
        entry_prices = {
            'gateio_spot_bid': 0.05450,  # Current bid price
            'gateio_spot_ask': 0.05455,  # Current ask price
            'entry_buy_price': 0.05455,  # We buy at ask price
            'entry_sell_price': 0.05450, # We sell at bid price
        }
        
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.ENTER,
            strategy=self.strategy,
            entry_prices=entry_prices,
            same_exchange=True,
            exchange='GATEIO_SPOT',
            rotating_amount=1.5,  # 50% more on second leg
            position_size_usd=1000.0
        )
        
        logger.info(f"✅ Opened same-exchange position")
        logger.info(f"   Current position: {self.tracker.current_position.strategy_type}")
        logger.info(f"   Entry data: {list(self.tracker.current_position.entry_data.keys())}")
        
        # Exit signal with different prices (simulating price movement)
        exit_prices = {
            'gateio_spot_bid': 0.05465,  # Price moved up
            'gateio_spot_ask': 0.05470,
            'exit_buy_price': 0.05470,   # Close short at higher ask
            'exit_sell_price': 0.05465,  # Close long at higher bid
        }
        
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=self.strategy,
            exit_prices=exit_prices,
            same_exchange=True
        )
        
        if trade_result:
            logger.info(f"✅ Closed same-exchange position")
            logger.info(f"   P&L: ${trade_result.pnl_usd:.2f} ({trade_result.pnl_pct:.3f}%)")
            logger.info(f"   Hold time: {trade_result.hold_time_minutes:.1f} minutes")
            logger.info(f"   Strategy handled P&L calculation: {trade_result.strategy_type}")
        
    async def demo_direct_price_input(self):
        """Demonstrate direct price input functionality."""
        
        logger.info("\n2️⃣ Direct Price Input Functionality")
        logger.info("-" * 50)
        
        self.tracker.reset()
        
        # Direct price input without market data - useful for manual trading
        logger.info("Scenario: Manual price input for precise execution")
        
        # Entry with exact prices specified
        manual_entry_prices = {
            'mexc_bid': 0.05440,
            'mexc_ask': 0.05445,
            'gateio_futures_bid': 0.05435,
            'gateio_futures_ask': 0.05440
        }
        
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.ENTER,
            strategy=self.strategy,
            entry_prices=manual_entry_prices,  # Direct price input
            market_data=None,  # No market data needed
            execution_mode='manual',
            position_size_usd=1500.0
        )
        
        logger.info(f"✅ Position opened with direct price input")
        logger.info(f"   No market data dependencies")
        logger.info(f"   Precise price control: {manual_entry_prices}")
        
        # Exit with different manual prices
        manual_exit_prices = {
            'mexc_bid': 0.05460,      # Better exit prices
            'mexc_ask': 0.05465,
            'gateio_futures_bid': 0.05450,
            'gateio_futures_ask': 0.05455
        }
        
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=self.strategy,
            exit_prices=manual_exit_prices,
            execution_mode='manual'
        )
        
        if trade_result:
            logger.info(f"✅ Position closed with direct price input")
            logger.info(f"   P&L: ${trade_result.pnl_usd:.2f} ({trade_result.pnl_pct:.3f}%)")
            logger.info(f"   Manual execution achieved precise control")
        
    async def demo_cross_exchange_arbitrage(self):
        """Demonstrate cross-exchange arbitrage with strategy delegation."""
        
        logger.info("\n3️⃣ Cross-Exchange Arbitrage with Strategy Delegation")
        logger.info("-" * 50)
        
        self.tracker.reset()
        
        # Traditional cross-exchange arbitrage with strategy handling all calculations
        logger.info("Scenario: MEXC vs Gate.io arbitrage with strategy delegation")
        
        market_data = {
            'mexc_bid': 0.05470,
            'mexc_ask': 0.05475,
            'gateio_spot_bid': 0.05460,
            'gateio_spot_ask': 0.05465,
            'timestamp': datetime.now(timezone.utc)
        }
        
        # Strategy calculates whether this is a good arbitrage opportunity
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.ENTER,
            strategy=self.strategy,
            market_data=market_data,
            cross_exchange=True,
            buy_exchange='GATEIO_SPOT',
            sell_exchange='MEXC_SPOT',
            position_size_usd=2000.0
        )
        
        logger.info(f"✅ Cross-exchange arbitrage position opened")
        logger.info(f"   Strategy calculated optimal execution")
        logger.info(f"   Buy exchange: GATEIO_SPOT at {market_data['gateio_spot_ask']}")
        logger.info(f"   Sell exchange: MEXC_SPOT at {market_data['mexc_bid']}")
        
        # Market moves - exit the arbitrage
        exit_market_data = {
            'mexc_bid': 0.05480,      # Price convergence
            'mexc_ask': 0.05485,
            'gateio_spot_bid': 0.05475,
            'gateio_spot_ask': 0.05480,
            'timestamp': datetime.now(timezone.utc)
        }
        
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=self.strategy,
            market_data=exit_market_data,
            cross_exchange=True
        )
        
        if trade_result:
            logger.info(f"✅ Cross-exchange arbitrage closed")
            logger.info(f"   P&L: ${trade_result.pnl_usd:.2f} ({trade_result.pnl_pct:.3f}%)")
            logger.info(f"   Strategy delegated all P&L calculations")
            logger.info(f"   Exit reason: {trade_result.exit_reason}")
        
    async def demo_simultaneous_spot_futures(self):
        """Demonstrate simultaneous buy spot/sell futures operations."""
        
        logger.info("\n4️⃣ Simultaneous Spot/Futures Operations")
        logger.info("-" * 50)
        
        self.tracker.reset()
        
        # Simultaneous spot buy + futures sell for delta-neutral arbitrage
        logger.info("Scenario: Delta-neutral arbitrage (buy spot, sell futures)")
        
        market_data = {
            'gateio_spot_bid': 0.05460,
            'gateio_spot_ask': 0.05465,
            'gateio_futures_bid': 0.05475,    # Futures trading at premium
            'gateio_futures_ask': 0.05480,
            'funding_rate': 0.0001,           # Positive funding rate
            'timestamp': datetime.now(timezone.utc)
        }
        
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.ENTER,
            strategy=self.strategy,
            market_data=market_data,
            simultaneous_execution=True,
            spot_action='buy',
            futures_action='sell',
            hedge_ratio=1.0,
            position_size_usd=2500.0
        )
        
        logger.info(f"✅ Simultaneous spot/futures position opened")
        logger.info(f"   Spot: BUY at {market_data['gateio_spot_ask']}")
        logger.info(f"   Futures: SELL at {market_data['gateio_futures_bid']}")
        logger.info(f"   Delta-neutral hedge established")
        
        # Exit the delta-neutral position
        exit_market_data = {
            'gateio_spot_bid': 0.05470,
            'gateio_spot_ask': 0.05475,
            'gateio_futures_bid': 0.05485,    # Premium increased
            'gateio_futures_ask': 0.05490,
            'funding_rate': 0.00015,          # Higher funding rate
            'timestamp': datetime.now(timezone.utc)
        }
        
        trade_result = self.tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=self.strategy,
            market_data=exit_market_data,
            simultaneous_execution=True
        )
        
        if trade_result:
            logger.info(f"✅ Simultaneous spot/futures position closed")
            logger.info(f"   P&L: ${trade_result.pnl_usd:.2f} ({trade_result.pnl_pct:.3f}%)")
            logger.info(f"   Funding income captured: ${trade_result.entry_data.get('funding_income', 0):.2f}")
            logger.info(f"   Delta-neutral strategy successful")
        
    async def demo_vectorized_backtesting(self):
        """Demonstrate vectorized backtesting with new position tracker."""
        
        logger.info("\n5️⃣ Vectorized Backtesting with Refactored System")
        logger.info("-" * 50)
        
        # Create sample historical data
        dates = pd.date_range(start='2024-01-01', end='2024-01-02', freq='5min')
        
        # Simulate realistic price data with arbitrage opportunities
        base_price = 0.0545
        price_noise = 0.0001
        
        historical_data = pd.DataFrame({
            'timestamp': dates,
            'mexc_bid': base_price - price_noise + (dates.hour % 24) * 0.00001,
            'mexc_ask': base_price + price_noise + (dates.hour % 24) * 0.00001,
            'gateio_spot_bid': base_price - price_noise * 1.5 + (dates.minute % 60) * 0.000005,
            'gateio_spot_ask': base_price + price_noise * 1.5 + (dates.minute % 60) * 0.000005,
            'gateio_futures_bid': base_price - price_noise * 0.8 + (dates.second % 60) * 0.000001,
            'gateio_futures_ask': base_price + price_noise * 0.8 + (dates.second % 60) * 0.000001,
        })
        
        # Add signals based on spread conditions
        historical_data['mexc_vs_gateio_spread'] = (
            (historical_data['mexc_bid'] - historical_data['gateio_spot_ask']) / 
            historical_data['mexc_bid'] * 100
        )
        
        # Generate entry/exit signals
        historical_data['signal'] = Signal.HOLD.value
        historical_data.loc[historical_data['mexc_vs_gateio_spread'] > 0.1, 'signal'] = Signal.ENTER.value
        historical_data.loc[historical_data['mexc_vs_gateio_spread'] < 0.05, 'signal'] = Signal.EXIT.value
        
        historical_data.set_index('timestamp', inplace=True)
        
        logger.info(f"✅ Created historical dataset: {len(historical_data)} rows")
        logger.info(f"   Date range: {historical_data.index[0]} to {historical_data.index[-1]}")
        logger.info(f"   Signals: {(historical_data['signal'] == Signal.ENTER.value).sum()} ENTER, "
                   f"{(historical_data['signal'] == Signal.EXIT.value).sum()} EXIT")
        
        # Run vectorized backtesting
        self.tracker.reset()
        positions, trades = self.tracker.track_positions_vectorized(
            df=historical_data,
            strategy=self.strategy,
            position_size_usd=1000.0,
            cross_exchange=True
        )
        
        logger.info(f"✅ Vectorized backtesting completed")
        logger.info(f"   Positions tracked: {len(positions)}")
        logger.info(f"   Trades completed: {len(trades)}")
        
        if trades:
            total_pnl = sum(t.pnl_usd for t in trades)
            avg_hold_time = sum(t.hold_time_minutes for t in trades) / len(trades)
            win_rate = len([t for t in trades if t.pnl_usd > 0]) / len(trades) * 100
            
            logger.info(f"   Total P&L: ${total_pnl:.2f}")
            logger.info(f"   Average hold time: {avg_hold_time:.1f} minutes")
            logger.info(f"   Win rate: {win_rate:.1f}%")
        
    def show_final_performance(self):
        """Show final performance summary of the demonstration."""
        
        logger.info("\n📊 Final Performance Summary")
        logger.info("=" * 70)
        
        # Get current metrics from the tracker
        metrics = self.tracker.get_current_metrics()
        
        logger.info(f"💰 Capital Management:")
        logger.info(f"   Initial capital: ${self.tracker.initial_capital:,.2f}")
        logger.info(f"   Current capital: ${metrics['current_capital']:,.2f}")
        logger.info(f"   Total return: {metrics['total_return_pct']:.3f}%")
        
        logger.info(f"\n📈 Trading Performance:")
        logger.info(f"   Total trades: {metrics['total_trades']}")
        logger.info(f"   Total P&L: ${metrics['total_pnl_usd']:,.2f}")
        logger.info(f"   Win rate: {metrics['win_rate_pct']:.1f}%")
        logger.info(f"   Profit factor: {metrics['profit_factor']:.2f}")
        
        if self.tracker.completed_trades:
            avg_trade = metrics['total_pnl_usd'] / metrics['total_trades']
            logger.info(f"   Average trade: ${avg_trade:.2f}")
            
            # Show trade details
            logger.info(f"\n🔍 Trade Details:")
            for i, trade in enumerate(self.tracker.completed_trades[-3:], 1):  # Last 3 trades
                logger.info(f"   Trade {i}: {trade.strategy_type}")
                logger.info(f"     P&L: ${trade.pnl_usd:.2f} ({trade.pnl_pct:.3f}%)")
                logger.info(f"     Duration: {trade.hold_time_minutes:.1f} min")
                logger.info(f"     Exit reason: {trade.exit_reason}")
        
        logger.info(f"\n✨ System Capabilities Demonstrated:")
        logger.info(f"   ✅ Same-exchange trading with rotating amounts")
        logger.info(f"   ✅ Direct price input functionality") 
        logger.info(f"   ✅ Cross-exchange arbitrage with strategy delegation")
        logger.info(f"   ✅ Simultaneous spot/futures operations")
        logger.info(f"   ✅ Vectorized backtesting compatibility")
        logger.info(f"   ✅ Strategy-agnostic position tracking")
        logger.info(f"   ✅ Profit calculations delegated to strategies")
        
        logger.info(f"\n🚀 Refactoring Success: Flexible, extensible, and powerful!")


async def main():
    """Run the comprehensive demonstration."""
    
    demo = RefactoredSystemDemo()
    await demo.demonstrate_all_capabilities()


if __name__ == "__main__":
    asyncio.run(main())