"""
Simple Configuration Loader for Arbitrage PoC

Minimal configuration management without complex architecture patterns.
"""

import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ArbitrageConfig:
    """Simple arbitrage configuration"""
    symbol: str
    entry_threshold_pct: float
    exit_threshold_pct: float
    position_size: float
    check_interval_seconds: int
    monitoring_duration_minutes: int


@dataclass
class ExchangeEndpoints:
    """Exchange API endpoints"""
    mexc_url: str
    mexc_symbol_format: str
    gateio_url: str
    gateio_symbol_format: str


def load_simple_config(config_path: str = None) -> tuple[ArbitrageConfig, ExchangeEndpoints]:
    """
    Load simple configuration from YAML file
    
    Args:
        config_path: Path to config file (defaults to config/simple_arbitrage_config.yaml)
    
    Returns:
        (ArbitrageConfig, ExchangeEndpoints)
    """
    if config_path is None:
        project_root = Path(__file__).parent.parent
        config_path = project_root / "config" / "simple_arbitrage_config.yaml"
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    # Create arbitrage config
    arbitrage_data = data['arbitrage']
    arbitrage_config = ArbitrageConfig(
        symbol=arbitrage_data['symbol'],
        entry_threshold_pct=arbitrage_data['entry_threshold_pct'],
        exit_threshold_pct=arbitrage_data['exit_threshold_pct'],
        position_size=arbitrage_data['position_size'],
        check_interval_seconds=arbitrage_data['check_interval_seconds'],
        monitoring_duration_minutes=arbitrage_data['monitoring_duration_minutes']
    )
    
    # Create exchange endpoints
    exchanges_data = data['exchanges']
    exchange_endpoints = ExchangeEndpoints(
        mexc_url=exchanges_data['mexc']['spot_book_ticker_url'],
        mexc_symbol_format=exchanges_data['mexc']['symbol_format'],
        gateio_url=exchanges_data['gateio']['futures_book_ticker_url'],
        gateio_symbol_format=exchanges_data['gateio']['symbol_format']
    )
    
    return arbitrage_config, exchange_endpoints


if __name__ == "__main__":
    # Test configuration loading
    try:
        config, endpoints = load_simple_config()
        print("Configuration loaded successfully:")
        print(f"Symbol: {config.symbol}")
        print(f"Entry threshold: {config.entry_threshold_pct}%")
        print(f"Exit threshold: {config.exit_threshold_pct}%")
        print(f"Position size: {config.position_size}")
        print(f"MEXC URL: {endpoints.mexc_url}")
        print(f"Gate.io URL: {endpoints.gateio_url}")
    except Exception as e:
        print(f"Configuration loading failed: {e}")