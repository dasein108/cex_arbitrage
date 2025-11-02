#!/bin/bash

# Quick Run Script for All Strategies
# Makes it easy to run different test scenarios

echo "🚀 Cross-Exchange Arbitrage Strategy Runner"
echo "=========================================="
echo ""
echo "Select an option:"
echo "1) Quick parameter test (real data, fast mode)"
echo "2) Full parameter test (real data, comprehensive)" 
echo "3) Test specific symbol (choose strategy and data source)"
echo "4) Test QUBIC with Mean Reversion (real data, the profitable strategy)"
echo "5) Run comprehensive symbol analysis (real data)"
echo "6) Test with synthetic data (development mode)"
echo "7) View README documentation"
echo ""
read -p "Enter choice [1-7]: " choice

# Set Python path
export PYTHONPATH=/Users/dasein/dev/cex_arbitrage/src

case $choice in
    1)
        echo "Running quick parameter test with real data..."
        python simple_all_strategies.py --quick --hours 24 --timeframe 5m
        ;;
    2)
        echo "Running full parameter test with comprehensive real data..."
        python simple_all_strategies.py --hours 48 --timeframe 5m
        ;;
    3)
        echo "Enter symbol to test (e.g., BTC_USDT, ETH_USDT, QUBIC_USDT):"
        read -p "Symbol: " symbol
        echo "Select strategy:"
        echo "1) Spike Capture (default)"
        echo "2) Mean Reversion (good for QUBIC)"
        read -p "Strategy [1-2]: " strategy_choice
        
        echo "Select data source:"
        echo "1) Real market data (recommended)"
        echo "2) Synthetic test data (development)"
        read -p "Data source [1-2]: " data_choice
        
        echo "Select timeframe (for real data):"
        echo "1) 5m (recommended for most strategies)"
        echo "2) 1m (more granular, more data)"
        read -p "Timeframe [1-2]: " timeframe_choice
        
        if [ "$timeframe_choice" = "2" ]; then
            timeframe="1m"
        else
            timeframe="5m"
        fi
        
        if [ "$data_choice" = "2" ]; then
            data_flag="--use-test-data --periods 1500"
        else
            data_flag="--hours 24 --timeframe $timeframe"
        fi
        
        if [ "$strategy_choice" = "2" ]; then
            echo "Testing $symbol with Mean Reversion strategy..."
            python quick_test.py --symbol "$symbol" --strategy mean_reversion $data_flag
        else
            echo "Testing $symbol with Spike Capture strategy..."
            python quick_test.py --symbol "$symbol" --strategy spike $data_flag
        fi
        ;;
    4)
        echo "Test QUBIC specifically with Mean Reversion (the profitable one):"
        echo "Testing QUBIC_USDT with mean reversion strategy and real data..."
        python quick_test.py --symbol QUBIC_USDT --strategy mean_reversion --hours 48 --timeframe 5m
        ;;
    5)
        echo "Running comprehensive analysis on multiple symbols with real data..."
        echo "Testing BTC_USDT..."
        python quick_test.py --symbol BTC_USDT --hours 24 --timeframe 5m
        echo ""
        echo "Testing ETH_USDT..."
        python quick_test.py --symbol ETH_USDT --hours 24 --timeframe 5m
        echo ""
        echo "Testing SOL_USDT..."
        python quick_test.py --symbol SOL_USDT --hours 24 --timeframe 5m
        ;;
    6)
        echo "Running synthetic data test mode (development)..."
        python simple_all_strategies.py --use-test-data --periods 1500 --quick
        ;;
    7)
        echo "Viewing README documentation..."
        cat README.md
        ;;
    *)
        echo "Invalid choice. Running default quick test with real data..."
        python simple_all_strategies.py --quick --hours 24 --timeframe 5m
        ;;
esac

echo ""
echo "✅ Analysis complete!"
echo ""
echo "💡 Tips:"
echo "   - Real market data is now the default for accurate backtesting"
echo "   - Optimized Spike Capture solves the 'MEXC +1%, Gate.io +0.5%' problem"
echo "   - Use 5m timeframe for most strategies, 1m for high-frequency testing"
echo "   - QUBIC Mean Reversion strategy shows consistent profitability with real data"
echo "   - Use quick_test.py for individual symbol testing"
echo "   - Use --use-test-data flag for development and parameter optimization"
echo "   - Check README.md for detailed strategy explanation"