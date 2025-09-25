#!/usr/bin/env python3
"""
Exchange Architecture Cleanup Script

Removes redundant exchange implementations and consolidates the architecture
around the new UnifiedCompositeExchange pattern.

This script will:
1. Identify redundant files that are being replaced
2. Create backup of legacy files 
3. Update import statements to use unified implementations
4. Remove deprecated interfaces and implementations

Run with: python cleanup_legacy_exchanges.py --dry-run  (to preview changes)
Run with: python cleanup_legacy_exchanges.py --execute  (to apply changes)
"""

import os
import shutil
import argparse
from pathlib import Path
from typing import List, Tuple
import re

# Base directory
BASE_DIR = Path(__file__).parent
SRC_DIR = BASE_DIR / "src"

# Files to be deprecated/removed
LEGACY_FILES = [
    # Abstract vs Composite redundancy
    "src/exchanges/interfaces/composite/abstract_private_exchange.py",
    
    # Duplicate MEXC implementations
    "src/exchanges/integrations/mexc/private_exchange_refactored.py", 
    "src/exchanges/integrations/mexc/private_exchange.py",
    
    # Duplicate Gate.io implementations  
    "src/exchanges/integrations/gateio/private_exchange_refactored.py",
    "src/exchanges/integrations/gateio/private_exchange.py", 
    
    # Legacy factory implementation
    "src/trading/arbitrage/exchange_factory.py",
    
    # Duplicate interface files
    "src/infrastructure/factories/factory_interface.py",
]

# Import replacements to apply
IMPORT_REPLACEMENTS = [
    (
        r"from exchanges\.integrations\.mexc\.private_exchange import.*",
        "from exchanges.integrations.mexc.mexc_unified_exchange import MexcUnifiedExchange"
    ),
    (
        r"from exchanges\.interfaces\.composite\.abstract_private_exchange import.*",  
        "from exchanges.interfaces.composite.unified_exchange import UnifiedCompositeExchange"
    ),
    (
        r"from exchanges\.interfaces\.composite\.base_private_exchange import CompositePrivateExchange",
        "from exchanges.interfaces.composite.unified_exchange import UnifiedCompositeExchange"
    ),
    (
        r"from trading\.arbitrage\.exchange_factory import.*",
        "from exchanges.interfaces.composite.unified_exchange import UnifiedExchangeFactory"
    )
]

def find_files_with_pattern(directory: Path, pattern: str) -> List[Path]:
    """Find all Python files containing a pattern."""
    matching_files = []
    
    for py_file in directory.rglob("*.py"):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if re.search(pattern, content):
                    matching_files.append(py_file)
        except Exception as e:
            print(f"Error reading {py_file}: {e}")
    
    return matching_files

def create_backup_directory() -> Path:
    """Create backup directory for legacy files."""
    backup_dir = BASE_DIR / "legacy_exchange_backup"
    backup_dir.mkdir(exist_ok=True)
    return backup_dir

def backup_file(file_path: Path, backup_dir: Path) -> None:
    """Backup a file to the backup directory.""" 
    if not file_path.exists():
        print(f"Warning: {file_path} does not exist, skipping backup")
        return
    
    # Create relative path in backup
    rel_path = file_path.relative_to(BASE_DIR)
    backup_path = backup_dir / rel_path
    
    # Create parent directories
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy file
    shutil.copy2(file_path, backup_path)
    print(f"Backed up: {rel_path}")

def update_imports_in_file(file_path: Path, dry_run: bool = True) -> bool:
    """Update import statements in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes_made = False
        
        # Apply import replacements
        for pattern, replacement in IMPORT_REPLACEMENTS:
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                changes_made = True
                content = new_content
                print(f"  Updated import in {file_path.relative_to(BASE_DIR)}")
        
        # Write back if changes made and not dry run
        if changes_made and not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        return changes_made
        
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def find_files_using_legacy_imports() -> List[Path]:
    """Find files that use legacy imports."""
    files_to_update = set()
    
    # Search for files using legacy imports
    for pattern, _ in IMPORT_REPLACEMENTS:
        matching_files = find_files_with_pattern(SRC_DIR, pattern)
        files_to_update.update(matching_files)
    
    return list(files_to_update)

def remove_legacy_files(legacy_files: List[str], dry_run: bool = True) -> None:
    """Remove legacy files.""" 
    for file_path_str in legacy_files:
        file_path = BASE_DIR / file_path_str
        
        if file_path.exists():
            if dry_run:
                print(f"Would remove: {file_path_str}")
            else:
                file_path.unlink()
                print(f"Removed: {file_path_str}")
        else:
            print(f"File not found: {file_path_str}")

def validate_new_architecture() -> bool:
    """Validate that new unified architecture files exist."""
    required_files = [
        "src/exchanges/interfaces/composite/unified_exchange.py",
        "src/exchanges/integrations/mexc/mexc_unified_exchange.py",
    ]
    
    all_exist = True
    for file_path_str in required_files:
        file_path = BASE_DIR / file_path_str
        if not file_path.exists():
            print(f"Error: Required new file missing: {file_path_str}")
            all_exist = False
        else:
            print(f"✓ New file exists: {file_path_str}")
    
    return all_exist

def create_migration_summary(files_to_update: List[Path], legacy_files: List[str]) -> None:
    """Create a summary of the migration changes."""
    summary_path = BASE_DIR / "exchange_migration_summary.md"
    
    with open(summary_path, 'w') as f:
        f.write("# Exchange Architecture Migration Summary\n\n")
        
        f.write("## New Unified Architecture\n\n")
        f.write("The exchange architecture has been simplified to use a single unified interface:\n\n")
        f.write("- `UnifiedCompositeExchange`: Single interface combining public + private operations\n")
        f.write("- `UnifiedExchangeFactory`: Simplified factory for exchange creation\n")
        f.write("- Exchange implementations (e.g., `MexcUnifiedExchange`): Consolidated implementations\n\n")
        
        f.write("## Files Removed\n\n")
        for file_path in legacy_files:
            f.write(f"- `{file_path}` (redundant implementation)\n")
        
        f.write(f"\n## Files Updated ({len(files_to_update)})\n\n")
        for file_path in files_to_update:
            rel_path = file_path.relative_to(BASE_DIR)
            f.write(f"- `{rel_path}` (import statements updated)\n")
        
        f.write("\n## Benefits\n\n")
        f.write("1. **Simplified Architecture**: Single interface eliminates Abstract vs Composite confusion\n")
        f.write("2. **Reduced Redundancy**: Eliminated duplicate implementations across exchanges\n")
        f.write("3. **Clearer Purpose**: Combined public + private operations for arbitrage use cases\n")
        f.write("4. **Easier Maintenance**: Single interface to maintain and extend\n")
        f.write("5. **Better Performance**: Unified implementation reduces overhead\n\n")
        
        f.write("## Usage Example\n\n")
        f.write("```python\n")
        f.write("from exchanges.interfaces.composite.unified_exchange import UnifiedExchangeFactory\n")
        f.write("from infrastructure.config.structs import ExchangeConfig\n")
        f.write("\n")
        f.write("# Create unified factory\n")
        f.write("factory = UnifiedExchangeFactory()\n")
        f.write("\n")
        f.write("# Create exchange with both market data and trading capabilities\n")
        f.write("config = ExchangeConfig(name='mexc', ...)\n")
        f.write("exchange = await factory.create_exchange('mexc', config, symbols)\n")
        f.write("\n")
        f.write("# Use for arbitrage (both public and private operations)\n")
        f.write("async with exchange.trading_session() as ex:\n")
        f.write("    # Observe market data\n")
        f.write("    orderbook = ex.get_orderbook(symbol)\n")
        f.write("    \n")
        f.write("    # Execute trades\n")
        f.write("    order = await ex.place_limit_order(symbol, side, quantity, price)\n")
        f.write("```\n")
    
    print(f"Migration summary written to: {summary_path}")

def main():
    parser = argparse.ArgumentParser(description="Clean up legacy exchange implementations")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Preview changes without applying them")
    parser.add_argument("--execute", action="store_true",
                       help="Execute the cleanup (removes files)")
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        print("Error: Must specify either --dry-run or --execute")
        return
    
    print("Exchange Architecture Cleanup")
    print("=" * 40)
    
    # Validate new architecture exists
    print("\n1. Validating new architecture files...")
    if not validate_new_architecture():
        print("Error: New architecture files missing. Please ensure unified implementations exist.")
        return
    
    # Find files that need import updates
    print("\n2. Finding files with legacy imports...")
    files_to_update = find_files_using_legacy_imports()
    print(f"Found {len(files_to_update)} files with legacy imports")
    
    # Create backup of legacy files
    print("\n3. Creating backups of legacy files...")
    backup_dir = create_backup_directory()
    
    for file_path_str in LEGACY_FILES:
        file_path = BASE_DIR / file_path_str
        if file_path.exists():
            backup_file(file_path, backup_dir)
    
    # Update import statements
    print("\n4. Updating import statements...")
    for file_path in files_to_update:
        update_imports_in_file(file_path, dry_run=args.dry_run)
    
    # Remove legacy files
    print("\n5. Removing legacy files...")
    remove_legacy_files(LEGACY_FILES, dry_run=args.dry_run)
    
    # Create migration summary
    print("\n6. Creating migration summary...")
    create_migration_summary(files_to_update, LEGACY_FILES)
    
    print("\n" + "=" * 40)
    if args.dry_run:
        print("DRY RUN COMPLETED - No files were actually changed")
        print("Run with --execute to apply changes")
    else:
        print("CLEANUP COMPLETED")
        print(f"Backup created in: {backup_dir}")
        print("Legacy files removed and imports updated")
    
    print(f"\nSummary:")
    print(f"- Files backed up: {len([f for f in LEGACY_FILES if (BASE_DIR / f).exists()])}")
    print(f"- Files to be removed: {len(LEGACY_FILES)}")
    print(f"- Files with updated imports: {len(files_to_update)}")

if __name__ == "__main__":
    main()