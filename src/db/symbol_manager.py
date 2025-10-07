"""
Symbol Manager for Normalized Database Schema

Handles symbol ID management and lookups for the normalized database schema
where symbols are stored in a separate table with foreign key relationships.
"""

import logging
from typing import Dict, Optional, Tuple
from exchanges.structs.common import Symbol
from .connection import get_db_manager

logger = logging.getLogger(__name__)

# Cache for symbol ID lookups to avoid repeated database queries
_symbol_id_cache: Dict[Tuple[str, str, str], int] = {}  # (exchange, base, quote) -> symbol_id
_exchange_id_cache: Dict[str, int] = {}  # exchange_name -> exchange_id


async def get_exchange_id(exchange_name: str) -> Optional[int]:
    """
    Get exchange ID from the exchanges table.
    
    Args:
        exchange_name: Exchange name (e.g., "MEXC_SPOT", "GATEIO_SPOT", "GATEIO_FUTURES")
        
    Returns:
        Exchange ID or None if not found
    """
    # Check cache first
    if exchange_name in _exchange_id_cache:
        return _exchange_id_cache[exchange_name]
    
    db = get_db_manager()
    try:
        query = "SELECT id FROM exchanges WHERE enum_value = $1"
        exchange_id = await db.fetchval(query, exchange_name.upper())
        
        if exchange_id:
            _exchange_id_cache[exchange_name] = exchange_id
        
        return exchange_id
    except Exception as e:
        logger.error(f"Failed to get exchange ID for {exchange_name}: {e}")
        return None


async def get_symbol_id(exchange_name: str, symbol: Symbol) -> Optional[int]:
    """
    Get symbol ID from the symbols table, creating if it doesn't exist.
    
    Args:
        exchange_name: Exchange name (e.g., "MEXC_SPOT", "GATEIO_SPOT", "GATEIO_FUTURES") 
        symbol: Symbol object with base and quote
        
    Returns:
        Symbol ID or None if failed
    """
    cache_key = (exchange_name.upper(), str(symbol.base).upper(), str(symbol.quote).upper())
    
    # Check cache first
    if cache_key in _symbol_id_cache:
        return _symbol_id_cache[cache_key]
    
    # Get exchange ID first
    exchange_id = await get_exchange_id(exchange_name)
    if exchange_id is None:
        logger.error(f"Exchange {exchange_name} not found in database")
        return None
    
    # Determine symbol type based on exchange name
    symbol_type = 'FUTURES' if 'FUTURES' in exchange_name.upper() else 'SPOT'
    
    db = get_db_manager()
    
    try:
        # Try to find existing symbol
        query = """
            SELECT id FROM symbols 
            WHERE exchange_id = $1 
            AND symbol_base = $2 
            AND symbol_quote = $3
            AND symbol_type = $4
        """
        
        symbol_id = await db.fetchval(
            query,
            exchange_id,
            str(symbol.base).upper(),
            str(symbol.quote).upper(),
            symbol_type
        )
        
        if symbol_id:
            # Cache the result
            _symbol_id_cache[cache_key] = symbol_id
            return symbol_id
        
        # Symbol doesn't exist, check if it exists with the exchange_symbol format
        exchange_symbol = f"{symbol.base}{symbol.quote}"
        
        # Try to find by exchange_symbol instead (in case it was inserted differently)
        alt_query = """
            SELECT id FROM symbols 
            WHERE exchange_id = $1 
            AND exchange_symbol = $2
            AND symbol_type = $3
        """
        
        symbol_id = await db.fetchval(
            alt_query,
            exchange_id,
            exchange_symbol,
            symbol_type
        )
        
        if symbol_id:
            # Cache the result
            _symbol_id_cache[cache_key] = symbol_id
            logger.debug(f"Found {symbol_type} symbol {symbol.base}/{symbol.quote} for {exchange_name} by exchange_symbol with ID {symbol_id}")
            return symbol_id
        
        # Symbol truly doesn't exist, create it
        insert_query = """
            INSERT INTO symbols (
                exchange_id, symbol_base, symbol_quote, 
                symbol_type, exchange_symbol, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        
        try:
            symbol_id = await db.fetchval(
                insert_query,
                exchange_id,
                str(symbol.base).upper(),
                str(symbol.quote).upper(),
                symbol_type,
                exchange_symbol,
                True
            )
        except Exception as insert_error:
            # If we get a duplicate key error, try to find the existing symbol one more time
            if "duplicate key value violates unique constraint" in str(insert_error):
                logger.warning(f"Symbol {symbol.base}/{symbol.quote} already exists, attempting to retrieve ID")
                
                # Try both lookup methods
                for query, params in [
                    (query, (exchange_id, str(symbol.base).upper(), str(symbol.quote).upper(), symbol_type)),
                    (alt_query, (exchange_id, exchange_symbol, symbol_type))
                ]:
                    existing_id = await db.fetchval(query, *params)
                    if existing_id:
                        _symbol_id_cache[cache_key] = existing_id
                        logger.debug(f"Retrieved existing {symbol_type} symbol {symbol.base}/{symbol.quote} with ID {existing_id}")
                        return existing_id
                
                logger.error(f"Could not retrieve existing symbol after duplicate key error: {symbol.base}/{symbol.quote}")
                return None
            else:
                raise insert_error
        
        if symbol_id:
            # Cache the newly created symbol
            _symbol_id_cache[cache_key] = symbol_id
            logger.debug(f"Created/updated {symbol_type} symbol {symbol.base}/{symbol.quote} for {exchange_name} with ID {symbol_id}")
            return symbol_id
        
        logger.error(f"Failed to create {symbol_type} symbol {symbol.base}/{symbol.quote} for {exchange_name}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get/create symbol ID for {symbol.base}/{symbol.quote} on {exchange_name}: {e}")
        return None


async def get_symbol_details(symbol_id: int) -> Optional[Tuple[str, str, str]]:
    """
    Get symbol details from symbol ID.
    
    Args:
        symbol_id: Symbol ID from database
        
    Returns:
        Tuple of (exchange_name, symbol_base, symbol_quote) or None if not found
    """
    db = get_db_manager()
    
    try:
        query = """
            SELECT e.enum_value, s.symbol_base, s.symbol_quote
            FROM symbols s
            JOIN exchanges e ON s.exchange_id = e.id
            WHERE s.id = $1
        """
        
        result = await db.fetchrow(query, symbol_id)
        
        if result:
            return (result['enum_value'], result['symbol_base'], result['symbol_quote'])
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get symbol details for ID {symbol_id}: {e}")
        return None


async def clear_symbol_cache():
    """Clear the symbol ID cache (useful for tests or when data changes)."""
    global _symbol_id_cache, _exchange_id_cache
    _symbol_id_cache.clear()
    _exchange_id_cache.clear()
    logger.debug("Symbol cache cleared")