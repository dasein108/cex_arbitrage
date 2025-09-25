from typing import Dict, Any, Optional, List

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage
# BaseExchangeMapper dependency removed - using direct utility functions
from infrastructure.networking.websocket.structs import MessageType

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class GateioPrivateMessageParser(MessageParser):
    """Gate.io private WebSocket message parser."""

    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['gateio', 'spot', 'private', 'ws', 'message_parser']
            logger = get_strategy_logger('ws.message_parser.gateio.spot.private', tags)
        
        self.logger = logger
        
        # Log initialization
        if self.logger:
            self.logger.info("GateioPrivateMessageParser initialized",
                            exchange="gateio",
                            api_type="spot_private")
            
            # Track component initialization
            self.logger.metric("gateio_spot_private_message_parsers_initialized", 1,
                              tags={"exchange": "gateio", "api_type": "spot_private"})

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse raw WebSocket message from Gate.io private channels."""
        try:
            import msgspec
            message = msgspec.json.decode(raw_message)
            
            if isinstance(message, dict):
                event = message.get("event")
                
                if event == "subscribe":
                    # Subscription confirmation/error
                    return await self._parse_subscription_response(message)
                elif event == "unsubscribe":
                    # Unsubscription confirmation
                    return ParsedMessage(
                        message_type=MessageType.SUBSCRIPTION_CONFIRM,
                        data={"action": "unsubscribe", "status": message.get("result", {}).get("status")},
                        raw_data=message
                    )
                elif event == "update":
                    # Data update message
                    return await self._parse_update_message(message)
                elif event in ["ping", "pong"]:
                    # Ping/pong messages
                    return ParsedMessage(
                        message_type=MessageType.HEARTBEAT,
                        raw_data=message
                    )
                else:
                    # Handle messages without event field or unknown events
                    # Could be authentication responses or other formats
                    method = message.get("method")
                    if method == "RESULT":
                        # Authentication result or other results
                        return ParsedMessage(
                            message_type=MessageType.SUBSCRIPTION_CONFIRM,
                            raw_data=message
                        )
                    else:
                        if self.logger:
                            self.logger.debug(f"Unknown Gate.io private message format: {message}",
                                            exchange="gateio",
                                            api_type="spot_private")
                        return ParsedMessage(
                            message_type=MessageType.UNKNOWN,
                            raw_data=message
                        )
            
            return None
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to parse Gate.io private message: {e}",
                                exchange="gateio",
                                error_type=type(e).__name__,
                                api_type="spot_private")
            return None

    async def _parse_subscription_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Parse Gate.io private subscription response."""
        # Get channel name from message
        channel = message.get("channel", "")
        
        # Check for errors first
        error = message.get("error")
        if error:
            error_code = error.get("code", "unknown")
            error_msg = error.get("message", "unknown error")
            if self.logger:
                self.logger.error(f"Gate.io private subscription error {error_code}: {error_msg}",
                                exchange="gateio",
                                error_code=error_code,
                                error_message=error_msg,
                                api_type="spot_private")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                data={"error_code": error_code, "error_message": error_msg},
                raw_data=message
            )
        
        # Check result status
        result = message.get("result", {})
        status = result.get("status")
        
        if status == "success":
            if self.logger:
                self.logger.debug(f"Gate.io private subscription successful for channel: {channel}",
                                exchange="gateio",
                                channel=channel,
                                api_type="spot_private")
            return ParsedMessage(
                message_type=MessageType.SUBSCRIPTION_CONFIRM,
                channel=channel,
                data={"action": "subscribe", "status": "success"},
                raw_data=message
            )
        elif status == "fail":
            if self.logger:
                self.logger.error(f"Gate.io private subscription failed for channel: {channel}",
                                exchange="gateio",
                                channel=channel,
                                api_type="spot_private")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                data={"action": "subscribe", "status": "fail"},
                raw_data=message
            )
        else:
            if self.logger:
                self.logger.warning(f"Unknown Gate.io private subscription status: {status}",
                                  exchange="gateio",
                                  status=status,
                                  api_type="spot_private")
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data=message
            )

    async def _parse_update_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io private update message."""
        # Gate.io private update format: {"event": "update", "channel": "spot.balances", "result": [...]}
        channel = message.get("channel", "")
        result_data = message.get("result", [])
        
        if not channel:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                raw_data=message
            )
        
        if channel == "spot.balances":
            return await self._parse_balance_update(result_data)
        elif channel in ["spot.orders", "spot.orders_v2"]:
            return await self._parse_order_update(result_data)
        elif channel in ["spot.user_trades", "spot.usertrades", "spot.usertrades_v2"]:
            return await self._parse_user_trade_update(result_data)
        else:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data={"channel": channel, "data": result_data}
            )

    async def _parse_balance_update(self, data: List[Dict[str, Any]]) -> Optional[ParsedMessage]:
        """Parse Gate.io balance update."""
        try:
            balances = {}
            
            # Gate.io balance update format:
            # [
            #   {
            #     "currency": "USDT",
            #     "available": "1000.0",
            #     "locked": "0.0"
            #   }, ...
            # ]
            
            balance_list = data if isinstance(data, list) else [data]
            
            for balance_data in balance_list:
                # Use direct utility function to transform Gate.io balance to unified AssetBalance
                from exchanges.integrations.gateio.utils import ws_to_balance
                balance = ws_to_balance(balance_data)
                balances[balance.asset] = balance
            
            return ParsedMessage(
                message_type=MessageType.BALANCE,
                data=balances,
                raw_data=data
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to parse balance update: {e}",
                                exchange="gateio",
                                error_type=type(e).__name__,
                                api_type="spot_private")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_order_update(self, data: List[Dict[str, Any]]) -> Optional[ParsedMessage]:
        """Parse Gate.io order update."""
        try:
            orders = []
            
            # Gate.io order update format similar to REST API
            order_list = data if isinstance(data, list) else [data]
            
            for order_data in order_list:
                # Use direct utility function to transform Gate.io order to unified Order
                from exchanges.integrations.gateio.utils import ws_to_order
                order = ws_to_order(order_data)
                orders.append(order)
            
            return ParsedMessage(
                message_type=MessageType.ORDER,
                data=orders,
                raw_data=data
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to parse order update: {e}",
                                exchange="gateio",
                                error_type=type(e).__name__,
                                api_type="spot_private")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_user_trade_update(self, data: List[Dict[str, Any]]) -> Optional[ParsedMessage]:
        """Parse Gate.io user trade update."""
        try:
            trades = []
            
            # Gate.io user trade format
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                # Use direct utility function to transform Gate.io trade to unified Trade
                from exchanges.integrations.gateio.utils import ws_to_trade
                trade = ws_to_trade(trade_data)
                trades.append(trade)
            
            return ParsedMessage(
                message_type=MessageType.TRADE,
                data=trades,
                raw_data=data
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to parse user trade update: {e}",
                                exchange="gateio",
                                error_type=type(e).__name__,
                                api_type="spot_private")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                raw_data={"error": str(e), "data": data}
            )

    def get_supported_message_types(self) -> List[str]:
        """Get list of supported message types."""
        return ["balance_update", "order_update", "user_trade", "subscription", "result", "ping_pong", "other", "error"]