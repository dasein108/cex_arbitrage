"""
WebSocket Transport Utilities

Factory utilities for creating WebSocket managers with proper strategy injection.
Provides unified interface for WebSocket creation similar to REST transport pattern.

HFT COMPLIANT: Sub-millisecond strategy creation with pre-validated combinations.
"""
from collections.abc import Awaitable

from config.structs import ExchangeConfig
from .ws_manager import WebSocketManager, WebSocketManagerConfig
from .strategies.strategy_set import WebSocketStrategySet
from infrastructure.utils.exchange_utils import exchange_name_to_enum
from exchanges.structs.enums import ExchangeEnum
from infrastructure.logging import get_strategy_logger


def create_websocket_manager(
    exchange_config: ExchangeConfig,
    connect_method: Awaitable,
    auth_method: Awaitable,
    is_private: bool = False,
    message_handler=None,
    connection_handler=None,
    **kwargs
) -> WebSocketManager:
    """
    Factory function to create WebSocketManager with direct strategy instantiation.

    Simplified method for creating WebSocket transport without factory overhead.

    Args:
        exchange_config: Exchange configuration
        is_private: Whether to use private API (requires credentials)
        message_handler: Callback for parsed messages
        connection_handler: Callback for connection state changes
        **kwargs: Additional strategy configuration

    Returns:
        WebSocketManager with configured strategies

    Raises:
        ValueError: If private API requested but no credentials available
        :param auth_method:
        :param connect_method:
    """
    if is_private and not exchange_config.has_credentials():
        raise ValueError("API key and secret key required for private WebSocket access")

    # Direct strategy creation based on exchange
    exchange = exchange_name_to_enum(exchange_config.name)
    api_type = 'private' if is_private else 'public'
    
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.ws.strategies.private import (
                MexcPrivateConnectionStrategy, 
                MexcPrivateSubscriptionStrategy, 
                MexcPrivateMessageParser
            )

            # connection_strategy = MexcPrivateConnectionStrategy(exchange_config)
            subscription_strategy = MexcPrivateSubscriptionStrategy()
            
            parser_logger = get_strategy_logger(f'ws.message_parser.mexc.private', ['mexc', 'private', 'ws', 'message_parser'])
            message_parser = MexcPrivateMessageParser(parser_logger)
            
        else:
            from exchanges.integrations.mexc.ws.strategies.public import (
                MexcPublicConnectionStrategy,
                MexcPublicSubscriptionStrategy,
                MexcPublicMessageParser
            )

            # connection_strategy = MexcPublicConnectionStrategy(exchange_config)
            subscription_strategy = MexcPublicSubscriptionStrategy()
            
            parser_logger = get_strategy_logger(f'ws.message_parser.mexc.public', ['mexc', 'public', 'ws', 'message_parser'])
            message_parser = MexcPublicMessageParser(parser_logger)
            
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.ws.strategies.spot.private import (
                GateioPrivateConnectionStrategy,
                GateioPrivateSubscriptionStrategy,
                GateioPrivateMessageParser
            )

            # connection_strategy = GateioPrivateConnectionStrategy(exchange_config)
            subscription_strategy = GateioPrivateSubscriptionStrategy()
            
            parser_logger = get_strategy_logger(f'ws.message_parser.gateio.private', ['gateio', 'private', 'ws', 'message_parser'])
            message_parser = GateioPrivateMessageParser(parser_logger)
            
        else:
            from exchanges.integrations.gateio.ws.strategies.spot.public import (
                GateioPublicConnectionStrategy,
                GateioPublicSubscriptionStrategy,
                GateioPublicMessageParser
            )
# No mapping imports needed - strategies use direct utilities
            
            # connection_strategy = GateioPublicConnectionStrategy(exchange_config)
            subscription_strategy = GateioPublicSubscriptionStrategy()
            
            parser_logger = get_strategy_logger(f'ws.message_parser.gateio.public', ['gateio', 'public', 'ws', 'message_parser'])
            message_parser = GateioPublicMessageParser(parser_logger)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol
        
        if is_private:
            from exchanges.integrations.gateio.ws.strategies.futures.private import (
                GateioPrivateFuturesConnectionStrategy,
                GateioPrivateFuturesSubscriptionStrategy,
                GateioPrivateFuturesMessageParser
            )
            
            # connection_strategy = GateioPrivateFuturesConnectionStrategy(exchange_config)
            subscription_strategy = GateioPrivateFuturesSubscriptionStrategy()
            
            parser_logger = get_strategy_logger(f'ws.message_parser.gateio_futures.private', ['gateio_futures', 'private', 'ws', 'message_parser'])
            message_parser = GateioPrivateFuturesMessageParser(parser_logger)
            
        else:
            from exchanges.integrations.gateio.ws.strategies import (
                GateioPublicFuturesConnectionStrategy,
                GateioPublicFuturesSubscriptionStrategy,
                GateioPublicFuturesMessageParser
            )
            
            # connection_strategy = GateioPublicFuturesConnectionStrategy(exchange_config)
            subscription_strategy = GateioPublicFuturesSubscriptionStrategy()
            
            parser_logger = get_strategy_logger(f'ws.message_parser.gateio_futures.public', ['gateio_futures', 'public', 'ws', 'message_parser'])
            message_parser = GateioPublicFuturesMessageParser(parser_logger)
            
    else:
        raise ValueError(f"Exchange {exchange.value} WebSocket strategies not implemented")
    
    strategy_set = WebSocketStrategySet(
        # connection_strategy=connection_strategy,
        subscription_strategy=subscription_strategy,
        message_parser=message_parser
    )

    # Configure manager for HFT performance
    manager_config = WebSocketManagerConfig(
        batch_processing_enabled=True,
        batch_size=100,
        max_pending_messages=1000,
        enable_performance_tracking=True
    )

    # Create and return WebSocket manager
    return WebSocketManager(
        config=exchange_config.websocket,
        strategies=strategy_set,
        connect_method=connect_method,
        auth_method=auth_method,
        message_handler=message_handler,
        manager_config=manager_config,
        connection_handler=connection_handler
    )