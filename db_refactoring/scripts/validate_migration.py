#!/usr/bin/env python3
"""
Database Migration Validation Script

Comprehensive validation and testing framework for the database refactoring project.
Provides automated testing for each phase of the migration process.
"""

import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import sys
import os

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db.connection import get_db_manager, initialize_database
from db.operations import *
from config.structs import DatabaseConfig

@dataclass
class ValidationResult:
    """Result of a validation test."""
    test_name: str
    passed: bool
    message: str
    duration_ms: float
    details: Optional[Dict[str, Any]] = None

class MigrationValidator:
    """Comprehensive migration validation framework."""
    
    def __init__(self):
        self.results: List[ValidationResult] = []
        self.db_initialized = False
    
    async def initialize(self, db_config: DatabaseConfig):
        """Initialize database connection for validation."""
        try:
            await initialize_database(db_config)
            self.db_initialized = True
            print("✅ Database connection initialized")
        except Exception as e:
            print(f"❌ Database initialization failed: {e}")
            raise
    
    def add_result(self, test_name: str, passed: bool, message: str, 
                   duration_ms: float, details: Optional[Dict] = None):
        """Add a validation result."""
        self.results.append(ValidationResult(
            test_name=test_name,
            passed=passed,
            message=message,
            duration_ms=duration_ms,
            details=details
        ))
    
    async def run_test(self, test_name: str, test_func, *args, **kwargs):
        """Run a single validation test with timing."""
        start_time = time.perf_counter()
        
        try:
            result = await test_func(*args, **kwargs)
            end_time = time.perf_counter()
            duration = (end_time - start_time) * 1000  # Convert to milliseconds
            
            if isinstance(result, tuple):
                passed, message, details = result
            else:
                passed, message, details = result, "Test completed", None
            
            self.add_result(test_name, passed, message, duration, details)
            
        except Exception as e:
            end_time = time.perf_counter()
            duration = (end_time - start_time) * 1000
            self.add_result(test_name, False, f"Test failed: {e}", duration)
    
    def print_results(self):
        """Print comprehensive validation results."""
        print("\n" + "=" * 80)
        print("DATABASE MIGRATION VALIDATION RESULTS")
        print("=" * 80)
        
        passed_tests = sum(1 for r in self.results if r.passed)
        total_tests = len(self.results)
        
        print(f"Overall Results: {passed_tests}/{total_tests} tests passed")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        # Group results by phase
        phase_results = {}
        for result in self.results:
            phase = result.test_name.split('_')[0] if '_' in result.test_name else 'General'
            if phase not in phase_results:
                phase_results[phase] = []
            phase_results[phase].append(result)
        
        for phase, results in phase_results.items():
            print(f"\n📊 {phase.upper()} PHASE RESULTS:")
            print("-" * 40)
            
            for result in results:
                status = "✅" if result.passed else "❌"
                print(f"{status} {result.test_name}: {result.message} ({result.duration_ms:.2f}ms)")
                
                if result.details:
                    for key, value in result.details.items():
                        print(f"    {key}: {value}")
        
        # Performance summary
        print(f"\n⚡ PERFORMANCE SUMMARY:")
        print("-" * 40)
        slow_tests = [r for r in self.results if r.duration_ms > 1000]  # >1 second
        fast_tests = [r for r in self.results if r.duration_ms < 10]    # <10ms
        
        print(f"Fast tests (<10ms): {len(fast_tests)}")
        print(f"Slow tests (>1s): {len(slow_tests)}")
        
        if slow_tests:
            print("\nSlow tests requiring optimization:")
            for test in slow_tests:
                print(f"  ⚠️  {test.test_name}: {test.duration_ms:.2f}ms")
        
        # Final status
        print("\n" + "=" * 80)
        if passed_tests == total_tests:
            print("🎉 ALL VALIDATION TESTS PASSED!")
        else:
            print(f"⚠️  {total_tests - passed_tests} TESTS FAILED - REVIEW REQUIRED")
        print("=" * 80)
    
    def export_results(self, filename: str):
        """Export results to JSON for analysis."""
        export_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'total_tests': len(self.results),
                'passed_tests': sum(1 for r in self.results if r.passed),
                'average_duration': sum(r.duration_ms for r in self.results) / len(self.results) if self.results else 0
            },
            'results': [
                {
                    'test_name': r.test_name,
                    'passed': r.passed,
                    'message': r.message,
                    'duration_ms': r.duration_ms,
                    'details': r.details
                }
                for r in self.results
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"📄 Results exported to {filename}")

# Phase 1 Validation Tests

async def validate_exchange_table_exists():
    """Test P1.1: Exchange table exists and is accessible."""
    db = get_db_manager()
    
    # Check table exists
    query = """
        SELECT COUNT(*) as table_count
        FROM information_schema.tables 
        WHERE table_name = 'exchanges'
    """
    
    result = await db.fetchval(query)
    
    if result == 1:
        # Check table has data
        count_query = "SELECT COUNT(*) FROM exchanges"
        exchange_count = await db.fetchval(count_query)
        
        return True, f"Exchange table exists with {exchange_count} records", {
            'table_exists': True,
            'record_count': exchange_count
        }
    else:
        return False, "Exchange table does not exist", {'table_exists': False}

async def validate_exchange_indexes():
    """Test P1.1: Exchange table indexes are created."""
    db = get_db_manager()
    
    expected_indexes = [
        'idx_exchanges_enum_value',
        'idx_exchanges_active', 
        'idx_exchanges_market_type'
    ]
    
    query = """
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'exchanges' AND indexname = ANY($1)
    """
    
    existing_indexes = await db.fetch(query, expected_indexes)
    existing_names = [row['indexname'] for row in existing_indexes]
    
    missing_indexes = set(expected_indexes) - set(existing_names)
    
    if not missing_indexes:
        return True, f"All {len(expected_indexes)} indexes created", {
            'expected_indexes': expected_indexes,
            'existing_indexes': existing_names
        }
    else:
        return False, f"Missing indexes: {list(missing_indexes)}", {
            'missing_indexes': list(missing_indexes)
        }

async def validate_exchange_enum_mapping():
    """Test P1.1: All ExchangeEnum values are in database."""
    from exchanges.structs.enums import ExchangeEnum
    
    missing_enums = []
    found_enums = []
    
    for exchange_enum in ExchangeEnum:
        exchange = await get_exchange_by_enum(exchange_enum)
        if exchange:
            found_enums.append(exchange_enum.value)
        else:
            missing_enums.append(exchange_enum.value)
    
    if not missing_enums:
        return True, f"All {len(found_enums)} ExchangeEnum values mapped", {
            'mapped_enums': [str(e) for e in found_enums],
            'total_enums': len(found_enums)
        }
    else:
        return False, f"Missing enum mappings: {missing_enums}", {
            'missing_enums': [str(e) for e in missing_enums],
            'found_enums': [str(e) for e in found_enums]
        }

async def validate_exchange_lookup_performance():
    """Test P1.1: Exchange lookup performance meets HFT targets."""
    from exchanges.structs.enums import ExchangeEnum
    
    # Warm up
    await get_exchange_by_enum(ExchangeEnum.MEXC)
    
    # Performance test
    iterations = 1000
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        await get_exchange_by_enum(ExchangeEnum.MEXC)
    
    end_time = time.perf_counter()
    avg_time_ms = ((end_time - start_time) / iterations) * 1000
    
    target_ms = 1.0  # HFT target: <1ms
    
    if avg_time_ms < target_ms:
        return True, f"Performance target met: {avg_time_ms:.3f}ms avg", {
            'average_time_ms': avg_time_ms,
            'target_ms': target_ms,
            'iterations': iterations
        }
    else:
        return False, f"Performance target missed: {avg_time_ms:.3f}ms avg (target: {target_ms}ms)", {
            'average_time_ms': avg_time_ms,
            'target_ms': target_ms,
            'performance_ratio': avg_time_ms / target_ms
        }

async def validate_exchange_crud_operations():
    """Test P1.1: Exchange CRUD operations work correctly."""
    
    # Test data
    test_exchange = Exchange(
        name="VALIDATION_TEST_EXCHANGE",
        enum_value="VALIDATION_TEST",
        display_name="Validation Test Exchange",
        market_type="SPOT",
        rate_limit_requests_per_second=100
    )
    
    try:
        # Test INSERT
        exchange_id = await insert_exchange(test_exchange)
        
        # Test SELECT
        retrieved = await get_exchange_by_id(exchange_id)
        if not retrieved or retrieved.name != test_exchange.name:
            return False, "Insert/Select failed - retrieved data mismatch", None
        
        # Test UPDATE
        update_success = await update_exchange(exchange_id, {
            'display_name': 'Updated Test Exchange',
            'rate_limit_requests_per_second': 200
        })
        
        if not update_success:
            return False, "Update operation failed", None
        
        # Verify update
        updated = await get_exchange_by_id(exchange_id)
        if updated.display_name != 'Updated Test Exchange':
            return False, "Update verification failed", None
        
        # Test DEACTIVATE (soft delete)
        deactivate_success = await deactivate_exchange(exchange_id)
        if not deactivate_success:
            return False, "Deactivation failed", None
        
        # Clean up - remove test record
        db = get_db_manager()
        await db.execute("DELETE FROM exchanges WHERE id = $1", exchange_id)
        
        return True, "All CRUD operations successful", {
            'test_exchange_id': exchange_id,
            'operations_tested': ['INSERT', 'SELECT', 'UPDATE', 'DEACTIVATE']
        }
        
    except Exception as e:
        # Clean up on error
        try:
            db = get_db_manager()
            await db.execute("DELETE FROM exchanges WHERE name = $1", test_exchange.name)
        except:
            pass
        
        return False, f"CRUD operation failed: {e}", None

# Phase 2 Validation Tests (for future use)

async def validate_symbol_table_migration():
    """Test P1.2: Symbol table creation and population."""
    # TODO: Implement when P1.2 is complete
    return True, "Symbol validation not yet implemented", None

async def validate_normalized_data_migration():
    """Test P2.1: Data migration accuracy."""
    # TODO: Implement when P2.1 is complete  
    return True, "Data migration validation not yet implemented", None

# Cache Validation Tests

async def validate_cache_infrastructure():
    """Test P1.3: Cache infrastructure performance."""
    # TODO: Implement when P1.3 is complete
    return True, "Cache validation not yet implemented", None

# Main Validation Runner

async def run_phase1_validation():
    """Run all Phase 1 validation tests."""
    
    # Default database config for testing
    db_config = DatabaseConfig(
        host="localhost",
        port=5432,
        database="cex_arbitrage",
        username="postgres",
        password=os.getenv("DB_PASSWORD", ""),
        min_pool_size=1,
        max_pool_size=5
    )
    
    validator = MigrationValidator()
    
    try:
        await validator.initialize(db_config)
        
        print("🚀 Starting Phase 1 Validation Tests")
        print("=" * 50)
        
        # P1.1 Exchange Table Tests
        await validator.run_test("P1.1_table_exists", validate_exchange_table_exists)
        await validator.run_test("P1.1_indexes_created", validate_exchange_indexes)
        await validator.run_test("P1.1_enum_mapping", validate_exchange_enum_mapping)
        await validator.run_test("P1.1_lookup_performance", validate_exchange_lookup_performance)
        await validator.run_test("P1.1_crud_operations", validate_exchange_crud_operations)
        
        # Future tests (will be enabled as phases complete)
        # await validator.run_test("P1.2_symbol_table", validate_symbol_table_migration)
        # await validator.run_test("P1.3_cache_infrastructure", validate_cache_infrastructure)
        
        # Print results
        validator.print_results()
        
        # Export results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        validator.export_results(f"validation_results_{timestamp}.json")
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False
    
    # Return overall success
    passed = sum(1 for r in validator.results if r.passed)
    total = len(validator.results)
    return passed == total

if __name__ == "__main__":
    """
    Usage:
    python validate_migration.py                    # Run Phase 1 validation
    python validate_migration.py --phase 2         # Run Phase 2 validation (future)
    python validate_migration.py --all             # Run all available validations
    """
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Migration Validation")
    parser.add_argument("--phase", type=int, default=1, help="Phase to validate (1, 2, 3, 4)")
    parser.add_argument("--all", action="store_true", help="Run all available validations")
    
    args = parser.parse_args()
    
    if args.phase == 1 or args.all:
        success = asyncio.run(run_phase1_validation())
        sys.exit(0 if success else 1)
    else:
        print(f"Phase {args.phase} validation not yet implemented")
        sys.exit(1)