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
    check_interval = 10 * 60  # Check every 15 minutes
    
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


if __name__ == "__main__":
    import os
    asyncio.run(run_live_rebalancer())
