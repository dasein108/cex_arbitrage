"""
Utility functions for portfolio rebalancing.
"""

from typing import Dict, List, Tuple
import json
from datetime import datetime
from pathlib import Path
import numpy as np

from .config import RebalanceEvent, PortfolioState


def save_backtest_results(results, config, filename: str = None):
    """
    Save backtest results to JSON file.
    
    Args:
        results: BacktestResults object
        config: RebalanceConfig object
        filename: Optional filename (auto-generated if None)
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_results_{timestamp}.json"
    
    # Convert results to dict
    results_dict = {
        'backtest_info': {
            'start_date': results.start_date.isoformat(),
            'end_date': results.end_date.isoformat(),
            'days_tested': results.days_tested,
            'timestamp': datetime.now().isoformat()
        },
        'config': {
            'upside_threshold': config.upside_threshold,
            'downside_threshold': config.downside_threshold,
            'sell_percentage': config.sell_percentage,
            'usdt_reserve': config.usdt_reserve,
            'min_order_value': config.min_order_value,
            'cooldown_minutes': config.cooldown_minutes,
            'initial_capital': config.initial_capital,
            'trading_fee': config.trading_fee
        },
        'performance': {
            'total_return': results.total_return,
            'annualized_return': results.annualized_return,
            'sharpe_ratio': results.sharpe_ratio,
            'max_drawdown': results.max_drawdown,
            'win_rate': results.win_rate
        },
        'trading': {
            'total_trades': results.total_trades,
            'total_rebalances': results.total_rebalances,
            'total_fees': results.total_fees,
            'avg_rebalance_size': results.avg_rebalance_size
        },
        'portfolio': {
            'initial_value': results.initial_value,
            'final_value': results.final_value,
            'best_performer': {
                'asset': results.best_performer[0],
                'return': results.best_performer[1]
            },
            'worst_performer': {
                'asset': results.worst_performer[0],
                'return': results.worst_performer[1]
            }
        }
    }
    
    # Save to file
    with open(filename, 'w') as f:
        json.dump(results_dict, f, indent=2)
    
    print(f"Results saved to {filename}")


def export_rebalance_history(rebalancer, filename: str = None):
    """
    Export rebalancing history to CSV.
    
    Args:
        rebalancer: ThresholdCascadeRebalancer instance
        filename: Optional filename (auto-generated if None)
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rebalance_history_{timestamp}.csv"
    
    import csv
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow([
            'timestamp', 'trigger_asset', 'trigger_deviation',
            'action_type', 'symbol', 'side', 'quantity', 'price',
            'value_usdt', 'reason', 'event_fees'
        ])
        
        # Write data
        for event in rebalancer.rebalance_history:
            for action in event.actions:
                writer.writerow([
                    action.timestamp.isoformat(),
                    event.trigger_asset,
                    f"{event.trigger_deviation:.4f}",
                    action.action_type.value,
                    action.symbol,
                    action.side,
                    f"{action.quantity:.8f}",
                    f"{action.price:.8f}",
                    f"{action.value_usdt:.2f}",
                    action.reason,
                    f"{event.fees_paid:.2f}"
                ])
    
    print(f"Rebalance history exported to {filename}")


def calculate_buy_hold_benchmark(initial_prices: Dict[str, float], 
                                final_prices: Dict[str, float],
                                initial_capital: float,
                                equal_weight: bool = True) -> Dict:
    """
    Calculate buy-and-hold benchmark performance.
    
    Args:
        initial_prices: Starting prices for each asset
        final_prices: Ending prices for each asset
        initial_capital: Starting capital
        equal_weight: Whether to use equal weighting
        
    Returns:
        Dictionary with benchmark metrics
    """
    assets = list(initial_prices.keys())
    
    if equal_weight:
        # Equal weight allocation
        per_asset_value = initial_capital / len(assets)
        initial_quantities = {
            asset: per_asset_value / initial_prices[asset]
            for asset in assets
        }
    else:
        # Market cap weighting (simplified - would need market cap data)
        initial_quantities = {
            asset: initial_capital / (len(assets) * initial_prices[asset])
            for asset in assets
        }
    
    # Calculate final value
    final_value = sum(
        initial_quantities[asset] * final_prices[asset]
        for asset in assets
    )
    
    total_return = (final_value - initial_capital) / initial_capital
    
    # Calculate individual asset returns
    asset_returns = {
        asset: (final_prices[asset] - initial_prices[asset]) / initial_prices[asset]
        for asset in assets
    }
    
    return {
        'strategy': 'buy_and_hold',
        'initial_value': initial_capital,
        'final_value': final_value,
        'total_return': total_return,
        'asset_returns': asset_returns,
        'best_asset': max(asset_returns.items(), key=lambda x: x[1]),
        'worst_asset': min(asset_returns.items(), key=lambda x: x[1])
    }


def analyze_rebalance_timing(rebalancer, price_data: Dict) -> Dict:
    """
    Analyze the timing and effectiveness of rebalances.
    
    Args:
        rebalancer: ThresholdCascadeRebalancer instance
        price_data: Historical price data
        
    Returns:
        Analysis results
    """
    if not rebalancer.rebalance_history:
        return {}
    
    successful_rebalances = 0
    total_impact = 0
    
    for event in rebalancer.rebalance_history:
        if event.portfolio_after and event.portfolio_before:
            value_change = (event.portfolio_after.total_value - 
                          event.portfolio_before.total_value)
            
            if value_change > 0:
                successful_rebalances += 1
            
            total_impact += value_change
    
    return {
        'total_events': len(rebalancer.rebalance_history),
        'successful_events': successful_rebalances,
        'success_rate': successful_rebalances / len(rebalancer.rebalance_history),
        'average_impact': total_impact / len(rebalancer.rebalance_history),
        'total_impact': total_impact
    }


def format_portfolio_report(state: PortfolioState) -> str:
    """
    Format portfolio state into a readable report.
    
    Args:
        state: Current portfolio state
        
    Returns:
        Formatted string report
    """
    report = f"""
Portfolio Report - {state.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
{'='*50}

Total Portfolio Value: ${state.total_value:,.2f}
USDT Balance: ${state.usdt_balance:,.2f}
Mean Asset Value: ${state.mean_asset_value:,.2f}

Asset Positions:
"""
    
    for symbol, asset in state.assets.items():
        report += f"""
{symbol:>8}: {asset.quantity:>12.6f} @ ${asset.current_price:>8.4f}
         Value: ${asset.value_usdt:>10.2f} ({asset.weight:>6.1%})
         Deviation: {asset.deviation:>+7.1%}
"""
    
    # Calculate portfolio balance
    weights = [asset.weight for asset in state.assets.values()]
    weight_std = np.std(weights) if len(weights) > 1 else 0
    
    report += f"""
Portfolio Metrics:
- Target Weight per Asset: {state.target_weight:.1%}
- Weight Standard Deviation: {weight_std:.3f}
- Assets in Portfolio: {state.asset_count}
"""
    
    return report


def validate_assets_on_mexc(assets: List[str]) -> Tuple[List[str], List[str]]:
    """
    Validate that assets exist on MEXC (simplified version).
    
    Args:
        assets: List of asset symbols to validate
        
    Returns:
        Tuple of (valid_assets, invalid_assets)
    """
    # This is a simplified validation
    # In production, you'd call MEXC API to get exchange info
    
    # Common MEXC assets (partial list for validation)
    known_assets = {
        'BTC', 'ETH', 'BNB', 'ADA', 'DOT', 'LINK', 'UNI', 'LTC',
        'BCH', 'XLM', 'EOS', 'TRX', 'XMR', 'ATOM', 'VET', 'FIL',
        'THETA', 'DOGE', 'SHIB', 'MATIC', 'AVAX', 'LUNA', 'SOL',
        'NEAR', 'ALGO', 'MANA', 'SAND', 'CRV', 'COMP', 'AAVE',
        'SUSHI', 'YFI', 'SNX', 'MKR', 'BAT', 'ZRX', 'KNC'
    }
    
    valid = [asset for asset in assets if asset.upper() in known_assets]
    invalid = [asset for asset in assets if asset.upper() not in known_assets]
    
    return valid, invalid


def calculate_optimal_rebalance_size(volatility: float, correlation: float) -> float:
    """
    Calculate optimal rebalance size based on asset characteristics.
    
    Args:
        volatility: Asset volatility (std dev of returns)
        correlation: Average correlation with other assets
        
    Returns:
        Suggested rebalance percentage (0.1 to 0.3)
    """
    # Higher volatility -> smaller rebalances
    vol_factor = max(0.1, min(0.3, 0.25 - volatility))
    
    # Higher correlation -> larger rebalances (diversification benefit)
    corr_factor = 0.15 + (correlation * 0.1)
    
    return min(0.3, max(0.1, (vol_factor + corr_factor) / 2))