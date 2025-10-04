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
        data = msgspec.structs.asdict(context)
        
        # Handle Symbol
        if 'symbol' in data and data['symbol']:
            data['symbol'] = {
                'base': data['symbol'].base,
                'quote': data['symbol'].quote,
                'is_futures': getattr(data['symbol'], 'is_futures', False)
            }
        
        # Handle multiple symbols for multi-exchange tasks
        if 'symbols' in data and data['symbols']:
            data['symbols'] = [
                {
                    'base': symbol.base,
                    'quote': symbol.quote,
                    'is_futures': getattr(symbol, 'is_futures', False)
                } for symbol in data['symbols']
            ]
        
        # Handle enums
        if 'side' in data and data['side']:
            data['side'] = data['side'].value if hasattr(data['side'], 'value') else data['side']
        if 'exchange_name' in data and data['exchange_name']:
            data['exchange_name'] = data['exchange_name'].value if hasattr(data['exchange_name'], 'value') else data['exchange_name']
        if 'exchange_names' in data and data['exchange_names']:
            data['exchange_names'] = [
                enum_val.value if hasattr(enum_val, 'value') else enum_val
                for enum_val in data['exchange_names']
            ]
        if 'state' in data and data['state']:
            data['state'] = data['state'].value if hasattr(data['state'], 'value') else data['state']
        
        # Handle Exception
        if 'error' in data and data['error']:
            data['error'] = {
                'type': type(data['error']).__name__,
                'message': str(data['error'])
            }
        
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
                quote=obj_data['symbol']['quote'],
                is_futures=obj_data['symbol'].get('is_futures', False)
            )
        
        # Reconstruct multiple symbols
        if 'symbols' in obj_data and obj_data['symbols']:
            obj_data['symbols'] = [
                Symbol(
                    base=symbol_data['base'],
                    quote=symbol_data['quote'],
                    is_futures=symbol_data.get('is_futures', False)
                ) for symbol_data in obj_data['symbols']
            ]
        
        # Reconstruct enums
        if 'side' in obj_data and obj_data['side'] is not None:
            obj_data['side'] = Side(obj_data['side'])
        
        if 'exchange_name' in obj_data and obj_data['exchange_name'] is not None:
            obj_data['exchange_name'] = ExchangeEnum(obj_data['exchange_name'])
        
        if 'exchange_names' in obj_data and obj_data['exchange_names']:
            obj_data['exchange_names'] = [
                ExchangeEnum(enum_val) for enum_val in obj_data['exchange_names']
            ]
        
        if 'state' in obj_data:
            obj_data['state'] = TradingStrategyState(obj_data['state'])
        
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
                'exchange_names': data.get('exchange_names', []),
                'symbol': data.get('symbol', {}),
                'symbols': data.get('symbols', []),
                'persisted_at': data.get('_persisted_at', 0),
                'schema_version': data.get('_schema_version', '1.0.0')
            }
        except (json.JSONDecodeError, KeyError) as e:
            return {'error': str(e)}