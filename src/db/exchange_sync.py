"""
Exchange Synchronization Service

Handles automatic exchange registration and management during data collector startup.
Ensures exchanges are properly registered in the database before symbol synchronization.
"""

import logging
from typing import List, Optional
from exchanges.structs.enums import ExchangeEnum
from .models import Exchange, SymbolType
from .operations import get_exchange_by_enum_value, insert_exchange
from .connection import get_db_manager


logger = logging.getLogger(__name__)


class ExchangeSyncService:
    """
    Service for synchronizing exchange information with the database.
    
    Handles automatic registration of exchanges during data collector startup.
    """
    
    def __init__(self):
        self.logger = logger
    
    async def ensure_exchange_exists(self, exchange_enum: ExchangeEnum) -> Exchange:
        """
        Ensure exchange exists in database, create if missing.
        
        Args:
            exchange_enum: Exchange enum to register
            
        Returns:
            Exchange instance from database
        """
        try:
            # Check if exchange already exists
            existing_exchange = await get_exchange_by_enum_value(exchange_enum.value)
            if existing_exchange:
                self.logger.debug(f"Exchange {exchange_enum.value} already exists with ID {existing_exchange.id}")
                return existing_exchange
            
            # Create new exchange
            self.logger.info(f"Registering new exchange: {exchange_enum.value}")
            
            # Create exchange from enum with default values
            new_exchange = Exchange.from_exchange_enum(exchange_enum)
            
            # Insert into database
            exchange_id = await insert_exchange(new_exchange)
            new_exchange.id = exchange_id
            
            self.logger.info(f"Successfully registered exchange {exchange_enum.value} with ID {exchange_id}")
            return new_exchange
            
        except Exception as e:
            self.logger.error(f"Failed to ensure exchange {exchange_enum.value} exists: {e}")
            raise
    
    async def sync_exchanges(self, exchange_enums: List[ExchangeEnum]) -> List[Exchange]:
        """
        Synchronize multiple exchanges with database.
        
        Args:
            exchange_enums: List of exchange enums to sync
            
        Returns:
            List of Exchange instances from database
        """
        try:
            self.logger.info(f"Synchronizing {len(exchange_enums)} exchanges")
            
            exchanges = []
            for exchange_enum in exchange_enums:
                exchange = await self.ensure_exchange_exists(exchange_enum)
                exchanges.append(exchange)
            
            self.logger.info(f"Successfully synchronized {len(exchanges)} exchanges")
            return exchanges
            
        except Exception as e:
            self.logger.error(f"Failed to sync exchanges: {e}")
            raise
    
    async def get_exchange_market_type(self, exchange_enum: ExchangeEnum) -> str:
        """
        Determine market type for exchange.
        
        Args:
            exchange_enum: Exchange enum
            
        Returns:
            Market type (SPOT, FUTURES, OPTIONS)
        """
        # Determine market type from exchange name
        exchange_name = exchange_enum.value.upper()
        
        if 'FUTURES' in exchange_name:
            return 'FUTURES'
        elif 'OPTIONS' in exchange_name:
            return 'OPTIONS'
        else:
            return 'SPOT'
    
    async def get_symbol_type_for_exchange(self, exchange_enum: ExchangeEnum) -> SymbolType:
        """
        Get default symbol type for exchange.
        
        Args:
            exchange_enum: Exchange enum
            
        Returns:
            SymbolType enum value
        """
        market_type = await self.get_exchange_market_type(exchange_enum)
        
        if market_type == 'FUTURES':
            return SymbolType.FUTURES
        else:
            return SymbolType.SPOT


# Global service instance
_exchange_sync_service = None

def get_exchange_sync_service() -> ExchangeSyncService:
    """Get global exchange sync service instance."""
    global _exchange_sync_service
    if _exchange_sync_service is None:
        _exchange_sync_service = ExchangeSyncService()
    return _exchange_sync_service