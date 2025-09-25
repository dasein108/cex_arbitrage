"""
Gate.io Exchange Implementation

Modernized Gate.io integration following the MEXC pattern with unified configuration.
Uses composition pattern with separate public and private exchange implementations.

Architecture:
- GateioPublicExchange: Market data operations (no authentication required)
- GateioPrivateExchange: Full trading operations (includes public via composition)
- Unified ExchangeConfig with WebSocket configuration injection
- HFT-compliant performance with sub-50ms execution targets

HFT Compliance:
- No caching of real-time trading data (balances, orders, trades)
- Real-time streaming orderbook data only
- Fresh API calls for all trading operations
- Configuration data caching only (symbol info, endpoints)
"""

# Re-export the main Gate.io exchange implementations
from exchanges.integrations.gateio.public_exchange import GateioPublicExchange
from exchanges.integrations.gateio.gateio_unified_exchange import GateioUnifiedExchange

# For backward compatibility, alias the unified exchange as the main exchange
GateioExchange = GateioUnifiedExchange

__all__ = ['GateioPublicExchange', 'GateioUnifiedExchange', 'GateioExchange']