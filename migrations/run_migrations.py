#!/usr/bin/env python3
"""
Database Migration Runner

Runs SQL migration scripts in order and tracks their execution.
Designed for the CEX Arbitrage data collection system.
"""

import asyncio
import asyncpg
import logging
import sys
import time
from pathlib import Path
from typing import List, Tuple, Optional
import argparse

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.config.config_manager import HftConfig
from db.structs import DatabaseConfig


class MigrationRunner:
    """Database migration runner with safe execution and rollback."""
    
    def __init__(self, db_config: DatabaseConfig):
        """
        Initialize migration runner.
        
        Args:
            db_config: Database configuration
        """
        self.db_config = db_config
        self.logger = logging.getLogger(__name__)
        self.migrations_dir = Path(__file__).parent
        
    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection."""
        return await asyncpg.connect(
            host=self.db_config.host,
            port=self.db_config.port,
            database=self.db_config.database,
            user=self.db_config.username,
            password=self.db_config.password
        )
    
    def get_migration_files(self) -> List[Tuple[str, Path]]:
        """
        Get list of migration files in order.
        
        Returns:
            List of (version, file_path) tuples sorted by version
        """
        migration_files = []
        
        for sql_file in self.migrations_dir.glob("*.sql"):
            if sql_file.name.startswith("run_migrations"):
                continue
                
            # Extract version from filename (e.g., "001_description.sql" -> "001")
            try:
                version = sql_file.name[:3]
                if version.isdigit():
                    migration_files.append((version, sql_file))
            except (IndexError, ValueError):
                self.logger.warning(f"Skipping invalid migration file: {sql_file.name}")
        
        # Sort by version
        migration_files.sort(key=lambda x: x[0])
        return migration_files
    
    async def is_migration_applied(self, conn: asyncpg.Connection, version: str) -> bool:
        """
        Check if a migration has been applied.
        
        Args:
            conn: Database connection
            version: Migration version
            
        Returns:
            True if migration has been applied
        """
        try:
            result = await conn.fetchval(
                "SELECT is_migration_applied($1)",
                version
            )
            return result
        except Exception:
            # If function doesn't exist, check table directly
            try:
                result = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM migration_history WHERE version = $1)",
                    version
                )
                return result
            except Exception:
                # Migration infrastructure not set up
                return False
    
    async def apply_migration(
        self, 
        conn: asyncpg.Connection, 
        version: str, 
        file_path: Path
    ) -> bool:
        """
        Apply a single migration.
        
        Args:
            conn: Database connection
            version: Migration version
            file_path: Path to migration SQL file
            
        Returns:
            True if migration was applied successfully
        """
        self.logger.info(f"Applying migration {version}: {file_path.name}")
        
        try:
            # Read migration SQL
            sql_content = file_path.read_text(encoding='utf-8')
            
            # Record start time
            start_time = time.time()
            
            # Execute migration in a transaction
            async with conn.transaction():
                await conn.execute(sql_content)
            
            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            self.logger.info(
                f"✅ Migration {version} applied successfully "
                f"(execution time: {execution_time_ms}ms)"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to apply migration {version}: {e}")
            return False
    
    async def get_migration_status(self, conn: asyncpg.Connection) -> List[dict]:
        """
        Get status of all migrations.
        
        Args:
            conn: Database connection
            
        Returns:
            List of migration status records
        """
        try:
            rows = await conn.fetch("SELECT * FROM get_migration_status()")
            return [dict(row) for row in rows]
        except Exception:
            # Fallback if function doesn't exist
            try:
                rows = await conn.fetch(
                    "SELECT version, description, applied_at, applied_by "
                    "FROM migration_history ORDER BY version"
                )
                return [dict(row) for row in rows]
            except Exception:
                return []
    
    async def run_migrations(
        self, 
        target_version: Optional[str] = None,
        dry_run: bool = False
    ) -> bool:
        """
        Run pending migrations.
        
        Args:
            target_version: Optional target version to migrate to
            dry_run: If True, only show what would be executed
            
        Returns:
            True if all migrations were applied successfully
        """
        self.logger.info("🚀 Starting database migration process")
        
        try:
            # Get migration files
            migration_files = self.get_migration_files()
            
            if not migration_files:
                self.logger.warning("No migration files found")
                return True
            
            # Connect to database
            conn = await self.get_connection()
            
            try:
                applied_count = 0
                skipped_count = 0
                
                for version, file_path in migration_files:
                    # Check target version limit
                    if target_version and version > target_version:
                        self.logger.info(f"⏭️  Stopping at target version {target_version}")
                        break
                    
                    # Check if already applied
                    if await self.is_migration_applied(conn, version):
                        self.logger.debug(f"⏭️  Migration {version} already applied, skipping")
                        skipped_count += 1
                        continue
                    
                    if dry_run:
                        self.logger.info(f"🔄 Would apply migration {version}: {file_path.name}")
                        continue
                    
                    # Apply migration
                    success = await self.apply_migration(conn, version, file_path)
                    if not success:
                        self.logger.error(f"❌ Migration process stopped at version {version}")
                        return False
                    
                    applied_count += 1
                
                if dry_run:
                    self.logger.info("✅ Dry run completed - no changes made")
                else:
                    self.logger.info(
                        f"✅ Migration process completed - "
                        f"Applied: {applied_count}, Skipped: {skipped_count}"
                    )
                
                return True
                
            finally:
                await conn.close()
                
        except Exception as e:
            self.logger.error(f"❌ Migration process failed: {e}")
            return False
    
    async def show_status(self):
        """Show current migration status."""
        self.logger.info("📊 Current Migration Status")
        
        try:
            conn = await self.get_connection()
            
            try:
                status_records = await self.get_migration_status(conn)
                
                if not status_records:
                    self.logger.info("No migrations have been applied yet")
                    return
                
                print("\n" + "="*80)
                print(f"{'Version':<10} {'Description':<40} {'Applied At':<20} {'Applied By':<15}")
                print("="*80)
                
                for record in status_records:
                    applied_at = record['applied_at'].strftime("%Y-%m-%d %H:%M:%S")
                    print(
                        f"{record['version']:<10} "
                        f"{record['description'][:38]:<40} "
                        f"{applied_at:<20} "
                        f"{record['applied_by']:<15}"
                    )
                
                print("="*80)
                print(f"Total migrations applied: {len(status_records)}")
                
            finally:
                await conn.close()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to get migration status: {e}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Database Migration Runner")
    parser.add_argument(
        "--action", 
        choices=["migrate", "status"], 
        default="migrate",
        help="Action to perform (default: migrate)"
    )
    parser.add_argument(
        "--target", 
        help="Target migration version (e.g., 001)"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Show what would be executed without making changes"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Load database configuration
        config = HftConfig()
        db_config_data = config.get_database_config()
        db_config = DatabaseConfig(
            host=db_config_data.get("host", "localhost"),
            port=int(db_config_data.get("port", 5432)),
            database=db_config_data.get("database", "cex_arbitrage"),
            username=db_config_data.get("username", "arbitrage_user"),
            password=db_config_data.get("password", "")
        )
        
        # Create migration runner
        runner = MigrationRunner(db_config)
        
        # Execute requested action
        if args.action == "status":
            await runner.show_status()
        else:
            success = await runner.run_migrations(
                target_version=args.target,
                dry_run=args.dry_run
            )
            if not success:
                sys.exit(1)
        
    except Exception as e:
        logger.error(f"❌ Migration runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())