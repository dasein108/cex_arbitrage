"""
Enhanced serialization support for ArbitrageTaskContext

Extends TaskSerializer with arbitrage-specific struct handling following PROJECT_GUIDES.md.
"""

import json
import time
from typing import Any, Dict, Optional, Type, TypeVar
import msgspec

from exchanges.structs import Symbol, Side, ExchangeEnum, Order, OrderType, OrderStatus
from trading.struct import TradingStrategyState
from trading.task_manager.serialization import TaskSerializer

from arbitrage_task_context import (
    ArbitrageState, 
    Position, 
    PositionState, 
    TradingParameters,
    ArbitrageOpportunity,
    ArbitrageTaskContext
)

T = TypeVar('T', bound=msgspec.Struct)


class ArbitrageTaskSerializer(TaskSerializer):
    """Enhanced TaskSerializer with arbitrage-specific struct handling."""
    
    @staticmethod
    def serialize_context(context: msgspec.Struct) -> str:
        """Serialize arbitrage task context to JSON string with enhanced support."""
        
        def _serialize_value(value):
            """Recursively serialize complex values including arbitrage structs."""
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
            elif isinstance(value, Order):
                # Special handling for Order objects
                return {
                    'order_id': value.order_id,
                    'symbol': _serialize_value(value.symbol),
                    'side': value.side.value,
                    'order_type': value.order_type.value,
                    'quantity': value.quantity,
                    'price': value.price,
                    'filled_quantity': value.filled_quantity,
                    'status': value.status.value,
                    'timestamp': value.timestamp,
                    'client_order_id': value.client_order_id,
                    'average_price': value.average_price,
                    'fee': value.fee,
                    'fee_asset': value.fee_asset,
                    '_type': 'Order'  # Type marker for deserialization
                }
            elif isinstance(value, (Position, PositionState, TradingParameters, ArbitrageOpportunity)):
                # Handle arbitrage-specific structs
                struct_dict = msgspec.structs.asdict(value)
                serialized_dict = {k: _serialize_value(v) for k, v in struct_dict.items()}
                serialized_dict['_type'] = type(value).__name__  # Type marker
                return serialized_dict
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
        data['_schema_version'] = "1.1.0"  # Updated version for arbitrage support
        data['_context_type'] = type(context).__name__
        
        return json.dumps(data, indent=2)
    
    @staticmethod
    def deserialize_context(data: str, context_class: Type[T]) -> T:
        """Deserialize JSON string to arbitrage task context."""
        obj_data = json.loads(data)
        
        # Remove metadata fields
        obj_data.pop('_persisted_at', None)
        obj_data.pop('_schema_version', None)
        obj_data.pop('_context_type', None)
        
        def _deserialize_value(value, expected_type=None):
            """Recursively deserialize complex values."""
            if isinstance(value, dict):
                if '_type' in value:
                    # Handle typed structs
                    struct_type = value.pop('_type')
                    if struct_type == 'Order':
                        return Order(
                            order_id=value['order_id'],
                            symbol=Symbol(base=value['symbol']['base'], quote=value['symbol']['quote']),
                            side=Side(value['side']),
                            order_type=OrderType(value['order_type']),
                            quantity=value['quantity'],
                            price=value['price'],
                            filled_quantity=value.get('filled_quantity', 0.0),
                            status=OrderStatus(value['status']),
                            timestamp=value.get('timestamp'),
                            client_order_id=value.get('client_order_id'),
                            average_price=value.get('average_price'),
                            fee=value.get('fee'),
                            fee_asset=value.get('fee_asset')
                        )
                    elif struct_type == 'Position':
                        return Position(
                            qty=value['qty'],
                            price=value['price'],
                            side=Side(value['side']) if value.get('side') is not None else None
                        )
                    elif struct_type == 'PositionState':
                        return PositionState(
                            spot=_deserialize_value(value['spot']),
                            futures=_deserialize_value(value['futures'])
                        )
                    elif struct_type == 'TradingParameters':
                        return TradingParameters(
                            max_entry_cost_pct=value['max_entry_cost_pct'],
                            min_profit_pct=value['min_profit_pct'],
                            max_hours=value['max_hours'],
                            spot_fee=value['spot_fee'],
                            fut_fee=value['fut_fee']
                        )
                    elif struct_type == 'ArbitrageOpportunity':
                        return ArbitrageOpportunity(
                            direction=value['direction'],
                            spread_pct=value['spread_pct'],
                            buy_price=value['buy_price'],
                            sell_price=value['sell_price'],
                            max_quantity=value['max_quantity'],
                            timestamp=value['timestamp']
                        )
                else:
                    # Regular dict - recursively deserialize values
                    return {k: _deserialize_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [_deserialize_value(item) for item in value]
            else:
                return value
        
        # Handle Symbol reconstruction
        if 'symbol' in obj_data and obj_data['symbol']:
            obj_data['symbol'] = Symbol(
                base=obj_data['symbol']['base'],
                quote=obj_data['symbol']['quote']
            )
        
        # Handle arbitrage-specific fields
        if 'arbitrage_state' in obj_data:
            obj_data['arbitrage_state'] = ArbitrageState(obj_data['arbitrage_state'])
        
        if 'state' in obj_data:
            obj_data['state'] = TradingStrategyState(obj_data['state'])
        
        # Handle nested structs
        for field_name in ['positions', 'params', 'current_opportunity']:
            if field_name in obj_data and obj_data[field_name]:
                obj_data[field_name] = _deserialize_value(obj_data[field_name])
        
        # Handle active_orders dict with nested Order objects
        if 'active_orders' in obj_data and obj_data['active_orders']:
            active_orders = {}
            for exchange_type, orders_dict in obj_data['active_orders'].items():
                active_orders[exchange_type] = {}
                for order_id, order_data in orders_dict.items():
                    active_orders[exchange_type][order_id] = _deserialize_value(order_data)
            obj_data['active_orders'] = active_orders
        
        # Handle error reconstruction
        if 'error' in obj_data and obj_data['error']:
            obj_data['error'] = Exception(obj_data['error']['message'])
        
        return context_class(**obj_data)