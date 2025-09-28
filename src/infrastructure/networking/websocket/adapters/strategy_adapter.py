"""
Strategy Pattern Adapter

This module provides adapters to wrap old strategy pattern components in the new
direct handling interface, enabling backward compatibility during migration.

Key Features:
- Wraps legacy strategy components to work with new handler interface
- Minimal performance overhead for legacy path
- Gradual migration support
- Maintains existing strategy pattern behavior
"""

from typing import Any, Optional, Dict
import asyncio

from infrastructure.networking.websocket.message_types import WebSocketMessageType
from infrastructure.logging import get_logger


class StrategyPatternAdapter:
    """
    Adapter to wrap old strategy pattern components in new handler interface.
    
    This adapter allows legacy strategy-based WebSocket handling to work with
    the new direct handling architecture. It serves as a bridge during migration
    to ensure backward compatibility.
    
    Performance Note:
    - This adapter maintains the existing strategy pattern overhead
    - Should only be used during migration period
    - Switch to direct handlers for optimal performance
    """
    
    def __init__(
        self,
        exchange_name: str,
        strategy_set: Any,  # WebSocketStrategySet from legacy code
        message_handler: Optional[callable] = None
    ):
        """
        Initialize adapter with legacy strategy components.
        
        Args:
            exchange_name: Name of the exchange
            strategy_set: Legacy WebSocketStrategySet instance
            message_handler: Optional custom message handler
        """
        super().__init__(exchange_name)
        self.strategy_set = strategy_set
        self.message_handler = message_handler
        self.logger = get_logger(f"strategy_adapter.{exchange_name}", tags=["adapter", "legacy"])
        
        # Legacy compatibility tracking
        self._legacy_message_count = 0
        self._parsing_errors = 0
    
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Handle message using legacy strategy pattern.
        
        This method maintains the old strategy pattern flow:
        1. Use strategy set message parser
        2. Parse message to structured format
        3. Call legacy message handler
        
        Args:
            raw_message: Raw WebSocket message
        """
        try:
            self._legacy_message_count += 1
            
            # Legacy path: Use strategy pattern message parser
            if hasattr(self.strategy_set, 'message_parser'):
                parsed_message = await self.strategy_set.message_parser.parse_message(raw_message)
                
                if parsed_message and self.message_handler:
                    await self.message_handler(parsed_message)
                elif parsed_message:
                    # Default handling if no custom handler provided
                    await self._default_legacy_handling(parsed_message)
                else:
                    self.logger.warning("Failed to parse message with legacy parser")
                    self._parsing_errors += 1
            else:
                self.logger.error("Strategy set has no message parser")
                
        except Exception as e:
            await self._handle_error(raw_message, e)
    
    async def _default_legacy_handling(self, parsed_message: Any) -> None:
        """
        Default handling for parsed messages when no custom handler provided.
        
        Args:
            parsed_message: Parsed message from legacy strategy parser
        """
        # Basic logging for legacy messages
        self.logger.debug(f"Processed legacy message: {type(parsed_message).__name__}")
    
    async def _detect_message_type(self, raw_message: Any) -> WebSocketMessageType:
        """
        Detect message type using legacy strategy pattern.
        
        This method attempts to determine message type through the legacy
        strategy pattern if available, otherwise returns UNKNOWN.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            Detected message type or UNKNOWN
        """
        try:
            # Attempt to use legacy strategy for type detection
            if hasattr(self.strategy_set, 'message_parser'):
                # Most legacy parsers don't have explicit type detection
                # Try to parse and infer type from result
                parsed = await self.strategy_set.message_parser.parse_message(raw_message)
                
                if parsed:
                    # Infer type based on parsed message structure
                    return self._infer_legacy_message_type(parsed)
            
            return WebSocketMessageType.UNKNOWN
            
        except Exception as e:
            self.logger.warning(f"Legacy type detection failed: {e}")
            return WebSocketMessageType.UNKNOWN
    
    def _infer_legacy_message_type(self, parsed_message: Any) -> WebSocketMessageType:
        """
        Infer message type from legacy parsed message structure.
        
        Args:
            parsed_message: Parsed message from legacy parser
            
        Returns:
            Inferred message type
        """
        # Basic type inference based on common patterns
        message_str = str(type(parsed_message).__name__).lower()
        
        if 'orderbook' in message_str or 'book' in message_str:
            return WebSocketMessageType.ORDERBOOK
        elif 'trade' in message_str:
            return WebSocketMessageType.TRADE
        elif 'ticker' in message_str:
            return WebSocketMessageType.TICKER
        elif 'order' in message_str:
            return WebSocketMessageType.ORDER_UPDATE
        elif 'balance' in message_str:
            return WebSocketMessageType.BALANCE_UPDATE
        elif 'position' in message_str:
            return WebSocketMessageType.POSITION_UPDATE
        else:
            return WebSocketMessageType.UNKNOWN
    
    # Legacy interface compatibility
    def get_strategy_set(self) -> Any:
        """Get the underlying legacy strategy set."""
        return self.strategy_set
    
    def set_message_handler(self, handler: callable) -> None:
        """Set custom message handler for parsed messages."""
        self.message_handler = handler
    
    def get_legacy_stats(self) -> Dict[str, Any]:
        """Get statistics specific to legacy adapter."""
        return {
            "legacy_message_count": self._legacy_message_count,
            "parsing_errors": self._parsing_errors,
            "error_rate": self._parsing_errors / max(1, self._legacy_message_count),
            "has_message_parser": hasattr(self.strategy_set, 'message_parser'),
            "has_message_handler": self.message_handler is not None
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status including legacy stats."""
        base_status = {
            "is_connected": self.is_connected,
            "message_count": self.message_count,
            "exchange_name": self.exchange_name
        }
        
        legacy_stats = self.get_legacy_stats()
        base_status.update(legacy_stats)
        
        return base_status


# Factory function for creating strategy adapters
def create_strategy_adapter(
    exchange_name: str,
    strategy_set: Any,
    message_handler: Optional[callable] = None
) -> StrategyPatternAdapter:
    """
    Create a strategy pattern adapter for legacy components.
    
    Args:
        exchange_name: Name of the exchange
        strategy_set: Legacy WebSocketStrategySet instance
        message_handler: Optional custom message handler
        
    Returns:
        Strategy pattern adapter instance
    """
    return StrategyPatternAdapter(exchange_name, strategy_set, message_handler)