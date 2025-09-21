#!/bin/bash
# =============================================================================
# Database Migration Script
# =============================================================================
# Simple wrapper for running database migrations
# Usage: ./migrate.sh [action] [options]

set -e  # Exit on any error

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
ACTION="migrate"
DRY_RUN=false
VERBOSE=false
TARGET=""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Usage function
usage() {
    echo "Database Migration Script"
    echo ""
    echo "Usage: $0 [action] [options]"
    echo ""
    echo "Actions:"
    echo "  migrate    Run pending migrations (default)"
    echo "  status     Show migration status"
    echo ""
    echo "Options:"
    echo "  --target VERSION   Migrate to specific version (e.g., 001)"
    echo "  --dry-run         Show what would be executed"
    echo "  --verbose         Enable verbose output"
    echo "  --help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                           # Run all pending migrations"
    echo "  $0 status                    # Show migration status"
    echo "  $0 migrate --dry-run         # Show what would be migrated"
    echo "  $0 migrate --target 001      # Migrate up to version 001"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        migrate|status)
            ACTION="$1"
            shift
            ;;
        --target)
            TARGET="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is required but not installed${NC}"
    exit 1
fi

# Check if we're in the right directory
if [[ ! -f "$SCRIPT_DIR/run_migrations.py" ]]; then
    echo -e "${RED}Error: run_migrations.py not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Build Python command
PYTHON_CMD="python3 $SCRIPT_DIR/run_migrations.py --action $ACTION"

if [[ -n "$TARGET" ]]; then
    PYTHON_CMD="$PYTHON_CMD --target $TARGET"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    PYTHON_CMD="$PYTHON_CMD --dry-run"
fi

if [[ "$VERBOSE" == "true" ]]; then
    PYTHON_CMD="$PYTHON_CMD --verbose"
fi

# Set PYTHONPATH to include src directory
export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"

# Change to project root directory
cd "$PROJECT_ROOT"

# Display action
case $ACTION in
    migrate)
        if [[ "$DRY_RUN" == "true" ]]; then
            echo -e "${BLUE}🔍 Performing dry run of database migrations...${NC}"
        else
            echo -e "${GREEN}🚀 Running database migrations...${NC}"
        fi
        ;;
    status)
        echo -e "${BLUE}📊 Checking migration status...${NC}"
        ;;
esac

# Execute the Python migration script
echo "Executing: $PYTHON_CMD"
echo ""

if eval "$PYTHON_CMD"; then
    case $ACTION in
        migrate)
            if [[ "$DRY_RUN" == "true" ]]; then
                echo -e "${GREEN}✅ Dry run completed successfully${NC}"
            else
                echo -e "${GREEN}✅ Migrations completed successfully${NC}"
            fi
            ;;
        status)
            echo -e "${GREEN}✅ Status check completed${NC}"
            ;;
    esac
else
    echo -e "${RED}❌ Migration failed${NC}"
    exit 1
fi