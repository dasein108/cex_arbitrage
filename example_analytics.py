#!/usr/bin/env python3
"""
Analytics Examples Wrapper

Wrapper to run the analytics examples from the project root.
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run the analytics examples."""
    project_root = Path(__file__).parent
    example_script = project_root / "hedged_arbitrage" / "analytics" / "example_usage.py"
    
    if not example_script.exists():
        print(f"❌ Example script not found at: {example_script}")
        return 1
    
    import os
    original_cwd = os.getcwd()
    
    try:
        os.chdir(example_script.parent)
        cmd = [sys.executable, "example_usage.py"] + sys.argv[1:]
        result = subprocess.run(cmd, capture_output=False)
        return result.returncode
        
    except Exception as e:
        print(f"❌ Failed to run examples: {e}")
        return 1
    finally:
        os.chdir(original_cwd)

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)