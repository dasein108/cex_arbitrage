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
from cex.gateio.gateio_public_exchange import GateioPublicExchange
from cex.gateio.gateio_private_exchange import GateioPrivateExchange

# For backward compatibility, alias the private exchange as the main exchange
GateioExchange = GateioPrivateExchange

__all__ = ['GateioPublicExchange', 'GateioPrivateExchange', 'GateioExchange']