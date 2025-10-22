"""
Asset Transfer Demo - MEXC to Gate.io

Real-life demonstration of cross-exchange asset transfers using the AssetTransferModule.
This script shows the complete process of transferring assets from MEXC to Gate.io
with full tracking, monitoring, and error handling.

Features:
- Complete transfer lifecycle management
- Real-time status monitoring
- Comprehensive logging
- Error handling and recovery
- Balance verification before/after transfer

Usage:
    python src/examples/demo/asset_transfer_demo.py --asset USDT --amount 100.0
"""

import asyncio
import argparse
import time
from typing import Dict, Optional
from datetime import datetime, timedelta

from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.structs.common import AssetName
from exchanges.structs.enums import ExchangeEnum, WithdrawalStatus
from exchanges.exchange_factory import get_composite_implementation
from config.config_manager import HftConfig
from infrastructure.logging import get_logger
from trading.strategies.implementations.cross_exchange_arbitrage_strategy.asset_transfer_module import (
    AssetTransferModule, TransferRequest
)


class AssetTransferDemo:
    """Complete asset transfer demonstration with monitoring and tracking."""
    
    def __init__(self):
        self.logger = get_logger("asset_transfer_demo")
        self.config_manager = HftConfig()
        self.exchanges: Dict[ExchangeEnum, CompositePrivateSpotExchange] = {}
        self.transfer_module = None
        
    async def initialize_exchanges(self):
        """Initialize MEXC and Gate.io exchange connections."""
        self.logger.info("🚀 Initializing exchange connections...")
        
        try:
            # Get exchange configurations
            mexc_config = self.config_manager.get_exchange_config("mexc_spot")
            gateio_config = self.config_manager.get_exchange_config("gateio_spot")
            
            # Create composite exchange implementations
            mexc_exchange = get_composite_implementation(mexc_config, is_private=True)
            gateio_exchange = get_composite_implementation(gateio_config, is_private=True)

            # Store in exchanges dict
            self.exchanges = {
                ExchangeEnum.MEXC: mexc_exchange,
                ExchangeEnum.GATEIO: gateio_exchange
            }
            
            # Initialize the transfer module
            self.transfer_module = AssetTransferModule(self.exchanges)
            await self.transfer_module.initialize()
            self.logger.info("✅ Exchange connections initialized successfully")
            
            # Test connectivity
            await self._test_connectivity()
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize exchanges: {e}")
            raise
    
    async def _test_connectivity(self):
        """Test connectivity to both exchanges."""
        self.logger.info("🔍 Testing exchange connectivity...")
        
        for exchange_enum, exchange in self.exchanges.items():
            try:
                # Test by getting account balances
                balances = exchange.balances
                balance_count = len([b for b in balances.values() if b.available > 0])
                self.logger.info(f"✅ {exchange_enum.name}: Connected ({balance_count} assets with balance)")
                
            except Exception as e:
                self.logger.error(f"❌ {exchange_enum.name}: Connection failed - {e}")
                raise
    
    async def check_balances(self, asset: AssetName) -> Dict[ExchangeEnum, float]:
        """Check asset balances on both exchanges."""
        self.logger.info(f"💰 Checking {asset} balances...")
        
        balances = {}
        for exchange_enum, exchange in self.exchanges.items():
            try:
                balance = await exchange.get_asset_balance(asset)
                available = balance.available if balance else 0.0
                balances[exchange_enum] = available
                
                self.logger.info(f"  {exchange_enum.name}: {available:.8f} {asset}")
                
            except Exception as e:
                self.logger.warning(f"  {exchange_enum.name}: Failed to get balance - {e}")
                balances[exchange_enum] = 0.0
        
        return balances
    
    async def validate_transfer_requirements(self, asset: AssetName, amount: float) -> bool:
        """Validate that transfer requirements are met."""
        self.logger.info(f"🔍 Validating transfer requirements for {amount} {asset}...")
        
        try:
            # Check MEXC has sufficient balance
            mexc_balance = await self.exchanges[ExchangeEnum.MEXC].get_asset_balance(asset)
            if not mexc_balance or mexc_balance.available < amount:
                self.logger.error(f"❌ Insufficient {asset} balance on MEXC: {mexc_balance.available if mexc_balance else 0} < {amount}")
                return False
            
            # Get asset info for both exchanges
            mexc_info = self.exchanges[ExchangeEnum.MEXC].assets_info[asset]
            gateio_info = self.exchanges[ExchangeEnum.GATEIO].assets_info[asset]
            
            # Check withdrawal enabled on MEXC
            if  not mexc_info.withdraw_enable:
                self.logger.error(f"❌ {asset} withdrawals disabled on MEXC")
                return False
            
            # Check deposit enabled on Gate.io
            if not gateio_info.deposit_enable:
                self.logger.error(f"❌ {asset} deposits disabled on Gate.io")
                return False
            
            # Find common networks
            mexc_networks = set(mexc_info.networks.keys())
            gateio_networks = set(gateio_info.networks.keys())
            common_networks = mexc_networks & gateio_networks
            
            if not common_networks:
                self.logger.error(f"❌ No common networks between MEXC and Gate.io for {asset}")
                self.logger.info(f"  MEXC networks: {mexc_networks}")
                self.logger.info(f"  Gate.io networks: {gateio_networks}")
                return False
            
            # Check network limits
            valid_networks = []
            for network in common_networks:
                mexc_net = mexc_info.networks[network]
                gateio_net = gateio_info.networks[network]
                
                if (mexc_net.withdraw_enable and gateio_net.deposit_enable and
                    amount >= mexc_net.withdraw_min and
                    (not mexc_net.withdraw_max or amount <= mexc_net.withdraw_max)):
                    
                    valid_networks.append({
                        'network': network,
                        'fee': mexc_net.withdraw_fee,
                        'min': mexc_net.withdraw_min,
                        'max': mexc_net.withdraw_max,
                    })
                    self.logger.info(f"  ✅ Valid network: {network} (fee={mexc_net.withdraw_fee}, min={mexc_net.withdraw_min}, max={mexc_net.withdraw_max})")
            
            if not valid_networks:
                self.logger.error(f"❌ No valid networks for transfer amount {amount} {asset}")
                return False
            
            # Show valid networks
            self.logger.info(f"✅ Found {len(valid_networks)} valid networks:")
            for net in sorted(valid_networks, key=lambda x: x['fee']):
                self.logger.info(f"  {net['network']}: fee={net['fee']}, min={net['min']}, max={net['max']}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Validation failed: {e}")
            return False
    
    async def execute_transfer(self, asset: AssetName, amount: float) -> Optional[TransferRequest]:
        """Execute the asset transfer."""
        self.logger.info(f"🚀 Starting transfer: {amount} {asset} from MEXC to Gate.io...")
        
        try:
            # Record pre-transfer balances
            pre_balances = await self.check_balances(asset)
            
            # Execute transfer
            transfer_request = await self.transfer_module.transfer_asset(
                asset=asset,
                from_exchange=ExchangeEnum.MEXC,
                to_exchange=ExchangeEnum.GATEIO,
                amount=amount
            )
            
            self.logger.info(f"✅ Transfer initiated successfully!")
            self.logger.info(f"  Transfer ID: {transfer_request.transfer_id}")
            self.logger.info(f"  Transaction ID: {transfer_request.withdrawal_id}")
            self.logger.info(f"  Estimated Fee: {transfer_request.fees} {asset}")
            self.logger.info(f"  Initiated: {transfer_request.initiated}")
            
            return transfer_request
            
        except Exception as e:
            self.logger.error(f"❌ Transfer execution failed: {e}")
            return None
    
    async def monitor_transfer(self, transfer_request: TransferRequest, timeout_minutes: int = 30) -> bool:
        """Monitor transfer progress until completion or timeout."""
        self.logger.info(f"👀 Monitoring transfer {transfer_request.transfer_id}...")
        
        start_time = datetime.now()
        timeout_time = start_time + timedelta(minutes=timeout_minutes)
        check_interval = 30  # Check every 30 seconds
        
        while datetime.now() < timeout_time:
            try:
                # Check transfer status
                is_complete = await self.transfer_module.update_transfer_status(transfer_request.transfer_id)
                
                # Get updated transfer request with latest tracking info
                updated_request = self.transfer_module.get_transfer_request(transfer_request.transfer_id)
                if updated_request:
                    self.logger.info(f"📊 Transfer tracking update:")
                    self.logger.info(f"  Initiated: {updated_request.initiated}")
                    self.logger.info(f"  Completed: {updated_request.completed}")
                    if updated_request.withdrawal_status:
                        self.logger.info(f"  Current status: {updated_request.withdrawal_status.name}")
                    if updated_request.last_status_check:
                        self.logger.info(f"  Last checked: {updated_request.last_status_check.strftime('%H:%M:%S')}")
                
                if is_complete:
                    self.logger.info(f"✅ Transfer completed successfully!")
                    return True
                
                # Check if transfer failed
                if updated_request and updated_request.withdrawal_status == WithdrawalStatus.FAILED:
                    self.logger.error(f"❌ Transfer failed on exchange")
                    return False
                
                # Wait before next check
                elapsed = (datetime.now() - start_time).total_seconds() / 60
                self.logger.info(f"⏱️  Elapsed: {elapsed:.1f} minutes, checking again in {check_interval} seconds...")
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                self.logger.error(f"❌ Error monitoring transfer: {e}")
                await asyncio.sleep(check_interval)
        
        self.logger.warning(f"⏰ Transfer monitoring timed out after {timeout_minutes} minutes")
        
        # Show final status
        final_request = self.transfer_module.get_transfer_request(transfer_request.transfer_id)
        if final_request:
            self.logger.info(f"📊 Final transfer status:")
            self.logger.info(f"  Transfer ID: {final_request.transfer_id}")
            self.logger.info(f"  Transaction ID: {final_request.withdrawal_id}")
            self.logger.info(f"  Initiated: {final_request.initiated}")
            self.logger.info(f"  Completed: {final_request.completed}")
            if final_request.withdrawal_status:
                self.logger.info(f"  Final status: {final_request.withdrawal_status.name}")
        
        return False
    
    async def verify_transfer_completion(self, asset: AssetName, amount: float, 
                                       pre_balances: Dict[ExchangeEnum, float]) -> bool:
        """Verify transfer completion by checking balance changes."""
        self.logger.info(f"🔍 Verifying transfer completion...")
        
        try:
            # Get post-transfer balances
            post_balances = await self.check_balances(asset)
            
            # Calculate changes
            mexc_change = post_balances[ExchangeEnum.MEXC] - pre_balances[ExchangeEnum.MEXC]
            gateio_change = post_balances[ExchangeEnum.GATEIO] - pre_balances[ExchangeEnum.GATEIO]
            
            self.logger.info(f"💰 Balance changes:")
            self.logger.info(f"  MEXC: {mexc_change:+.8f} {asset}")
            self.logger.info(f"  Gate.io: {gateio_change:+.8f} {asset}")
            
            # Verify expected changes (allowing for fees)
            expected_mexc_decrease = -amount
            tolerance = amount * 0.05  # 5% tolerance for fees
            
            if abs(mexc_change - expected_mexc_decrease) <= tolerance and gateio_change > 0:
                self.logger.info(f"✅ Transfer verified! Balances updated correctly")
                return True
            else:
                self.logger.warning(f"⚠️  Balance changes don't match expected transfer")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Verification failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup resources."""
        self.logger.info("🧹 Cleaning up resources...")
        
        try:
            for exchange in self.exchanges.values():
                if hasattr(exchange, 'close'):
                    await exchange.close()
            
            self.logger.info("✅ Cleanup completed")
            
        except Exception as e:
            self.logger.warning(f"⚠️  Cleanup warning: {e}")
    
    async def run_demo(self, asset: AssetName, amount: float):
        """Run the complete asset transfer demo."""
        self.logger.info("=" * 80)
        self.logger.info("🎯 Asset Transfer Demo - MEXC to Gate.io")
        self.logger.info("=" * 80)
        self.logger.info(f"Asset: {asset}")
        self.logger.info(f"Amount: {amount}")
        self.logger.info(f"From: MEXC")
        self.logger.info(f"To: Gate.io")
        self.logger.info("=" * 80)
        
        try:
            # Step 1: Initialize exchanges
            await self.initialize_exchanges()
            
            # Step 2: Check initial balances
            pre_balances = await self.check_balances(asset)
            
            # Step 3: Validate transfer requirements
            if not await self.validate_transfer_requirements(asset, amount):
                self.logger.error("❌ Transfer requirements not met. Aborting.")
                return False
            
            # Step 4: Execute transfer
            transfer_request = await self.execute_transfer(asset, amount)
            if not transfer_request:
                self.logger.error("❌ Transfer execution failed. Aborting.")
                return False
            
            # Step 5: Monitor transfer progress
            success = await self.monitor_transfer(transfer_request, timeout_minutes=30)
            
            # Step 6: Verify completion
            if success:
                verified = await self.verify_transfer_completion(asset, amount, pre_balances)
                if verified:
                    self.logger.info("🎉 Asset transfer demo completed successfully!")
                    
                    # Step 7: Show final transfer summary
                    await self.show_transfer_summary()
                    return True
                else:
                    self.logger.warning("⚠️  Transfer may have completed but verification failed")
                    await self.show_transfer_summary()
                    return False
            else:
                self.logger.error("❌ Transfer did not complete within timeout")
                await self.show_transfer_summary()
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Demo failed with error: {e}")
            return False
        
        finally:
            await self.cleanup()
    
    async def show_transfer_summary(self):
        """Show summary of all transfers."""
        if not self.transfer_module:
            return
            
        self.logger.info("📋 Transfer Summary:")
        
        # Get all active transfers
        all_transfers = self.transfer_module.get_all_active_transfers()
        if not all_transfers:
            self.logger.info("  No active transfers")
            return
        
        # Show transfers by status
        pending_transfers = self.transfer_module.get_transfers_by_status(initiated=False)
        active_transfers = self.transfer_module.get_transfers_by_status(initiated=True, completed=False)
        completed_transfers = self.transfer_module.get_transfers_by_status(completed=True)
        
        self.logger.info(f"  📝 Total transfers: {len(all_transfers)}")
        self.logger.info(f"  ⏳ Pending: {len(pending_transfers)}")
        self.logger.info(f"  🔄 Active: {len(active_transfers)}")
        self.logger.info(f"  ✅ Completed: {len(completed_transfers)}")
        
        # Show details for active transfers
        if active_transfers:
            self.logger.info("  🔍 Active transfer details:")
            for transfer_id, transfer in active_transfers.items():
                self.logger.info(f"    {transfer_id}:")
                self.logger.info(f"      Asset: {transfer.amount} {transfer.asset}")
                self.logger.info(f"      Route: {transfer.from_exchange.name} → {transfer.to_exchange.name}")
                self.logger.info(f"      TX ID: {transfer.withdrawal_id}")
                if transfer.withdrawal_status:
                    self.logger.info(f"      Status: {transfer.withdrawal_status.name}")
                if transfer.last_status_check:
                    self.logger.info(f"      Last check: {transfer.last_status_check.strftime('%H:%M:%S')}")


async def main():
    """Main entry point for the asset transfer demo."""
    parser = argparse.ArgumentParser(description="Asset Transfer Demo - MEXC to Gate.io")
    parser.add_argument("--asset", type=str, default="F",
                       help="Asset to transfer (default: USDT)")
    parser.add_argument("--amount", type=float, default=2440.0,
                       help="Amount to transfer (default: 100.0)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Validate only, don't execute transfer")
    
    args = parser.parse_args()
    
    demo = AssetTransferDemo()
    
    try:
        if args.dry_run:
            # Dry run - validation only
            await demo.initialize_exchanges()
            await demo.check_balances(AssetName(args.asset))
            success = await demo.validate_transfer_requirements(AssetName(args.asset), args.amount)
            print(f"Dry run result: {'✅ VALID' if success else '❌ INVALID'}")
        else:
            # Full transfer execution
            success = await demo.run_demo(AssetName(args.asset), args.amount)
            exit_code = 0 if success else 1
            exit(exit_code)
            
    except KeyboardInterrupt:
        print("\n⚠️  Demo interrupted by user")
        await demo.cleanup()
        exit(1)
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        await demo.cleanup()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())