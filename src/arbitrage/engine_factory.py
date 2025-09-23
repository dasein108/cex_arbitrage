"""
Engine Factory

Factory for creating appropriate arbitrage engine instances.
Streamlines the engine selection architecture.

HFT COMPLIANT: Fast engine instantiation with minimal overhead.
"""

from core.logging import get_logger
from typing import Dict, Type, Union
from arbitrage.types import ArbitrageConfig
from interfaces.exchanges.base.base_private_exchange import BasePrivateExchangeInterface

logger = get_logger('arbitrage.engine_factory')


class EngineType:
    """Engine type constants."""
    SIMPLE = "simple"
    PRODUCTION = "production"


class EngineFactory:
    """
    Factory for creating arbitrage engine instances.
    
    Provides clean abstraction for engine selection and instantiation.
    Eliminates architectural debt from mixed engine usage.
    """
    
    _engines: Dict[str, Type] = {}
    
    @classmethod
    def register_engine(cls, engine_type: str, engine_class: Type):
        """
        Register an engine type.
        
        Args:
            engine_type: Engine type identifier
            engine_class: Engine class to register
        """
        cls._engines[engine_type] = engine_class
        logger.debug(f"Registered engine type: {engine_type}")
    
    @classmethod
    def create_engine(
        cls,
        engine_type: str,
        config: ArbitrageConfig,
        exchanges: Dict[str, BasePrivateExchangeInterface]
    ) -> Union['SimpleArbitrageEngine', 'ArbitrageEngine']:
        """
        Create engine instance based on type.
        
        Args:
            engine_type: Type of engine to create
            config: Arbitrage configuration
            exchanges: Dictionary of exchange instances
            
        Returns:
            Engine instance
            
        Raises:
            ValueError: If engine type is not registered
        """
        if engine_type not in cls._engines:
            available_types = list(cls._engines.keys())
            raise ValueError(
                f"Unknown engine type: {engine_type}. "
                f"Available types: {available_types}"
            )
        
        engine_class = cls._engines[engine_type]
        logger.info(f"Creating {engine_type} engine: {engine_class.__name__}")
        
        return engine_class(config, exchanges)
    
    @classmethod
    def get_recommended_engine_type(cls, config: ArbitrageConfig) -> str:
        """
        Get recommended engine type based on configuration.
        
        Args:
            config: Arbitrage configuration
            
        Returns:
            Recommended engine type
        """
        # Production recommendation logic
        if config.enable_dry_run:
            # For testing and development
            return EngineType.SIMPLE
        elif len(config.arbitrage_pairs) > 10 or config.target_execution_time_ms < 30:
            # High-performance requirements
            return EngineType.PRODUCTION
        else:
            # Standard use cases
            return EngineType.SIMPLE
    
    @classmethod
    def list_available_engines(cls) -> Dict[str, str]:
        """
        List available engine types and their descriptions.
        
        Returns:
            Dictionary mapping engine types to descriptions
        """
        descriptions = {
            EngineType.SIMPLE: "Simplified engine for testing and basic arbitrage",
            EngineType.PRODUCTION: "Full-featured engine for production HFT trading"
        }
        
        available = {}
        for engine_type in cls._engines.keys():
            available[engine_type] = descriptions.get(
                engine_type, 
                f"Custom engine: {cls._engines[engine_type].__name__}"
            )
        
        return available


# Register default engines
def _register_default_engines():
    """Register default engine implementations."""
    try:
        # Register simple engine
        from arbitrage.simple_engine import SimpleArbitrageEngine
        EngineFactory.register_engine(EngineType.SIMPLE, SimpleArbitrageEngine)
    except ImportError as e:
        logger.warning(f"Could not register simple engine: {e}")
    
    try:
        # Register production engine
        from arbitrage.engine import ArbitrageEngine
        EngineFactory.register_engine(EngineType.PRODUCTION, ArbitrageEngine)
    except ImportError as e:
        logger.warning(f"Could not register production engine: {e}")


# Auto-register on module import
_register_default_engines()