"""
Gate.io Exchange Implementation

High-performance Gate.io integration following unified cex system.
Implements PublicExchangeInterface and PrivateExchangeInterface for seamless
arbitrage engine integration.

Architecture:
- Composition pattern with separate REST and WebSocket implementations
- HFT compliance with no real-time data caching
- Type-safe data structures using msgspec.Struct
- Unified exception handling system
"""

from .gateio_exchange import GateioExchange

__all__ = ['GateioExchange']