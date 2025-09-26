"""
Enhanced Exchange Factory with Migration Support.

Factory supporting both unified (legacy) and composite patterns with automatic
pattern selection based on calling context and feature flags. Enables gradual
migration from unified to composite architecture.
"""

import os
import inspect
import asyncio
from typing import Union, List, Optional, Dict, Any
from config.config_manager import HftConfig
from exchanges.structs.common import Symbol
from infrastructure.logging import HFTLoggerFactory, HFTLoggerInterface
from infrastructure.exceptions.system import InitializationError

from .composite_exchange_factory import CompositeExchangeFactory
from .migration_adapter import UnifiedToCompositeAdapter, LegacyInterfaceWarning
from .exchange_registry import ExchangePair, ExchangeRegistry


class EnhancedExchangeFactory:
    """
    Factory supporting both unified (legacy) and composite patterns.
    
    Features:
    - Automatic pattern detection based on calling context
    - Feature flags for forced migration modes
    - Performance tracking and migration analytics
    - Concurrent exchange creation
    - Legacy compatibility warnings
    """
    
    def __init__(self, 
                 config_manager: Optional[HftConfig] = None, 
                 logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize enhanced factory.
        
        Args:
            config_manager: Configuration manager instance
            logger: Optional logger instance
        """
        self.config_manager = config_manager or HftConfig()
        self.logger = logger or HFTLoggerFactory.create_logger("EnhancedExchangeFactory", "INFO")
        self.composite_factory = CompositeExchangeFactory(config_manager, logger)
        
        # Migration control
        self._migration_mode = self._check_migration_mode()
        self._force_composite = self._check_force_composite()
        self._legacy_components = self._get_legacy_components()
        
        # Analytics
        self._unified_requests = 0
        self._composite_requests = 0
        self._migration_warnings = 0
    
    def _check_migration_mode(self) -> bool:
        """Check if we're in migration mode."""
        return os.environ.get("ENABLE_MIGRATION_MODE", "true").lower() == "true"
    
    def _check_force_composite(self) -> bool:
        """Check if composite pattern is forced."""
        return os.environ.get("FORCE_COMPOSITE_PATTERN", "false").lower() == "true"
    
    def _get_legacy_components(self) -> List[str]:
        """Get list of components that still need unified interface."""
        # These components haven't been migrated to composite pattern yet
        default_legacy = [
            "arbitrageengine",
            "riskcontroller", 
            "marketmakingdemo",
            "simpleengine",
            "legacybot"
        ]
        
        # Allow override via environment
        env_legacy = os.environ.get("LEGACY_COMPONENTS", "")
        if env_legacy:
            return [comp.strip().lower() for comp in env_legacy.split(",")]
        
        return default_legacy
    
    def _should_use_unified(self, exchange_name: str, caller_info: Optional[str] = None) -> bool:
        """
        Determine if unified pattern should be used.
        
        Args:
            exchange_name: Name of the exchange
            caller_info: Optional caller information for detection
            
        Returns:
            True if unified interface should be used, False for composite
        """
        # Force composite if flag is set
        if self._force_composite:
            return False
        
        # If migration mode is disabled, always use composite
        if not self._migration_mode:
            return False
        
        # Check caller stack to detect legacy components
        caller_info = caller_info or self._detect_calling_component()
        
        if caller_info:
            caller_lower = caller_info.lower()
            for legacy_component in self._legacy_components:
                if legacy_component in caller_lower:
                    self.logger.warning(
                        "Using unified adapter for legacy component",
                        component=legacy_component,
                        exchange=exchange_name,
                        caller=caller_info
                    )
                    self._migration_warnings += 1
                    LegacyInterfaceWarning.warn_unified_interface_usage(legacy_component)
                    return True
        
        return False
    
    def _detect_calling_component(self) -> Optional[str]:
        """Detect calling component from stack trace."""
        try:
            # Look through stack to find calling component
            stack = inspect.stack()
            for frame_info in stack[2:]:  # Skip current and immediate caller
                filename = frame_info.filename.lower()
                function_name = frame_info.function.lower()
                
                # Check filename for component patterns
                for legacy_component in self._legacy_components:
                    if legacy_component in filename or legacy_component in function_name:
                        return f"{frame_info.filename}:{frame_info.function}"
            
            return None
        except Exception:
            return None
    
    async def create_exchange(self,
                             exchange_name: str,
                             symbols: Optional[List[Symbol]] = None,
                             use_unified: Optional[bool] = None,
                             private_enabled: bool = True) -> Union[UnifiedToCompositeAdapter, ExchangePair]:
        """
        Create exchange with automatic pattern selection.
        
        Args:
            exchange_name: Name of the exchange
            symbols: Symbols to initialize
            use_unified: Force unified pattern (for backward compatibility)
            private_enabled: Whether to create private exchange
            
        Returns:
            UnifiedToCompositeAdapter or ExchangePair based on mode
        """
        try:
            # Determine pattern to use
            if use_unified is None:
                use_unified = self._should_use_unified(exchange_name)
            
            # Track request type
            if use_unified:
                self._unified_requests += 1
            else:
                self._composite_requests += 1
            
            # Create exchange pair using composite factory
            pair = await self.composite_factory.create_exchange_pair(
                exchange_name, symbols, private_enabled
            )
            
            if use_unified:
                # Wrap in adapter for unified interface
                adapter = UnifiedToCompositeAdapter(
                    public_exchange=pair.public,
                    private_exchange=pair.private,
                    logger=self.logger
                )
                
                self.logger.info("Created unified interface adapter",
                               exchange=exchange_name,
                               has_private=pair.private is not None)
                
                return adapter
            else:
                # Return composite pattern directly
                self.logger.info("Created composite exchange pair",
                               exchange=exchange_name,
                               has_private=pair.private is not None)
                
                return pair
                
        except Exception as e:
            self.logger.error("Failed to create exchange",
                            exchange=exchange_name,
                            use_unified=use_unified,
                            error=str(e))
            raise InitializationError(f"Failed to create exchange {exchange_name}: {e}")
    
    async def create_public_exchange(self, 
                                   exchange_name: str, 
                                   symbols: Optional[List[Symbol]] = None):
        """Create public exchange using composite pattern."""
        return await self.composite_factory.create_public_exchange(exchange_name, symbols)
    
    async def create_private_exchange(self, 
                                    exchange_name: str, 
                                    symbols_info: Optional[Any] = None):
        """Create private exchange using composite pattern."""
        return await self.composite_factory.create_private_exchange(exchange_name, symbols_info)
    
    async def create_exchange_pair(self, 
                                 exchange_name: str,
                                 symbols: Optional[List[Symbol]] = None,
                                 private_enabled: bool = True) -> ExchangePair:
        """Create exchange pair using composite pattern."""
        return await self.composite_factory.create_exchange_pair(exchange_name, symbols, private_enabled)
    
    async def create_multiple_exchanges(self,
                                      exchange_names: List[str],
                                      symbols: Optional[List[Symbol]] = None,
                                      use_unified: bool = False,
                                      private_enabled: bool = True) -> Dict[str, Union[UnifiedToCompositeAdapter, ExchangePair]]:
        """
        Create multiple exchanges concurrently.
        
        Args:
            exchange_names: List of exchange names
            symbols: Symbols to initialize
            use_unified: Whether to use unified interface
            private_enabled: Whether to create private exchanges
            
        Returns:
            Dictionary mapping exchange names to exchange instances
        """
        self.logger.info("Creating multiple exchanges concurrently",
                        exchanges=exchange_names,
                        count=len(exchange_names),
                        use_unified=use_unified)
        
        # Create tasks for concurrent execution
        tasks = [
            asyncio.create_task(
                self.create_exchange(name, symbols, use_unified, private_enabled),
                name=f"create_{name}"
            )
            for name in exchange_names
        ]
        
        # Wait for all exchanges to be created
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        exchange_map = {}
        successful_count = 0
        
        for exchange_name, result in zip(exchange_names, results):
            if isinstance(result, Exception):
                self.logger.error("Failed to create exchange",
                                exchange=exchange_name,
                                error=str(result))
                continue
            
            exchange_map[exchange_name] = result
            successful_count += 1
        
        self.logger.info("Multiple exchange creation completed",
                        requested=len(exchange_names),
                        successful=successful_count,
                        failed=len(exchange_names) - successful_count)
        
        return exchange_map
    
    def list_available_exchanges(self) -> List[str]:
        """List all available exchanges."""
        return self.composite_factory.list_available_exchanges()
    
    def list_spot_exchanges(self) -> List[str]:
        """List available spot exchanges."""
        return self.composite_factory.list_spot_exchanges()
    
    
    def get_exchange_info(self, exchange_name: str) -> Dict:
        """Get exchange information."""
        return self.composite_factory.get_exchange_info(exchange_name)
    
    def has_feature(self, exchange_name: str, feature: str) -> bool:
        """Check if exchange has specific feature."""
        return ExchangeRegistry.has_feature(exchange_name, feature)
    
    def get_migration_stats(self) -> Dict:
        """Get migration statistics and analytics."""
        total_requests = self._unified_requests + self._composite_requests
        
        return {
            "migration_mode_enabled": self._migration_mode,
            "force_composite": self._force_composite,
            "total_requests": total_requests,
            "unified_requests": self._unified_requests,
            "composite_requests": self._composite_requests,
            "unified_percentage": (self._unified_requests / total_requests * 100) if total_requests > 0 else 0,
            "migration_warnings": self._migration_warnings,
            "legacy_components": self._legacy_components,
            "factory_performance": self.composite_factory.get_performance_stats()
        }
    
    def recommend_migration(self) -> List[str]:
        """Provide migration recommendations based on usage patterns."""
        recommendations = []
        
        if self._unified_requests > 0:
            recommendations.append(
                f"Found {self._unified_requests} unified interface requests. "
                f"Consider migrating to composite pattern for better performance and maintainability."
            )
        
        if self._migration_warnings > 0:
            recommendations.append(
                f"Issued {self._migration_warnings} legacy component warnings. "
                f"Update these components to use composite exchanges directly."
            )
        
        if self._force_composite:
            recommendations.append(
                "Force composite mode is enabled. All new code should use composite pattern."
            )
        
        if not recommendations:
            recommendations.append("Migration analytics show good adoption of composite pattern.")
        
        return recommendations
    
    async def close_all_exchanges(self):
        """Close all exchanges created by this factory."""
        await self.composite_factory.close_all_exchanges()
    
    def set_migration_mode(self, enabled: bool):
        """Enable or disable migration mode."""
        self._migration_mode = enabled
        self.logger.info("Migration mode updated", enabled=enabled)
    
    def add_legacy_component(self, component_name: str):
        """Add component to legacy list."""
        component_lower = component_name.lower()
        if component_lower not in self._legacy_components:
            self._legacy_components.append(component_lower)
            self.logger.info("Added legacy component", component=component_name)
    
    def remove_legacy_component(self, component_name: str):
        """Remove component from legacy list (after migration)."""
        component_lower = component_name.lower()
        if component_lower in self._legacy_components:
            self._legacy_components.remove(component_lower)
            self.logger.info("Removed legacy component", component=component_name)


# Convenience functions for global usage
_global_factory: Optional[EnhancedExchangeFactory] = None

def get_global_factory() -> EnhancedExchangeFactory:
    """Get or create global factory instance."""
    global _global_factory
    if _global_factory is None:
        _global_factory = EnhancedExchangeFactory()
    return _global_factory

def set_global_factory(factory: EnhancedExchangeFactory):
    """Set global factory instance."""
    global _global_factory
    _global_factory = factory

async def create_exchange_simple(exchange_name: str, 
                                symbols: Optional[List[Symbol]] = None) -> Union[UnifiedToCompositeAdapter, ExchangePair]:
    """Simple exchange creation using global factory."""
    factory = get_global_factory()
    return await factory.create_exchange(exchange_name, symbols)