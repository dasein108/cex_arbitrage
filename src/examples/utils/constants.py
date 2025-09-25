"""
Shared constants for example scripts and tests.

Eliminates duplicate symbol definitions and test parameters across all examples.
"""

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

# Standard test symbols used across all demos and tests
TEST_SYMBOLS = [
    Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False),
    Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False),
]

# Additional symbols for comprehensive testing
EXTENDED_TEST_SYMBOLS = [
    Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False),
    Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False),
    Symbol(base=AssetName('BNB'), quote=AssetName('USDT'), is_futures=False),
    Symbol(base=AssetName('ADA'), quote=AssetName('USDT'), is_futures=False),
]

# Timeout constants
DEFAULT_TEST_TIMEOUT = 30
DEFAULT_MONITOR_DURATION = 20
DEFAULT_CONNECTION_TIMEOUT = 10

# Display constants
DEMO_SEPARATOR = "=" * 60