"""
PnL Calculator for NEIROETH Arbitrage

Comprehensive profit and loss estimation for arbitrage strategies.
Accounts for exchange fees, slippage, funding rates, and execution costs
to provide accurate profitability analysis.

Features:
- Exchange-specific fee calculations
- Slippage modeling based on order book depth
- Funding rate impact for futures positions
- Risk-adjusted return calculations
- Cost-benefit analysis with execution timing
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple
from decimal import Decimal, ROUND_HALF_UP
import logging

import msgspec

try:
    from .data_fetcher import UnifiedSnapshot
    from .spread_analyzer import SpreadOpportunity
except ImportError:
    from data_fetcher import UnifiedSnapshot
    from spread_analyzer import SpreadOpportunity

logger = logging.getLogger(__name__)


class ExchangeFees(msgspec.Struct):
    """Exchange-specific fee structure."""
    exchange: str
    maker_fee: float    # Maker fee percentage (e.g., 0.002 for 0.2%)
    taker_fee: float    # Taker fee percentage
    futures_fee: Optional[float] = None  # Futures trading fee (if applicable)
    funding_rate: Optional[float] = None  # Current funding rate for futures


class TradeExecution(msgspec.Struct):
    """Individual trade execution details."""
    exchange: str
    side: str          # 'buy' or 'sell'
    symbol: str        # 'NEIROETH/USDT'
    quantity: float
    price: float
    fee_rate: float
    fee_amount: float
    slippage: float    # Price impact from slippage
    timestamp: datetime


class ArbitragePnL(msgspec.Struct):
    """
    Complete arbitrage P&L calculation.
    
    Provides comprehensive profit analysis including all costs and risks.
    """
    opportunity_id: str
    calculation_time: datetime
    
    # Trade details
    buy_execution: TradeExecution
    sell_execution: TradeExecution
    total_quantity: float
    
    # Gross profit
    gross_revenue: float      # Sell proceeds
    gross_cost: float        # Buy cost
    gross_profit: float      # Before fees and costs
    
    # Costs
    total_fees: float        # All exchange fees
    estimated_slippage: float # Price impact costs
    funding_cost: float      # Futures funding cost (if applicable)
    execution_cost: float    # Network/infrastructure costs
    
    # Net profit
    net_profit: float        # After all costs
    net_profit_pct: float    # As percentage of capital deployed
    
    # Risk metrics
    max_drawdown_risk: float # Maximum potential loss
    execution_risk_score: float  # 0-1 scale of execution risk
    capital_required: float  # Total capital needed for trade
    
    # Performance metrics
    roi_annualized: Optional[float] = None  # Annualized ROI if duration known
    sharpe_ratio: Optional[float] = None    # Risk-adjusted return
    profit_per_unit_risk: float = 0.0      # Profit / risk ratio


class PnLCalculator:
    """
    Advanced P&L calculator for NEIROETH arbitrage strategies.
    
    Provides accurate profit estimation accounting for all trading costs
    and market conditions. Optimized for high-frequency decision making.
    """
    
    # Exchange fee schedules (as of implementation date)
    EXCHANGE_FEES = {
        'GATEIO_SPOT': ExchangeFees(
            exchange='GATEIO_SPOT',
            maker_fee=0.002,  # 0.2%
            taker_fee=0.002   # 0.2%
        ),
        'GATEIO_FUTURES': ExchangeFees(
            exchange='GATEIO_FUTURES', 
            maker_fee=0.0002,  # 0.02%
            taker_fee=0.0005,  # 0.05%
            futures_fee=0.00075
        ),
        'MEXC_SPOT': ExchangeFees(
            exchange='MEXC_SPOT',
            maker_fee=0.0,  # 0.0%
            taker_fee=0.0005   # 0.05%
        )
    }
    
    # Slippage estimation parameters
    SLIPPAGE_FACTORS = {
        'low_liquidity': 0.001,    # 0.1% for thin order books
        'medium_liquidity': 0.0005, # 0.05% for normal conditions
        'high_liquidity': 0.0002    # 0.02% for deep order books
    }
    
    # Risk assessment parameters
    BASE_EXECUTION_RISK = 0.1  # 10% base execution risk
    CROSS_EXCHANGE_RISK_PREMIUM = 0.05  # 5% additional risk for cross-exchange
    
    def __init__(self):
        self.logger = logger.getChild("PnLCalculator")
        self._current_funding_rates: Dict[str, float] = {}
    
    async def calculate_arbitrage_pnl(
        self,
        opportunity: SpreadOpportunity,
        quantity: float,
        execution_speed: str = 'fast'  # 'fast', 'medium', 'slow'
    ) -> Optional[ArbitragePnL]:
        """
        Calculate complete P&L for an arbitrage opportunity.
        
        Args:
            opportunity: SpreadOpportunity to analyze
            quantity: Trade quantity in base asset
            execution_speed: Execution speed assumption for slippage
            
        Returns:
            ArbitragePnL with comprehensive profit analysis
        """
        if quantity <= 0:
            self.logger.error("Quantity must be positive")
            return None
            
        # Validate opportunity
        if not self._validate_opportunity(opportunity):
            return None
            
        # Determine execution parameters
        buy_fee_rate, sell_fee_rate = self._get_fee_rates(opportunity)
        slippage_rate = self._estimate_slippage(quantity, execution_speed, opportunity)
        
        # Calculate trade executions
        buy_execution = self._calculate_buy_execution(
            opportunity, quantity, buy_fee_rate, slippage_rate
        )
        
        sell_execution = self._calculate_sell_execution(
            opportunity, quantity, sell_fee_rate, slippage_rate
        )
        
        # Calculate gross profit
        gross_revenue = sell_execution.quantity * sell_execution.price
        gross_cost = buy_execution.quantity * buy_execution.price
        gross_profit = gross_revenue - gross_cost
        
        # Calculate all costs
        total_fees = buy_execution.fee_amount + sell_execution.fee_amount
        estimated_slippage = (buy_execution.slippage + sell_execution.slippage) * quantity
        funding_cost = await self._calculate_funding_cost(opportunity, quantity)
        execution_cost = self._estimate_execution_costs(opportunity, quantity)
        
        # Net profit calculation
        total_costs = total_fees + estimated_slippage + funding_cost + execution_cost
        net_profit = gross_profit - total_costs
        
        # Capital requirements
        capital_required = max(gross_cost, gross_revenue)  # Maximum capital needed
        net_profit_pct = (net_profit / capital_required) * 100 if capital_required > 0 else 0
        
        # Risk assessment
        max_drawdown_risk = self._calculate_max_drawdown_risk(opportunity, quantity)
        execution_risk_score = self._assess_execution_risk(opportunity, execution_speed)
        profit_per_unit_risk = net_profit / max_drawdown_risk if max_drawdown_risk > 0 else 0
        
        # Performance metrics
        roi_annualized = self._calculate_annualized_roi(net_profit_pct, opportunity.duration_estimate)
        sharpe_ratio = self._calculate_sharpe_ratio(net_profit, max_drawdown_risk)
        
        pnl = ArbitragePnL(
            opportunity_id=f"{opportunity.opportunity_type}_{opportunity.timestamp.isoformat()}",
            calculation_time=datetime.utcnow(),
            buy_execution=buy_execution,
            sell_execution=sell_execution,
            total_quantity=quantity,
            gross_revenue=gross_revenue,
            gross_cost=gross_cost,
            gross_profit=gross_profit,
            total_fees=total_fees,
            estimated_slippage=estimated_slippage,
            funding_cost=funding_cost,
            execution_cost=execution_cost,
            net_profit=net_profit,
            net_profit_pct=net_profit_pct,
            max_drawdown_risk=max_drawdown_risk,
            execution_risk_score=execution_risk_score,
            capital_required=capital_required,
            roi_annualized=roi_annualized,
            sharpe_ratio=sharpe_ratio,
            profit_per_unit_risk=profit_per_unit_risk
        )
        
        self.logger.debug(f"Calculated P&L for {opportunity.opportunity_type}: "
                         f"net_profit=${net_profit:.4f} ({net_profit_pct:.2f}%), "
                         f"risk_score={execution_risk_score:.2f}")
        
        return pnl
    
    async def estimate_portfolio_impact(
        self,
        opportunities: List[SpreadOpportunity],
        portfolio_size: float,
        max_position_pct: float = 10.0
    ) -> Dict[str, float]:
        """
        Estimate portfolio-level impact of multiple arbitrage opportunities.
        
        Args:
            opportunities: List of opportunities to analyze
            portfolio_size: Total portfolio value in USDT
            max_position_pct: Maximum percentage per position (10% default)
            
        Returns:
            Portfolio impact analysis
        """
        if not opportunities:
            return {}
            
        max_position_size = portfolio_size * (max_position_pct / 100)
        
        total_profit = 0.0
        total_risk = 0.0
        total_capital_required = 0.0
        opportunity_count = 0
        
        for opportunity in opportunities:
            # Calculate position size based on opportunity and limits
            position_size = min(
                max_position_size / opportunity.buy_price,  # Based on max position
                opportunity.max_quantity * 0.5  # Conservative size vs available liquidity
            )
            
            if position_size <= 0:
                continue
                
            pnl = await self.calculate_arbitrage_pnl(opportunity, position_size)
            if pnl:
                total_profit += pnl.net_profit
                total_risk += pnl.max_drawdown_risk
                total_capital_required += pnl.capital_required
                opportunity_count += 1
        
        return {
            'total_opportunities': opportunity_count,
            'total_estimated_profit': total_profit,
            'total_risk_exposure': total_risk,
            'total_capital_required': total_capital_required,
            'capital_utilization_pct': (total_capital_required / portfolio_size) * 100 if portfolio_size > 0 else 0,
            'portfolio_profit_pct': (total_profit / portfolio_size) * 100 if portfolio_size > 0 else 0,
            'risk_adjusted_return': total_profit / total_risk if total_risk > 0 else 0,
            'average_profit_per_trade': total_profit / opportunity_count if opportunity_count > 0 else 0
        }
    
    def update_funding_rates(self, funding_rates: Dict[str, float]):
        """Update current funding rates for futures calculations."""
        self._current_funding_rates.update(funding_rates)
        self.logger.debug(f"Updated funding rates: {funding_rates}")
    
    def _validate_opportunity(self, opportunity: SpreadOpportunity) -> bool:
        """Validate opportunity has required data for P&L calculation."""
        required_fields = [
            opportunity.buy_exchange, opportunity.sell_exchange,
            opportunity.buy_price, opportunity.sell_price, opportunity.spread_abs
        ]
        
        if not all(required_fields):
            self.logger.error("Opportunity missing required fields")
            return False
            
        if opportunity.buy_price <= 0 or opportunity.sell_price <= 0:
            self.logger.error("Invalid prices in opportunity")
            return False
            
        return True
    
    def _get_fee_rates(self, opportunity: SpreadOpportunity) -> Tuple[float, float]:
        """Get fee rates for buy and sell exchanges."""
        buy_fees = self.EXCHANGE_FEES.get(opportunity.buy_exchange)
        sell_fees = self.EXCHANGE_FEES.get(opportunity.sell_exchange)
        
        # Default to taker fees (worst case) if not found
        buy_rate = buy_fees.taker_fee if buy_fees else 0.002
        sell_rate = sell_fees.taker_fee if sell_fees else 0.002
        
        return buy_rate, sell_rate
    
    def _estimate_slippage(
        self, 
        quantity: float, 
        execution_speed: str, 
        opportunity: SpreadOpportunity
    ) -> float:
        """Estimate slippage based on quantity and market conditions."""
        base_slippage = self.SLIPPAGE_FACTORS['medium_liquidity']
        
        # Adjust for execution speed
        speed_multipliers = {'fast': 1.5, 'medium': 1.0, 'slow': 0.7}
        speed_factor = speed_multipliers.get(execution_speed, 1.0)
        
        # Adjust for liquidity (based on max_quantity)
        if opportunity.max_quantity > 0:
            liquidity_ratio = quantity / opportunity.max_quantity
            if liquidity_ratio > 0.5:  # Using more than 50% of available liquidity
                liquidity_factor = 1.0 + (liquidity_ratio - 0.5) * 2  # Increase slippage
            else:
                liquidity_factor = 1.0
        else:
            liquidity_factor = 2.0  # Unknown liquidity, assume high slippage
        
        return base_slippage * speed_factor * liquidity_factor
    
    def _calculate_buy_execution(
        self,
        opportunity: SpreadOpportunity,
        quantity: float,
        fee_rate: float,
        slippage_rate: float
    ) -> TradeExecution:
        """Calculate buy-side execution details."""
        # Apply slippage to price (buy at higher price due to slippage)
        execution_price = opportunity.buy_price * (1 + slippage_rate)
        
        # Calculate fee
        notional_value = quantity * execution_price
        fee_amount = notional_value * fee_rate
        
        return TradeExecution(
            exchange=opportunity.buy_exchange,
            side='buy',
            symbol='NEIROETH/USDT',
            quantity=quantity,
            price=execution_price,
            fee_rate=fee_rate,
            fee_amount=fee_amount,
            slippage=opportunity.buy_price * slippage_rate,  # Absolute slippage cost
            timestamp=datetime.utcnow()
        )
    
    def _calculate_sell_execution(
        self,
        opportunity: SpreadOpportunity,
        quantity: float,
        fee_rate: float,
        slippage_rate: float
    ) -> TradeExecution:
        """Calculate sell-side execution details."""
        # Apply slippage to price (sell at lower price due to slippage)
        execution_price = opportunity.sell_price * (1 - slippage_rate)
        
        # Calculate fee
        notional_value = quantity * execution_price
        fee_amount = notional_value * fee_rate
        
        return TradeExecution(
            exchange=opportunity.sell_exchange,
            side='sell',
            symbol='NEIROETH/USDT',
            quantity=quantity,
            price=execution_price,
            fee_rate=fee_rate,
            fee_amount=fee_amount,
            slippage=opportunity.sell_price * slippage_rate,  # Absolute slippage cost
            timestamp=datetime.utcnow()
        )
    
    async def _calculate_funding_cost(
        self, 
        opportunity: SpreadOpportunity, 
        quantity: float
    ) -> float:
        """Calculate funding cost for futures positions."""
        if opportunity.opportunity_type != 'delta_neutral':
            return 0.0
            
        # Get current funding rate for futures
        futures_exchange = None
        if 'FUTURES' in opportunity.buy_exchange:
            futures_exchange = opportunity.buy_exchange
        elif 'FUTURES' in opportunity.sell_exchange:
            futures_exchange = opportunity.sell_exchange
            
        if not futures_exchange:
            return 0.0
            
        funding_rate = self._current_funding_rates.get(futures_exchange, 0.0001)  # Default 0.01%
        
        # Funding is paid every 8 hours, calculate for expected holding period
        holding_hours = (opportunity.duration_estimate or 60) / 3600  # Convert seconds to hours
        funding_periods = holding_hours / 8
        
        notional_value = quantity * opportunity.buy_price
        funding_cost = notional_value * funding_rate * funding_periods
        
        return abs(funding_cost)  # Always a cost for arbitrage
    
    def _estimate_execution_costs(self, opportunity: SpreadOpportunity, quantity: float) -> float:
        """Estimate additional execution costs (network fees, etc.)."""
        # Base cost per trade
        base_cost = 1.0  # $1 base execution cost
        
        # Add cost for cross-exchange complexity
        if opportunity.buy_exchange != opportunity.sell_exchange:
            base_cost += 0.5  # Additional $0.50 for cross-exchange coordination
            
        # Scale with trade size (larger trades have relatively lower fixed costs)
        notional_value = quantity * opportunity.buy_price
        if notional_value > 1000:  # For trades > $1000
            size_factor = min(1.0, 1000 / notional_value)  # Reduce relative cost for larger trades
            base_cost *= size_factor
            
        return base_cost
    
    def _calculate_max_drawdown_risk(self, opportunity: SpreadOpportunity, quantity: float) -> float:
        """Calculate maximum potential loss from execution risks."""
        notional_value = quantity * opportunity.buy_price
        
        # Base execution risk
        base_risk = notional_value * self.BASE_EXECUTION_RISK
        
        # Additional risk for cross-exchange trades
        if opportunity.buy_exchange != opportunity.sell_exchange:
            cross_exchange_risk = notional_value * self.CROSS_EXCHANGE_RISK_PREMIUM
        else:
            cross_exchange_risk = 0.0
            
        # Market volatility risk (based on spread volatility)
        volatility_risk = notional_value * (opportunity.spread_pct / 100) * 0.5  # 50% of spread as risk
        
        return base_risk + cross_exchange_risk + volatility_risk
    
    def _assess_execution_risk(self, opportunity: SpreadOpportunity, execution_speed: str) -> float:
        """Assess execution risk score (0-1 scale)."""
        risk_score = self.BASE_EXECUTION_RISK
        
        # Add risk for cross-exchange complexity
        if opportunity.buy_exchange != opportunity.sell_exchange:
            risk_score += self.CROSS_EXCHANGE_RISK_PREMIUM
            
        # Adjust for execution speed
        speed_risk_factors = {'fast': 1.2, 'medium': 1.0, 'slow': 0.8}
        risk_score *= speed_risk_factors.get(execution_speed, 1.0)
        
        # Adjust for opportunity confidence
        if hasattr(opportunity, 'confidence_score') and opportunity.confidence_score:
            risk_score *= (1.0 - opportunity.confidence_score * 0.3)  # Max 30% reduction
            
        return min(1.0, risk_score)  # Cap at 100%
    
    def _calculate_annualized_roi(self, profit_pct: float, duration_seconds: Optional[float]) -> Optional[float]:
        """Calculate annualized ROI if duration is known."""
        if not duration_seconds or duration_seconds <= 0:
            return None
            
        # Convert to annual basis
        seconds_per_year = 365.25 * 24 * 3600
        annualization_factor = seconds_per_year / duration_seconds
        
        return profit_pct * annualization_factor
    
    def _calculate_sharpe_ratio(self, profit: float, risk: float) -> Optional[float]:
        """Calculate Sharpe ratio for risk-adjusted returns."""
        if risk <= 0:
            return None
            
        # Simplified Sharpe calculation (assuming zero risk-free rate)
        return profit / risk