"""Centralized task serialization utilities.

Provides unified JSON serialization for task contexts with proper handling
of complex nested structures like Symbol, ExchangeEnum, and Exception objects.
"""

import json
import time
from typing import Any, Dict, Optional, Type, TypeVar
import msgspec

from exchanges.structs import Symbol, Side, ExchangeEnum
from exchanges.structs.enums import OrderStatus, OrderType, TimeInForce
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
            elif isinstance(value, msgspec.Struct):
                # Handle nested msgspec.Struct objects (like TradingParameters)
                return {k: _serialize_value(v) for k, v in msgspec.structs.asdict(value).items()}
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
        
        # State is already a string literal, no conversion needed
        # 'state' field remains as string for Literal type compatibility
        
        # Handle direction enum for DeltaNeutralTask (avoid circular import)
        if 'direction' in obj_data and obj_data['direction'] is not None:
            try:
                # Import Direction only when needed to avoid circular import
                from trading.tasks.delta_neutral_task import Direction
                obj_data['direction'] = Direction(obj_data['direction'])
            except ImportError:
                # If import fails, leave as is - the specific task recovery will handle it
                pass
        
        # Handle ArbitrageState - now string literal, no conversion needed
        # 'arbitrage_state' field remains as string for Literal type compatibility
        
        # Handle TradingParameters nested struct
        if 'params' in obj_data and obj_data['params'] is not None:
            try:
                from trading.tasks.arbitrage_task_context import TradingParameters
                params_data = obj_data['params']
                obj_data['params'] = TradingParameters(
                    max_entry_cost_pct=params_data.get('max_entry_cost_pct', 0.5),
                    min_profit_pct=params_data.get('min_profit_pct', 0.1),
                    max_hours=params_data.get('max_hours', 6.0),
                    spot_fee=params_data.get('spot_fee', 0.0005),
                    fut_fee=params_data.get('fut_fee', 0.0005),
                    limit_orders_enabled=params_data.get('limit_orders_enabled', False),
                    limit_offset_ticks=params_data.get('limit_offset_ticks', 2),
                    limit_profit_pct=params_data.get('limit_profit_pct', 0.05)
                )
            except ImportError:
                # If import fails, leave as is - the specific task recovery will handle it
                pass
        
        # Handle PositionState and Position nested structs for ArbitrageTaskContext
        if 'positions_state' in obj_data and obj_data['positions_state'] is not None:
            try:
                from trading.tasks.arbitrage_task_context import PositionState, Position
                positions_state_data = obj_data['positions_state']
                
                def reconstruct_position(pos_data):
                    if pos_data is None:
                        return Position()
                    side = Side(pos_data['side']) if pos_data.get('side') is not None else None
                    return Position(
                        qty=pos_data.get('qty', 0.0),
                        price=pos_data.get('price', 0.0),
                        side=side
                    )
                
                # Handle positions_state nested structure
                if 'positions' in positions_state_data:
                    positions_dict = {}
                    for key, pos_data in positions_state_data['positions'].items():
                        positions_dict[key] = reconstruct_position(pos_data)
                    obj_data['positions_state'] = PositionState(positions=positions_dict)
                else:
                    # Direct position data
                    positions_dict = {}
                    for key, pos_data in positions_state_data.items():
                        positions_dict[key] = reconstruct_position(pos_data)
                    obj_data['positions_state'] = PositionState(positions=positions_dict)
            except ImportError:
                # If import fails, leave as is - the specific task recovery will handle it
                pass
        
        # Handle active_orders nested Order objects for ArbitrageTaskContext
        if 'active_orders' in obj_data and obj_data['active_orders'] is not None:
            try:
                from exchanges.structs.common import Order
                active_orders_data = obj_data['active_orders']
                
                def reconstruct_order(order_data):
                    """Reconstruct Order object from dict data."""
                    if order_data is None:
                        return None
                    
                    # Handle Symbol reconstruction
                    symbol_data = order_data.get('symbol')
                    symbol = Symbol(
                        base=symbol_data['base'],
                        quote=symbol_data['quote']
                    ) if symbol_data else None
                    
                    # Handle enum conversions
                    side = Side(order_data['side']) if order_data.get('side') is not None else None
                    order_type = OrderType(order_data['order_type']) if order_data.get('order_type') is not None else OrderType.LIMIT
                    status = OrderStatus(order_data['status']) if order_data.get('status') is not None else OrderStatus.NEW
                    time_in_force = TimeInForce(order_data['time_in_force']) if order_data.get('time_in_force') is not None else TimeInForce.GTC
                    
                    return Order(
                        symbol=symbol,
                        order_id=order_data.get('order_id', ''),
                        side=side,
                        order_type=order_type,
                        quantity=order_data.get('quantity', 0.0),
                        client_order_id=order_data.get('client_order_id'),
                        price=order_data.get('price'),
                        filled_quantity=order_data.get('filled_quantity', 0.0),
                        remaining_quantity=order_data.get('remaining_quantity'),
                        status=status,
                        timestamp=order_data.get('timestamp'),
                        average_price=order_data.get('average_price'),
                        fee=order_data.get('fee'),
                        fee_asset=order_data.get('fee_asset'),
                        time_in_force=time_in_force
                    )
                
                # Reconstruct nested active_orders structure
                reconstructed_active_orders = {}
                for exchange_key, orders_dict in active_orders_data.items():
                    reconstructed_orders = {}
                    for order_id, order_data in orders_dict.items():
                        reconstructed_orders[order_id] = reconstruct_order(order_data)
                    reconstructed_active_orders[exchange_key] = reconstructed_orders
                
                obj_data['active_orders'] = reconstructed_active_orders
            except ImportError:
                # If import fails, leave as is - the specific task recovery will handle it
                pass
        
        # Handle ArbitrageOpportunity nested struct
        if 'current_opportunity' in obj_data and obj_data['current_opportunity'] is not None:
            try:
                from trading.tasks.arbitrage_task_context import ArbitrageOpportunity
                opp_data = obj_data['current_opportunity']
                obj_data['current_opportunity'] = ArbitrageOpportunity(
                    direction=opp_data.get('direction', ''),
                    spread_pct=opp_data.get('spread_pct', 0.0),
                    buy_price=opp_data.get('buy_price', 0.0),
                    sell_price=opp_data.get('sell_price', 0.0),
                    max_quantity=opp_data.get('max_quantity', 0.0),
                    timestamp=opp_data.get('timestamp', 0.0)
                )
            except ImportError:
                # If import fails, leave as is - the specific task recovery will handle it
                pass
        
        # Handle spot_exchange and futures_exchange enums (for SpotFuturesArbitrageTask)
        if 'spot_exchange' in obj_data and obj_data['spot_exchange'] is not None:
            obj_data['spot_exchange'] = ExchangeEnum(obj_data['spot_exchange'])
        
        if 'futures_exchange' in obj_data and obj_data['futures_exchange'] is not None:
            obj_data['futures_exchange'] = ExchangeEnum(obj_data['futures_exchange'])
        
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