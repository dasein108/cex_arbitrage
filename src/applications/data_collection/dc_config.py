"""
Data Collector Configuration Management

Simplified configuration access for the data collection system.
Uses the centralized HftConfig for consistent config handling.
"""

from config.config_manager import get_data_collector_config, get_database_config
from config.structs import DataCollectorConfig, DatabaseConfig, AnalyticsConfig


def load_data_collector_config(config_path: str = "config.yaml") -> DataCollectorConfig:
    """
    Convenience function to load data collector configuration.
    
    Args:
        config_path: Path to configuration file (unused, maintained for compatibility)
        
    Returns:
        DataCollectorConfig instance
    """
    return get_data_collector_config()


# Legacy compatibility exports
def get_exchange_config() -> DatabaseConfig:
    """Legacy function for database config access."""
    return get_database_config()