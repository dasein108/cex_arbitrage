"""
Exchange Demo Base Class

Provides common functionality for all exchange demo scripts to eliminate
code duplication and standardize demo patterns.
"""

import sys
import asyncio
from typing import List, Optional, Any, Dict
from abc import ABC, abstractmethod

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName, ExchangeName
from config.config_manager import HftConfig
from exchanges.transport_factory import create_rest_client, create_websocket_client
from exchanges.utils.exchange_utils import get_exchange_enum
from infrastructure.logging import HFTLoggerInterface, get_logger
from ..utils.constants import TEST_SYMBOLS, DEMO_SEPARATOR


class ExchangeDemoBase(ABC):
    """Base class for all exchange demo scripts with shared functionality."""
    
    def __init__(self, exchange_name: str, logger: Optional[HFTLoggerInterface] = None):
        self.exchange_name = exchange_name.upper()
        self.logger = logger or get_logger(f'demo.{exchange_name.lower()}')
        
        # Initialize components
        self.config = None
        self.rest_client = None
        self.websocket_client = None
        self._initialized = False
        
        self.logger.info(f"Initializing {self.__class__.__name__}",
                        exchange=self.exchange_name)
    
    async def setup(self, 
                   need_rest: bool = True, 
                   need_websocket: bool = False,
                   is_private: bool = False) -> Dict[str, Any]:
        """Unified setup for exchange connections."""
        if self._initialized:
            return {"status": "already_initialized"}
            
        try:
            # Load configuration
            config_manager = HftConfig()
            self.config = config_manager.get_exchange_config(self.exchange_name.lower())
            
            # Verify private credentials if needed
            if is_private:
                if not self.config.credentials.api_key or not self.config.credentials.secret_key:
                    raise ValueError(f"{self.exchange_name} API credentials are required for private operations")
                
                self.logger.info("Using API credentials",
                               exchange=self.exchange_name,
                               api_key_preview=f"{self.config.credentials.api_key[:8]}...")
            
            # Setup REST client if needed
            if need_rest:
                exchange_enum = get_exchange_enum(self.exchange_name)
                self.rest_client = create_rest_client(
                    exchange=exchange_enum,
                    is_private=is_private,
                    config=self.config
                )
                self.logger.info("REST client initialized",
                               exchange=self.exchange_name,
                               client_type="private" if is_private else "public")
            
            # Setup WebSocket client if needed
            if need_websocket:
                # WebSocket setup will be handled by specific demo implementations
                # since they need different handlers
                pass
                
            self._initialized = True
            
            return {
                "status": "success",
                "exchange": self.exchange_name,
                "rest_initialized": need_rest,
                "websocket_initialized": need_websocket,
                "private_mode": is_private
            }
            
        except Exception as e:
            error_msg = f"Failed to setup {self.exchange_name}: {e}"
            self.logger.error("Setup failed",
                            exchange=self.exchange_name,
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise ValueError(error_msg) from e
    
    async def cleanup(self) -> None:
        """Standardized cleanup for all resources."""
        try:
            if self.rest_client:
                await self.rest_client.close()
                self.logger.info("REST client closed", exchange=self.exchange_name)
                
            if self.websocket_client:
                await self.websocket_client.close()
                self.logger.info("WebSocket client closed", exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Cleanup error",
                            exchange=self.exchange_name,
                            error_message=str(e))
        finally:
            self._initialized = False
    
    def get_test_symbols(self, extended: bool = False) -> List[Symbol]:
        """Get standard test symbols for demos."""
        if extended:
            from ..utils.constants import EXTENDED_TEST_SYMBOLS
            return EXTENDED_TEST_SYMBOLS.copy()
        return TEST_SYMBOLS.copy()
    
    def print_header(self, title: str) -> None:
        """Print standardized demo header."""
        self.logger.info(f"🚀 Starting {title}")
        self.logger.info(DEMO_SEPARATOR)
    
    def print_footer(self, title: str) -> None:
        """Print standardized demo footer."""
        self.logger.info(DEMO_SEPARATOR)
        self.logger.info(f"✅ {title} completed")
    
    def print_section(self, section_name: str) -> None:
        """Print standardized section header."""
        self.logger.info(f"\n=== {self.exchange_name} {section_name.upper()} ===")
    
    async def safe_execute(self, 
                          operation: str,
                          func,
                          *args,
                          **kwargs) -> Dict[str, Any]:
        """Safely execute operations with consistent error handling."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            self.logger.info(f"✅ {operation} completed",
                           exchange=self.exchange_name,
                           execution_time_ms=execution_time)
            
            return {
                "status": "success",
                "result": result,
                "execution_time_ms": execution_time,
                "operation": operation
            }
            
        except Exception as e:
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            self.logger.error(f"❌ {operation} failed",
                            exchange=self.exchange_name,
                            error_type=type(e).__name__,
                            error_message=str(e),
                            execution_time_ms=execution_time)
            
            return {
                "status": "error",
                "result": None,
                "execution_time_ms": execution_time,
                "operation": operation,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    @abstractmethod
    async def run_demo(self, **kwargs) -> Dict[str, Any]:
        """Run the specific demo implementation."""
        pass
    
    async def main(self, args: Optional[List[str]] = None) -> int:
        """Standardized main method for all demos."""
        if args is None:
            args = sys.argv[1:]
        
        try:
            # Parse basic arguments (specific demos can extend this)
            exchange_name = args[0] if args else self.exchange_name.lower()
            self.exchange_name = exchange_name.upper()
            
            # Run the demo
            result = await self.run_demo(args=args)
            
            if result.get("status") == "success":
                print(f"\n✅ {self.exchange_name} demo completed successfully!")
                return 0
            else:
                print(f"\n❌ {self.exchange_name} demo failed: {result.get('error', 'Unknown error')}")
                return 1
                
        except KeyboardInterrupt:
            print(f"\n🛑 {self.exchange_name} demo interrupted by user")
            return 130
        except Exception as e:
            print(f"\n❌ {self.exchange_name} demo failed: {e}")
            return 1
        finally:
            await self.cleanup()


class RestDemoMixin:
    """Mixin providing common REST API demo functionality."""
    
    async def test_ping(self) -> Dict[str, Any]:
        """Test ping functionality."""
        return await self.safe_execute("ping", self.rest_client.ping)
    
    async def test_server_time(self) -> Dict[str, Any]:
        """Test server time retrieval."""
        result = await self.safe_execute("server_time", self.rest_client.get_server_time)
        if result["status"] == "success":
            result["result"] = {"server_time": result["result"]}
        return result
    
    async def test_exchange_info(self) -> Dict[str, Any]:
        """Test exchange info retrieval."""
        result = await self.safe_execute("exchange_info", self.rest_client.get_exchange_info)
        if result["status"] == "success":
            # Structure result for display
            exchange_info = result["result"]
            sample_symbols = []
            for i, (symbol, info) in enumerate(exchange_info.items()):
                if i >= 3:
                    break
                sample_symbols.append({
                    "symbol": str(symbol),
                    "base_precision": info.base_precision,
                    "quote_precision": info.quote_precision,
                    "min_base_amount": info.min_base_amount,
                    "min_quote_amount": info.min_quote_amount
                })
            
            result["result"] = {
                "total_symbols": len(exchange_info),
                "sample_symbols": sample_symbols
            }
        return result


class WebSocketDemoMixin:
    """Mixin providing common WebSocket demo functionality."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_manager = None
    
    def setup_data_manager(self) -> None:
        """Setup unified data manager for WebSocket data."""
        from .data_manager import UnifiedDataManager
        self.data_manager = UnifiedDataManager(self.exchange_name, self.logger)
    
    def get_websocket_performance_summary(self) -> Dict[str, Any]:
        """Get WebSocket performance summary."""
        if not self.websocket_client:
            return {"error": "WebSocket client not initialized"}
            
        metrics = self.websocket_client.get_performance_metrics()
        data_summary = self.data_manager.get_summary() if self.data_manager else {}
        
        return {
            "connection_metrics": metrics,
            "data_summary": data_summary,
            "performance_summary": self.data_manager.get_performance_summary() if self.data_manager else {}
        }