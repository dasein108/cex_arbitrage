"""
Engine Utilities

Simple functions for arbitrage engine creation and selection.
Replaces the over-engineered EngineFactory pattern with direct instantiation.

HFT COMPLIANT: Minimal overhead engine creation.
"""

from infrastructure.logging import get_logger
from typing import Dict, Union
from archive.trading.arbitrage.types import ArbitrageConfig
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange

logger = get_logger('arbitrage.engine_utils')


def get_recommended_engine_type(config: ArbitrageConfig) -> str:
    """
    Get recommended engine type based on configuration.
    
    Args:
        config: Arbitrage configuration
        
    Returns:
        Recommended engine type ("simple" or "production")
    """
    # Production recommendation logic
    if config.enable_dry_run:
        # For testing and development
        return "simple"
    elif len(config.arbitrage_pairs) > 10 or config.target_execution_time_ms < 30:
        # High-performance requirements
        return "production"
    else:
        # Standard use cases
        return "simple"


def create_engine(
    engine_type: str,
    config: ArbitrageConfig,
    exchanges: Dict[str, CompositePrivateSpotExchange]
) -> Union['SimpleArbitrageEngine', 'ArbitrageEngine']:
    """
    Create arbitrage engine instance based on type.
    
    Args:
        engine_type: Type of engine to create ("simple" or "production")
        config: Arbitrage configuration
        exchanges: Dictionary of exchange instances
        
    Returns:
        Engine instance
        
    Raises:
        ValueError: If engine type is not supported
        ImportError: If engine module cannot be imported
    """
    logger.info(f"Creating {engine_type} engine")
    
    if engine_type == "simple":
        try:
            from archive.trading.arbitrage.simple_engine import SimpleArbitrageEngine
            return SimpleArbitrageEngine(config, exchanges)
        except ImportError as e:
            logger.error(f"Could not import SimpleArbitrageEngine: {e}")
            raise
    elif engine_type == "production":
        try:
            from archive.trading.arbitrage.engine import ArbitrageEngine
            return ArbitrageEngine(config, exchanges)
        except ImportError as e:
            logger.error(f"Could not import ArbitrageEngine: {e}")
            raise
    else:
        available_types = ["simple", "production"]
        raise ValueError(
            f"Unknown engine type: {engine_type}. "
            f"Available types: {available_types}"
        )


def list_available_engines() -> Dict[str, str]:
    """
    List available engine types and their descriptions.
    
    Returns:
        Dictionary mapping engine types to descriptions
    """
    return {
        "simple": "Simplified engine for testing and basic arbitrage",
        "production": "Full-featured engine for production HFT trading"
    }