"""Centralized task serialization utilities.

Provides unified JSON serialization for task contexts with proper handling
of complex nested structures like Symbol, ExchangeEnum, and Exception objects.
"""

import json
import time
from typing import Any, Dict, Optional, Type, TypeVar
import msgspec

from exchanges.structs import Symbol, Side, ExchangeEnum
from trading.struct import TradingStrategyState

T = TypeVar('T', bound=msgspec.Struct)


class TaskSerializer:
    """Centralized task serialization with enhanced struct handling."""
    
    @staticmethod
    def serialize_context(context: msgspec.Struct) -> str:
        """Serialize task context to JSON string.
        
        Args:
            context: Task context to serialize
            
        Returns:
            str: JSON string representation
        """
        def _serialize_value(value):
            """Recursively serialize complex values."""
            if hasattr(value, 'value'):  # Enum types
                return value.value
            elif isinstance(value, Symbol):
                return {
                    'base': value.base,
                    'quote': value.quote
                }
            elif isinstance(value, Exception):
                return {
                    'type': type(value).__name__,
                    'message': str(value)
                }
            elif isinstance(value, dict):
                return {k: _serialize_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                return [_serialize_value(item) for item in value]
            else:
                return value
        
        # Convert struct to dict and recursively serialize all values
        data = {k: _serialize_value(v) for k, v in msgspec.structs.asdict(context).items()}
        
        # Add metadata
        data['_persisted_at'] = time.time()
        data['_schema_version'] = "1.0.0"
        
        return json.dumps(data, indent=2)
    
    @staticmethod
    def deserialize_context(data: str, context_class: Type[T]) -> T:
        """Deserialize JSON string to task context.
        
        Args:
            data: JSON string data
            context_class: Context class for instantiation
            
        Returns:
            T: Deserialized context instance
        """
        obj_data = json.loads(data)
        
        # Remove metadata fields
        obj_data.pop('_persisted_at', None)
        obj_data.pop('_schema_version', None)
        
        # Reconstruct Symbol
        if 'symbol' in obj_data and obj_data['symbol']:
            obj_data['symbol'] = Symbol(
                base=obj_data['symbol']['base'],
                quote=obj_data['symbol']['quote']
            )
        
        
        # Reconstruct enums
        if 'side' in obj_data and obj_data['side'] is not None:
            obj_data['side'] = Side(obj_data['side'])
        
        if 'exchange_name' in obj_data and obj_data['exchange_name'] is not None:
            obj_data['exchange_name'] = ExchangeEnum(obj_data['exchange_name'])
        
        # Reconstruct DeltaNeutralTask dict fields with Side enum keys
        if 'exchange_names' in obj_data and obj_data['exchange_names']:
            exchange_names_dict = {}
            for side_value, exchange_value in obj_data['exchange_names'].items():
                if isinstance(side_value, str):
                    if side_value.isdigit():
                        side_key = Side(int(side_value))  # e.g., "1" -> 1 -> Side.BUY
                    else:
                        side_key = Side[side_value]  # e.g., "BUY" -> Side.BUY
                else:
                    side_key = Side(side_value)
                exchange_names_dict[side_key] = ExchangeEnum(exchange_value) if exchange_value else None
            obj_data['exchange_names'] = exchange_names_dict
        
        if 'filled_quantity' in obj_data and obj_data['filled_quantity']:
            filled_quantity_dict = {}
            for side_value, quantity in obj_data['filled_quantity'].items():
                if isinstance(side_value, str):
                    if side_value.isdigit():
                        side_key = Side(int(side_value))  # e.g., "1" -> 1 -> Side.BUY
                    else:
                        side_key = Side[side_value]  # e.g., "BUY" -> Side.BUY
                else:
                    side_key = Side(side_value)
                filled_quantity_dict[side_key] = quantity
            obj_data['filled_quantity'] = filled_quantity_dict
        
        if 'avg_price' in obj_data and obj_data['avg_price']:
            avg_price_dict = {}
            for side_value, price in obj_data['avg_price'].items():
                if isinstance(side_value, str):
                    if side_value.isdigit():
                        side_key = Side(int(side_value))  # e.g., "1" -> 1 -> Side.BUY
                    else:
                        side_key = Side[side_value]  # e.g., "BUY" -> Side.BUY
                else:
                    side_key = Side(side_value)
                avg_price_dict[side_key] = price
            obj_data['avg_price'] = avg_price_dict
        
        if 'offset_ticks' in obj_data and obj_data['offset_ticks']:
            offset_ticks_dict = {}
            for side_value, ticks in obj_data['offset_ticks'].items():
                if isinstance(side_value, str):
                    if side_value.isdigit():
                        side_key = Side(int(side_value))  # e.g., "1" -> 1 -> Side.BUY
                    else:
                        side_key = Side[side_value]  # e.g., "BUY" -> Side.BUY
                else:
                    side_key = Side(side_value)
                offset_ticks_dict[side_key] = ticks
            obj_data['offset_ticks'] = offset_ticks_dict
        
        if 'tick_tolerance' in obj_data and obj_data['tick_tolerance']:
            tick_tolerance_dict = {}
            for side_value, tolerance in obj_data['tick_tolerance'].items():
                if isinstance(side_value, str):
                    if side_value.isdigit():
                        side_key = Side(int(side_value))  # e.g., "1" -> 1 -> Side.BUY
                    else:
                        side_key = Side[side_value]  # e.g., "BUY" -> Side.BUY
                else:
                    side_key = Side(side_value)
                tick_tolerance_dict[side_key] = tolerance
            obj_data['tick_tolerance'] = tick_tolerance_dict
        
        if 'order_id' in obj_data and obj_data['order_id']:
            order_id_dict = {}
            for side_value, order_id in obj_data['order_id'].items():
                if isinstance(side_value, str):
                    if side_value.isdigit():
                        side_key = Side(int(side_value))  # e.g., "1" -> 1 -> Side.BUY
                    else:
                        side_key = Side[side_value]  # e.g., "BUY" -> Side.BUY
                else:
                    side_key = Side(side_value)
                order_id_dict[side_key] = order_id
            obj_data['order_id'] = order_id_dict
        
        if 'state' in obj_data:
            obj_data['state'] = TradingStrategyState(obj_data['state'])
        
        # Handle direction enum for DeltaNeutralTask (avoid circular import)
        if 'direction' in obj_data and obj_data['direction'] is not None:
            try:
                # Import Direction only when needed to avoid circular import
                from trading.tasks.delta_neutral_task import Direction
                obj_data['direction'] = Direction(obj_data['direction'])
            except ImportError:
                # If import fails, leave as is - the specific task recovery will handle it
                pass
        
        # Reconstruct Exception
        if 'error' in obj_data and obj_data['error']:
            obj_data['error'] = Exception(obj_data['error']['message'])
        
        return context_class(**obj_data)
    
    @staticmethod
    def extract_task_metadata(json_data: str) -> Dict[str, Any]:
        """Extract task metadata for recovery without full deserialization.
        
        Args:
            json_data: JSON string containing task data
            
        Returns:
            Dict containing extracted metadata
        """
        try:
            data = json.loads(json_data)
            return {
                'task_id': data.get('task_id', ''),
                'state': data.get('state', ''),
                'exchange_name': data.get('exchange_name'),
                'symbol': data.get('symbol', {}),
                'persisted_at': data.get('_persisted_at', 0),
                'schema_version': data.get('_schema_version', '1.0.0')
            }
        except (json.JSONDecodeError, KeyError) as e:
            return {'error': str(e)}