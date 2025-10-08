#!/usr/bin/env python3
"""
Enhanced Delta Neutral Strategy Runner

Wrapper script to run the enhanced 3-exchange delta neutral strategy from the project root.
This ensures correct import paths and provides a convenient entry point.

Usage from project root:
    python run_enhanced_delta_neutral.py
    python run_enhanced_delta_neutral.py --symbol BTC --quote USDT --duration 10
    python run_enhanced_delta_neutral.py --symbol ETH --quote USDT --position-size 200 --entry-threshold 0.15
"""

import sys
import subprocess
from pathlib import Path
import argparse


def main():
    """Run the enhanced delta neutral strategy with proper path setup."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Enhanced 3-Exchange Delta Neutral Strategy')
    parser.add_argument('--symbol', default='NEIROETH', help='Base symbol to trade (default: NEIROETH)')
    parser.add_argument('--quote', default='USDT', help='Quote currency (default: USDT)')
    parser.add_argument('--duration', type=int, default=5, help='Strategy duration in minutes (default: 5)')
    parser.add_argument('--position-size', type=float, default=100.0, help='Base position size (default: 100.0)')
    parser.add_argument('--entry-threshold', type=float, default=0.1, help='Entry threshold percentage (default: 0.1)')
    parser.add_argument('--exit-threshold', type=float, default=0.01, help='Exit threshold percentage (default: 0.01)')
    
    args = parser.parse_args()
    
    # Get the strategy script path
    project_root = Path(__file__).parent
    strategy_script = project_root / "hedged_arbitrage" / "strategy" / "enhanced_delta_neutral_task.py"
    
    if not strategy_script.exists():
        print(f"❌ Strategy script not found at: {strategy_script}")
        return 1
    
    print(f"🚀 Enhanced 3-Exchange Delta Neutral Strategy")
    print(f"Symbol: {args.symbol}/{args.quote}")
    print(f"Duration: {args.duration} minutes")
    print(f"Position Size: {args.position_size}")
    print(f"Entry Threshold: {args.entry_threshold}%")
    print(f"Exit Threshold: {args.exit_threshold}%")
    print()
    
    # Set environment variables for the strategy
    import os
    os.environ['STRATEGY_SYMBOL'] = args.symbol
    os.environ['STRATEGY_QUOTE'] = args.quote
    os.environ['STRATEGY_DURATION'] = str(args.duration)
    os.environ['STRATEGY_POSITION_SIZE'] = str(args.position_size)
    os.environ['STRATEGY_ENTRY_THRESHOLD'] = str(args.entry_threshold)
    os.environ['STRATEGY_EXIT_THRESHOLD'] = str(args.exit_threshold)
    
    try:
        # Run the strategy script with proper PYTHONPATH from project root
        cmd = [sys.executable, str(strategy_script)]
        env = os.environ.copy()
        env['PYTHONPATH'] = str(project_root / 'src')
        result = subprocess.run(cmd, env=env, capture_output=False)
        return result.returncode
        
    except Exception as e:
        print(f"❌ Failed to run enhanced strategy: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)