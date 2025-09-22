from typing import Dict
from structs.common import OrderStatus, OrderType, Side, TimeInForce, KlineInterval


class BaseMappingConfiguration:
    """
    Configuration container for exchange-specific mapping dictionaries.

    Stores all mapping dictionaries used by an exchange implementation.
    Enables configuration-driven mapping without code changes.
    """

    def __init__(
        self,
        order_status_mapping: Dict[OrderStatus, str],
        order_type_mapping: Dict[OrderType, str],
        side_mapping: Dict[Side, str],
        time_in_force_mapping: Dict[TimeInForce, str],
        kline_interval_mapping: Dict[KlineInterval, str]
    ):
        # Forward mappings (unified -> exchange)
        self.order_status_mapping = order_status_mapping
        self.order_type_mapping = order_type_mapping
        self.side_mapping = side_mapping
        self.time_in_force_mapping = time_in_force_mapping
        self.kline_interval_mapping = kline_interval_mapping

        # Reverse mappings (exchange -> unified) - auto-generated
        self.order_status_reverse = {v: k for k, v in order_status_mapping.items()}
        self.order_type_reverse = {v: k for k, v in order_type_mapping.items()}
        self.side_reverse = {v: k for k, v in side_mapping.items()}
        self.time_in_force_reverse = {v: k for k, v in time_in_force_mapping.items()}
        self.kline_interval_reverse = {v: k for k, v in kline_interval_mapping.items()}
