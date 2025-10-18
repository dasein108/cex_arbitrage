"""
Example live trading setup for portfolio rebalancing.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from exchanges.dual_exchange import DualExchange
from src.applications.portfolio_rebalancer import (
    LiveRebalancer, RebalanceConfig
)


async def run_live_rebalancer():
    """Run live portfolio rebalancer on MEXC."""
    
    # ============================================
    # CONFIGURATION - ADJUST THESE SETTINGS
    # ============================================
    
    # Your volatile assets (ensure these exist on MEXC)
    assets = ['HANA', 'AIA', 'XAN']  # Replace with your chosen assets
    
    # Rebalancing configuration for volatile crypto
    config = RebalanceConfig(
        upside_threshold=0.40,      # 40% above mean triggers sell
        downside_threshold=0.35,    # 35% below mean triggers buy
        sell_percentage=0.20,       # Sell 20% of outperformer
        usdt_reserve=0.30,         # Keep 30% as USDT reserve
        min_order_value=15.0,      # Minimum $15 orders
        cooldown_minutes=30,       # 30min cooldown per asset
        initial_capital=1000.0,    # Starting capital (for tracking)
        trading_fee=0.001          # MEXC fee
    )
    
    # Check interval (seconds)
    check_interval = 60  # Check every minute
    
    # ============================================
    # EXCHANGE SETUP
    # ============================================
    
    print("""
=== Live Portfolio Rebalancer ===
WARNING: This will execute REAL trades on MEXC!
Ensure you have:
1. Valid MEXC API credentials in environment
2. Sufficient USDT balance
3. Tested with small amounts first
""")
    
    # Confirm before proceeding
    confirm = input("Type 'YES' to proceed with live trading: ")
    if confirm != 'YES':
        print("Cancelled.")
        return
    
    # Create live rebalancer (it will initialize MEXC config internally)
    print("Creating rebalancer with MEXC connection...")
    rebalancer = LiveRebalancer(
        assets=assets,
        config=config
    )
    
    try:
        # Initialize exchange and portfolio
        await rebalancer.initialize()
        
        # Optional: Initialize portfolio with equal weights
        # Only run this ONCE when starting with a new portfolio!
        initialize = input("\nInitialize portfolio with equal weights? (y/n): ")
        if initialize.lower() == 'y':
            await rebalancer.initialize_portfolio()
        
        print(f"""
=== Starting Live Rebalancing ===
Assets: {', '.join(assets)}
Check Interval: {check_interval} seconds

Configuration:
- Upside: {config.upside_threshold:.0%} above mean
- Downside: {config.downside_threshold:.0%} below mean  
- Sell Size: {config.sell_percentage:.0%} of position
- USDT Reserve: {config.usdt_reserve:.0%}
- Min Order: ${config.min_order_value:.2f}
- Cooldown: {config.cooldown_minutes} minutes

Press Ctrl+C to stop...
""")
        
        # Run rebalancing loop
        await rebalancer.run_forever(check_interval=check_interval)
        
    except KeyboardInterrupt:
        print("\n\nStopping rebalancer...")
        await rebalancer.stop()
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        await rebalancer.stop()
    
    finally:
        # Cleanup
        await DualExchange.cleanup_all()
        print("Shutdown complete.")


async def dry_run_mode():
    """
    Dry run mode - monitors prices and simulates rebalancing without executing trades.
    """
    
    assets = ['BTC', 'ETH', 'BNB']  # Use major pairs for testing
    
    config = RebalanceConfig(
        upside_threshold=0.20,      # Lower thresholds for more frequent triggers
        downside_threshold=0.20,
        sell_percentage=0.20,
        usdt_reserve=0.30,
        min_order_value=15.0,
        cooldown_minutes=15,
        initial_capital=10000.0,   # Simulated capital
        trading_fee=0.001
    )
    
    print("""
=== DRY RUN MODE ===
Monitoring prices and simulating rebalancing decisions.
No actual trades will be executed.
""")
    
    # For dry run, we only need public data
    from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRestInterface
    from src.applications.portfolio_rebalancer.portfolio_tracker import PortfolioTracker
    from src.applications.portfolio_rebalancer.rebalancer import ThresholdCascadeRebalancer
    from exchanges.structs import Symbol
    from exchanges.structs.types import AssetName
    from config.config_manager import HftConfig
    
    # Initialize HFT config and MEXC REST client
    hft_config = HftConfig()
    mexc_config = hft_config.get_exchange_config('mexc')
    rest_client = MexcPublicSpotRestInterface(mexc_config)
    
    # Initialize tracker and rebalancer
    tracker = PortfolioTracker(assets, config.initial_capital, config)
    rebalancer = ThresholdCascadeRebalancer(assets, config, tracker)
    
    # Initialize with equal weights (simulated)
    print("Fetching initial prices...")
    prices = {}
    for asset in assets:
        symbol = Symbol(base=AssetName(asset), quote=AssetName('USDT'))
        orderbook = await rest_client.get_orderbook(symbol, limit=5)
        mid_price = (orderbook.bids[0].price + orderbook.asks[0].price) / 2
        prices[asset] = mid_price
        print(f"  {asset}: ${mid_price:.2f}")
    
    tracker.initialize_equal_weights(prices, datetime.now())
    
    print("\nStarting dry run monitoring (Ctrl+C to stop)...\n")
    
    try:
        while True:
            # Fetch current prices
            for asset in assets:
                symbol = Symbol(base=AssetName(asset), quote=AssetName('USDT'))
                orderbook = await rest_client.get_orderbook(symbol, limit=5)
                mid_price = (orderbook.bids[0].price + orderbook.asks[0].price) / 2
                prices[asset] = mid_price
            
            # Update portfolio state
            state = tracker.update_prices(prices, datetime.now())
            
            # Check for rebalancing
            trigger = rebalancer.check_rebalance_needed(state)
            
            if trigger:
                symbol, deviation, direction = trigger
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] REBALANCE TRIGGER!")
                print(f"  Asset: {symbol}")
                print(f"  Deviation: {deviation:+.1%}")
                print(f"  Direction: {direction}")
                
                # Calculate what would be done
                actions = rebalancer.calculate_rebalance_actions(state, trigger)
                print(f"  Simulated Actions:")
                for action in actions:
                    print(f"    - {action}")
                
                # Simulate execution in tracker
                for action in actions:
                    try:
                        tracker.execute_trade(
                            symbol=action.symbol,
                            quantity=action.quantity,
                            price=action.price,
                            side=action.side,
                            timestamp=action.timestamp
                        )
                    except Exception as e:
                        print(f"    Simulation error: {e}")
            
            # Print status every 5 minutes
            if datetime.now().minute % 5 == 0 and datetime.now().second < 30:
                metrics = tracker.get_portfolio_metrics()
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Portfolio Status:")
                print(f"  Value: ${state.total_value:.2f} ({metrics['total_return']:+.2%})")
                print(f"  Positions: ", end="")
                for asset, asset_state in state.assets.items():
                    print(f"{asset}:{asset_state.weight:.1%} ", end="")
                print()
            
            # Wait before next check
            await asyncio.sleep(30)
            
    except KeyboardInterrupt:
        print("\n\nDry run stopped.")
        
        # Print final statistics
        metrics = tracker.get_portfolio_metrics()
        stats = rebalancer.get_statistics()
        
        print("\n=== Final Statistics ===")
        print(f"Total Return: {metrics['total_return']:+.2%}")
        print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
        print(f"Rebalance Events: {stats['total_events']}")
        print(f"Total Volume: ${stats['total_volume']:.2f}")
        print(f"Simulated Fees: ${stats['total_fees']:.2f}")


if __name__ == "__main__":
    import os
    
    print("Portfolio Rebalancer - Live Trading\n")
    print("Select mode:")
    print("1. Live Trading (REAL MONEY)")
    print("2. Dry Run (Simulation)")
    
    choice = input("\nEnter choice (1 or 2): ")
    
    if choice == '1':
        # Check for API keys
        if not os.getenv('MEXC_API_KEY') or not os.getenv('MEXC_SECRET_KEY'):
            print("\nERROR: MEXC API credentials not found in environment!")
            print("Set MEXC_API_KEY and MEXC_SECRET_KEY environment variables.")
            sys.exit(1)
        
        asyncio.run(run_live_rebalancer())
    elif choice == '2':
        asyncio.run(dry_run_mode())
    else:
        print("Invalid choice.")