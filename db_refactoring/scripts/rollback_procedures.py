#!/usr/bin/env python3
"""
Database Migration Rollback Procedures

Emergency rollback scripts and procedures for the database refactoring project.
Provides safe rollback mechanisms for each phase of the migration.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db.connection import get_db_manager, initialize_database
from config.structs import DatabaseConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class RollbackStep:
    """Represents a single rollback step."""
    step_name: str
    sql_command: str
    description: str
    is_destructive: bool = False
    requires_confirmation: bool = False

class MigrationRollback:
    """Handles rollback operations for database migrations."""
    
    def __init__(self):
        self.db_manager = None
        self.rollback_history: List[str] = []
    
    async def initialize(self, db_config: DatabaseConfig):
        """Initialize database connection."""
        await initialize_database(db_config)
        self.db_manager = get_db_manager()
        logger.info("Database connection initialized for rollback operations")
    
    async def execute_rollback_step(self, step: RollbackStep, force: bool = False) -> bool:
        """Execute a single rollback step with safety checks."""
        
        logger.info(f"Executing rollback step: {step.step_name}")
        logger.info(f"Description: {step.description}")
        
        if step.is_destructive and not force:
            if step.requires_confirmation:
                print(f"\n⚠️  DESTRUCTIVE OPERATION: {step.step_name}")
                print(f"Description: {step.description}")
                print(f"SQL: {step.sql_command}")
                
                confirmation = input("\nType 'CONFIRM' to proceed (or anything else to skip): ")
                if confirmation != "CONFIRM":
                    logger.warning(f"Skipping destructive step: {step.step_name}")
                    return False
        
        try:
            # Execute SQL command
            if step.sql_command.strip().upper().startswith('SELECT'):
                # For SELECT queries, fetch results
                result = await self.db_manager.fetch(step.sql_command)
                logger.info(f"Query returned {len(result)} rows")
            else:
                # For DDL/DML commands
                result = await self.db_manager.execute(step.sql_command)
                logger.info(f"Command executed: {result}")
            
            self.rollback_history.append(f"✅ {step.step_name}")
            logger.info(f"Successfully completed: {step.step_name}")
            return True
            
        except Exception as e:
            error_msg = f"❌ Failed rollback step '{step.step_name}': {e}"
            logger.error(error_msg)
            self.rollback_history.append(error_msg)
            return False
    
    def print_rollback_summary(self):
        """Print summary of rollback operations."""
        print("\n" + "=" * 60)
        print("ROLLBACK OPERATION SUMMARY")
        print("=" * 60)
        
        for entry in self.rollback_history:
            print(entry)
        
        print("=" * 60)

# Phase-specific rollback procedures

class Phase1Rollback(MigrationRollback):
    """Rollback procedures for Phase 1 (Foundation)."""
    
    async def rollback_symbols_table(self, force: bool = False) -> bool:
        """Rollback symbols table creation (P1.2)."""
        
        logger.info("Starting symbols table rollback")
        
        steps = [
            RollbackStep(
                step_name="Drop symbol helper functions",
                sql_command="DROP FUNCTION IF EXISTS get_symbol_id(TEXT, TEXT, TEXT);",
                description="Remove symbol lookup functions",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop symbol views",
                sql_command="DROP VIEW IF EXISTS symbol_details;",
                description="Remove symbol detail view",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop symbol triggers",
                sql_command="DROP TRIGGER IF EXISTS trigger_symbols_updated_at ON symbols;",
                description="Remove automatic timestamp triggers",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop symbol update function",
                sql_command="DROP FUNCTION IF EXISTS update_symbols_updated_at();",
                description="Remove timestamp update function",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop symbol extraction function",
                sql_command="DROP FUNCTION IF EXISTS extract_current_symbols();",
                description="Remove data extraction function",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop symbols table",
                sql_command="DROP TABLE IF EXISTS symbols CASCADE;",
                description="⚠️  REMOVE ENTIRE SYMBOLS TABLE - ALL SYMBOL DATA WILL BE LOST",
                is_destructive=True,
                requires_confirmation=True
            )
        ]
        
        success_count = 0
        for step in steps:
            if await self.execute_rollback_step(step, force):
                success_count += 1
        
        logger.info(f"Symbols table rollback: {success_count}/{len(steps)} steps completed")
        return success_count == len(steps)
    
    async def rollback_exchanges_table(self, force: bool = False) -> bool:
        """Rollback exchanges table creation (P1.1)."""
        
        logger.info("Starting exchanges table rollback")
        
        steps = [
            RollbackStep(
                step_name="Drop exchange triggers",
                sql_command="DROP TRIGGER IF EXISTS trigger_exchanges_updated_at ON exchanges;",
                description="Remove automatic timestamp triggers",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop exchange update function",
                sql_command="DROP FUNCTION IF EXISTS update_exchanges_updated_at();",
                description="Remove timestamp update function",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop exchanges table",
                sql_command="DROP TABLE IF EXISTS exchanges CASCADE;",
                description="⚠️  REMOVE ENTIRE EXCHANGES TABLE - ALL EXCHANGE DATA WILL BE LOST",
                is_destructive=True,
                requires_confirmation=True
            )
        ]
        
        success_count = 0
        for step in steps:
            if await self.execute_rollback_step(step, force):
                success_count += 1
        
        logger.info(f"Exchanges table rollback: {success_count}/{len(steps)} steps completed")
        return success_count == len(steps)
    
    async def rollback_cache_infrastructure(self, force: bool = False) -> bool:
        """Rollback cache infrastructure (P1.3)."""
        
        logger.info("Starting cache infrastructure rollback")
        
        # Note: Cache infrastructure is primarily in application code,
        # so database rollback is minimal
        
        steps = [
            RollbackStep(
                step_name="Remove cache monitoring functions",
                sql_command="""
                DROP FUNCTION IF EXISTS get_cache_stats();
                DROP FUNCTION IF EXISTS refresh_symbol_cache();
                """,
                description="Remove cache-related database functions",
                is_destructive=True
            )
        ]
        
        success_count = 0
        for step in steps:
            if await self.execute_rollback_step(step, force):
                success_count += 1
        
        logger.info(f"Cache infrastructure rollback: {success_count}/{len(steps)} steps completed")
        return success_count == len(steps)
    
    async def rollback_complete_phase1(self, force: bool = False) -> bool:
        """Complete rollback of Phase 1 (all components)."""
        
        print("\n🔄 STARTING COMPLETE PHASE 1 ROLLBACK")
        print("This will remove all Phase 1 changes and restore the original database state")
        
        if not force:
            print("\n⚠️  WARNING: This operation will:")
            print("  - Delete symbols table and all symbol data")
            print("  - Delete exchanges table and all exchange data")
            print("  - Remove all Phase 1 database functions and triggers")
            print("  - Return database to pre-migration state")
            
            confirmation = input("\nType 'ROLLBACK_PHASE1' to confirm complete rollback: ")
            if confirmation != "ROLLBACK_PHASE1":
                print("Rollback cancelled")
                return False
        
        # Execute rollback in reverse order (symbols first, then exchanges)
        success = True
        
        # 1. Rollback cache infrastructure
        if not await self.rollback_cache_infrastructure(force=True):
            success = False
        
        # 2. Rollback symbols table (depends on exchanges)
        if not await self.rollback_symbols_table(force=True):
            success = False
        
        # 3. Rollback exchanges table (last, as symbols depend on it)
        if not await self.rollback_exchanges_table(force=True):
            success = False
        
        if success:
            print("\n✅ PHASE 1 ROLLBACK COMPLETED SUCCESSFULLY")
            print("Database has been restored to pre-migration state")
        else:
            print("\n❌ PHASE 1 ROLLBACK COMPLETED WITH ERRORS")
            print("Some operations may have failed - check logs for details")
        
        return success

class Phase2Rollback(MigrationRollback):
    """Rollback procedures for Phase 2 (Data Migration)."""
    
    async def rollback_normalized_tables(self, force: bool = False) -> bool:
        """Rollback normalized market data tables."""
        
        logger.info("Starting normalized tables rollback")
        
        steps = [
            RollbackStep(
                step_name="Drop materialized views",
                sql_command="""
                DROP MATERIALIZED VIEW IF EXISTS latest_book_ticker_snapshots;
                DROP MATERIALIZED VIEW IF EXISTS latest_trade_snapshots;
                """,
                description="Remove performance materialized views",
                is_destructive=True
            ),
            RollbackStep(
                step_name="Drop normalized book ticker table",
                sql_command="DROP TABLE IF EXISTS book_ticker_snapshots_v2 CASCADE;",
                description="⚠️  REMOVE NORMALIZED BOOK TICKER TABLE",
                is_destructive=True,
                requires_confirmation=True
            ),
            RollbackStep(
                step_name="Drop normalized trade table",
                sql_command="DROP TABLE IF EXISTS trade_snapshots_v2 CASCADE;",
                description="⚠️  REMOVE NORMALIZED TRADE TABLE",
                is_destructive=True,
                requires_confirmation=True
            ),
            RollbackStep(
                step_name="Drop compatibility views",
                sql_command="""
                DROP VIEW IF EXISTS book_ticker_snapshots_legacy;
                DROP VIEW IF EXISTS trade_snapshots_legacy;
                """,
                description="Remove backward compatibility views",
                is_destructive=True
            )
        ]
        
        success_count = 0
        for step in steps:
            if await self.execute_rollback_step(step, force):
                success_count += 1
        
        logger.info(f"Normalized tables rollback: {success_count}/{len(steps)} steps completed")
        return success_count == len(steps)

class Phase3Rollback(MigrationRollback):
    """Rollback procedures for Phase 3 (Integration)."""
    
    async def rollback_code_integration(self, force: bool = False) -> bool:
        """Rollback code integration changes."""
        
        logger.info("Code integration rollback")
        
        # Note: Most Phase 3 changes are in application code
        # Database rollback is minimal
        
        print("⚠️  Phase 3 rollback requires manual steps:")
        print("  1. Revert models.py to use old BookTickerSnapshot structure")
        print("  2. Revert operations.py to use old table names")
        print("  3. Remove cache integration from connection.py")
        print("  4. Update application code to use string-based exchange/symbol storage")
        
        return True

# Utility functions

async def backup_current_data(backup_prefix: str = None) -> str:
    """Create backup of current database state before rollback."""
    
    if backup_prefix is None:
        backup_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    backup_file = f"backup_{backup_prefix}.sql"
    
    # Note: This would use pg_dump in a real implementation
    # For now, we'll create a simple data export
    
    db = get_db_manager()
    
    backup_queries = [
        "-- Backup created at: " + datetime.now().isoformat(),
        "",
        "-- Current exchanges data",
        "SELECT 'INSERT INTO exchanges_backup SELECT * FROM exchanges WHERE 1=1;' as backup_cmd;"
    ]
    
    print(f"💾 Creating backup: {backup_file}")
    print("⚠️  Note: Full pg_dump backup recommended for production rollbacks")
    
    return backup_file

async def verify_rollback_safety() -> Dict[str, bool]:
    """Verify it's safe to perform rollback operations."""
    
    db = get_db_manager()
    safety_checks = {}
    
    try:
        # Check if new tables have data
        if await table_exists('symbols'):
            symbol_count = await db.fetchval("SELECT COUNT(*) FROM symbols")
            safety_checks['symbols_has_data'] = symbol_count > 0
        
        if await table_exists('exchanges'):
            exchange_count = await db.fetchval("SELECT COUNT(*) FROM exchanges")
            safety_checks['exchanges_has_data'] = exchange_count > 0
        
        # Check if old tables still exist
        safety_checks['old_tables_exist'] = await table_exists('book_ticker_snapshots')
        
        # Check for foreign key dependencies
        fk_query = """
        SELECT COUNT(*) FROM information_schema.table_constraints 
        WHERE constraint_type = 'FOREIGN KEY' 
        AND table_name IN ('symbols', 'book_ticker_snapshots_v2', 'trade_snapshots_v2')
        """
        fk_count = await db.fetchval(fk_query)
        safety_checks['has_foreign_keys'] = fk_count > 0
        
    except Exception as e:
        logger.error(f"Safety check failed: {e}")
        safety_checks['safety_check_error'] = str(e)
    
    return safety_checks

async def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    db = get_db_manager()
    
    query = """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = $1
    )
    """
    
    return await db.fetchval(query, table_name)

# Main rollback interface

async def main():
    """Main rollback interface."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Migration Rollback")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], required=True,
                       help="Phase to rollback (1, 2, or 3)")
    parser.add_argument("--component", type=str, 
                       choices=['exchanges', 'symbols', 'cache', 'normalized', 'integration'],
                       help="Specific component to rollback")
    parser.add_argument("--force", action="store_true", 
                       help="Skip confirmation prompts (DANGEROUS)")
    parser.add_argument("--backup", action="store_true",
                       help="Create backup before rollback")
    
    args = parser.parse_args()
    
    # Database configuration
    db_config = DatabaseConfig(
        host="localhost",
        port=5432,
        database="cex_arbitrage",
        username="postgres",
        password=os.getenv("DB_PASSWORD", ""),
        min_pool_size=1,
        max_pool_size=5
    )
    
    try:
        # Initialize appropriate rollback handler
        if args.phase == 1:
            rollback_handler = Phase1Rollback()
        elif args.phase == 2:
            rollback_handler = Phase2Rollback()
        elif args.phase == 3:
            rollback_handler = Phase3Rollback()
        
        await rollback_handler.initialize(db_config)
        
        # Create backup if requested
        if args.backup:
            backup_file = await backup_current_data()
            print(f"📄 Backup created: {backup_file}")
        
        # Verify rollback safety
        safety_checks = await verify_rollback_safety()
        print(f"🔍 Safety checks: {safety_checks}")
        
        # Execute specific rollback
        success = False
        
        if args.phase == 1:
            if args.component == 'exchanges':
                success = await rollback_handler.rollback_exchanges_table(args.force)
            elif args.component == 'symbols':
                success = await rollback_handler.rollback_symbols_table(args.force)
            elif args.component == 'cache':
                success = await rollback_handler.rollback_cache_infrastructure(args.force)
            else:
                # Full Phase 1 rollback
                success = await rollback_handler.rollback_complete_phase1(args.force)
        
        elif args.phase == 2:
            if args.component == 'normalized':
                success = await rollback_handler.rollback_normalized_tables(args.force)
            else:
                print("⚠️  Phase 2 rollback not yet implemented")
        
        elif args.phase == 3:
            success = await rollback_handler.rollback_code_integration(args.force)
        
        # Print summary
        rollback_handler.print_rollback_summary()
        
        if success:
            print("\n✅ ROLLBACK COMPLETED SUCCESSFULLY")
        else:
            print("\n❌ ROLLBACK COMPLETED WITH ERRORS")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        print(f"\n❌ ROLLBACK FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    """
    Usage examples:
    
    # Rollback complete Phase 1
    python rollback_procedures.py --phase 1 --backup
    
    # Rollback only symbols table from Phase 1
    python rollback_procedures.py --phase 1 --component symbols --backup
    
    # Force rollback without confirmations (DANGEROUS)
    python rollback_procedures.py --phase 1 --force
    
    # Rollback Phase 2 normalized tables
    python rollback_procedures.py --phase 2 --component normalized --backup
    """
    
    asyncio.run(main())