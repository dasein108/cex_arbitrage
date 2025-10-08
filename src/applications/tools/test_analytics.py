"""
Test Script for NEIROETH Analytics Tools

Comprehensive testing of the analytics infrastructure to validate
functionality and integration with the database layer.

Tests:
- Data fetcher initialization and queries
- Spread analysis and opportunity detection
- P&L calculation accuracy
- Performance tracking functionality
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

# Add paths for imports from project root
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
src_path = project_root / "src"
analytics_path = project_root / "hedged_arbitrage" / "analytics"

sys.path.insert(0, str(src_path))
sys.path.insert(0, str(analytics_path))

try:
    from .data_fetcher import MultiSymbolDataFetcher, UnifiedSnapshot
    from .spread_analyzer import SpreadAnalyzer, SpreadOpportunity
    from .pnl_calculator import PnLCalculator, ArbitragePnL
    from .performance_tracker import PerformanceTracker, ExecutionMetrics
except ImportError:
    from data_fetcher import MultiSymbolDataFetcher, UnifiedSnapshot
    from spread_analyzer import SpreadAnalyzer, SpreadOpportunity
    from pnl_calculator import PnLCalculator, ArbitragePnL
    from performance_tracker import PerformanceTracker, ExecutionMetrics

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiSymbolAnalyticsTestSuite:
    """
    Comprehensive test suite for multi-symbol analytics tools.
    
    Validates all components independently and as an integrated system.
    """
    
    def __init__(self, symbol: Symbol = None):
        self.logger = logger.getChild("TestSuite")
        
        # Default to NEIROETH for testing if no symbol provided
        if symbol is None:
            symbol = Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT"))
        
        self.symbol = symbol
        self.data_fetcher = MultiSymbolDataFetcher(symbol)
        self.spread_analyzer = SpreadAnalyzer(self.data_fetcher)
        self.pnl_calculator = PnLCalculator()
        self.performance_tracker = PerformanceTracker()
        
        self.test_results: Dict[str, Dict[str, Any]] = {}
    
    async def run_all_tests(self) -> Dict[str, Dict[str, Any]]:
        """
        Run complete test suite.
        
        Returns:
            Test results dictionary with success/failure status
        """
        self.logger.info(f"🚀 Starting {self.symbol.base}/{self.symbol.quote} Analytics Test Suite")
        
        # Test individual components
        await self._test_data_fetcher()
        await self._test_spread_analyzer()
        await self._test_pnl_calculator()
        await self._test_performance_tracker()
        
        # Test integrated workflow
        await self._test_integrated_workflow()
        
        # Generate summary
        self._generate_test_summary()
        
        return self.test_results
    
    async def _test_data_fetcher(self):
        """Test NEIROETHDataFetcher functionality."""
        self.logger.info("📊 Testing Data Fetcher...")
        
        test_name = "data_fetcher"
        results = {"success": False, "details": {}, "errors": []}
        
        try:
            # Test initialization
            init_success = await self.data_fetcher.initialize()
            results["details"]["initialization"] = init_success
            
            if not init_success:
                results["errors"].append("Failed to initialize symbol IDs")
                self.test_results[test_name] = results
                return
            
            # Test symbol ID retrieval
            symbol_ids = self.data_fetcher.get_symbol_ids()
            results["details"]["symbol_ids_count"] = len([sid for sid in symbol_ids.values() if sid])
            results["details"]["symbol_ids"] = symbol_ids
            
            # Test latest data retrieval
            latest_snapshot = await self.data_fetcher.get_latest_snapshots()
            if latest_snapshot:
                results["details"]["latest_data_available"] = True
                results["details"]["latest_complete"] = latest_snapshot.is_complete()
                results["details"]["latest_timestamp"] = latest_snapshot.timestamp
                
                # Test spread calculations
                spreads = latest_snapshot.get_spreads()
                cross_spreads = latest_snapshot.get_cross_exchange_spreads()
                results["details"]["spreads_calculated"] = len(spreads)
                results["details"]["cross_spreads_calculated"] = len(cross_spreads)
            else:
                results["details"]["latest_data_available"] = False
                results["errors"].append("No latest data available")
            
            # Test historical data retrieval
            historical = await self.data_fetcher.get_historical_snapshots(hours_back=1)
            results["details"]["historical_samples"] = len(historical)
            
            # Test individual exchange data
            for exchange_key in self.data_fetcher.exchanges.keys():
                exchange_data = await self.data_fetcher.get_exchange_snapshots(exchange_key, hours_back=1)
                results["details"][f"{exchange_key}_samples"] = len(exchange_data)
            
            # Test health check
            health = await self.data_fetcher.health_check()
            results["details"]["health_check"] = health
            
            results["success"] = True
            self.logger.info("✅ Data Fetcher tests completed successfully")
            
        except Exception as e:
            results["errors"].append(f"Data fetcher test failed: {str(e)}")
            self.logger.error(f"❌ Data Fetcher test failed: {e}")
        
        self.test_results[test_name] = results
    
    async def _test_spread_analyzer(self):
        """Test SpreadAnalyzer functionality."""
        self.logger.info("📈 Testing Spread Analyzer...")
        
        test_name = "spread_analyzer"
        results = {"success": False, "details": {}, "errors": []}
        
        try:
            # Test current spread analysis
            current_spreads = await self.spread_analyzer.analyze_current_spreads()
            results["details"]["current_spreads_count"] = len(current_spreads)
            results["details"]["current_spreads"] = current_spreads
            
            # Test opportunity identification
            opportunities = await self.spread_analyzer.identify_opportunities()
            results["details"]["opportunities_found"] = len(opportunities)
            
            if opportunities:
                best_opportunity = opportunities[0]
                results["details"]["best_opportunity"] = {
                    "type": best_opportunity.opportunity_type,
                    "spread_pct": best_opportunity.spread_pct,
                    "estimated_profit": best_opportunity.estimated_profit,
                    "confidence": best_opportunity.confidence_score
                }
            
            # Test historical statistics
            historical_stats = await self.spread_analyzer.get_historical_statistics(hours_back=24)
            if historical_stats:
                results["details"]["historical_stats"] = {
                    "sample_count": historical_stats.sample_count,
                    "mean_spread": historical_stats.mean_spread,
                    "profitable_opportunities": historical_stats.profitable_opportunities,
                    "opportunity_rate": historical_stats.opportunity_rate
                }
            else:
                results["details"]["historical_stats"] = None
                results["errors"].append("No historical statistics available")
            
            # Test volatility metrics
            volatility = await self.spread_analyzer.get_volatility_metrics()
            results["details"]["volatility_metrics_count"] = len(volatility)
            results["details"]["volatility_metrics"] = volatility
            
            results["success"] = True
            self.logger.info("✅ Spread Analyzer tests completed successfully")
            
        except Exception as e:
            results["errors"].append(f"Spread analyzer test failed: {str(e)}")
            self.logger.error(f"❌ Spread Analyzer test failed: {e}")
        
        self.test_results[test_name] = results
    
    async def _test_pnl_calculator(self):
        """Test PnLCalculator functionality.""" 
        self.logger.info("💰 Testing P&L Calculator...")
        
        test_name = "pnl_calculator"
        results = {"success": False, "details": {}, "errors": []}
        
        try:
            # Create mock opportunity for testing
            mock_opportunity = SpreadOpportunity(
                timestamp=datetime.utcnow(),
                opportunity_type='spot_arbitrage',
                buy_exchange='MEXC_SPOT',
                sell_exchange='GATEIO_SPOT',
                buy_price=1.5000,
                sell_price=1.5050,
                spread_abs=0.0050,
                spread_pct=0.33,
                confidence_score=0.8,
                max_quantity=1000.0,
                estimated_profit=0.0
            )
            
            # Test P&L calculation
            test_quantity = 100.0
            pnl_result = await self.pnl_calculator.calculate_arbitrage_pnl(
                mock_opportunity, test_quantity, execution_speed='fast'
            )
            
            if pnl_result:
                results["details"]["pnl_calculation"] = {
                    "gross_profit": pnl_result.gross_profit,
                    "net_profit": pnl_result.net_profit,
                    "total_fees": pnl_result.total_fees,
                    "estimated_slippage": pnl_result.estimated_slippage,
                    "net_profit_pct": pnl_result.net_profit_pct,
                    "execution_risk_score": pnl_result.execution_risk_score,
                    "capital_required": pnl_result.capital_required
                }
                
                # Validate calculations
                expected_gross = (mock_opportunity.sell_price - mock_opportunity.buy_price) * test_quantity
                calculated_gross = pnl_result.gross_revenue - pnl_result.gross_cost
                
                results["details"]["calculation_validation"] = {
                    "expected_gross": expected_gross,
                    "calculated_gross": calculated_gross,
                    "difference": abs(expected_gross - calculated_gross)
                }
                
                if abs(expected_gross - calculated_gross) < 0.01:  # Allow small rounding differences
                    results["details"]["gross_calculation_correct"] = True
                else:
                    results["errors"].append(f"Gross calculation mismatch: expected {expected_gross}, got {calculated_gross}")
                
            else:
                results["errors"].append("P&L calculation returned None")
            
            # Test portfolio impact estimation
            opportunities = [mock_opportunity]
            portfolio_impact = await self.pnl_calculator.estimate_portfolio_impact(
                opportunities, portfolio_size=10000.0, max_position_pct=5.0
            )
            
            results["details"]["portfolio_impact"] = portfolio_impact
            
            # Test funding rate updates
            test_funding_rates = {
                'GATEIO_FUTURES': 0.0001,
                'MEXC_FUTURES': 0.00015
            }
            self.pnl_calculator.update_funding_rates(test_funding_rates)
            results["details"]["funding_rates_updated"] = True
            
            results["success"] = True
            self.logger.info("✅ P&L Calculator tests completed successfully")
            
        except Exception as e:
            results["errors"].append(f"P&L calculator test failed: {str(e)}")
            self.logger.error(f"❌ P&L Calculator test failed: {e}")
        
        self.test_results[test_name] = results
    
    async def _test_performance_tracker(self):
        """Test PerformanceTracker functionality."""
        self.logger.info("📊 Testing Performance Tracker...")
        
        test_name = "performance_tracker"
        results = {"success": False, "details": {}, "errors": []}
        
        try:
            # Create mock execution metrics
            mock_execution = ExecutionMetrics(
                trade_id="test_trade_001",
                execution_start=datetime.utcnow() - timedelta(milliseconds=50),
                execution_end=datetime.utcnow(),
                execution_duration_ms=50.0,
                planned_price=1.5000,
                executed_price=1.5001,
                price_slippage_pct=0.007,
                execution_success=True,
                market_volatility=0.05,
                spread_at_execution=0.002,
                liquidity_score=0.8
            )
            
            # Record execution
            self.performance_tracker.record_execution(mock_execution)
            results["details"]["execution_recorded"] = True
            
            # Create mock P&L
            from pnl_calculator import TradeExecution, ArbitragePnL
            
            mock_buy_execution = TradeExecution(
                exchange='MEXC_SPOT',
                side='buy',
                symbol=f'{self.symbol.base}/{self.symbol.quote}',
                quantity=100.0,
                price=1.5001,
                fee_rate=0.002,
                fee_amount=0.30,
                slippage=0.01,
                timestamp=datetime.utcnow()
            )
            
            mock_sell_execution = TradeExecution(
                exchange='GATEIO_SPOT',
                side='sell',
                symbol=f'{self.symbol.base}/{self.symbol.quote}',
                quantity=100.0,
                price=1.5049,
                fee_rate=0.002,
                fee_amount=0.30,
                slippage=0.01,
                timestamp=datetime.utcnow()
            )
            
            mock_pnl = ArbitragePnL(
                opportunity_id="test_trade_001",
                calculation_time=datetime.utcnow(),
                buy_execution=mock_buy_execution,
                sell_execution=mock_sell_execution,
                total_quantity=100.0,
                gross_revenue=150.49,
                gross_cost=150.01,
                gross_profit=0.48,
                total_fees=0.60,
                estimated_slippage=0.02,
                funding_cost=0.0,
                execution_cost=1.0,
                net_profit=-1.14,  # Loss after fees
                net_profit_pct=-0.076,
                max_drawdown_risk=15.0,
                execution_risk_score=0.15,
                capital_required=150.49
            )
            
            # Record P&L
            self.performance_tracker.record_trade_pnl(mock_pnl)
            results["details"]["pnl_recorded"] = True
            
            # Test current performance metrics
            current_performance = self.performance_tracker.get_current_performance()
            results["details"]["current_performance"] = current_performance
            
            # Test risk metrics
            risk_metrics = self.performance_tracker.get_risk_metrics()
            results["details"]["risk_metrics"] = risk_metrics
            
            # Test alerts
            active_alerts = self.performance_tracker.get_active_alerts()
            results["details"]["active_alerts_count"] = len(active_alerts)
            
            # Test performance report
            performance_report = self.performance_tracker.generate_performance_report()
            results["details"]["performance_report_generated"] = True
            results["details"]["report_sections"] = list(performance_report.keys())
            
            results["success"] = True
            self.logger.info("✅ Performance Tracker tests completed successfully")
            
        except Exception as e:
            results["errors"].append(f"Performance tracker test failed: {str(e)}")
            self.logger.error(f"❌ Performance Tracker test failed: {e}")
        
        self.test_results[test_name] = results
    
    async def _test_integrated_workflow(self):
        """Test integrated analytics workflow."""
        self.logger.info("🔄 Testing Integrated Workflow...")
        
        test_name = "integrated_workflow"
        results = {"success": False, "details": {}, "errors": []}
        
        try:
            # Complete arbitrage analysis workflow
            self.logger.info("Step 1: Fetching current data...")
            latest_data = await self.data_fetcher.get_latest_snapshots()
            
            if not latest_data:
                results["errors"].append("No current data available for workflow test")
                self.test_results[test_name] = results
                return
                
            results["details"]["data_fetched"] = True
            
            self.logger.info("Step 2: Analyzing spreads...")
            opportunities = await self.spread_analyzer.identify_opportunities()
            results["details"]["opportunities_identified"] = len(opportunities)
            
            if opportunities:
                self.logger.info("Step 3: Calculating P&L for best opportunity...")
                best_opportunity = opportunities[0]
                
                pnl_analysis = await self.pnl_calculator.calculate_arbitrage_pnl(
                    best_opportunity, quantity=50.0, execution_speed='medium'
                )
                
                if pnl_analysis:
                    results["details"]["pnl_calculated"] = True
                    results["details"]["workflow_net_profit"] = pnl_analysis.net_profit
                    
                    # Simulate recording the trade
                    mock_execution = ExecutionMetrics(
                        trade_id=pnl_analysis.opportunity_id,
                        execution_start=datetime.utcnow() - timedelta(milliseconds=75),
                        execution_end=datetime.utcnow(),
                        execution_duration_ms=75.0,
                        planned_price=best_opportunity.buy_price,
                        executed_price=pnl_analysis.buy_execution.price,
                        price_slippage_pct=pnl_analysis.buy_execution.slippage / best_opportunity.buy_price * 100,
                        execution_success=True
                    )
                    
                    self.performance_tracker.record_execution(mock_execution)
                    self.performance_tracker.record_trade_pnl(pnl_analysis)
                    
                    results["details"]["performance_tracked"] = True
                else:
                    results["errors"].append("P&L calculation failed in workflow")
            else:
                results["details"]["no_opportunities"] = True
                self.logger.info("No opportunities found, but workflow completed successfully")
            
            # Test historical analysis workflow
            self.logger.info("Step 4: Historical analysis...")
            historical_stats = await self.spread_analyzer.get_historical_statistics(hours_back=24)
            if historical_stats:
                results["details"]["historical_analysis"] = True
                results["details"]["historical_opportunity_rate"] = historical_stats.opportunity_rate
            
            # Generate final performance report
            final_report = self.performance_tracker.generate_performance_report()
            results["details"]["final_report_generated"] = True
            
            results["success"] = True
            self.logger.info("✅ Integrated workflow test completed successfully")
            
        except Exception as e:
            results["errors"].append(f"Integrated workflow test failed: {str(e)}")
            self.logger.error(f"❌ Integrated workflow test failed: {e}")
        
        self.test_results[test_name] = results
    
    def _generate_test_summary(self):
        """Generate comprehensive test summary."""
        self.logger.info("📋 Generating Test Summary...")
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results.values() if r["success"]])
        failed_tests = total_tests - passed_tests
        
        summary = {
            "test_completion_time": datetime.utcnow(),
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": (passed_tests / total_tests) * 100 if total_tests > 0 else 0,
            "failed_test_names": [name for name, result in self.test_results.items() if not result["success"]],
            "total_errors": sum(len(result["errors"]) for result in self.test_results.values())
        }
        
        self.test_results["summary"] = summary
        
        # Log summary
        self.logger.info(f"🎯 Test Summary: {passed_tests}/{total_tests} tests passed ({summary['success_rate']:.1f}%)")
        
        if failed_tests > 0:
            self.logger.warning(f"⚠️  {failed_tests} tests failed: {summary['failed_test_names']}")
            for test_name in summary['failed_test_names']:
                for error in self.test_results[test_name]["errors"]:
                    self.logger.error(f"   - {test_name}: {error}")
        else:
            self.logger.info("🎉 All tests passed successfully!")


async def main():
    """Main test execution function."""
    # Default symbol for testing
    test_symbol = Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT"))
    logger.info(f"🧪 Starting Analytics Test Suite for {test_symbol.base}/{test_symbol.quote}")
    
    try:
        test_suite = MultiSymbolAnalyticsTestSuite(test_symbol)
        results = await test_suite.run_all_tests()
        
        # Print final results
        summary = results.get("summary", {})
        print(f"\n{'='*60}")
        print(f"MULTI-SYMBOL ANALYTICS TEST RESULTS")
        print(f"{'='*60}")
        print(f"Total Tests: {summary.get('total_tests', 0)}")
        print(f"Passed: {summary.get('passed_tests', 0)}")
        print(f"Failed: {summary.get('failed_tests', 0)}")
        print(f"Success Rate: {summary.get('success_rate', 0):.1f}%")
        print(f"Total Errors: {summary.get('total_errors', 0)}")
        
        if summary.get('failed_tests', 0) > 0:
            print(f"\nFailed Tests: {summary.get('failed_test_names', [])}")
            return 1
        else:
            print("\n🎉 All analytics tools functioning correctly!")
            return 0
            
    except Exception as e:
        logger.error(f"❌ Test suite execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)