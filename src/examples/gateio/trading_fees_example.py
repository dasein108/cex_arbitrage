"""
Gate.io Trading Fees Example

Demonstrates how to retrieve personal trading fees using the Gate.io private API.
Shows proper usage of the get_trading_fees() method with error handling and
integration patterns for HFT arbitrage cost calculations.

Requirements:
- Gate.io API credentials (API_KEY and SECRET_KEY)
- Active Gate.io account with trading permissions

HFT Compliance:
- Never caches fees data (fresh API calls only)
- Uses async/await for optimal performance
- Proper resource cleanup and error handling
"""

import asyncio
import logging
import os
from typing import Optional

from exchanges.gateio.rest.gateio_private import GateioPrivateExchange
from exchanges.interface.structs import TradingFee, Symbol, AssetName
from common.exceptions import ExchangeAPIError


# Configure logging for better debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TradingFeesDemo:
    """
    Comprehensive demonstration of Gate.io trading fees functionality.
    
    Features:
    - Basic fees retrieval
    - Error handling scenarios  
    - Cost calculation examples
    - Integration with arbitrage strategies
    """
    
    def __init__(self, api_key: str, secret_key: str):
        """
        Initialize the demo with Gate.io credentials.
        
        Args:
            api_key: Gate.io API key
            secret_key: Gate.io secret key
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.exchange: Optional[GateioPrivateExchange] = None
    
    async def __aenter__(self):
        """Async context manager entry - initialize exchange client."""
        self.exchange = GateioPrivateExchange(self.api_key, self.secret_key)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources."""
        if self.exchange:
            await self.exchange.close()
    
    async def demonstrate_basic_fees_retrieval(self) -> Optional[TradingFee]:
        """
        Demonstrate basic trading fees retrieval.
        
        Expected Gate.io Response Format:
        {
            "user_id": 10003,
            "taker_fee": "0.002",      # 0.2% taker fee
            "maker_fee": "0.002",      # 0.2% maker fee  
            "gt_discount": false,      # GT token discount status
            "gt_taker_fee": "0.0015",  # GT discounted taker fee
            "gt_maker_fee": "0.0015",  # GT discounted maker fee
            "loan_fee": "0.18",        # Margin loan fee (annual)
            "point_type": "0"          # Fee tier level
        }
        
        Returns:
            TradingFee object with parsed fee information, or None if failed
        """
        try:
            logger.info("📊 Retrieving personal trading fees from Gate.io...")
            
            # HFT COMPLIANT: Fresh API call, no caching
            trading_fee = await self.exchange.get_trading_fees()
            
            # Display fee information
            logger.info("✅ Successfully retrieved trading fees:")
            logger.info(f"   💰 Maker Fee: {trading_fee.maker_percentage:.3f}% ({trading_fee.maker_rate:.4f})")
            logger.info(f"   💰 Taker Fee: {trading_fee.taker_percentage:.3f}% ({trading_fee.taker_rate:.4f})")
            logger.info(f"   🎯 Fee Tier: {trading_fee.point_type}")
            logger.info(f"   🏢 Exchange: {trading_fee.exchange}")
            
            # Additional fee information if available
            if trading_fee.spot_maker is not None:
                logger.info(f"   📈 Spot Maker: {trading_fee.spot_maker * 100:.3f}%")
            if trading_fee.spot_taker is not None:
                logger.info(f"   📉 Spot Taker: {trading_fee.spot_taker * 100:.3f}%")
            
            return trading_fee
            
        except ExchangeAPIError as e:
            logger.error(f"❌ Gate.io API Error: {e.code} - {e.message}")
            if e.api_code:
                logger.error(f"   Gate.io Error Code: {e.api_code}")
            return None
        
        except Exception as e:
            logger.error(f"❌ Unexpected error retrieving fees: {str(e)}")
            return None
    
    async def demonstrate_symbol_specific_fees(self, symbol: Symbol) -> Optional[TradingFee]:
        """
        Demonstrate symbol-specific fees retrieval.
        
        Note: Gate.io API Limitation - will return account-level fees regardless
        of the symbol parameter due to API constraints.
        
        Args:
            symbol: Trading symbol to request fees for
            
        Returns:
            TradingFee object with symbol field populated, or None if failed
        """
        try:
            logger.info(f"📊 Retrieving symbol-specific trading fees for {symbol.base}/{symbol.quote}...")
            
            # HFT COMPLIANT: Fresh API call with symbol parameter
            trading_fee = await self.exchange.get_trading_fees(symbol=symbol)
            
            # Display fee information with symbol context
            logger.info("✅ Successfully retrieved symbol-specific trading fees:")
            logger.info(f"   🎯 Symbol: {symbol.base}/{symbol.quote}")
            logger.info(f"   💰 Maker Fee: {trading_fee.maker_percentage:.3f}% ({trading_fee.maker_rate:.4f})")
            logger.info(f"   💰 Taker Fee: {trading_fee.taker_percentage:.3f}% ({trading_fee.taker_rate:.4f})")
            logger.info(f"   🎯 Fee Tier: {trading_fee.point_type}")
            logger.info(f"   🏢 Exchange: {trading_fee.exchange}")
            
            # Show symbol field in response
            if trading_fee.symbol:
                logger.info(f"   📈 Response Symbol: {trading_fee.symbol.base}/{trading_fee.symbol.quote}")
            else:
                logger.info(f"   ⚠️  Response Symbol: None (account-level fees returned)")
            
            logger.warning("⚠️  Gate.io API Limitation: Symbol parameter accepted but account-level fees returned")
            logger.info("   This is due to Gate.io's /spot/fee endpoint not supporting symbol-specific rates")
            
            return trading_fee
            
        except ExchangeAPIError as e:
            logger.error(f"❌ Gate.io API Error: {e.code} - {e.message}")
            return None
        
        except Exception as e:
            logger.error(f"❌ Unexpected error retrieving symbol-specific fees: {str(e)}")
            return None
    
    async def demonstrate_error_scenarios(self):
        """
        Demonstrate various error handling scenarios.
        
        Common Error Scenarios:
        - Invalid API credentials (401 Unauthorized)
        - Network connectivity issues (500 Internal Server Error) 
        - Rate limiting (429 Too Many Requests)
        - API maintenance (503 Service Unavailable)
        """
        logger.info("🚨 Demonstrating error handling scenarios...")
        
        # Create client with invalid credentials for demonstration
        try:
            invalid_client = GateioPrivateExchange("invalid_key", "invalid_secret")
            
            # This should fail with authentication error
            await invalid_client.get_trading_fees()
            
        except ExchangeAPIError as e:
            logger.info(f"✅ Expected authentication error caught: {e.code} - {e.message}")
            
        except Exception as e:
            logger.info(f"✅ Expected error caught: {str(e)}")
        
        finally:
            # Always clean up resources
            if 'invalid_client' in locals():
                await invalid_client.close()
    
    async def demonstrate_cost_calculations(self, trading_fee: TradingFee):
        """
        Demonstrate how to use fees data for arbitrage cost calculations.
        
        Args:
            trading_fee: TradingFee object from previous retrieval
        """
        if not trading_fee:
            logger.warning("⚠️ No trading fee data available for cost calculations")
            return
        
        logger.info("💡 Demonstrating cost calculations for arbitrage strategies:")
        
        # Example arbitrage scenario parameters
        trade_amount_usdt = 1000  # $1000 trade size
        spread_percentage = 0.25  # 0.25% spread between exchanges
        
        # Calculate trading costs
        entry_cost = trade_amount_usdt * trading_fee.taker_rate  # Market buy (taker)
        exit_cost = trade_amount_usdt * trading_fee.maker_rate   # Limit sell (maker)
        total_cost = entry_cost + exit_cost
        
        # Calculate net profit potential
        gross_profit = trade_amount_usdt * (spread_percentage / 100)
        net_profit = gross_profit - total_cost
        profit_margin = (net_profit / trade_amount_usdt) * 100
        
        logger.info(f"   📊 Trade Size: ${trade_amount_usdt:,.2f}")
        logger.info(f"   📈 Market Spread: {spread_percentage:.3f}%")
        logger.info(f"   💸 Entry Cost (Taker): ${entry_cost:.2f}")
        logger.info(f"   💸 Exit Cost (Maker): ${exit_cost:.2f}")
        logger.info(f"   💸 Total Fees: ${total_cost:.2f}")
        logger.info(f"   💰 Gross Profit: ${gross_profit:.2f}")
        logger.info(f"   💰 Net Profit: ${net_profit:.2f}")
        logger.info(f"   📈 Net Margin: {profit_margin:.4f}%")
        
        # Profitability assessment
        if net_profit > 0:
            logger.info("   ✅ Arbitrage opportunity is profitable!")
        else:
            logger.info("   ❌ Arbitrage opportunity is not profitable after fees")
        
        # Calculate minimum profitable spread
        min_spread_rate = total_cost / trade_amount_usdt
        min_spread_percentage = min_spread_rate * 100
        logger.info(f"   🎯 Minimum Profitable Spread: {min_spread_percentage:.4f}%")
    
    async def demonstrate_integration_patterns(self, trading_fee: TradingFee):
        """
        Demonstrate integration patterns with existing arbitrage framework.
        
        Args:
            trading_fee: TradingFee object from previous retrieval
        """
        if not trading_fee:
            logger.warning("⚠️ No trading fee data available for integration examples")
            return
        
        logger.info("🔗 Demonstrating integration with arbitrage framework:")
        
        # Example: Dynamic fee-adjusted opportunity detection
        logger.info("   Example 1: Fee-Adjusted Opportunity Detection")
        logger.info(f"     - Use maker rate ({trading_fee.maker_percentage:.3f}%) for limit order strategies")
        logger.info(f"     - Use taker rate ({trading_fee.taker_percentage:.3f}%) for market order strategies")
        logger.info(f"     - Adjust minimum spread thresholds based on total fee cost")
        
        # Example: Risk management integration
        logger.info("   Example 2: Risk Management Integration")
        logger.info(f"     - Include fee costs in position sizing calculations")
        logger.info(f"     - Factor fees into maximum acceptable loss limits")
        logger.info(f"     - Use fee tier ({trading_fee.point_type}) for volume-based strategies")
        
        # Example: Performance monitoring
        logger.info("   Example 3: Performance Monitoring")
        logger.info(f"     - Track actual vs expected fee costs")
        logger.info(f"     - Monitor for fee tier changes that affect profitability")
        logger.info(f"     - Calculate fee-adjusted returns for strategy evaluation")


async def main():
    """
    Main demonstration function showing comprehensive fees endpoint usage.
    """
    # Get API credentials from environment variables
    api_key = os.getenv('GATEIO_API_KEY')
    secret_key = os.getenv('GATEIO_SECRET_KEY')
    
    if not api_key or not secret_key:
        logger.error("❌ Missing Gate.io API credentials!")
        logger.error("   Please set GATEIO_API_KEY and GATEIO_SECRET_KEY environment variables")
        logger.error("   Example:")
        logger.error("     export GATEIO_API_KEY='your_api_key_here'")
        logger.error("     export GATEIO_SECRET_KEY='your_secret_key_here'")
        return
    
    logger.info("🚀 Starting Gate.io Trading Fees Example Demo")
    logger.info("=" * 60)
    
    # Use async context manager for proper resource cleanup
    async with TradingFeesDemo(api_key, secret_key) as demo:
        
        # 1. Basic fees retrieval (account-level)
        trading_fee = await demo.demonstrate_basic_fees_retrieval()
        
        logger.info("-" * 60)
        
        # 1b. Symbol-specific fees retrieval (demonstrates API limitation)
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False)
        trading_fee_symbol = await demo.demonstrate_symbol_specific_fees(btc_usdt)
        
        logger.info("-" * 60)
        
        # 2. Error handling scenarios
        await demo.demonstrate_error_scenarios()
        
        logger.info("-" * 60)
        
        # 3. Cost calculations for arbitrage
        await demo.demonstrate_cost_calculations(trading_fee)
        
        logger.info("-" * 60)
        
        # 4. Integration patterns
        await demo.demonstrate_integration_patterns(trading_fee)
    
    logger.info("=" * 60)
    logger.info("✅ Gate.io Trading Fees Example Demo Complete!")


if __name__ == "__main__":
    """
    Run the trading fees example.
    
    Usage:
        export GATEIO_API_KEY='your_api_key_here'
        export GATEIO_SECRET_KEY='your_secret_key_here'
        python src/examples/gateio/trading_fees_example.py
    """
    asyncio.run(main())