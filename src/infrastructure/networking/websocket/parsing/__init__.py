"""
WebSocket message parsing utilities.

Common utilities for parsing WebSocket messages across all exchanges,
providing standardized JSON decoding, error handling, symbol extraction,
and message creation patterns to eliminate code duplication.
"""

from .message_parsing_utils import MessageParsingUtils, ExchangeMessageHandler
from .symbol_extraction import (
    SymbolExtractionStrategy, 
    UniversalSymbolExtractor,
    GateioSymbolExtraction,
    MexcSymbolExtraction
)
from .error_handling import WebSocketErrorHandler, ParseErrorType
from .universal_transformer import (
    UniversalDataTransformer,
    DataType,
    TransformationStrategy,
    GateioTransformationStrategy,
    GateioFuturesTransformationStrategy,
    MexcTransformationStrategy,
    create_gateio_transformer,
    create_gateio_futures_transformer,
    create_mexc_transformer
)

__all__ = [
    'MessageParsingUtils',
    'ExchangeMessageHandler',
    'SymbolExtractionStrategy',
    'UniversalSymbolExtractor',
    'GateioSymbolExtraction',
    'MexcSymbolExtraction',
    'WebSocketErrorHandler',
    'ParseErrorType',
    'UniversalDataTransformer',
    'DataType',
    'TransformationStrategy',
    'GateioTransformationStrategy',
    'GateioFuturesTransformationStrategy',
    'MexcTransformationStrategy',
    'create_gateio_transformer',
    'create_gateio_futures_transformer',
    'create_mexc_transformer'
]