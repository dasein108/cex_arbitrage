#!/usr/bin/env python3
"""
Multi-Exchange Asset Status Checker Tool

Enhanced tool to check deposit/withdrawal status and available networks
for coins configured in config.yaml arbitrage_pairs across multiple exchanges.

Features:
- Supports multiple exchanges: MEXC_spot and Gate.io spot
- Configurable exchanges using a simple list
- Separate columns for each exchange showing deposit/withdrawal status
- Shows available networks for each exchange
- Handles cases where an asset exists on one exchange but not another
- Uses separated domain architecture (private exchanges for get_assets_info)
- HFT compliant (no caching of real-time trading data)
- Clean tabular output format

Usage:
    python asset_status_checker.py
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional
import yaml

from exchanges.interfaces import PublicSpotRest, PrivateSpotRest

# Add parent directories to path for imports
project_root = Path(__file__).parent.parent.parent  # Points to src/
sys.path.insert(0, str(project_root))

from exchanges.structs.types import AssetName
from exchanges.structs.common import AssetInfo
from exchanges.exchange_factory import get_rest_implementation
from exchanges.structs.enums import ExchangeEnum
from config.config_manager import HftConfig


class AssetStatusChecker:
    """Multi-exchange asset status checker for configured trading pairs."""

    def __init__(self):
        self.config = HftConfig()

        # Configure exchanges to check (easily configurable)
        self.exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]  # Add exchanges here

        # Exchange instances
        self.exchange_instances: Dict[ExchangeEnum, PrivateSpotRest] = {}

        # Exchange display names for clean output
        self.exchange_display_names = {
            ExchangeEnum.MEXC: 'MEXC',
             ExchangeEnum.GATEIO: 'Gate.io'
        }

        # Exchange enum mapping
        self.exchange_enums = {
            'mexc_spot': ExchangeEnum.MEXC,
            'gateio_spot': ExchangeEnum.GATEIO
        }

    async def initialize(self):
        """Initialize all configured exchange clients."""
        for exchange_enum in self.exchanges:
            exchange_config = self.config.get_exchange_config(exchange_enum.value)

            # Create private composite exchange using factory
            self.exchange_instances[exchange_enum] = get_rest_implementation(
                exchange_config=exchange_config,
                is_private=True
            )

    def get_coins_from_config(self) -> Set[str]:
        """Extract unique base assets from config.yaml arbitrage_pairs."""
        config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        coins = set()
        arbitrage_pairs = config.get('arbitrage', {}).get('arbitrage_pairs', [])

        for pair in arbitrage_pairs:
            if pair.get('is_enabled', True):  # Only include enabled pairs
                base_asset = pair.get('base_asset')
                if base_asset:
                    coins.add(base_asset)

        return coins

    async def fetch_asset_info_all_exchanges(self) -> Dict[str, Dict[AssetName, AssetInfo]]:
        """Fetch asset information from all configured exchanges."""
        assets_info_by_exchange = {}

        for exchange_key in self.exchanges:
            exchange_instance = self.exchange_instances.get(exchange_key)
            if not exchange_instance:
                print(f"Warning: {exchange_key} exchange not properly initialized")
                assets_info_by_exchange[exchange_key] = {}
                continue

            try:
                assets_info = await exchange_instance.get_assets_info()
                assets_info_by_exchange[exchange_key] = assets_info
                print(f"✓ Fetched {len(assets_info)} assets from {self.exchange_display_names[exchange_key]}")
            except Exception as e:
                print(f"✗ Failed to fetch assets from {self.exchange_display_names[exchange_key]}: {e}")
                assets_info_by_exchange[exchange_key] = {}

        return assets_info_by_exchange

    def format_networks(self, networks: Dict[str, any]) -> str:
        """Format available networks with withdrawal fees as comma-separated string."""
        if not networks:
            return "N/A"

        available_networks = []
        for network_name, network_info in networks.items():
            if network_info.deposit_enable or network_info.withdraw_enable:
                # Add withdrawal fee in parentheses if available
                if hasattr(network_info, 'withdraw_fee') and network_info.withdraw_fee is not None and network_info.withdraw_fee > 0:
                    available_networks.append(f"{network_name}({network_info.withdraw_fee})")
                else:
                    available_networks.append(network_name)
        return ", ".join(sorted(available_networks)) if available_networks else "None"

    def display_results(self, coins: Set[str], assets_info_by_exchange: Dict[str, Dict[AssetName, AssetInfo]]):
        """Display results in clean multi-exchange tabular format."""
        print("Multi-Exchange Asset Deposit/Withdrawal Status")
        
        # Calculate total width based on configured exchanges
        col_widths = [10] + [12, 13, 35] * len(self.exchanges)
        total_width = sum(col_widths)
        print("=" * total_width)

        # Build dynamic header based on configured exchanges
        header_parts = ["Coin"]
        for exchange_key in self.exchanges:
            exchange_name = self.exchange_display_names[exchange_key]
            header_parts.extend([f"{exchange_name} Deposit", f"{exchange_name} Withdraw", f"{exchange_name} Networks"])

        # Print header
        header_line = "".join(f"{part:<{col_widths[i]}}" for i, part in enumerate(header_parts))
        print(header_line)
        print("-" * total_width)

        # Track statistics per exchange
        exchange_stats = {exchange_key: {'found': 0, 'missing': set()} for exchange_key in self.exchanges}

        for coin in sorted(coins):
            asset_name = AssetName(coin)
            row_parts = [coin]

            for exchange_key in self.exchanges:
                assets_info = assets_info_by_exchange.get(exchange_key, {})

                if asset_name in assets_info:
                    exchange_stats[exchange_key]['found'] += 1
                    asset_info = assets_info[asset_name]

                    deposit_status = "✓" if asset_info.deposit_enable else "✗"
                    withdraw_status = "✓" if asset_info.withdraw_enable else "✗"
                    networks_str = self.format_networks(asset_info.networks)

                    row_parts.extend([deposit_status, withdraw_status, networks_str])
                else:
                    exchange_stats[exchange_key]['missing'].add(coin)
                    row_parts.extend(["N/A", "N/A", "Not Found"])

            # Print row with proper spacing
            row_line = "".join(f"{part:<{col_widths[i]}}" for i, part in enumerate(row_parts))
            print(row_line)

        # Display summary statistics
        print("\n" + "=" * total_width)
        print("SUMMARY STATISTICS")
        print("-" * total_width)

        for exchange_key in self.exchanges:
            exchange_name = self.exchange_display_names[exchange_key]
            stats = exchange_stats[exchange_key]

            print(f"\n{exchange_name}:")
            print(f"  Found: {stats['found']}/{len(coins)} assets")
            if stats['missing']:
                missing_list = ', '.join(sorted(stats['missing']))
                print(f"  Missing: {missing_list}")

        print(f"\nTotal configured coins: {len(coins)}")

    async def run(self):
        """Main execution flow."""
        try:
            # Validate environment variables for all configured exchanges
            print(
                f"Initializing {len(self.exchanges)} exchanges: {', '.join([self.exchange_display_names[ex] for ex in self.exchanges])}...")
            await self.initialize()

            # Get coins from configuration
            coins = self.get_coins_from_config()
            print(f"\nChecking status for {len(coins)} configured coins across {len(self.exchanges)} exchanges...")

            # Fetch asset information from all exchanges
            assets_info_by_exchange = await self.fetch_asset_info_all_exchanges()

            # Display results
            print("\n")
            self.display_results(coins, assets_info_by_exchange)

        except Exception as e:
            print(f"Error: {e}")
            if "700003" in str(e):
                print("\nTip: This error usually occurs due to system time synchronization issues.")
                print("Please ensure your system clock is accurate and try again.")
            sys.exit(1)
        finally:
            # Close all exchange connections
            for exchange_key, exchange_instance in self.exchange_instances.items():
                if exchange_instance:
                    try:
                        await exchange_instance.close()
                    except Exception as e:
                        print(f"Warning: Error closing {self.exchange_display_names[exchange_key]} connection: {e}")


async def main():
    """Main entry point."""
    checker = AssetStatusChecker()
    await checker.run()


if __name__ == "__main__":
    asyncio.run(main())