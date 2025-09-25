"""
Universal Data Transformer for WebSocket message parsing.

Provides unified transformation patterns that eliminate duplicate parsing logic
across all exchange implementations while maintaining exchange-specific customization.
"""

from typing import Dict, Any, Optional, List, Callable, Union
from enum import Enum
from abc import ABC, abstractmethod

from infrastructure.logging.interfaces import HFTLoggerInterface
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.structs.common import Symbol, OrderBook, Trade, BookTicker
from infrastructure.networking.websocket.parsing.symbol_extraction import UniversalSymbolExtractor
from infrastructure.networking.websocket.parsing.error_handling import WebSocketErrorHandler


class DataType(Enum):
    """Data transformation types supported by the universal transformer."""
    ORDERBOOK = "orderbook"
    TRADES = "trades"
    BOOK_TICKER = "book_ticker"
    TICKER = "ticker"
    SUBSCRIPTION = "subscription"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    OTHER = "other"


class TransformationStrategy(ABC):
    """Strategy interface for exchange-specific data transformation."""
    
    @abstractmethod
    def transform_orderbook(self, data: Dict[str, Any], symbol_str: str) -> OrderBook:
        """Transform raw orderbook data to unified OrderBook."""
        pass
    
    @abstractmethod
    def transform_trades(self, data: Dict[str, Any], symbol_str: str) -> List[Trade]:
        """Transform raw trades data to unified Trade list."""
        pass
    
    @abstractmethod
    def transform_book_ticker(self, data: Dict[str, Any], symbol_str: str) -> BookTicker:
        """Transform raw book ticker data to unified BookTicker."""
        pass
    
    @abstractmethod
    def get_symbol_from_data(self, data: Dict[str, Any], data_type: DataType) -> Optional[str]:
        """Extract symbol string from raw data based on data type."""
        pass


class GateioTransformationStrategy(TransformationStrategy):
    """Gate.io-specific transformation strategy."""
    
    def transform_orderbook(self, data: Dict[str, Any], symbol_str: str) -> OrderBook:
        """Transform Gate.io orderbook data."""
        from exchanges.integrations.gateio.utils import ws_to_orderbook
        return ws_to_orderbook(data, symbol_str)
    
    def transform_trades(self, data: Dict[str, Any], symbol_str: str) -> List[Trade]:
        """Transform Gate.io trades data."""
        from exchanges.integrations.gateio.utils import ws_to_trade
        
        trades = []
        # Gate.io trades format is typically a list of trade objects
        trade_list = data if isinstance(data, list) else [data]
        
        for trade_data in trade_list:
            trade = ws_to_trade(trade_data, symbol_str)
            trades.append(trade)
        
        return trades
    
    def transform_book_ticker(self, data: Dict[str, Any], symbol_str: str) -> BookTicker:
        """Transform Gate.io book ticker data."""
        from exchanges.integrations.gateio.utils import ws_to_book_ticker
        return ws_to_book_ticker(data, symbol_str)
    
    def get_symbol_from_data(self, data: Dict[str, Any], data_type: DataType) -> Optional[str]:
        """Extract symbol from Gate.io data based on message type."""
        if data_type == DataType.TRADES:
            # Gate.io trades use 'currency_pair' field
            if isinstance(data, list) and len(data) > 0:
                first_trade = data[0] if isinstance(data[0], dict) else {}
                return first_trade.get('currency_pair', '') or first_trade.get('s', '')
            elif isinstance(data, dict):
                return data.get('currency_pair', '') or data.get('s', '')
        else:
            # Standard symbol fields for other data types
            return data.get('s', '') or data.get('symbol', '')


class GateioFuturesTransformationStrategy(TransformationStrategy):
    """Gate.io futures-specific transformation strategy."""
    
    def transform_orderbook(self, data: Dict[str, Any], symbol_str: str) -> OrderBook:
        """Transform Gate.io futures orderbook data."""
        from exchanges.integrations.gateio.utils import futures_ws_to_orderbook
        return futures_ws_to_orderbook(data, symbol_str)
    
    def transform_trades(self, data: Dict[str, Any], symbol_str: str) -> List[Trade]:
        """Transform Gate.io futures trades data."""
        from exchanges.integrations.gateio.utils import futures_ws_to_trade
        
        trades = []
        trades_data = data if isinstance(data, list) else [data]
        
        for trade_data in trades_data:
            trade = futures_ws_to_trade(trade_data)
            trades.append(trade)
        
        return trades
    
    def transform_book_ticker(self, data: Dict[str, Any], symbol_str: str) -> BookTicker:
        """Transform Gate.io futures book ticker data."""
        from exchanges.integrations.gateio.utils import futures_ws_to_book_ticker
        return futures_ws_to_book_ticker(data, symbol_str)
    
    def get_symbol_from_data(self, data: Dict[str, Any], data_type: DataType) -> Optional[str]:
        """Extract symbol from Gate.io futures data."""
        if data_type == DataType.TRADES:
            # Gate.io futures trades use 'contract' field
            if isinstance(data, list) and len(data) > 0:
                return data[0].get('contract', '') if isinstance(data[0], dict) else ''
            else:
                return data.get('contract', '') or data.get('s', '')
        else:
            # Futures use 'contract' field primarily
            return data.get('contract', '') or data.get('s', '')


class MexcTransformationStrategy(TransformationStrategy):
    """MEXC-specific transformation strategy."""
    
    def transform_orderbook(self, data: Dict[str, Any], symbol_str: str) -> OrderBook:
        """Transform MEXC orderbook data."""
        from exchanges.integrations.mexc import utils as mexc_utils
        return mexc_utils.ws_to_orderbook(data, symbol_str)
    
    def transform_trades(self, data: Dict[str, Any], symbol_str: str) -> List[Trade]:
        """Transform MEXC trades data."""
        from exchanges.integrations.mexc import utils as mexc_utils
        # MEXC trades data can be single trade or list
        if isinstance(data, list):
            return [mexc_utils.ws_to_trade(trade_data, symbol_str) for trade_data in data]
        else:
            return [mexc_utils.ws_to_trade(data, symbol_str)]
    
    def transform_book_ticker(self, data: Dict[str, Any], symbol_str: str) -> BookTicker:
        """Transform MEXC book ticker data."""
        from exchanges.integrations.mexc import utils as mexc_utils
        return mexc_utils.ws_to_book_ticker(data, symbol_str)
    
    def get_symbol_from_data(self, data: Dict[str, Any], data_type: DataType) -> Optional[str]:
        """Extract symbol from MEXC data."""
        # MEXC typically uses 's' or 'symbol' fields
        return data.get('s', '') or data.get('symbol', '')


class UniversalDataTransformer:
    """
    Universal data transformer that eliminates parsing duplication.
    
    Provides unified transformation interface that delegates to exchange-specific
    strategies while handling common patterns like symbol extraction, error handling,
    and message creation.
    """
    
    def __init__(self, 
                 transformation_strategy: TransformationStrategy,
                 symbol_extractor: UniversalSymbolExtractor,
                 error_handler: WebSocketErrorHandler,
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize universal transformer with exchange-specific strategy."""
        self.transformation_strategy = transformation_strategy
        self.symbol_extractor = symbol_extractor
        self.error_handler = error_handler
        self.logger = logger
    
    async def transform_data(self,
                           data_type: DataType,
                           data: Dict[str, Any],
                           channel: str = "",
                           context: str = "") -> Optional[ParsedMessage]:
        """
        Universal data transformation method that handles all common patterns.
        
        This single method replaces all individual _parse_*_update methods
        across all exchange parsers.
        """
        try:
            # Step 1: Extract symbol using common extraction logic
            symbol_str = self.transformation_strategy.get_symbol_from_data(data, data_type)
            
            # Fallback to symbol extractor if needed
            if not symbol_str:
                symbol = self.symbol_extractor.extract_symbol(data, channel)
                symbol_str = str(symbol) if symbol else None
            else:
                symbol = self.symbol_extractor.extract_symbol({'s': symbol_str}, channel)
            
            if not symbol:
                return self.error_handler.handle_missing_fields_error(
                    ["symbol"], data, f"{data_type.value} update in {context}"
                )
            
            # Step 2: Transform data using exchange-specific strategy
            transformed_data = await self._transform_by_type(
                data_type, data, symbol_str, context
            )
            
            if not transformed_data:
                return self.error_handler.handle_transformation_error(
                    data, Exception(f"Transformation returned None"), 
                    data_type.value, context
                )
            
            # Step 3: Create unified ParsedMessage
            message_type = self._get_message_type(data_type)
            
            return ParsedMessage(
                message_type=message_type,
                symbol=symbol,
                channel=channel,
                data=transformed_data,
                raw_data=data
            )
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                data, e, data_type.value, context
            )
    
    async def _transform_by_type(self,
                               data_type: DataType,
                               data: Dict[str, Any],
                               symbol_str: str,
                               context: str) -> Optional[Any]:
        """Transform data based on type using exchange strategy."""
        try:
            if data_type == DataType.ORDERBOOK:
                return self.transformation_strategy.transform_orderbook(data, symbol_str)
            elif data_type == DataType.TRADES:
                return self.transformation_strategy.transform_trades(data, symbol_str)
            elif data_type == DataType.BOOK_TICKER:
                return self.transformation_strategy.transform_book_ticker(data, symbol_str)
            else:
                # For other types, return data as-is for now
                return data
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Transformation failed for {data_type.value}",
                                exchange=self.error_handler.exchange_name,
                                error=str(e),
                                context=context)
            raise
    
    def _get_message_type(self, data_type: DataType) -> MessageType:
        """Convert DataType to MessageType."""
        type_mapping = {
            DataType.ORDERBOOK: MessageType.ORDERBOOK,
            DataType.TRADES: MessageType.TRADES,
            DataType.BOOK_TICKER: MessageType.BOOK_TICKER,
            DataType.TICKER: MessageType.TICKER,
            DataType.SUBSCRIPTION: MessageType.SUBSCRIPTION_CONFIRM,
            DataType.HEARTBEAT: MessageType.HEARTBEAT,
            DataType.ERROR: MessageType.ERROR,
            DataType.OTHER: MessageType.OTHER
        }
        return type_mapping.get(data_type, MessageType.UNKNOWN)
    
    async def transform_subscription_response(self,
                                            message: Dict[str, Any],
                                            channel: str,
                                            context: str = "") -> Optional[ParsedMessage]:
        """Transform subscription response with common patterns."""
        try:
            # Check for errors first
            error = message.get("error")
            if error:
                return self.error_handler.handle_subscription_error(
                    message, channel, {"error": error}
                )
            
            # Check result status
            result = message.get("result", {})
            status = result.get("status")
            
            if status == "success":
                from infrastructure.networking.websocket.parsing.message_parsing_utils import MessageParsingUtils
                return MessageParsingUtils.create_subscription_response(
                    channel=channel,
                    status="success",
                    raw_data=message
                )
            elif status == "fail":
                return self.error_handler.handle_subscription_error(
                    message, channel, {"status": status, "result": result}
                )
            else:
                return self.error_handler.handle_unknown_message_type(
                    {**message, "unknown_status": status}, 
                    context=f"{context} subscription with status: {status}"
                )
                
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                message, e, "subscription_response", context
            )


# Factory functions for easy instantiation
def create_gateio_transformer(symbol_extractor: UniversalSymbolExtractor,
                             error_handler: WebSocketErrorHandler,
                             logger: Optional[HFTLoggerInterface] = None) -> UniversalDataTransformer:
    """Create transformer for Gate.io spot markets."""
    strategy = GateioTransformationStrategy()
    return UniversalDataTransformer(strategy, symbol_extractor, error_handler, logger)


def create_gateio_futures_transformer(symbol_extractor: UniversalSymbolExtractor,
                                     error_handler: WebSocketErrorHandler,
                                     logger: Optional[HFTLoggerInterface] = None) -> UniversalDataTransformer:
    """Create transformer for Gate.io futures markets."""
    strategy = GateioFuturesTransformationStrategy()
    return UniversalDataTransformer(strategy, symbol_extractor, error_handler, logger)


def create_mexc_transformer(symbol_extractor: UniversalSymbolExtractor,
                           error_handler: WebSocketErrorHandler,
                           logger: Optional[HFTLoggerInterface] = None) -> UniversalDataTransformer:
    """Create transformer for MEXC markets."""
    strategy = MexcTransformationStrategy()
    return UniversalDataTransformer(strategy, symbol_extractor, error_handler, logger)