"""
Real-Time Risk Monitoring System for Delta-Neutral Strategy
Critical safety mechanisms for low-liquidity crypto markets
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np
from collections import deque


class RiskLevel(Enum):
    """Risk alert levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Position:
    """Active trading position"""
    id: str
    symbol: str
    spot_exchange: str
    futures_exchange: str
    spot_size: float
    futures_size: float
    spot_entry_price: float
    futures_entry_price: float
    entry_time: datetime
    target_spread_bps: float
    max_loss_usd: float
    hedge_ratio: float = 1.0
    
    @property
    def age_hours(self) -> float:
        return (datetime.now() - self.entry_time).total_seconds() / 3600
    
    @property
    def total_size_usd(self) -> float:
        return abs(self.spot_size * self.spot_entry_price)


@dataclass
class RiskAlert:
    """Risk monitoring alert"""
    timestamp: datetime
    level: RiskLevel
    position_id: str
    symbol: str
    alert_type: str
    message: str
    recommended_action: str
    data: Dict = field(default_factory=dict)


@dataclass
class MarketSnapshot:
    """Current market state for a symbol"""
    symbol: str
    spot_bid: float
    spot_ask: float
    spot_bid_qty: float
    spot_ask_qty: float
    futures_bid: float
    futures_ask: float
    futures_bid_qty: float
    futures_ask_qty: float
    timestamp: datetime
    
    @property
    def spot_mid(self) -> float:
        return (self.spot_bid + self.spot_ask) / 2
    
    @property
    def futures_mid(self) -> float:
        return (self.futures_bid + self.futures_ask) / 2
    
    @property
    def spread_bps(self) -> float:
        return (self.futures_mid - self.spot_mid) / self.spot_mid * 10000
    
    @property
    def exit_liquidity_usd(self) -> float:
        """Estimate available exit liquidity"""
        return min(
            self.spot_bid_qty * self.spot_bid,
            self.futures_ask_qty * self.futures_ask
        )


class RiskMonitor:
    """
    Real-time risk monitoring system for delta-neutral positions
    Designed for low-liquidity crypto market safety
    """
    
    def __init__(self, max_total_exposure_usd: float = 100000,
                 max_position_age_hours: float = 24,
                 min_exit_liquidity_ratio: float = 0.5):
        """Initialize risk monitor with safety parameters"""
        
        # Risk limits
        self.max_total_exposure_usd = max_total_exposure_usd
        self.max_position_age_hours = max_position_age_hours
        self.min_exit_liquidity_ratio = min_exit_liquidity_ratio
        self.max_correlation_deviation = 0.05  # Max 5% correlation breakdown
        self.max_hedge_ratio_drift = 0.1  # Max 10% hedge ratio drift
        
        # State tracking
        self.positions: Dict[str, Position] = {}
        self.market_snapshots: Dict[str, MarketSnapshot] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.correlation_buffer: Dict[str, deque] = {}
        self.volatility_buffer: Dict[str, deque] = {}
        
        # Alert callbacks
        self.alert_callbacks: List[Callable[[RiskAlert], None]] = []
        
        # Circuit breaker state
        self.emergency_stop = False
        self.emergency_reason = ""
        
        # Performance tracking
        self.risk_check_times = deque(maxlen=100)
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def add_position(self, position: Position) -> None:
        """Add position to monitoring"""
        self.positions[position.id] = position
        
        # Initialize buffers for this symbol
        if position.symbol not in self.correlation_buffer:
            self.correlation_buffer[position.symbol] = deque(maxlen=100)
            self.volatility_buffer[position.symbol] = deque(maxlen=100)
        
        self.logger.info(f"Added position {position.id} for {position.symbol}")
    
    def remove_position(self, position_id: str) -> None:
        """Remove position from monitoring"""
        if position_id in self.positions:
            position = self.positions.pop(position_id)
            self.logger.info(f"Removed position {position_id} for {position.symbol}")
    
    def update_market_data(self, snapshot: MarketSnapshot) -> None:
        """Update market data and trigger risk checks"""
        self.market_snapshots[snapshot.symbol] = snapshot
        
        # Update correlation tracking
        if snapshot.symbol in self.correlation_buffer:
            self.correlation_buffer[snapshot.symbol].append(
                (snapshot.spot_mid, snapshot.futures_mid, snapshot.timestamp)
            )
        
        # Trigger risk checks for affected positions
        for position in self.positions.values():
            if position.symbol == snapshot.symbol:
                self._check_position_risks(position, snapshot)
    
    def emergency_shutdown(self, reason: str) -> None:
        """Trigger emergency stop for all positions"""
        self.emergency_stop = True
        self.emergency_reason = reason
        
        alert = RiskAlert(
            timestamp=datetime.now(),
            level=RiskLevel.CRITICAL,
            position_id="ALL",
            symbol="ALL",
            alert_type="EMERGENCY_STOP",
            message=f"Emergency shutdown triggered: {reason}",
            recommended_action="CLOSE_ALL_POSITIONS_IMMEDIATELY",
            data={'reason': reason, 'active_positions': len(self.positions)}
        )
        
        self._trigger_alert(alert)
        self.logger.critical(f"EMERGENCY STOP: {reason}")
    
    def get_portfolio_risk_summary(self) -> Dict:
        """Get comprehensive portfolio risk assessment"""
        start_time = datetime.now()
        
        total_exposure = sum(pos.total_size_usd for pos in self.positions.values())
        
        # Risk score calculation (0-100)
        risk_score = 0
        risk_factors = []
        
        # Exposure risk
        exposure_ratio = total_exposure / self.max_total_exposure_usd
        if exposure_ratio > 0.8:
            risk_score += 30
            risk_factors.append(f"High exposure: {exposure_ratio:.1%}")
        
        # Position concentration
        if self.positions:
            max_position_ratio = max(pos.total_size_usd for pos in self.positions.values()) / total_exposure
            if max_position_ratio > 0.3:
                risk_score += 20
                risk_factors.append(f"Position concentration: {max_position_ratio:.1%}")
        
        # Stale positions
        stale_positions = [p for p in self.positions.values() if p.age_hours > self.max_position_age_hours * 0.8]
        if stale_positions:
            risk_score += len(stale_positions) * 10
            risk_factors.append(f"Stale positions: {len(stale_positions)}")
        
        # Liquidity risk
        low_liquidity_positions = 0
        for position in self.positions.values():
            snapshot = self.market_snapshots.get(position.symbol)
            if snapshot and snapshot.exit_liquidity_usd < position.total_size_usd * self.min_exit_liquidity_ratio:
                low_liquidity_positions += 1
        
        if low_liquidity_positions > 0:
            risk_score += low_liquidity_positions * 15
            risk_factors.append(f"Low liquidity positions: {low_liquidity_positions}")
        
        # Emergency state
        if self.emergency_stop:
            risk_score = 100
            risk_factors.append("EMERGENCY STOP ACTIVE")
        
        # Performance tracking
        check_time = (datetime.now() - start_time).total_seconds() * 1000
        self.risk_check_times.append(check_time)
        
        return {
            'timestamp': datetime.now(),
            'risk_score': min(risk_score, 100),
            'risk_level': self._get_risk_level(risk_score),
            'total_exposure_usd': total_exposure,
            'exposure_ratio': exposure_ratio,
            'active_positions': len(self.positions),
            'risk_factors': risk_factors,
            'emergency_stop': self.emergency_stop,
            'emergency_reason': self.emergency_reason,
            'avg_check_time_ms': np.mean(self.risk_check_times) if self.risk_check_times else 0
        }
    
    def _check_position_risks(self, position: Position, snapshot: MarketSnapshot) -> None:
        """Comprehensive position-level risk checking"""
        
        # 1. Age risk
        if position.age_hours > self.max_position_age_hours:
            self._trigger_alert(RiskAlert(
                timestamp=datetime.now(),
                level=RiskLevel.HIGH,
                position_id=position.id,
                symbol=position.symbol,
                alert_type="POSITION_AGE",
                message=f"Position exceeds max age: {position.age_hours:.1f} hours",
                recommended_action="CLOSE_POSITION",
                data={'age_hours': position.age_hours, 'max_age': self.max_position_age_hours}
            ))
        
        # 2. Exit liquidity risk
        exit_liquidity_ratio = snapshot.exit_liquidity_usd / position.total_size_usd
        if exit_liquidity_ratio < self.min_exit_liquidity_ratio:
            level = RiskLevel.CRITICAL if exit_liquidity_ratio < 0.2 else RiskLevel.HIGH
            self._trigger_alert(RiskAlert(
                timestamp=datetime.now(),
                level=level,
                position_id=position.id,
                symbol=position.symbol,
                alert_type="LIQUIDITY_RISK",
                message=f"Insufficient exit liquidity: {exit_liquidity_ratio:.1%}",
                recommended_action="REDUCE_POSITION" if exit_liquidity_ratio > 0.2 else "EMERGENCY_EXIT",
                data={
                    'exit_liquidity_usd': snapshot.exit_liquidity_usd,
                    'position_size_usd': position.total_size_usd,
                    'liquidity_ratio': exit_liquidity_ratio
                }
            ))
        
        # 3. Spread risk
        current_spread = snapshot.spread_bps
        spread_change = current_spread - position.target_spread_bps
        
        if abs(spread_change) > 200:  # Spread moved >200 bps against us
            self._trigger_alert(RiskAlert(
                timestamp=datetime.now(),
                level=RiskLevel.MEDIUM,
                position_id=position.id,
                symbol=position.symbol,
                alert_type="SPREAD_RISK",
                message=f"Large spread movement: {spread_change:+.1f} bps from target",
                recommended_action="MONITOR_CLOSELY",
                data={
                    'current_spread_bps': current_spread,
                    'target_spread_bps': position.target_spread_bps,
                    'spread_change_bps': spread_change
                }
            ))
        
        # 4. Correlation breakdown
        correlation = self._calculate_spot_futures_correlation(position.symbol)
        if correlation and correlation < (1.0 - self.max_correlation_deviation):
            self._trigger_alert(RiskAlert(
                timestamp=datetime.now(),
                level=RiskLevel.HIGH,
                position_id=position.id,
                symbol=position.symbol,
                alert_type="CORRELATION_BREAKDOWN",
                message=f"Spot-futures correlation breakdown: {correlation:.3f}",
                recommended_action="CLOSE_POSITION",
                data={'correlation': correlation, 'min_correlation': 1.0 - self.max_correlation_deviation}
            ))
        
        # 5. Hedge ratio drift
        current_ratio = abs(position.futures_size / position.spot_size)
        hedge_drift = abs(current_ratio - position.hedge_ratio) / position.hedge_ratio
        
        if hedge_drift > self.max_hedge_ratio_drift:
            self._trigger_alert(RiskAlert(
                timestamp=datetime.now(),
                level=RiskLevel.MEDIUM,
                position_id=position.id,
                symbol=position.symbol,
                alert_type="HEDGE_DRIFT",
                message=f"Hedge ratio drift: {hedge_drift:.1%}",
                recommended_action="REBALANCE_HEDGE",
                data={
                    'current_ratio': current_ratio,
                    'target_ratio': position.hedge_ratio,
                    'drift_pct': hedge_drift * 100
                }
            ))
        
        # 6. Unrealized PnL risk
        unrealized_pnl = self._calculate_unrealized_pnl(position, snapshot)
        loss_ratio = abs(unrealized_pnl) / position.total_size_usd if unrealized_pnl < 0 else 0
        
        if loss_ratio > 0.05:  # >5% loss
            level = RiskLevel.CRITICAL if loss_ratio > 0.10 else RiskLevel.HIGH
            self._trigger_alert(RiskAlert(
                timestamp=datetime.now(),
                level=level,
                position_id=position.id,
                symbol=position.symbol,
                alert_type="UNREALIZED_LOSS",
                message=f"Large unrealized loss: {loss_ratio:.1%}",
                recommended_action="CLOSE_POSITION" if loss_ratio > 0.08 else "REVIEW_POSITION",
                data={
                    'unrealized_pnl_usd': unrealized_pnl,
                    'loss_ratio': loss_ratio,
                    'position_size_usd': position.total_size_usd
                }
            ))
    
    def _calculate_spot_futures_correlation(self, symbol: str, window: int = 50) -> Optional[float]:
        """Calculate rolling correlation between spot and futures prices"""
        if symbol not in self.correlation_buffer:
            return None
        
        buffer = self.correlation_buffer[symbol]
        if len(buffer) < window:
            return None
        
        spot_prices = [x[0] for x in list(buffer)[-window:]]
        futures_prices = [x[1] for x in list(buffer)[-window:]]
        
        return np.corrcoef(spot_prices, futures_prices)[0, 1]
    
    def _calculate_unrealized_pnl(self, position: Position, snapshot: MarketSnapshot) -> float:
        """Calculate current unrealized PnL for position"""
        # Spot PnL (long position)
        spot_pnl = (snapshot.spot_mid - position.spot_entry_price) * position.spot_size
        
        # Futures PnL (short position) 
        futures_pnl = (position.futures_entry_price - snapshot.futures_mid) * position.futures_size
        
        return spot_pnl + futures_pnl
    
    def _get_risk_level(self, risk_score: int) -> RiskLevel:
        """Convert risk score to risk level"""
        if risk_score >= 80:
            return RiskLevel.CRITICAL
        elif risk_score >= 60:
            return RiskLevel.HIGH
        elif risk_score >= 30:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _trigger_alert(self, alert: RiskAlert) -> None:
        """Trigger risk alert and notify callbacks"""
        self.alert_history.append(alert)
        
        # Log alert
        level_name = alert.level.name
        self.logger.warning(f"RISK ALERT [{level_name}] {alert.alert_type}: {alert.message}")
        
        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Alert callback failed: {e}")
    
    def add_alert_callback(self, callback: Callable[[RiskAlert], None]) -> None:
        """Add callback for risk alerts"""
        self.alert_callbacks.append(callback)
    
    def get_recent_alerts(self, hours: int = 1) -> List[RiskAlert]:
        """Get alerts from the last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alert_history if alert.timestamp > cutoff]


# Example usage and testing
if __name__ == "__main__":
    
    def alert_handler(alert: RiskAlert):
        """Example alert handler"""
        print(f"ALERT: {alert.level.name} - {alert.message}")
        if alert.level == RiskLevel.CRITICAL:
            print(f"RECOMMENDED ACTION: {alert.recommended_action}")
    
    # Initialize monitor
    monitor = RiskMonitor(max_total_exposure_usd=50000)
    monitor.add_alert_callback(alert_handler)
    
    # Add sample position
    position = Position(
        id="pos_001",
        symbol="BTC",
        spot_exchange="binance",
        futures_exchange="binance",
        spot_size=1.0,
        futures_size=-1.0,
        spot_entry_price=45000,
        futures_entry_price=45100,
        entry_time=datetime.now() - timedelta(hours=2),
        target_spread_bps=100,
        max_loss_usd=1000
    )
    
    monitor.add_position(position)
    
    # Simulate market data update
    snapshot = MarketSnapshot(
        symbol="BTC",
        spot_bid=44800,
        spot_ask=44820,
        spot_bid_qty=0.5,
        spot_ask_qty=0.3,
        futures_bid=44900,
        futures_ask=44920,
        futures_bid_qty=0.8,
        futures_ask_qty=0.6,
        timestamp=datetime.now()
    )
    
    monitor.update_market_data(snapshot)
    
    # Get risk summary
    summary = monitor.get_portfolio_risk_summary()
    print(f"Portfolio Risk Summary: {summary}")
    
    # Test emergency stop
    # monitor.emergency_shutdown("Market volatility exceeded limits")