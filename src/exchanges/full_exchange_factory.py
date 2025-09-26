from typing import Dict, Optional, List

from config.structs import ExchangeConfig
from exchanges.interfaces.composite.unified_exchange import UnifiedCompositeExchange
from exchanges.structs import Symbol, ExchangeEnum
from exchanges.utils.exchange_utils import get_exchange_enum
from infrastructure.logging import get_exchange_logger


class FullExchangeFactory:
    """
    Simplified factory for creating unified exchange instances.

    Follows semantic naming convention migration:
    - Accepts string exchange_name inputs for high-level API
    - Uses ExchangeEnum internally for type safety
    - Employs get_exchange_enum() for conversion
    """

    def __init__(self):
        self._supported_exchanges = {
            ExchangeEnum.MEXC: 'exchanges.integrations.mexc.mexc_unified_exchange.MexcUnifiedExchange',
            ExchangeEnum.GATEIO: 'exchanges.integrations.gateio.gateio_unified_exchange.GateioUnifiedExchange',
            ExchangeEnum.GATEIO_FUTURES: 'exchanges.integrations.gateio.gateio_futures_unified_exchange.GateioFuturesUnifiedExchange'
        }
        self._active_exchanges: Dict[str, UnifiedCompositeExchange] = {}

    async def create_exchange(self,
                            exchange_name: str,
                            symbols: Optional[List[Symbol]] = None,
                            config: Optional[ExchangeConfig] = None) -> UnifiedCompositeExchange:
        """
        Create a unified exchange instance using config_manager pattern.

        Args:
            exchange_name: Exchange name (mexc, gateio, gateio_futures, etc.)
            symbols: Optional symbols to initialize
            config: Optional exchange configuration (if not provided, loads from config_manager)

        Returns:
            Initialized exchange instance
        """
        # Convert string exchange_name to ExchangeEnum internally
        try:
            exchange_enum = get_exchange_enum(exchange_name)
        except ValueError as e:
            raise ValueError(f"Unsupported exchange: {exchange_name}. {e}")

        if exchange_enum not in self._supported_exchanges:
            supported_names = [enum.value for enum in self._supported_exchanges.keys()]
            raise ValueError(f"Exchange '{exchange_name}' not implemented. Supported: {supported_names}")

        # Get config from config_manager if not provided
        if config is None:
            from config.config_manager import get_exchange_config
            config = get_exchange_config(exchange_enum.value)

        # Dynamic import to avoid circular dependencies
        module_path = self._supported_exchanges[exchange_enum]
        module_name, class_name = module_path.rsplit('.', 1)

        try:
            import importlib
            module = importlib.import_module(module_name)
            exchange_class = getattr(module, class_name)

            # Create and initialize exchange with ExchangeEnum internally
            exchange = exchange_class(config=config, symbols=symbols, exchange_enum=exchange_enum)
            await exchange.initialize()

            # Track for cleanup using semantic name
            self._active_exchanges[exchange_enum.value] = exchange

            return exchange

        except ImportError as e:
            raise ImportError(f"Failed to import {exchange_name} exchange: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to create {exchange_name} exchange: {e}")

    async def create_multiple_exchanges(self,
                                      exchange_names: List[str],
                                      symbols: Optional[List[Symbol]] = None,
                                      exchange_configs: Optional[Dict[str, ExchangeConfig]] = None) -> Dict[str, UnifiedCompositeExchange]:
        """
        Create multiple exchanges concurrently.

        Args:
            exchange_names: List of exchange names to create
            symbols: Optional symbols for all exchanges
            exchange_configs: Optional dict mapping exchange names to configs (loads from config_manager if not provided)

        Returns:
            Dict mapping exchange names to initialized exchanges
        """
        import asyncio

        async def create_single(name: str) -> tuple[str, UnifiedCompositeExchange]:
            try:
                config = exchange_configs.get(name) if exchange_configs else None
                exchange = await self.create_exchange(name, symbols, config)
                return name, exchange
            except Exception as e:
                logger = get_exchange_logger('factory', 'unified')
                logger.error(f"Failed to create {name} exchange: {e}")
                return name, None

        # Create all exchanges concurrently
        tasks = [create_single(name) for name in exchange_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict, filtering out failed exchanges
        exchanges = {}
        for result in results:
            if isinstance(result, tuple) and result[1] is not None:
                name, exchange = result
                exchanges[name] = exchange

        return exchanges

    async def close_all(self) -> None:
        """Close all managed exchanges."""
        for exchange in self._active_exchanges.values():
            try:
                await exchange.close()
            except Exception as e:
                logger = get_exchange_logger('factory', 'unified')
                logger.error(f"Error closing exchange: {e}")

        self._active_exchanges.clear()

    def get_supported_exchanges(self) -> List[str]:
        """Get list of supported exchange names."""
        return list(self._supported_exchanges.keys())

    @property
    def active_exchanges(self) -> Dict[str, UnifiedCompositeExchange]:
        """Get currently active exchanges."""
        return self._active_exchanges.copy()
