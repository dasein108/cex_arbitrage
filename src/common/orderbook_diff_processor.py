"""
Orderbook Diff Processing System

Abstract interface and implementations for exchange-specific orderbook diff parsing.
Designed for HFT performance with <100μs processing time per update.

Key Features:
- Exchange-specific diff format handling
- Unified output format for HFTOrderBook integration
- Zero-allocation parsing in hot paths
- Support for both incremental diffs and snapshots
- Error handling with fast-fail semantics

Performance Targets:
- <50μs parsing time for typical diff messages
- Zero memory allocation in steady state
- O(n) parsing complexity where n = number of price levels
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional, Union
from dataclasses import dataclass

from exchanges.structs.common import Symbol


@dataclass
class ParsedOrderbookUpdate:
    """
    Unified orderbook update structure for HFTOrderBook consumption.
    
    Designed for zero-copy semantics and efficient processing.
    """
    symbol: Symbol
    bid_updates: List[Tuple[float, float]]  # (price, size) tuples
    ask_updates: List[Tuple[float, float]]  # (price, size) tuples
    timestamp: float
    sequence: Optional[int] = None
    is_snapshot: bool = False
    is_final_level_update: bool = False  # For MEXC full depth updates


class OrderbookDiffProcessor(ABC):
    """
    Abstract composite class for exchange-specific orderbook diff processing.
    
    Each exchange implementation handles the specific message format and
    converts to unified ParsedOrderbookUpdate for HFTOrderBook consumption.
    """
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        self.logger = logging.getLogger(f"{__name__}.{exchange_name}")
    
    @abstractmethod
    def parse_diff_message(
        self, 
        raw_message: Union[Dict[str, Any], bytes], 
        symbol: Symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """
        Parse exchange-specific diff message into unified format.
        
        Args:
            raw_message: Raw message from exchange (JSON dict or protobuf bytes)
            symbol: Symbol for the update
            
        Returns:
            ParsedOrderbookUpdate or None if message is invalid/irrelevant
            
        Performance: Target <50μs for typical messages
        """
        pass
    
    @abstractmethod
    def is_snapshot_message(self, raw_message: Union[Dict[str, Any], bytes]) -> bool:
        """
        Determine if message is a full snapshot vs incremental update.
        
        Args:
            raw_message: Raw message from exchange
            
        Returns:
            True if message is a full orderbook snapshot
            
        Performance: Target <1μs (should be simple field check)
        """
        pass
    
    @abstractmethod
    def extract_sequence(self, raw_message: Union[Dict[str, Any], bytes]) -> Optional[int]:
        """
        Extract sequence number from message for ordering validation.
        
        Args:
            raw_message: Raw message from exchange
            
        Returns:
            Sequence number or None if not available
            
        Performance: Target <1μs (should be simple field extraction)
        """
        pass
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics for monitoring."""
        return {
            'exchange': self.exchange_name,
            'processor_type': self.__class__.__name__
        }


class MexcOrderbookDiffProcessor(OrderbookDiffProcessor):
    """
    MEXC-specific orderbook diff processor.
    
    Handles MEXC's differential depth update format as documented:
    - Protobuf and JSON message formats
    - Incremental updates with price/size pairs
    - Full depth snapshots vs partial updates
    - Sequence number tracking for order validation
    
    MEXC Format Reference:
    - spot@public.limit.depth.v3.api@BTCUSDT@20 (20 levels)
    - spot@public.increase.depth.v3.api@BTCUSDT (incremental)
    """
    
    def __init__(self):
        super().__init__("MEXC")
        
        # MEXC-specific constants for fast parsing
        self._JSON_DEPTH_INDICATORS = frozenset(['d', 'bids', 'asks'])
        self._PROTOBUF_DEPTH_MAGIC = b'depth'
        
        # Performance tracking
        self._stats = {
            'messages_processed': 0,
            'json_messages': 0,
            'protobuf_messages': 0,
            'parse_errors': 0,
            'invalid_messages': 0
        }
    
    def parse_diff_message(
        self, 
        raw_message: Union[Dict[str, Any], bytes], 
        symbol: Symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """
        Parse MEXC orderbook diff message.
        
        MEXC JSON Format:
        {
            "c": "spot@public.limit.depth.v3.api@BTCUSDT@20",
            "d": {
                "bids": [["50000", "0.1"], ["49999", "0.0"]], // 0 size = remove
                "asks": [["50001", "0.2"], ["50002", "0.0"]], 
                "version": "12345"
            },
            "t": 1672531200000
        }
        
        MEXC Protobuf Format: PublicAggreDepthsV3Api with bids/asks arrays
        """
        try:
            self._stats['messages_processed'] += 1
            
            # Handle JSON format
            if isinstance(raw_message, dict):
                return self._parse_json_diff(raw_message, symbol)
            
            # Handle protobuf format
            elif isinstance(raw_message, bytes):
                return self._parse_protobuf_diff(raw_message, symbol)
            
            else:
                self.logger.warning(f"Unknown message type: {type(raw_message)}")
                self._stats['invalid_messages'] += 1
                return None
                
        except Exception as e:
            self.logger.error(f"Error parsing MEXC diff message: {e}")
            self._stats['parse_errors'] += 1
            return None
    
    def _parse_json_diff(
        self, 
        message: Dict[str, Any], 
        symbol: Symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """Parse MEXC JSON diff message with HFT optimization."""
        self._stats['json_messages'] += 1
        
        # Fast validation - check for required fields
        data = message.get('d')
        if not data or not isinstance(data, dict):
            return None
        
        # Extract timestamp (MEXC provides millisecond timestamps)
        timestamp = float(message.get('t', time.time() * 1000)) / 1000.0
        
        # Extract sequence/version for ordering
        sequence = None
        version_str = data.get('version')
        if version_str:
            try:
                sequence = int(version_str)
            except (ValueError, TypeError):
                pass
        
        # Parse bid updates with zero-allocation approach
        bid_updates = []
        bids_data = data.get('bids', [])
        for bid_item in bids_data:
            if isinstance(bid_item, list) and len(bid_item) >= 2:
                try:
                    price = float(bid_item[0])
                    size = float(bid_item[1])
                    bid_updates.append((price, size))
                except (ValueError, TypeError, IndexError):
                    continue
        
        # Parse ask updates with zero-allocation approach
        ask_updates = []
        asks_data = data.get('asks', [])
        for ask_item in asks_data:
            if isinstance(ask_item, list) and len(ask_item) >= 2:
                try:
                    price = float(ask_item[0])
                    size = float(ask_item[1])
                    ask_updates.append((price, size))
                except (ValueError, TypeError, IndexError):
                    continue
        
        # Determine if this is a snapshot (based on channel name)
        channel = message.get('c', '')
        is_snapshot = 'limit.depth' in channel  # vs 'increase.depth'
        
        return ParsedOrderbookUpdate(
            symbol=symbol,
            bid_updates=bid_updates,
            ask_updates=ask_updates,
            timestamp=timestamp,
            sequence=sequence,
            is_snapshot=is_snapshot
        )
    
    def _parse_protobuf_diff(
        self, 
        data: bytes, 
        symbol: Symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """Parse MEXC protobuf diff message."""
        self._stats['protobuf_messages'] += 1
        
        try:
            # Use MEXC protobuf parser utilities
            from exchanges.integrations.mexc.ws.protobuf_parser import MexcProtobufParser
            
            wrapper = MexcProtobufParser.parse_wrapper_message(data)
            
            # Check for depth data
            if wrapper.HasField('publicAggreDepths'):
                depth_data = wrapper.publicAggreDepths
                
                bid_updates = []
                for bid_item in depth_data.bids:
                    price = float(bid_item.price)
                    size = float(bid_item.quantity)
                    bid_updates.append((price, size))
                
                ask_updates = []
                for ask_item in depth_data.asks:
                    price = float(ask_item.price)
                    size = float(ask_item.quantity)
                    ask_updates.append((price, size))
                
                return ParsedOrderbookUpdate(
                    symbol=symbol,
                    bid_updates=bid_updates,
                    ask_updates=ask_updates,
                    timestamp=time.time(),  # Protobuf doesn't always include timestamp
                    sequence=None,  # Extract if available in protobuf
                    is_snapshot=True  # Protobuf messages are typically snapshots
                )
                
        except Exception as e:
            self.logger.error(f"Error parsing MEXC protobuf: {e}")
        
        return None
    
    def is_snapshot_message(self, raw_message: Union[Dict[str, Any], bytes]) -> bool:
        """
        Determine if MEXC message is snapshot vs incremental update.
        
        MEXC Channel Indicators:
        - spot@public.limit.depth.v3.api@BTCUSDT@20 → Snapshot (limit depth)
        - spot@public.increase.depth.v3.api@BTCUSDT → Incremental (increase depth)
        """
        if isinstance(raw_message, dict):
            channel = raw_message.get('c', '')
            return 'limit.depth' in channel
        
        elif isinstance(raw_message, bytes):
            # Protobuf messages are typically snapshots
            return self._PROTOBUF_DEPTH_MAGIC in raw_message[:50]
        
        return False
    
    def extract_sequence(self, raw_message: Union[Dict[str, Any], bytes]) -> Optional[int]:
        """Extract sequence number from MEXC message."""
        if isinstance(raw_message, dict):
            data = raw_message.get('d', {})
            version_str = data.get('version')
            if version_str:
                try:
                    return int(version_str)
                except (ValueError, TypeError):
                    pass
        
        # Protobuf sequence extraction would require specific implementation
        return None
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get MEXC-specific processing statistics."""
        base_stats = super().get_processing_stats()
        return {**base_stats, **self._stats}


class GateioOrderbookDiffProcessor(OrderbookDiffProcessor):
    """
    Gate.io-specific orderbook diff processor.
    
    Handles Gate.io's orderbook update format:
    - JSON-based message format
    - Incremental updates with price/size pairs
    - Event-driven architecture (update events)
    """
    
    def __init__(self):
        super().__init__("Gate.io")
        
        # Performance tracking
        self._stats = {
            'messages_processed': 0,
            'parse_errors': 0,
            'invalid_messages': 0
        }
    
    def parse_diff_message(
        self, 
        raw_message: Union[Dict[str, Any], bytes], 
        symbol: Symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """
        Parse Gate.io orderbook diff message.
        
        Gate.io Format:
        {
            "time": 1234567890,
            "channel": "spot.order_book_update",
            "event": "update",
            "result": {
                "t": 1234567890123,
                "e": "depthUpdate",
                "E": 1234567890456,
                "s": "BTC_USDT",
                "U": 157,
                "u": 160,
                "b": [["50000", "0.001"], ["49999", "0.0"]],
                "a": [["50001", "0.002"], ["50002", "0.0"]]
            }
        }
        """
        try:
            self._stats['messages_processed'] += 1
            
            if not isinstance(raw_message, dict):
                return None
            
            # Skip non-update events
            if raw_message.get('event') != 'update':
                return None
            
            result = raw_message.get('result', {})
            if not result:
                return None
            
            # Extract timestamp (Gate.io provides multiple timestamps)
            timestamp = float(result.get('E', time.time() * 1000)) / 1000.0
            
            # Extract sequence numbers
            first_update_id = result.get('U')
            final_update_id = result.get('u')
            sequence = final_update_id if final_update_id else None
            
            # Parse bid updates
            bid_updates = []
            bids_data = result.get('b', [])
            for bid_item in bids_data:
                if isinstance(bid_item, list) and len(bid_item) >= 2:
                    try:
                        price = float(bid_item[0])
                        size = float(bid_item[1])
                        bid_updates.append((price, size))
                    except (ValueError, TypeError, IndexError):
                        continue
            
            # Parse ask updates
            ask_updates = []
            asks_data = result.get('a', [])
            for ask_item in asks_data:
                if isinstance(ask_item, list) and len(ask_item) >= 2:
                    try:
                        price = float(ask_item[0])
                        size = float(ask_item[1])
                        ask_updates.append((price, size))
                    except (ValueError, TypeError, IndexError):
                        continue
            
            return ParsedOrderbookUpdate(
                symbol=symbol,
                bid_updates=bid_updates,
                ask_updates=ask_updates,
                timestamp=timestamp,
                sequence=sequence,
                is_snapshot=False  # Gate.io sends incremental updates
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io diff message: {e}")
            self._stats['parse_errors'] += 1
            return None
    
    def is_snapshot_message(self, raw_message: Union[Dict[str, Any], bytes]) -> bool:
        """Gate.io typically sends incremental updates, not snapshots."""
        # Gate.io uses incremental updates by default
        # Full snapshots would need to be requested separately
        return False
    
    def extract_sequence(self, raw_message: Union[Dict[str, Any], bytes]) -> Optional[int]:
        """Extract sequence number from Gate.io message."""
        if isinstance(raw_message, dict):
            result = raw_message.get('result', {})
            return result.get('u')  # Final update ID
        
        return None
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get Gate.io-specific processing statistics."""
        base_stats = super().get_processing_stats()
        return {**base_stats, **self._stats}