#!/usr/bin/env python3
"""
Debug HFT Logger Issue

Simple test to investigate why console logging isn't working.
Tests different import paths and configurations to isolate the problem.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

print("🔍 Starting HFT Logger Debug Test")
print(f"Python path: {sys.path[0]}")
print(f"Current directory: {os.getcwd()}")
print(f"ENVIRONMENT: {os.getenv('ENVIRONMENT', 'not_set')}")
print()

# Test 1: Direct logger creation with manual config
print("=" * 60)
print("TEST 1: Manual Logger Configuration")
print("=" * 60)

try:
    from infrastructure.logging.structs import LoggingConfig, ConsoleBackendConfig, PerformanceConfig
    from infrastructure.logging.factory import LoggerFactory
    
    # Create manual config
    manual_config = LoggingConfig(
        environment="dev",
        console=ConsoleBackendConfig(
            enabled=True,
            min_level="DEBUG",
            color=True,
            include_context=True
        ),
        performance=PerformanceConfig(
            buffer_size=1000,
            batch_size=10
        )
    )
    
    print("✅ Manual config created successfully")
    
    # Create logger with manual config
    manual_logger = LoggerFactory.create_logger("manual_test", manual_config)
    
    print("✅ Manual logger created successfully")
    
    # Test logging
    manual_logger.info("🎯 MANUAL CONFIG TEST: This should appear in console!")
    manual_logger.debug("🔧 Debug message from manual config")
    manual_logger.error("❌ Error message from manual config")
    
    print("✅ Manual logging test completed")
    
except Exception as e:
    print(f"❌ Manual config failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test 2: Factory with default config
print("=" * 60)
print("TEST 2: Factory Default Configuration")
print("=" * 60)

try:
    from infrastructure.logging.factory import get_logger
    
    # Clear cache to force fresh config load
    LoggerFactory.clear_cache()
    
    default_logger = get_logger("default_test")
    print("✅ Default logger created successfully")
    
    # Test logging
    default_logger.info("🎯 DEFAULT CONFIG TEST: This should appear in console!")
    default_logger.debug("🔧 Debug message from default config")
    default_logger.error("❌ Error message from default config")
    
    print("✅ Default logging test completed")
    
except Exception as e:
    print(f"❌ Default config failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test 3: Config manager import test
print("=" * 60)
print("TEST 3: Config Manager Import Test")
print("=" * 60)

try:
    # Test the import that factory.py tries
    print("Testing: from config import get_logging_config")
    try:
        from config import get_logging_config
        config = get_logging_config()
        print(f"✅ Old import path works: {type(config)}")
        print(f"   Config keys: {list(config.keys()) if hasattr(config, 'keys') else 'not dict-like'}")
    except Exception as e:
        print(f"❌ Old import path failed: {e}")
    
    print("\nTesting: from config.config_manager import get_logging_config")
    try:
        from config.config_manager import get_logging_config
        config = get_logging_config()
        print(f"✅ New import path works: {type(config)}")
        print(f"   Config keys: {list(config.keys()) if hasattr(config, 'keys') else 'not dict-like'}")
    except Exception as e:
        print(f"❌ New import path failed: {e}")
    
    print("\nTesting: from config.logging.config import get_logging_config")
    try:
        from config.logging.config import get_logging_config
        config = get_logging_config()
        print(f"✅ Logging config import works: {type(config)}")
        print(f"   Config keys: {list(config.keys()) if hasattr(config, 'keys') else 'not dict-like'}")
    except Exception as e:
        print(f"❌ Logging config import failed: {e}")
        
except Exception as e:
    print(f"❌ Config import test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test 4: Configuration content inspection
print("=" * 60)
print("TEST 4: Configuration Content Inspection")
print("=" * 60)

try:
    # Try to load and inspect the actual config
    from config.logging.config import get_logging_config
    
    config = get_logging_config()
    print(f"✅ Loaded config type: {type(config)}")
    
    if hasattr(config, 'keys'):
        print(f"✅ Config is dict-like with keys: {list(config.keys())}")
        
        if 'backends' in config:
            backends = config['backends']
            print(f"✅ Backends found: {list(backends.keys())}")
            
            if 'console' in backends:
                console_config = backends['console']
                print(f"✅ Console config: {console_config}")
                print(f"   Enabled: {console_config.get('enabled', 'not_set')}")
                print(f"   Min level: {console_config.get('min_level', 'not_set')}")
                print(f"   Color: {console_config.get('color', 'not_set')}")
        else:
            print("❌ No 'backends' key in config")
    else:
        print(f"❌ Config is not dict-like: {config}")
        
except Exception as e:
    print(f"❌ Config inspection failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test 5: Working logger with correct import
print("=" * 60)
print("TEST 5: Working Logger with Correct Import")
print("=" * 60)

try:
    # Clear cache
    from infrastructure.logging.factory import LoggerFactory
    LoggerFactory.clear_cache()
    
    # Try with the correct import path
    from config.logging.config import get_logger
    
    working_logger = get_logger("working_test")
    print("✅ Working logger created successfully")
    
    # Test all log levels
    working_logger.debug("🔧 DEBUG: This is a debug message")
    working_logger.info("ℹ️ INFO: This is an info message")
    working_logger.warning("⚠️ WARNING: This is a warning message")
    working_logger.error("❌ ERROR: This is an error message")
    working_logger.critical("🚨 CRITICAL: This is a critical message")
    
    print("✅ Working logger test completed")
    
except Exception as e:
    print(f"❌ Working logger test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test 6: Simple Python logging fallback
print("=" * 60)
print("TEST 6: Python Standard Logging Fallback")
print("=" * 60)

try:
    import logging
    
    # Configure basic logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    std_logger = logging.getLogger("fallback_test")
    
    std_logger.debug("🔧 STANDARD LOGGING: Debug message")
    std_logger.info("ℹ️ STANDARD LOGGING: Info message")
    std_logger.warning("⚠️ STANDARD LOGGING: Warning message")
    std_logger.error("❌ STANDARD LOGGING: Error message")
    
    print("✅ Standard logging works - this confirms console output is possible")
    
except Exception as e:
    print(f"❌ Standard logging failed: {e}")

print()
print("🏁 Logger Debug Test Complete")
print()
print("SUMMARY:")
print("- If manual config works but factory doesn't, it's an import issue")
print("- If no logs appear anywhere, it's a console/terminal issue")
print("- If standard logging works but HFT doesn't, it's HFT config issue")
print("- Check the console output above for specific error messages")