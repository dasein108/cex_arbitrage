#!/usr/bin/env python3
"""
Analytics Test Suite Wrapper

Wrapper to run the analytics test suite from the project root.
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run the analytics test suite."""
    project_root = Path(__file__).parent
    test_script = project_root / "hedged_arbitrage" / "analytics" / "test_analytics.py"
    
    if not test_script.exists():
        print(f"❌ Test script not found at: {test_script}")
        return 1
    
    import os
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_script.parent)
        cmd = [sys.executable, "test_analytics.py"] + sys.argv[1:]
        result = subprocess.run(cmd, capture_output=False)
        return result.returncode
        
    except Exception as e:
        print(f"❌ Failed to run tests: {e}")
        return 1
    finally:
        os.chdir(original_cwd)

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)