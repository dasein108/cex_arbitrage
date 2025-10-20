#!/usr/bin/env python3
"""
Optimized Cross-Exchange Arbitrage Demo

Demonstrates the enhanced arbitrage strategy with separate entry/exit logic,
position tracking, and improved risk management.

Key Features:
1. Separate entry/exit spread calculations
2. Real-time position P&L tracking
3. Multiple exit criteria (profit target, time limit, stop loss)
4. Enhanced risk management and liquidity validation
5. Performance analytics and monitoring

This addresses the critical issue where entry and exit arbitrage calculations
were identical in the original implementation.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from exchanges.structs import Symbol, AssetName, ExchangeEnum, BookTicker
from trading.analysis.optimized_cross_arbitrage_ta import (
    OptimizedCrossArbitrageTA, 
    create_optimized_cross_arbitrage_ta
)
from infrastructure.logging import get_logger


class OptimizedArbitrageDemo:
    """
    Demo class showcasing optimized cross-exchange arbitrage strategy.
    
    Simulates real trading conditions with mock market data to demonstrate
    the enhanced signal generation and risk management capabilities.
    """
    
    def __init__(self):
        self.logger = get_logger('optimized_arbitrage_demo')
        self.symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        self.ta: Optional[OptimizedCrossArbitrageTA] = None
        self.simulation_step = 0
        
    async def initialize(self):
        """Initialize the optimized TA module."""
        self.logger.info("🚀 Initializing Optimized Arbitrage Demo")
        
        # Create optimized TA with enhanced parameters
        self.ta = await create_optimized_cross_arbitrage_ta(
            symbol=self.symbol,
            lookback_hours=24,
            profit_target=0.5,      # 0.5% profit target
            max_holding_hours=2.0,  # 2 hours maximum hold time
            logger=self.logger
        )
        
        if self.ta.thresholds:
            self.logger.info("✅ Demo initialized successfully",
                           entry_threshold=f"{self.ta.thresholds.entry_spread:.4f}%",
                           profit_target=f"{self.ta.thresholds.profit_target:.2f}%",
                           total_costs=f"{self.ta.total_costs_pct:.2f}%")
        else:
            self.logger.warning("⚠️ Demo initialized without thresholds - using defaults")
    
    def create_mock_market_data(self, scenario: str = "normal") -> tuple[BookTicker, BookTicker, BookTicker]:
        """
        Create mock market data for different scenarios.
        
        Scenarios:
        - "normal": Regular market conditions
        - "opportunity": Arbitrage opportunity available
        - "exit_profit": Profitable exit available
        - "exit_loss": Stop loss scenario
        """
        base_price = 50000.0
        timestamp = datetime.now(timezone.utc)
        
        if scenario == "normal":
            # Normal market, no significant arbitrage
            mexc_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price - 1, ask_price=base_price,
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price - 1, ask_price=base_price,
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_futures = BookTicker(
                symbol=self.symbol,
                bid_price=base_price + 5, ask_price=base_price + 6,  # Small premium
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            
        elif scenario == "opportunity":
            # Arbitrage opportunity: futures trading at significant premium
            mexc_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price - 1, ask_price=base_price,
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price - 1, ask_price=base_price,
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_futures = BookTicker(
                symbol=self.symbol,
                bid_price=base_price + 25, ask_price=base_price + 26,  # Large premium
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            
        elif scenario == "exit_profit":
            # Profitable exit: futures premium compressed, spot can be sold higher
            mexc_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price + 9, ask_price=base_price + 10,
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price + 10, ask_price=base_price + 11,  # Higher than entry
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_futures = BookTicker(
                symbol=self.symbol,
                bid_price=base_price + 5, ask_price=base_price + 6,  # Premium compressed
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            
        elif scenario == "exit_loss":
            # Stop loss scenario: adverse price movement
            mexc_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price - 11, ask_price=base_price - 10,
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_spot = BookTicker(
                symbol=self.symbol,
                bid_price=base_price - 10, ask_price=base_price - 9,  # Lower than entry
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
            gateio_futures = BookTicker(
                symbol=self.symbol,
                bid_price=base_price + 15, ask_price=base_price + 16,  # Premium increased
                bid_quantity=10.0, ask_quantity=10.0,
                timestamp=timestamp
            )
        
        return mexc_spot, gateio_spot, gateio_futures
    
    async def simulate_trading_session(self, steps: int = 10):
        """
        Simulate a complete trading session with various market scenarios.
        
        Demonstrates entry signal generation, position management, and exit logic.
        """
        self.logger.info(f"🎯 Starting {steps}-step trading simulation")
        
        position_open = False
        step_scenarios = ["normal", "normal", "opportunity", "normal", "normal", 
                         "exit_profit", "normal", "exit_loss", "normal", "normal"]
        
        for step in range(min(steps, len(step_scenarios))):
            scenario = step_scenarios[step]
            self.simulation_step = step + 1
            
            self.logger.info(f"\n--- Step {self.simulation_step}: {scenario.upper()} ---")
            
            # Generate mock market data
            mexc_spot, gateio_spot, gateio_futures = self.create_mock_market_data(scenario)
            
            # Generate trading signal
            signal, data = self.ta.generate_optimized_signal(
                source_book=mexc_spot,
                dest_book=gateio_spot,
                hedge_book=gateio_futures,
                position_open=position_open
            )
            
            # Process signal
            if signal == 'enter' and not position_open:
                await self._process_entry_signal(data, mexc_spot, gateio_futures)
                position_open = True
                
            elif signal == 'exit' and position_open:
                await self._process_exit_signal(data)
                position_open = False
                
            else:
                await self._process_no_action(data, position_open)
            
            # Brief pause between steps
            await asyncio.sleep(0.5)
        
        # Final analytics
        await self._display_session_analytics()
    
    async def _process_entry_signal(self, data: dict, mexc_spot: BookTicker, gateio_futures: BookTicker):
        """Process entry signal and simulate position opening."""
        entry_spread = data.get('entry_spread_net', 0)
        conditions = data.get('entry_conditions', [])
        liquidity = data.get('liquidity_score', 0)
        
        self.logger.info(f"📈 ENTRY SIGNAL GENERATED",
                        entry_spread=f"{entry_spread:.4f}%",
                        conditions=conditions,
                        liquidity=f"{liquidity:.1f}",
                        mexc_ask=f"${mexc_spot.ask_price:.0f}",
                        futures_bid=f"${gateio_futures.bid_price:.0f}")
        
        # Simulate position opening
        self.logger.info("🚀 Executing arbitrage entry:",
                        action="BUY MEXC spot + SHORT Gate.io futures",
                        expected_profit=f"{entry_spread:.4f}%")
    
    async def _process_exit_signal(self, data: dict):
        """Process exit signal and simulate position closing."""
        pnl = data.get('total_pnl_pct', 0)
        reasons = data.get('exit_reasons', [])
        hours_held = data.get('hours_held', 0)
        spot_pnl = data.get('spot_pnl_pct', 0)
        futures_pnl = data.get('futures_pnl_pct', 0)
        
        self.logger.info(f"📉 EXIT SIGNAL GENERATED",
                        total_pnl=f"{pnl:.4f}%",
                        spot_pnl=f"{spot_pnl:.4f}%",
                        futures_pnl=f"{futures_pnl:.4f}%",
                        hours_held=f"{hours_held:.2f}h",
                        reasons=reasons)
        
        # Simulate position closing
        if pnl > 0:
            self.logger.info("✅ PROFITABLE EXIT - Position closed with profit")
        else:
            self.logger.info("❌ UNPROFITABLE EXIT - Position closed to limit loss")
    
    async def _process_no_action(self, data: dict, position_open: bool):
        """Process no-action scenario."""
        if position_open:
            pnl = data.get('total_pnl_pct', 0)
            hours_held = data.get('hours_held', 0)
            exit_spread = data.get('exit_spread_net', 0)
            
            self.logger.info(f"⏸️ HOLDING POSITION",
                            current_pnl=f"{pnl:.4f}%",
                            hours_held=f"{hours_held:.2f}h",
                            exit_spread=f"{exit_spread:.4f}%")
        else:
            entry_spread = data.get('entry_spread_net', 0)
            conditions = data.get('entry_conditions', [])
            threshold = data.get('entry_threshold', 0)
            
            self.logger.info(f"⏸️ NO ENTRY - Waiting for opportunity",
                            current_spread=f"{entry_spread:.4f}%",
                            required_spread=f"{threshold:.4f}%",
                            conditions_met=f"{len(conditions)}/4")
    
    async def _display_session_analytics(self):
        """Display comprehensive session analytics."""
        self.logger.info("\n" + "="*60)
        self.logger.info("📊 TRADING SESSION ANALYTICS")
        self.logger.info("="*60)
        
        # Get performance metrics
        metrics = self.ta.get_performance_metrics()
        analytics = self.ta.get_strategy_analytics()
        
        # Display key metrics
        self.logger.info("Performance Metrics:",
                        calculations=metrics['calculation_count'],
                        signals=metrics.get('signal_distribution', {}),
                        position_open=metrics['position_open'])
        
        self.logger.info("Strategy Configuration:",
                        profit_target=f"{analytics['configuration']['profit_target']:.2f}%",
                        stop_loss=f"{analytics['configuration']['stop_loss']:.2f}%",
                        max_hold_time=f"{analytics['configuration']['max_holding_hours']:.1f}h",
                        total_costs=f"{analytics['configuration']['total_costs_pct']:.2f}%")
        
        self.logger.info("Threshold Analysis:",
                        entry_threshold=f"{analytics['thresholds']['entry_spread']:.4f}%",
                        exit_threshold=f"{analytics['thresholds']['exit_spread']:.4f}%",
                        min_profitable=f"{analytics['thresholds']['min_profitable_spread']:.4f}%")
        
        recent_activity = analytics['recent_activity']
        if recent_activity['total_signals'] > 0:
            self.logger.info("Recent Activity:",
                            total_signals=recent_activity['total_signals'],
                            enter_signals=recent_activity['enter_signals'],
                            exit_signals=recent_activity['exit_signals'],
                            avg_entry_spread=f"{recent_activity['avg_entry_spread']:.4f}%")
    
    async def demonstrate_edge_cases(self):
        """Demonstrate edge cases and risk management."""
        self.logger.info("\n🧪 DEMONSTRATING EDGE CASES")
        
        # 1. Low liquidity scenario
        self.logger.info("\n--- Edge Case 1: Low Liquidity ---")
        mexc_spot, gateio_spot, gateio_futures = self.create_mock_market_data("opportunity")
        mexc_spot.ask_quantity = 0.1  # Very low liquidity
        gateio_futures.bid_quantity = 0.1
        
        signal, data = self.ta.generate_optimized_signal(mexc_spot, gateio_spot, gateio_futures, False)
        self.logger.info(f"Low liquidity result: {signal} (liquidity: {data.get('liquidity_score', 0):.1f})")
        
        # 2. Time-based exit
        self.logger.info("\n--- Edge Case 2: Time-Based Exit ---")
        if not self.ta.position_state.is_open:
            # Simulate position opening
            self.ta.position_state.is_open = True
            self.ta.position_state.entry_time = datetime.now(timezone.utc)
            self.ta.position_state.entry_spot_price = 50000.0
            self.ta.position_state.entry_futures_price = 50025.0
            
        # Simulate time passage (mock)
        import datetime
        old_time = self.ta.position_state.entry_time
        self.ta.position_state.entry_time = old_time - datetime.timedelta(hours=2.5)  # Exceed time limit
        
        mexc_spot, gateio_spot, gateio_futures = self.create_mock_market_data("normal")
        signal, data = self.ta.generate_optimized_signal(mexc_spot, gateio_spot, gateio_futures, True)
        self.logger.info(f"Time-based exit: {signal} (hours: {data.get('hours_held', 0):.1f})")
        
        # Reset for next test
        self.ta.position_state.is_open = False


async def main():
    """Main demo function."""
    demo = OptimizedArbitrageDemo()
    
    try:
        # Initialize the demo
        await demo.initialize()
        
        # Run main simulation
        await demo.simulate_trading_session(steps=10)
        
        # Demonstrate edge cases
        await demo.demonstrate_edge_cases()
        
        print("\n" + "="*60)
        print("🎯 DEMO COMPLETED SUCCESSFULLY")
        print("="*60)
        print("\nKey Improvements Demonstrated:")
        print("✅ Separate entry/exit spread calculations")
        print("✅ Position tracking and real-time P&L")
        print("✅ Multiple exit criteria (profit, time, stop loss)")
        print("✅ Enhanced risk management and liquidity validation")
        print("✅ Comprehensive analytics and performance monitoring")
        print("\nThe optimized strategy addresses the critical issue where")
        print("entry and exit calculations were identical, providing")
        print("significantly improved trading logic for cross-exchange arbitrage.")
        
    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())