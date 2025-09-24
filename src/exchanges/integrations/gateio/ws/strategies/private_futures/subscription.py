import logging
import msgspec
from typing import List, Dict, Any, Optional, Set

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction, PrivateWebsocketChannelType
from infrastructure.data_structures.common import Symbol
from exchanges.services import BaseExchangeMapper


class GateioPrivateFuturesSubscriptionStrategy(SubscriptionStrategy):
    """Gate.io private futures WebSocket subscription strategy."""

    def __init__(self, mapper: BaseExchangeMapper):
        super().__init__(mapper)  # Initialize parent with mandatory mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Track active subscriptions for private futures
        self._active_subscriptions: Set[str] = set()
        
        # Gate.io private futures channels
        self._private_futures_channels = {
            'orders': 'futures.orders',
            'balances': 'futures.balances', 
            'user_trades': 'futures.usertrades',
            'positions': 'futures.positions'
        }

    async def create_subscription_messages(self, action: SubscriptionAction, **kwargs) -> List[Dict[str, Any]]:
        """
        Create Gate.io private futures subscription messages with authentication.
        
        Gate.io futures requires authentication info in each subscription message.
        Format includes: {"time": X, "channel": Y, "event": Z, "payload": [...], "auth": {...}}
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
        Returns:
            List of authenticated messages, one per private futures channel type
        """
        event = self.mapper.from_subscription_action(action)
        messages = []

        # Private futures channel definitions
        private_futures_channels = [
            {
                "channel": self._private_futures_channels["orders"],
                "payload": ["!all"]  # Subscribe to all futures order updates
            },
            {
                "channel": self._private_futures_channels["user_trades"],
                "payload": ["!all"]  # Subscribe to all futures trade updates
            },
            {
                "channel": self._private_futures_channels["balances"],
                "payload": []  # Balances may not need payload
            },
            {
                "channel": self._private_futures_channels["positions"],
                "payload": ["!all"]  # Subscribe to all futures position updates
            }
        ]

        for channel_config in private_futures_channels:
            # Create authenticated message using connection's method
            # Note: We'll need to get the connection strategy to create auth messages
            import time
            timestamp = str(int(time.time()))
            
            # For now, create basic message structure
            # The actual authentication will be handled by the connection strategy
            message = {
                "time": int(timestamp),
                "channel": channel_config["channel"],
                "event": event,
                "payload": channel_config.get("payload", []),
                # Authentication will be added by the WebSocket manager using connection strategy
                "_requires_auth": True  # Flag to indicate this message needs authentication
            }

            messages.append(message)

            self.logger.debug(f"Created {event} message for {channel_config['channel']} (auth required)")

        self.logger.info(f"Created {len(messages)} authenticated private futures {event} messages")

        return messages
    
    def requires_authentication(self, message: Dict[str, Any]) -> bool:
        """Check if a message requires authentication."""
        return message.get("_requires_auth", False)

    async def subscribe_symbols(self, symbols: List[Symbol], 
                              channels: List[PrivateWebsocketChannelType]) -> List[Dict[str, Any]]:
        """
        Subscribe to Gate.io private futures channels for symbols.
        
        Private futures subscriptions don't require symbol-specific channels,
        but we still track symbols for completeness.
        """
        subscription_messages = []
        
        # Subscribe to private futures channels (not symbol-specific)
        for channel_name, channel_id in self._private_futures_channels.items():
            if channel_id not in self._active_subscriptions:
                subscription_msg = self._create_subscription_message(channel_id, "subscribe")
                subscription_messages.append(subscription_msg)
                self._active_subscriptions.add(channel_id)
                self.logger.info(f"Subscribing to Gate.io private futures channel: {channel_name}")
        
        return subscription_messages

    async def unsubscribe_symbols(self, symbols: List[Symbol]) -> List[Dict[str, Any]]:
        """
        Unsubscribe from Gate.io private futures channels.
        
        Since private channels are not symbol-specific, this is rarely used.
        """
        unsubscription_messages = []
        
        # For private futures, we typically don't unsubscribe individual channels
        # unless specifically requested. This is a placeholder for completeness.
        self.logger.info(f"Gate.io private futures unsubscribe requested for {len(symbols)} symbols")
        
        return unsubscription_messages

    async def subscribe_channels(self, channels: List[str]) -> List[Dict[str, Any]]:
        """Subscribe to specific Gate.io private futures channels by name."""
        subscription_messages = []
        
        for channel in channels:
            if channel in self._private_futures_channels.values():
                if channel not in self._active_subscriptions:
                    subscription_msg = self._create_subscription_message(channel, "subscribe")
                    subscription_messages.append(subscription_msg)
                    self._active_subscriptions.add(channel)
                    self.logger.info(f"Subscribing to Gate.io private futures channel: {channel}")
            else:
                self.logger.warning(f"Unknown Gate.io private futures channel: {channel}")
        
        return subscription_messages

    async def unsubscribe_channels(self, channels: List[str]) -> List[Dict[str, Any]]:
        """Unsubscribe from specific Gate.io private futures channels by name."""
        unsubscription_messages = []
        
        for channel in channels:
            if channel in self._active_subscriptions:
                unsubscription_msg = self._create_subscription_message(channel, "unsubscribe")
                unsubscription_messages.append(unsubscription_msg)
                self._active_subscriptions.remove(channel)
                self.logger.info(f"Unsubscribing from Gate.io private futures channel: {channel}")
        
        return unsubscription_messages

    def _create_subscription_message(self, channel: str, event: str) -> Dict[str, Any]:
        """Create Gate.io private futures subscription/unsubscription message."""
        import time
        
        message = {
            "time": int(time.time()),
            "channel": channel,
            "event": event,
            "payload": []  # Private futures channels typically don't need payload
        }
        
        return message

    def format_subscription_message(self, message: Dict[str, Any]) -> str:
        """Format subscription message as JSON string."""
        return msgspec.json.encode(message).decode()

    def is_subscription_confirmed(self, message: Dict[str, Any]) -> bool:
        """Check if message confirms a subscription."""
        return (
            message.get("event") == "subscribe" and
            message.get("error") is None and
            message.get("result", {}).get("status") == "success"
        )

    def is_unsubscription_confirmed(self, message: Dict[str, Any]) -> bool:
        """Check if message confirms an unsubscription."""
        return (
            message.get("event") == "unsubscribe" and
            message.get("error") is None and
            message.get("result", {}).get("status") == "success"
        )

    def get_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from Gate.io private futures message."""
        return message.get("channel")

    def get_symbol_from_message(self, message: Dict[str, Any]) -> Optional[Symbol]:
        """
        Extract symbol from Gate.io private futures message.
        
        Private futures messages may contain contract/symbol info in the payload.
        """
        try:
            channel = message.get("channel", "")
            result = message.get("result", {})
            
            # For orders, positions, and trades, symbol is in the result
            if isinstance(result, dict):
                contract = result.get("contract")
                if contract:
                    # Parse Gate.io futures contract format (e.g., "BTC_USDT")
                    if "_" in contract:
                        base, quote = contract.split("_", 1)
                        return Symbol(base=base, quote=quote, is_futures=True)
            
            # For array results (multiple items), check first item
            elif isinstance(result, list) and result:
                first_item = result[0]
                if isinstance(first_item, dict):
                    contract = first_item.get("contract")
                    if contract and "_" in contract:
                        base, quote = contract.split("_", 1)
                        return Symbol(base=base, quote=quote, is_futures=True)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Could not extract symbol from Gate.io private futures message: {e}")
            return None

    def get_subscription_status(self) -> Dict[str, Any]:
        """Get current subscription status."""
        return {
            "active_channels": list(self._active_subscriptions),
            "total_channels": len(self._active_subscriptions),
            "available_channels": list(self._private_futures_channels.values())
        }

    def is_subscription_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is a subscription-related message."""
        event = message.get("event", "")
        return event in ["subscribe", "unsubscribe"]

    async def handle_subscription_error(self, message: Dict[str, Any]) -> None:
        """Handle subscription error messages."""
        error = message.get("error", {})
        channel = message.get("channel", "unknown")
        error_code = error.get("code", "unknown")
        error_message = error.get("message", "Unknown error")
        
        self.logger.error(f"Gate.io private futures subscription error for {channel}: {error_code} - {error_message}")
        
        # Remove from active subscriptions if subscription failed
        if channel in self._active_subscriptions:
            self._active_subscriptions.remove(channel)

    def get_available_channels(self) -> List[str]:
        """Get list of available Gate.io private futures channels."""
        return list(self._private_futures_channels.values())

    def get_channel_description(self, channel: str) -> str:
        """Get description for a Gate.io private futures channel."""
        descriptions = {
            'futures.orders': 'Futures order updates',
            'futures.balances': 'Futures account balance changes',
            'futures.usertrades': 'Futures user trade confirmations',
            'futures.positions': 'Futures position updates'
        }
        return descriptions.get(channel, f"Unknown channel: {channel}")

    async def subscribe_all_private_channels(self) -> List[Dict[str, Any]]:
        """Subscribe to all available Gate.io private futures channels."""
        all_channels = list(self._private_futures_channels.values())
        return await self.subscribe_channels(all_channels)

    async def unsubscribe_all_channels(self) -> List[Dict[str, Any]]:
        """Unsubscribe from all active Gate.io private futures channels."""
        active_channels = list(self._active_subscriptions)
        return await self.unsubscribe_channels(active_channels)