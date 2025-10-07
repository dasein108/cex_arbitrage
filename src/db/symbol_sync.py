"""
Symbol Synchronization Service

Handles automatic symbol synchronization with exchanges during data collector startup.
Fetches symbol information from exchanges, compares with database state, and updates accordingly.
"""

import logging
from typing import List, Dict, Set, Optional, Tuple
from datetime import datetime
from exchanges.structs.enums import ExchangeEnum
from exchanges.structs.common import Symbol as ExchangeSymbol
from .models import Exchange, Symbol as DBSymbol, SymbolType
from .operations import (
    get_symbols_by_exchange, 
    insert_symbol, 
    update_symbol,
    get_symbol_by_exchange_and_pair
)
from .exchange_sync import get_exchange_sync_service
from .connection import get_db_manager


logger = logging.getLogger(__name__)


class SymbolSyncService:
    """
    Service for synchronizing symbol information with exchanges.
    
    Handles fetching symbols from exchange APIs, comparing with database state,
    and updating symbols (add new, mark inactive, update existing).
    """
    
    def __init__(self):
        self.logger = logger
        self.exchange_sync = get_exchange_sync_service()
    
    async def fetch_exchange_symbols(self, exchange_enum: ExchangeEnum) -> List[ExchangeSymbol]:
        """
        Fetch symbols from exchange API.
        
        Args:
            exchange_enum: Exchange to fetch symbols from
            
        Returns:
            List of exchange symbols
        """
        try:
            self.logger.info(f"Fetching symbols from {exchange_enum.value}")
            
            # Import exchange factory
            from exchanges.exchange_factory import get_composite_implementation
            from config.config_manager import get_exchange_config
            
            # Get exchange configuration
            config = get_exchange_config(exchange_enum.value)
            
            # Create composite public exchange
            composite = get_composite_implementation(
                exchange_config=config,
                is_private=False  # Public API for symbol info
            )
            
            # Get symbol information
            symbols_info = await composite.get_symbols_info()
            
            # Convert to list of ExchangeSymbol objects
            symbols = []
            for symbol_info in symbols_info.values():
                try:
                    # Create ExchangeSymbol from symbol info
                    symbol = ExchangeSymbol(
                        base=symbol_info.base,
                        quote=symbol_info.quote
                    )
                    symbols.append(symbol)
                except Exception as e:
                    self.logger.warning(f"Failed to create symbol from {symbol_info}: {e}")
                    continue
            
            # Close composite connection
            await composite.close()
            
            self.logger.info(f"Fetched {len(symbols)} symbols from {exchange_enum.value}")
            return symbols
            
        except Exception as e:
            self.logger.error(f"Failed to fetch symbols from {exchange_enum.value}: {e}")
            return []
    
    async def get_database_symbols(self, exchange_id: int) -> Dict[Tuple[str, str, SymbolType], DBSymbol]:
        """
        Get existing symbols from database for an exchange.
        
        Args:
            exchange_id: Exchange database ID
            
        Returns:
            Dictionary mapping (base, quote, type) -> DBSymbol
        """
        try:
            db_symbols = await get_symbols_by_exchange(exchange_id)
            
            # Create lookup dictionary
            symbol_map = {}
            for db_symbol in db_symbols:
                key = (
                    db_symbol.symbol_base.upper(),
                    db_symbol.symbol_quote.upper(), 
                    db_symbol.symbol_type
                )
                symbol_map[key] = db_symbol
            
            self.logger.debug(f"Found {len(symbol_map)} existing symbols for exchange {exchange_id}")
            return symbol_map
            
        except Exception as e:
            self.logger.error(f"Failed to get database symbols for exchange {exchange_id}: {e}")
            return {}
    
    async def sync_exchange_symbols(self, exchange_enum: ExchangeEnum) -> Dict[str, int]:
        """
        Synchronize symbols for a single exchange.
        
        Args:
            exchange_enum: Exchange to synchronize
            
        Returns:
            Statistics dictionary with counts
        """
        try:
            self.logger.info(f"Starting symbol sync for {exchange_enum.value}")
            
            # Ensure exchange exists in database
            exchange = await self.exchange_sync.ensure_exchange_exists(exchange_enum)
            
            # Get symbol type for this exchange
            symbol_type = await self.exchange_sync.get_symbol_type_for_exchange(exchange_enum)
            
            # Fetch symbols from exchange API
            exchange_symbols = await self.fetch_exchange_symbols(exchange_enum)
            if not exchange_symbols:
                self.logger.warning(f"No symbols fetched from {exchange_enum.value}")
                return {"added": 0, "updated": 0, "deactivated": 0, "errors": 0}
            
            # Get existing symbols from database
            db_symbols = await self.get_database_symbols(exchange.id)
            
            # Create sets for comparison
            exchange_symbol_keys = set()
            for symbol in exchange_symbols:
                key = (str(symbol.base).upper(), str(symbol.quote).upper(), symbol_type)
                exchange_symbol_keys.add(key)
            
            db_symbol_keys = set(db_symbols.keys())
            
            # Calculate differences
            new_symbols = exchange_symbol_keys - db_symbol_keys
            existing_symbols = exchange_symbol_keys & db_symbol_keys
            removed_symbols = db_symbol_keys - exchange_symbol_keys
            
            stats = {"added": 0, "updated": 0, "deactivated": 0, "errors": 0}
            
            # Add new symbols
            for base, quote, sym_type in new_symbols:
                try:
                    new_symbol = DBSymbol(
                        exchange_id=exchange.id,
                        symbol_base=base,
                        symbol_quote=quote,
                        symbol_type=sym_type,
                        exchange_symbol=f"{base}{quote}"  # Default format
                    )
                    
                    symbol_id = await insert_symbol(new_symbol)
                    self.logger.info(f"Added new symbol: {base}/{quote} (ID: {symbol_id})")
                    stats["added"] += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to add symbol {base}/{quote}: {e}")
                    stats["errors"] += 1
            
            # Update existing symbols (reactivate if needed)
            for symbol_key in existing_symbols:
                try:
                    db_symbol = db_symbols[symbol_key]
                    
                    # Check if symbol needs reactivation or updates
                    updates = {}
                    if not hasattr(db_symbol, 'is_active') or not getattr(db_symbol, 'is_active', True):
                        # Note: is_active was removed from simplified schema
                        # This is for future compatibility if we add it back
                        pass
                    
                    if updates:
                        await update_symbol(db_symbol.id, updates)
                        self.logger.debug(f"Updated symbol: {db_symbol.symbol_base}/{db_symbol.symbol_quote}")
                        stats["updated"] += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to update symbol {symbol_key}: {e}")
                    stats["errors"] += 1
            
            # Mark removed symbols as inactive
            for symbol_key in removed_symbols:
                try:
                    db_symbol = db_symbols[symbol_key]
                    
                    # Note: In simplified schema, we don't have is_active field
                    # For now, we'll log the delisted symbol
                    self.logger.warning(f"Symbol delisted from exchange: {db_symbol.symbol_base}/{db_symbol.symbol_quote}")
                    
                    # TODO: If we add is_active field back, uncomment this:
                    # await update_symbol(db_symbol.id, {"is_active": False})
                    # stats["deactivated"] += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to deactivate symbol {symbol_key}: {e}")
                    stats["errors"] += 1
            
            self.logger.info(
                f"Symbol sync completed for {exchange_enum.value}: "
                f"Added={stats['added']}, Updated={stats['updated']}, "
                f"Deactivated={stats['deactivated']}, Errors={stats['errors']}"
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to sync symbols for {exchange_enum.value}: {e}")
            return {"added": 0, "updated": 0, "deactivated": 0, "errors": 1}
    
    async def sync_all_exchanges(self, exchange_enums: List[ExchangeEnum]) -> Dict[str, Dict[str, int]]:
        """
        Synchronize symbols for all specified exchanges.
        
        Args:
            exchange_enums: List of exchanges to synchronize
            
        Returns:
            Dictionary mapping exchange name -> stats
        """
        try:
            self.logger.info(f"Starting symbol sync for {len(exchange_enums)} exchanges")
            
            all_stats = {}
            total_stats = {"added": 0, "updated": 0, "deactivated": 0, "errors": 0}
            
            for exchange_enum in exchange_enums:
                try:
                    stats = await self.sync_exchange_symbols(exchange_enum)
                    all_stats[exchange_enum.value] = stats
                    
                    # Add to totals
                    for key in total_stats:
                        total_stats[key] += stats[key]
                        
                except Exception as e:
                    self.logger.error(f"Failed to sync {exchange_enum.value}: {e}")
                    all_stats[exchange_enum.value] = {"added": 0, "updated": 0, "deactivated": 0, "errors": 1}
                    total_stats["errors"] += 1
            
            self.logger.info(
                f"Symbol sync completed for all exchanges: "
                f"Total Added={total_stats['added']}, Updated={total_stats['updated']}, "
                f"Deactivated={total_stats['deactivated']}, Errors={total_stats['errors']}"
            )
            
            all_stats["_totals"] = total_stats
            return all_stats
            
        except Exception as e:
            self.logger.error(f"Failed to sync all exchanges: {e}")
            return {"_totals": {"added": 0, "updated": 0, "deactivated": 0, "errors": len(exchange_enums)}}


# Global service instance
_symbol_sync_service = None

def get_symbol_sync_service() -> SymbolSyncService:
    """Get global symbol sync service instance."""
    global _symbol_sync_service
    if _symbol_sync_service is None:
        _symbol_sync_service = SymbolSyncService()
    return _symbol_sync_service