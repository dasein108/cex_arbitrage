"""
Minimal Test Suite for Simple Arbitrage PoC

Focused test coverage for core arbitrage logic without complex mocking
or extensive test infrastructure.

Usage:
    python -m pytest tests/test_simple_arbitrage_poc.py -v
"""

import pytest
import time
from unittest.mock import AsyncMock, patch
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from simple_arbitrage_poc import SimpleArbitragePoC, BookTicker, ArbitrageOpportunity


class TestSimpleArbitragePoCCore:
    """Test core arbitrage logic without external API dependencies"""
    
    @pytest.fixture
    def arbitrage_poc(self):
        """Create PoC instance with test configuration"""
        return SimpleArbitragePoC(
            symbol="ETH_USDT",
            entry_threshold_pct=0.06,
            exit_threshold_pct=0.03,
            position_size=1.0
        )
    
    @pytest.fixture
    def mexc_ticker(self):
        """Sample MEXC ticker data"""
        return BookTicker(
            symbol="ETHUSDT",
            bid_price=2000.0,
            ask_price=2001.0,
            bid_qty=10.0,
            ask_qty=10.0,
            timestamp=time.time()
        )
    
    @pytest.fixture
    def gateio_ticker(self):
        """Sample Gate.io ticker data"""
        return BookTicker(
            symbol="ETH_USDT",
            bid_price=2005.0,  # Higher bid for arbitrage opportunity
            ask_price=2006.0,
            bid_qty=10.0,
            ask_qty=10.0,
            timestamp=time.time()
        )
    
    def test_initialization(self, arbitrage_poc):
        """Test PoC initialization"""
        assert arbitrage_poc.symbol == "ETH_USDT"
        assert arbitrage_poc.entry_threshold_pct == 0.06
        assert arbitrage_poc.exit_threshold_pct == 0.03
        assert arbitrage_poc.position_size == 1.0
        assert arbitrage_poc.current_position is None
        assert arbitrage_poc.total_opportunities == 0
        assert arbitrage_poc.total_profit == 0.0
    
    def test_spread_calculation(self, arbitrage_poc, mexc_ticker, gateio_ticker):
        """Test arbitrage spread calculation logic"""
        spread_spot_to_futures, spread_futures_to_spot = arbitrage_poc.calculate_arbitrage_spreads(
            mexc_ticker, gateio_ticker
        )
        
        # Verify spread calculation accuracy
        # spot_to_futures: Buy MEXC ask (2001), Sell Gate.io bid (2005)
        expected_spot_to_futures = (2005.0 - 2001.0) / 2001.0 * 100  # ~0.20%
        
        # futures_to_spot: Buy Gate.io ask (2006), Sell MEXC bid (2000)
        expected_futures_to_spot = (2000.0 - 2006.0) / 2006.0 * 100  # ~-0.30%
        
        assert abs(spread_spot_to_futures - expected_spot_to_futures) < 0.001
        assert abs(spread_futures_to_spot - expected_futures_to_spot) < 0.001
        assert spread_spot_to_futures > 0  # Profitable direction
        assert spread_futures_to_spot < 0  # Unprofitable direction
    
    def test_entry_opportunity_detection(self, arbitrage_poc, mexc_ticker, gateio_ticker):
        """Test arbitrage entry opportunity detection"""
        # Should detect spot_to_futures opportunity (spread ~0.20% > 0.06% threshold)
        opportunity = arbitrage_poc.check_entry_opportunity(mexc_ticker, gateio_ticker)
        
        assert opportunity is not None
        assert opportunity.direction == "spot_to_futures"
        assert opportunity.spread_pct > 0.06  # Above entry threshold
        assert opportunity.entry_price_spot == 2001.0  # MEXC ask price
        assert opportunity.entry_price_futures == 2005.0  # Gate.io bid price
        assert opportunity.quantity == 1.0
        assert opportunity.estimated_profit > 0
    
    def test_no_entry_opportunity_below_threshold(self, arbitrage_poc):
        """Test no opportunity when spread below threshold"""
        # Create tickers with small spread
        mexc_ticker = BookTicker("ETHUSDT", 2000.0, 2000.5, 10.0, 10.0, time.time())
        gateio_ticker = BookTicker("ETH_USDT", 2000.2, 2000.7, 10.0, 10.0, time.time())
        
        opportunity = arbitrage_poc.check_entry_opportunity(mexc_ticker, gateio_ticker)
        assert opportunity is None  # Spread too small
    
    def test_no_entry_when_already_in_position(self, arbitrage_poc, mexc_ticker, gateio_ticker):
        """Test no new entry when already in position"""
        # Set existing position
        arbitrage_poc.current_position = ArbitrageOpportunity(
            direction="spot_to_futures",
            spread_pct=0.10,
            entry_price_spot=2000.0,
            entry_price_futures=2002.0,
            quantity=1.0,
            estimated_profit=2.0,
            timestamp=time.time()
        )
        
        opportunity = arbitrage_poc.check_entry_opportunity(mexc_ticker, gateio_ticker)
        assert opportunity is None  # Already in position
    
    def test_exit_opportunity_detection(self, arbitrage_poc):
        """Test exit opportunity detection"""
        # Set current position
        arbitrage_poc.current_position = ArbitrageOpportunity(
            direction="spot_to_futures",
            spread_pct=0.10,
            entry_price_spot=2000.0,
            entry_price_futures=2002.0,
            quantity=1.0,
            estimated_profit=2.0,
            timestamp=time.time()
        )
        
        # Create tickers with small spread (below exit threshold)
        mexc_ticker = BookTicker("ETHUSDT", 2000.0, 2000.5, 10.0, 10.0, time.time())
        gateio_ticker = BookTicker("ETH_USDT", 2000.2, 2000.7, 10.0, 10.0, time.time())
        
        should_exit = arbitrage_poc.check_exit_opportunity(mexc_ticker, gateio_ticker)
        assert should_exit is True  # Spread narrowed below exit threshold
    
    def test_no_exit_without_position(self, arbitrage_poc, mexc_ticker, gateio_ticker):
        """Test no exit signal when not in position"""
        should_exit = arbitrage_poc.check_exit_opportunity(mexc_ticker, gateio_ticker)
        assert should_exit is False  # No current position
    
    def test_percentage_calculation_precision(self, arbitrage_poc):
        """Test that percentage calculations are accurate"""
        mexc_ticker = BookTicker("ETHUSDT", 2000.0, 2001.0, 10.0, 10.0, time.time())
        gateio_ticker = BookTicker("ETH_USDT", 2002.2, 2003.0, 10.0, 10.0, time.time())
        
        spread_spot_to_futures, spread_futures_to_spot = arbitrage_poc.calculate_arbitrage_spreads(
            mexc_ticker, gateio_ticker
        )
        
        # Manual calculation verification
        # spot_to_futures: (2002.2 - 2001.0) / 2001.0 * 100 = 0.05997%
        expected = (2002.2 - 2001.0) / 2001.0 * 100
        assert abs(spread_spot_to_futures - expected) < 0.0001
        
        # Verify it's very close to 0.06% threshold
        assert spread_spot_to_futures < 0.06  # Just below threshold


@pytest.mark.asyncio
class TestAPIIntegration:
    """Basic API integration tests (can be mocked for CI/CD)"""
    
    @pytest.fixture
    def arbitrage_poc(self):
        return SimpleArbitragePoC(symbol="ETH_USDT")
    
    @patch('aiohttp.ClientSession.get')
    async def test_mexc_api_call(self, mock_get, arbitrage_poc):
        """Test MEXC API call with mocked response"""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "symbol": "ETHUSDT",
            "bidPrice": "2000.0",
            "askPrice": "2001.0",
            "bidQty": "10.0",
            "askQty": "10.0"
        })
        mock_get.return_value.__aenter__.return_value = mock_response
        
        ticker = await arbitrage_poc.get_mexc_book_ticker()
        
        assert ticker is not None
        assert ticker.symbol == "ETHUSDT"
        assert ticker.bid_price == 2000.0
        assert ticker.ask_price == 2001.0
    
    @patch('aiohttp.ClientSession.get')
    async def test_gateio_api_call(self, mock_get, arbitrage_poc):
        """Test Gate.io API call with mocked response"""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[
            {
                "contract": "ETH_USDT",
                "bid_price": "2000.0",
                "ask_price": "2001.0",
                "bid_size": "10.0",
                "ask_size": "10.0"
            }
        ])
        mock_get.return_value.__aenter__.return_value = mock_response
        
        ticker = await arbitrage_poc.get_gateio_book_ticker()
        
        assert ticker is not None
        assert ticker.symbol == "ETH_USDT"
        assert ticker.bid_price == 2000.0
        assert ticker.ask_price == 2001.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])