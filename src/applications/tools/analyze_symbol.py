#!/usr/bin/env python3
"""
Multi-Symbol Analytics Wrapper

Wrapper script to call the analytics tools from the project root directory.
This ensures correct import paths and provides a convenient entry point.

Usage from project root:
    python analyze_symbol.py --symbol NEIROETH --quote USDT
    python analyze_symbol.py --symbol BTC --quote USDT --mode historical
    python analyze_symbol.py --mode portfolio --symbols BTC,ETH,NEIROETH --quote USDT --portfolio-size 10000
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run the analytics tool with proper path setup."""
    # Get the actual analytics script path
    project_root = Path(__file__).parent
    analytics_script = project_root / "hedged_arbitrage" / "analytics" / "analyze_symbol.py"
    
    if not analytics_script.exists():
        print(f"❌ Analytics script not found at: {analytics_script}")
        return 1
    
    # Change to the analytics directory and run the script
    # This ensures imports work correctly
    import os
    original_cwd = os.getcwd()
    
    try:
        # Change to analytics directory
        os.chdir(analytics_script.parent)
        
        # Run the script with all arguments
        cmd = [sys.executable, "analyze_symbol.py"] + sys.argv[1:]
        result = subprocess.run(cmd, capture_output=False)
        return result.returncode
        
    except Exception as e:
        print(f"❌ Failed to run analytics: {e}")
        return 1
    finally:
        # Restore original directory
        os.chdir(original_cwd)

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)