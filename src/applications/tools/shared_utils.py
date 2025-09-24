#!/usr/bin/env python3
"""
Shared utilities for arbitrage tools.

Eliminates code duplication across the tools by providing unified:
- CLI argument parsing and management
- Logging configuration 
- Path resolution logic
- Error handling patterns

Follows CLAUDE.md SOLID principles and DRY compliance.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ToolConfig:
    """Configuration structure for arbitrage tools"""
    operation: str  # 'discover', 'fetch', 'analyze'
    data_dir: str = "data/arbitrage"
    output_dir: str = "output"
    discovery_file: str = "output/symbol_discovery_detailed.json"
    days: int = 3
    max_symbols: Optional[int] = None
    min_profit_score: float = 0.0
    filter_major_coins: bool = True
    validate_only: bool = False
    show_details: bool = False
    incremental: bool = False
    verbose: bool = False
    save_output: bool = True
    output_format: str = "detailed"


class LoggingConfigurator:
    """
    Unified logging configuration for all arbitrage tools.
    
    Responsibility: Configure consistent logging across tools (SRP).
    Eliminates duplication of logging setup code.
    """
    
    @staticmethod
    def setup_logging(verbose: bool = False, tool_name: str = "ArbitrageTool") -> logging.Logger:
        """
        Configure logging with consistent format and level.
        
        Args:
            verbose: Enable debug level logging
            tool_name: Name for the logger instance
            
        Returns:
            Configured logger instance
        """
        level = logging.DEBUG if verbose else logging.INFO
        
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        return logging.getLogger(tool_name)


class PathResolver:
    """
    Unified path resolution logic for all arbitrage tools.
    
    Responsibility: Handle path validation and conversion (SRP).
    Eliminates duplication of path handling code.
    """
    
    @staticmethod
    def resolve_path(path: str, base_dir: Optional[Path] = None) -> str:
        """
        Resolve relative paths to absolute paths.
        
        Args:
            path: Input path (relative or absolute)
            base_dir: Base directory for relative paths (default: current working dir)
            
        Returns:
            Absolute path string
        """
        if not Path(path).is_absolute():
            base = base_dir or Path.cwd()
            return str(base / path)
        return path
    
    @staticmethod
    def ensure_directory(path: str) -> Path:
        """
        Ensure directory exists, create if necessary.
        
        Args:
            path: Directory path to ensure
            
        Returns:
            Path object for the directory
        """
        dir_path = Path(path)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path
    
    @staticmethod
    def validate_file_exists(path: str, file_type: str = "file") -> bool:
        """
        Validate that a file exists.
        
        Args:
            path: File path to check
            file_type: Description of file type for error messages
            
        Returns:
            True if file exists
            
        Raises:
            FileNotFoundError: If file does not exist
        """
        if not Path(path).exists():
            raise FileNotFoundError(f"{file_type} not found: {path}")
        return True
    
    @staticmethod
    def find_latest_discovery_file(output_dir: str = "output", format_type: str = "detailed") -> str:
        """
        Find the latest symbol discovery file with timestamp.
        
        Args:
            output_dir: Directory to search for discovery files
            format_type: Format type to search for (detailed, summary, etc.)
            
        Returns:
            Path to the latest discovery file
            
        Raises:
            FileNotFoundError: If no discovery files found
        """
        import glob
        
        output_path = Path(output_dir)
        
        # Search for discovery files with timestamps
        pattern = f"symbol_discovery_{format_type}_*.json"
        search_pattern = str(output_path / pattern)
        
        discovery_files = glob.glob(search_pattern)
        
        if not discovery_files:
            # Fallback to non-timestamped filename
            fallback_file = str(output_path / f"symbol_discovery_{format_type}.json")
            if Path(fallback_file).exists():
                return fallback_file
            
            raise FileNotFoundError(
                f"No discovery files found matching pattern: {search_pattern}. "
                f"Run 'discover' command first to generate symbol discovery data."
            )
        
        # Sort by modification time to get the latest
        discovery_files.sort(key=lambda x: Path(x).stat().st_mtime, reverse=True)
        latest_file = discovery_files[0]
        
        return latest_file


class CLIManager:
    """
    Unified CLI management for arbitrage tools.
    
    Responsibility: Handle argument parsing and validation (SRP).
    Eliminates duplication of CLI code across tools.
    """
    
    def __init__(self, tool_name: str, description: str):
        """
        Initialize CLI manager for specific tool.
        
        Args:
            tool_name: Name of the tool for help text
            description: Tool description for help
        """
        self.tool_name = tool_name
        self.description = description
        self.parser = self._create_parser()
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """Create composite argument parser with common options"""
        parser = argparse.ArgumentParser(
            description=self.description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=self._get_tool_epilog()
        )
        
        # Common arguments for all tools
        parser.add_argument(
            '--data-dir',
            default="data/arbitrage",
            help='Directory for arbitrage data (default: data/arbitrage)'
        )
        
        parser.add_argument(
            '--output-dir',
            default="output",
            help='Output directory for results (default: output)'
        )
        
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Enable verbose logging'
        )
        
        return parser
    
    def add_discovery_arguments(self) -> None:
        """Add arguments specific to symbol discovery"""
        self.parser.add_argument(
            '--format',
            type=str,
            choices=['summary', 'detailed', 'filtered', 'matrix'],
            default='detailed',
            help='Output format (default: detailed)'
        )
        
        self.parser.add_argument(
            '--no-filter-major',
            action='store_true',
            help='Include major coins (BTC, ETH, etc.) in analysis'
        )
        
        self.parser.add_argument(
            '--no-save',
            action='store_true',
            help='Do not save output to file'
        )
    
    def add_fetcher_arguments(self) -> None:
        """Add arguments specific to data fetching"""
        self.parser.add_argument(
            '--discovery-file',
            default="output/symbol_discovery_detailed.json",
            help='Path to symbol discovery results JSON file'
        )
        
        self.parser.add_argument(
            '--days',
            type=int,
            default=3,
            help='Number of days of historical data to collect (default: 3)'
        )
        
        self.parser.add_argument(
            '--max-symbols',
            type=int,
            help='Maximum number of symbols to process (useful for testing)'
        )
        
        self.parser.add_argument(
            '--validate-only',
            action='store_true',
            help='Only validate existing data without collecting new data'
        )
    
    def add_analyzer_arguments(self) -> None:
        """Add arguments specific to analysis"""
        self.parser.add_argument(
            '--output',
            default="output/arbitrage_analysis_report.csv",
            help='Output CSV report filename'
        )
        
        self.parser.add_argument(
            '--max-symbols',
            type=int,
            help='Maximum number of symbols to analyze (useful for testing)'
        )
        
        self.parser.add_argument(
            '--min-profit-score',
            type=float,
            default=0.0,
            help='Minimum profit score threshold for reporting (default: 0.0)'
        )
        
        self.parser.add_argument(
            '--details',
            action='store_true',
            help='Show detailed analysis for each symbol (recommended for ≤5 symbols)'
        )
        
        self.parser.add_argument(
            '--incremental',
            action='store_true',
            help='Write results incrementally to CSV for immediate observation'
        )
    
    def parse_args(self) -> ToolConfig:
        """
        Parse command line arguments and return configuration.
        
        Returns:
            ToolConfig object with parsed arguments
        """
        args = self.parser.parse_args()
        
        # Map arguments to configuration
        config = ToolConfig(
            operation=self.tool_name.lower(),
            data_dir=args.data_dir,
            output_dir=getattr(args, 'output_dir', 'output'),
            verbose=args.verbose
        )
        
        # Add tool-specific arguments
        if hasattr(args, 'discovery_file'):
            config.discovery_file = args.discovery_file
        if hasattr(args, 'days'):
            config.days = args.days
        if hasattr(args, 'max_symbols'):
            config.max_symbols = args.max_symbols
        if hasattr(args, 'validate_only'):
            config.validate_only = args.validate_only
        if hasattr(args, 'output'):
            config.output_file = args.output
        if hasattr(args, 'min_profit_score'):
            config.min_profit_score = args.min_profit_score
        if hasattr(args, 'details'):
            config.show_details = args.details
        if hasattr(args, 'incremental'):
            config.incremental = args.incremental
        if hasattr(args, 'format'):
            config.output_format = args.format
        if hasattr(args, 'no_filter_major'):
            config.filter_major_coins = not args.no_filter_major
        if hasattr(args, 'no_save'):
            config.save_output = not args.no_save
        
        return config
    
    def _get_tool_epilog(self) -> str:
        """Get tool-specific epilog text"""
        base_workflow = """
Workflow:
  1. Run: python unified_arbitrage_tool.py discover  (generates symbol list)
  2. Run: python unified_arbitrage_tool.py fetch     (downloads candles data) 
  3. Run: python unified_arbitrage_tool.py analyze   (performs spread analysis)
        """
        
        return base_workflow


class ErrorHandler:
    """
    Unified error handling for arbitrage tools.
    
    Responsibility: Consistent error handling and reporting (SRP).
    Eliminates duplication of error handling patterns.
    """
    
    @staticmethod
    def handle_operation_error(operation: str, error: Exception, logger: logging.Logger) -> None:
        """
        Handle operation errors with consistent logging and exit.
        
        Args:
            operation: Name of the operation that failed
            error: Exception that occurred
            logger: Logger instance for error reporting
        """
        logger.error(f"💥 {operation} failed: {error}")
        
        # Import here to avoid circular imports
        import traceback
        # Always show traceback for debugging
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        
        print(f"\n💥 {operation} failed!")
        print("🔍 Check logs above for error details.")
        sys.exit(1)
    
    @staticmethod
    def handle_success(operation: str, result_info: str = "") -> None:
        """
        Handle successful operation completion.
        
        Args:
            operation: Name of the operation that succeeded
            result_info: Additional information about results
        """
        print(f"\n🎉 {operation} completed successfully!")
        if result_info:
            print(result_info)


class PerformanceTimer:
    """
    Simple performance timing utility.
    
    Responsibility: Track operation performance (SRP).
    """
    
    def __init__(self, operation_name: str, logger: logging.Logger):
        """
        Initialize timer for an operation.
        
        Args:
            operation_name: Name of operation being timed
            logger: Logger for performance reporting
        """
        self.operation_name = operation_name
        self.logger = logger
        self.start_time = None
    
    def __enter__(self):
        """Start timing"""
        import time
        self.start_time = time.perf_counter()
        self.logger.info(f"Starting {self.operation_name}...")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End timing and report"""
        import time
        if self.start_time is not None:
            elapsed = time.perf_counter() - self.start_time
            self.logger.info(f"{self.operation_name} completed in {elapsed:.2f} seconds")