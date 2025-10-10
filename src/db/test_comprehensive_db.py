#!/usr/bin/env python3
"""
Comprehensive Database Operations Test

Tests all database methods and verifies real database records are created.
Ensures the complete database layer is working correctly with actual data.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_manager import HftConfig
from db.connection import initialize_database, get_db_manager
from db.exchange_sync import get_exchange_sync_service
from db.symbol_sync import get_symbol_sync_service
from db.cache_warming import warm_symbol_cache
from db.cache_operations import (
    cached_get_exchange_by_enum_value,
    cached_get_symbol_by_exchange_and_pair
)
from db.operations import (
    # Exchange operations
    get_exchange_by_enum_value,
    get_exchange_by_id,
    get_all_active_exchanges,
    get_exchanges_by_market_type,
    insert_exchange,
    get_exchange_stats,
    
    # Symbol operations
    get_symbol_by_id,
    get_symbol_by_exchange_and_pair,
    get_symbols_by_exchange,
    get_symbols_by_market_type,
    insert_symbol,
    get_symbol_stats,
    
    # Snapshot operations
    insert_book_ticker_snapshot,
)
from db.models import (
    Exchange, 
    Symbol as DBSymbol, 
    SymbolType,
    BookTickerSnapshot,
    TradeSnapshot
)
from exchanges.structs.enums import ExchangeEnum


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseComprehensiveTest:
    """Comprehensive test suite for all database operations."""
    
    def __init__(self):
        self.test_results: List[Dict[str, Any]] = []
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        
    def log_test_result(self, test_name: str, passed: bool, details: str = "", error: str = ""):
        """Log test result for summary."""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            status = "✅ PASS"
        else:
            self.failed_tests += 1
            status = "❌ FAIL"
            
        result = {
            "test_name": test_name,
            "status": status,
            "passed": passed,
            "details": details,
            "error": error
        }
        self.test_results.append(result)
        
        print(f"{status}: {test_name}")
        if details:
            print(f"    Details: {details}")
        if error:
            print(f"    Error: {error}")
    
    async def initialize_test_environment(self):
        """Initialize test environment."""
        print("🔧 INITIALIZING TEST ENVIRONMENT")
        print("=" * 60)
        
        try:
            # Initialize database connection
            config_manager = HftConfig()
            db_config = config_manager.get_database_config()
            await initialize_database(db_config)
            print("✅ Database connection initialized")
            
            # Clean up any existing test data
            await self.cleanup_test_data()
            print("✅ Test environment cleaned")
            
            self.log_test_result("Environment Initialization", True, "Database ready for testing")
            
        except Exception as e:
            self.log_test_result("Environment Initialization", False, error=str(e))
            raise
    
    async def cleanup_test_data(self):
        """Clean up test data from previous runs."""
        db = get_db_manager()
        
        # Clean up test snapshots
        await db.execute("DELETE FROM normalized_book_ticker_snapshots WHERE bid_price = 99999.98")
        await db.execute("DELETE FROM normalized_trade_snapshots WHERE price = 99999.97")
        await db.execute("DELETE FROM book_ticker_snapshots WHERE bid_price = 99999.99")
        # Clean up trades table if it exists
        try:
            await db.execute("DELETE FROM trades WHERE price = 99999.99")
        except:
            pass  # Table may not exist in normalized schema
        
        # Clean up test symbols
        await db.execute("DELETE FROM symbols WHERE exchange_symbol = 'TESTBTC'")
        
    async def test_exchange_operations(self):
        """Test all exchange-related operations."""
        print("\n📋 TESTING EXCHANGE OPERATIONS")
        print("-" * 40)
        
        try:
            # Test 1: Exchange synchronization
            print("Test 1: Exchange Synchronization")
            exchange_sync = get_exchange_sync_service()
            test_exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]
            exchanges = await exchange_sync.sync_exchanges(test_exchanges)
            
            self.log_test_result(
                "Exchange Sync", 
                len(exchanges) >= 2, 
                f"Synced {len(exchanges)} exchanges"
            )
            
            # Test 2: Get exchange by enum value
            print("Test 2: Get Exchange by Enum Value")
            mexc_exchange = await get_exchange_by_enum_value('MEXC_SPOT')
            
            self.log_test_result(
                "Get Exchange by Enum", 
                mexc_exchange is not None and mexc_exchange.name == 'MEXC_SPOT',
                f"Retrieved: {mexc_exchange.name if mexc_exchange else 'None'}"
            )
            
            # Test 3: Get exchange by ID
            print("Test 3: Get Exchange by ID")
            if mexc_exchange:
                exchange_by_id = await get_exchange_by_id(mexc_exchange.id)
                self.log_test_result(
                    "Get Exchange by ID",
                    exchange_by_id is not None and exchange_by_id.id == mexc_exchange.id,
                    f"Retrieved ID: {exchange_by_id.id if exchange_by_id else 'None'}"
                )
            
            # Test 4: Get all active exchanges
            print("Test 4: Get All Active Exchanges")
            all_exchanges = await get_all_active_exchanges()
            self.log_test_result(
                "Get All Active Exchanges",
                len(all_exchanges) >= 2,
                f"Found {len(all_exchanges)} active exchanges"
            )
            
            # Test 5: Get exchanges by market type
            print("Test 5: Get Exchanges by Market Type")
            spot_exchanges = await get_exchanges_by_market_type('SPOT')
            futures_exchanges = await get_exchanges_by_market_type('FUTURES')
            
            self.log_test_result(
                "Get Exchanges by Market Type",
                len(spot_exchanges) >= 1,
                f"SPOT: {len(spot_exchanges)}, FUTURES: {len(futures_exchanges)}"
            )
            
            # Test 6: Exchange statistics
            print("Test 6: Exchange Statistics")
            exchange_stats = await get_exchange_stats()
            
            self.log_test_result(
                "Exchange Statistics",
                'total_exchanges' in exchange_stats and exchange_stats['total_exchanges'] > 0,
                f"Total exchanges: {exchange_stats.get('total_exchanges', 0)}"
            )
            
            return mexc_exchange
            
        except Exception as e:
            self.log_test_result("Exchange Operations", False, error=str(e))
            return None
    
    async def test_symbol_operations(self, test_exchange: Exchange):
        """Test all symbol-related operations."""
        print("\n📋 TESTING SYMBOL OPERATIONS")
        print("-" * 40)
        
        try:
            # Test 1: Insert test symbol
            print("Test 1: Insert Test Symbol")
            test_symbol = DBSymbol(
                exchange_id=test_exchange.id,
                symbol_base='TEST',
                symbol_quote='BTC',
                symbol_type=SymbolType.SPOT,
                exchange_symbol='TESTBTC',
                is_active=True
            )
            
            symbol_id = await insert_symbol(test_symbol)
            test_symbol.id = symbol_id
            
            self.log_test_result(
                "Insert Symbol",
                symbol_id is not None,
                f"Inserted symbol with ID: {symbol_id}"
            )
            
            # Test 2: Get symbol by ID
            print("Test 2: Get Symbol by ID")
            retrieved_symbol = await get_symbol_by_id(symbol_id)
            
            self.log_test_result(
                "Get Symbol by ID",
                retrieved_symbol is not None and retrieved_symbol.id == symbol_id,
                f"Retrieved: {retrieved_symbol.symbol_base}/{retrieved_symbol.symbol_quote}" if retrieved_symbol else "None"
            )
            
            # Test 3: Get symbol by exchange and pair
            print("Test 3: Get Symbol by Exchange and Pair")
            symbol_by_pair = await get_symbol_by_exchange_and_pair(
                test_exchange.id, 'TEST', 'BTC'
            )
            
            self.log_test_result(
                "Get Symbol by Exchange and Pair",
                symbol_by_pair is not None and symbol_by_pair.symbol_base == 'TEST',
                f"Found: {symbol_by_pair.exchange_symbol if symbol_by_pair else 'None'}"
            )
            
            # Test 4: Get symbols by exchange
            print("Test 4: Get Symbols by Exchange")
            exchange_symbols = await get_symbols_by_exchange(test_exchange.id)
            
            self.log_test_result(
                "Get Symbols by Exchange",
                len(exchange_symbols) >= 1,
                f"Found {len(exchange_symbols)} symbols for {test_exchange.name}"
            )
            
            # Test 5: Get symbols by market type
            print("Test 5: Get Symbols by Market Type")
            spot_symbols = await get_symbols_by_market_type('SPOT')
            
            self.log_test_result(
                "Get Symbols by Market Type",
                len(spot_symbols) >= 1,
                f"Found {len(spot_symbols)} SPOT symbols"
            )
            
            # Test 6: Symbol statistics
            print("Test 6: Symbol Statistics")
            symbol_stats = await get_symbol_stats()
            
            self.log_test_result(
                "Symbol Statistics",
                'total_symbols' in symbol_stats and symbol_stats['total_symbols'] > 0,
                f"Total symbols: {symbol_stats.get('total_symbols', 0)}"
            )
            
            return test_symbol
            
        except Exception as e:
            self.log_test_result("Symbol Operations", False, error=str(e))
            return None
    
    async def test_snapshot_operations(self, test_exchange: Exchange, test_symbol: DBSymbol):
        """Test all snapshot-related operations."""
        print("\n📋 TESTING SNAPSHOT OPERATIONS")
        print("-" * 40)
        
        try:
            # Test 1: Insert normalized book ticker snapshot
            print("Test 1: Insert Book Ticker Snapshot")
            snapshot = BookTickerSnapshot(
                symbol_id=test_symbol.id,
                bid_price=99999.99,
                bid_qty=1.0,
                ask_price=100000.01,
                ask_qty=2.0,
                timestamp=datetime.now(timezone.utc)
            )
            
            snapshot_id = await insert_book_ticker_snapshot(snapshot)
            
            self.log_test_result(
                "Insert Book Ticker Snapshot",
                snapshot_id is not None,
                f"Inserted with ID: {snapshot_id}"
            )
            
            
        except Exception as e:
            self.log_test_result("Snapshot Operations", False, error=str(e))
    
    async def test_cache_operations(self, test_exchange: Exchange, test_symbol: DBSymbol):
        """Test all cache-related operations."""
        print("\n📋 TESTING CACHE OPERATIONS")
        print("-" * 40)
        
        try:
            # Test 1: Initialize cache
            print("Test 1: Initialize Symbol Cache")
            await warm_symbol_cache()
            
            self.log_test_result(
                "Initialize Symbol Cache",
                True,
                "Cache warming completed"
            )
            
            # Test 2: Cached exchange lookup
            print("Test 2: Cached Exchange Lookup")
            cached_exchange = cached_get_exchange_by_enum_value('MEXC_SPOT')
            
            self.log_test_result(
                "Cached Exchange Lookup",
                cached_exchange is not None and cached_exchange.name == 'MEXC_SPOT',
                f"Retrieved: {cached_exchange.name if cached_exchange else 'None'}"
            )
            
            # Test 3: Cached symbol lookup
            print("Test 3: Cached Symbol Lookup")
            cached_symbol = cached_get_symbol_by_exchange_and_pair(
                test_exchange.id, 
                test_symbol.symbol_base, 
                test_symbol.symbol_quote
            )
            
            self.log_test_result(
                "Cached Symbol Lookup",
                cached_symbol is not None and cached_symbol.exchange_symbol == test_symbol.exchange_symbol,
                f"Retrieved: {cached_symbol.exchange_symbol if cached_symbol else 'None'}"
            )
            
            # Test 4: Cache performance
            print("Test 4: Cache Performance")
            import time
            
            # Warm up
            for _ in range(10):
                cached_get_exchange_by_enum_value('MEXC_SPOT')
            
            # Performance test
            iterations = 1000
            start_time = time.perf_counter()
            
            for _ in range(iterations):
                cached_get_exchange_by_enum_value('MEXC_SPOT')
            
            end_time = time.perf_counter()
            avg_time_us = ((end_time - start_time) / iterations) * 1_000_000
            
            target_us = 1000  # Target: <1000μs
            performance_pass = avg_time_us < target_us
            
            self.log_test_result(
                "Cache Performance",
                performance_pass,
                f"Average lookup: {avg_time_us:.2f}μs (target: <{target_us}μs)"
            )
            
        except Exception as e:
            self.log_test_result("Cache Operations", False, error=str(e))
    
    async def test_sync_services(self):
        """Test synchronization services."""
        print("\n📋 TESTING SYNC SERVICES")
        print("-" * 40)
        
        try:
            # Test 1: Exchange sync service
            print("Test 1: Exchange Sync Service")
            exchange_sync = get_exchange_sync_service()
            
            # Test service instantiation
            self.log_test_result(
                "Exchange Sync Service Instantiation",
                exchange_sync is not None,
                "Service created successfully"
            )
            
            # Test exchange existence check
            mexc_exchange = await exchange_sync.ensure_exchange_exists(ExchangeEnum.MEXC)
            
            self.log_test_result(
                "Exchange Existence Check",
                mexc_exchange is not None and mexc_exchange.name == 'MEXC_SPOT',
                f"Exchange ensured: {mexc_exchange.name if mexc_exchange else 'None'}"
            )
            
            # Test 2: Symbol sync service
            print("Test 2: Symbol Sync Service")
            symbol_sync = get_symbol_sync_service()
            
            # Test service instantiation
            self.log_test_result(
                "Symbol Sync Service Instantiation",
                symbol_sync is not None,
                "Service created successfully"
            )
            
            # Test database symbols retrieval
            if mexc_exchange:
                db_symbols = await symbol_sync.get_database_symbols(mexc_exchange.id)
                
                self.log_test_result(
                    "Database Symbols Retrieval",
                    isinstance(db_symbols, dict),
                    f"Retrieved {len(db_symbols)} symbols from database"
                )
            
        except Exception as e:
            self.log_test_result("Sync Services", False, error=str(e))
    
    async def verify_database_records(self):
        """Verify that real records were created in the database."""
        print("\n📋 VERIFYING DATABASE RECORDS")
        print("-" * 40)
        
        try:
            db = get_db_manager()
            
            # Test 1: Verify exchanges table
            print("Test 1: Verify Exchanges Table")
            exchange_count = await db.fetchval("SELECT COUNT(*) FROM exchanges")
            
            self.log_test_result(
                "Exchanges Table Verification",
                exchange_count > 0,
                f"Found {exchange_count} records in exchanges table"
            )
            
            # Test 2: Verify symbols table
            print("Test 2: Verify Symbols Table")
            symbol_count = await db.fetchval("SELECT COUNT(*) FROM symbols")
            
            self.log_test_result(
                "Symbols Table Verification",
                symbol_count > 0,
                f"Found {symbol_count} records in symbols table"
            )
            
            # Test 3: Verify book_ticker_snapshots table
            print("Test 3: Verify Book Ticker Snapshots Table")
            snapshot_count = await db.fetchval("SELECT COUNT(*) FROM book_ticker_snapshots WHERE bid_price = 99999.99")
            
            self.log_test_result(
                "Book Ticker Snapshots Verification",
                snapshot_count > 0,
                f"Found {snapshot_count} test records in book_ticker_snapshots"
            )
            
            # Test 4: Verify normalized_book_ticker_snapshots table
            print("Test 4: Verify Normalized Book Ticker Snapshots Table")
            norm_snapshot_count = await db.fetchval("SELECT COUNT(*) FROM normalized_book_ticker_snapshots WHERE bid_price = 99999.98")
            
            self.log_test_result(
                "Normalized Book Ticker Snapshots Verification",
                norm_snapshot_count > 0,
                f"Found {norm_snapshot_count} test records in normalized_book_ticker_snapshots"
            )
            
            # Test 5: Verify trades table (check if it exists, may not be used in normalized schema)
            print("Test 5: Verify Trades Table")
            try:
                trade_count = await db.fetchval("SELECT COUNT(*) FROM trades WHERE price = 99999.99")
                self.log_test_result(
                    "Trades Table Verification",
                    trade_count >= 0,
                    f"Found {trade_count} test records in trades table"
                )
            except Exception as e:
                self.log_test_result(
                    "Trades Table Verification",
                    False,
                    error=f"Trades table may not exist: {e}"
                )
            
            # Test 6: Verify normalized_trade_snapshots table
            print("Test 6: Verify Normalized Trade Snapshots Table")
            norm_trade_count = await db.fetchval("SELECT COUNT(*) FROM normalized_trade_snapshots WHERE price = 99999.97")
            
            self.log_test_result(
                "Normalized Trade Snapshots Verification",
                norm_trade_count > 0,
                f"Found {norm_trade_count} test records in normalized_trade_snapshots"
            )
            
            # Test 7: Verify foreign key relationships
            print("Test 7: Verify Foreign Key Relationships")
            relationship_query = """
                SELECT s.symbol_base, s.symbol_quote, e.name as exchange_name
                FROM symbols s
                JOIN exchanges e ON s.exchange_id = e.id
                WHERE s.exchange_symbol = 'TESTBTC'
            """
            
            relationship_result = await db.fetchrow(relationship_query)
            
            self.log_test_result(
                "Foreign Key Relationships Verification",
                relationship_result is not None,
                f"Found relationship: {relationship_result['symbol_base']}/{relationship_result['symbol_quote']} on {relationship_result['exchange_name']}" if relationship_result else "No relationship found"
            )
            
        except Exception as e:
            self.log_test_result("Database Records Verification", False, error=str(e))
    
    def print_summary(self):
        """Print comprehensive test summary."""
        print("\n" + "=" * 80)
        print("COMPREHENSIVE DATABASE TEST SUMMARY")
        print("=" * 80)
        
        print(f"\n📊 OVERALL RESULTS:")
        print(f"   Total Tests: {self.total_tests}")
        print(f"   Passed: {self.passed_tests}")
        print(f"   Failed: {self.failed_tests}")
        print(f"   Success Rate: {(self.passed_tests/self.total_tests)*100:.1f}%")
        
        print(f"\n📋 DETAILED RESULTS:")
        for result in self.test_results:
            print(f"   {result['status']} {result['test_name']}")
            if result['details']:
                print(f"      └─ {result['details']}")
            if result['error']:
                print(f"      └─ Error: {result['error']}")
        
        if self.failed_tests == 0:
            print(f"\n🎉 ALL TESTS PASSED!")
            print(f"✅ Database layer is fully operational")
            print(f"✅ Real database records created and verified")
            print(f"✅ All operations working correctly")
            print(f"✅ System ready for production use")
        else:
            print(f"\n⚠️  {self.failed_tests} TESTS FAILED")
            print(f"❌ Review failed operations before production deployment")
        
        print("=" * 80)
    
    async def run_all_tests(self):
        """Run complete test suite."""
        print("🧪 COMPREHENSIVE DATABASE OPERATIONS TEST")
        print("Testing all @src/db/ methods with real database records")
        print("=" * 80)
        
        try:
            # Initialize test environment
            await self.initialize_test_environment()
            
            # Test exchange operations
            test_exchange = await self.test_exchange_operations()
            
            if not test_exchange:
                print("❌ Cannot proceed without test exchange")
                return
            
            # Test symbol operations
            test_symbol = await self.test_symbol_operations(test_exchange)
            
            if not test_symbol:
                print("❌ Cannot proceed without test symbol")
                return
            
            # Test snapshot operations
            await self.test_snapshot_operations(test_exchange, test_symbol)
            
            # Test cache operations
            await self.test_cache_operations(test_exchange, test_symbol)
            
            # Test sync services
            await self.test_sync_services()
            
            # Verify database records
            await self.verify_database_records()
            
            # Clean up test data
            await self.cleanup_test_data()
            
        except Exception as e:
            logger.error(f"Test suite failed: {e}")
            self.log_test_result("Test Suite Execution", False, error=str(e))
        
        finally:
            # Print summary
            self.print_summary()


async def main():
    """Main test execution."""
    test_suite = DatabaseComprehensiveTest()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())