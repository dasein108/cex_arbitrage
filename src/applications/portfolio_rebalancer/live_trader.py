"""
Live trading implementation for portfolio rebalancing.
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from exchanges.structs import Symbol, Side, Order
from exchanges.structs.types import AssetName
from exchanges.dual_exchange import DualExchange
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from config.config_manager import HftConfig

from .config import RebalanceConfig
from .portfolio_tracker import PortfolioTracker
from .rebalancer import ThresholdCascadeRebalancer


class LiveRebalancer:
    """
    Live trading rebalancer using DualExchange interface.
    """
    
    def __init__(self, assets: List[str], config: Optional[RebalanceConfig] = None):
        """
        Initialize live rebalancer.
        
        Args:
            assets: List of asset symbols to trade
            config: Rebalancing configuration
        """
        self.assets = assets
        self.config = config or RebalanceConfig()
        
        # Initialize HFT config manager and DualExchange
        self.hft_config = HftConfig()
        self.mexc_config = self.hft_config.get_exchange_config('mexc')
        self.exchange = DualExchange.get_instance(self.mexc_config)
        
        # Create symbols
        self.symbols = [
            Symbol(base=AssetName(asset), quote=AssetName('USDT'))
            for asset in assets
        ]
        
        # Initialize tracker and rebalancer
        self.tracker = PortfolioTracker(assets, self.config.initial_capital, self.config)
        self.rebalancer = ThresholdCascadeRebalancer(assets, self.config, self.tracker)
        
        # Price tracking
        self.current_prices: Dict[str, float] = {}
        self.last_check = datetime.now()
        
        # Running state
        self.is_running = False
        
    async def initialize(self):
        """Initialize exchange connections and portfolio state."""
        print("Initializing exchange connections...")
        
        # Initialize exchange with symbols
        await self.exchange.initialize(
            symbols=self.symbols,
            public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
            private_channels=[
                PrivateWebsocketChannelType.ORDER,
                PrivateWebsocketChannelType.BALANCE
            ]
        )
        
        # Bind event handlers
        await self.exchange.bind_handlers(
            on_book_ticker=self._on_book_ticker,
            on_balance=self._on_balance_update,
            on_order=self._on_order_update
        )
        
        # Fetch initial balances
        await self._sync_portfolio_state()
        
        print("Initialization complete!")
    
    async def _on_book_ticker(self, book_ticker):
        """Handle incoming book ticker updates."""
        asset = book_ticker.symbol.base
        if asset in self.assets:
            # Use mid price
            mid_price = (book_ticker.bid_price + book_ticker.ask_price) / 2
            self.current_prices[asset] = mid_price
    
    async def _on_balance_update(self, balance):
        """Handle balance update events."""
        asset = balance.asset
        
        if asset == 'USDT':
            self.tracker.usdt_balance = balance.available
        elif asset in self.assets:
            self.tracker.positions[asset] = balance.available
    
    async def _on_order_update(self, order: Order):
        """Handle order update events."""
        if order.status in ['FILLED', 'PARTIALLY_FILLED']:
            print(f"Order {order.order_id} {order.status}: "
                  f"{order.side} {order.filled_quantity} {order.symbol.base} @ {order.price}")
    
    async def _sync_portfolio_state(self):
        """Synchronize portfolio state with exchange."""
        print("Syncing portfolio state...")
        
        # Get all balances
        balances = await self.exchange.private.get_balances()
        
        for balance in balances:
            asset = balance.asset
            
            if asset == 'USDT':
                self.tracker.usdt_balance = balance.available
                print(f"  USDT Balance: {balance.available:.2f}")
            elif asset in self.assets:
                self.tracker.positions[asset] = balance.available
                print(f"  {asset} Balance: {balance.available:.6f}")
    
    async def check_and_rebalance(self):
        """Check portfolio and execute rebalancing if needed."""
        # Wait for prices to be available
        if len(self.current_prices) < len(self.assets):
            return
        
        # Update portfolio state
        state = self.tracker.update_prices(self.current_prices, datetime.now())
        
        # Check for rebalancing
        event = self.rebalancer.execute_rebalance(state, self.current_prices)
        
        if event:
            print(f"\n=== Rebalancing Triggered ===")
            print(f"Trigger: {event.trigger_asset} deviation {event.trigger_deviation:.1%}")
            
            # Execute trades
            for action in event.actions:
                await self._execute_trade(action)
            
            print(f"Rebalancing complete! Fees paid: ${event.fees_paid:.2f}")
            
            # Re-sync state after trades
            await asyncio.sleep(2)  # Wait for trades to settle
            await self._sync_portfolio_state()
    
    async def _execute_trade(self, action):
        """
        Execute a single trade action.
        
        Args:
            action: RebalanceAction to execute
        """
        symbol = Symbol(base=AssetName(action.symbol), quote=AssetName('USDT'))
        
        try:
            if action.side == 'BUY':
                # Market buy using quote quantity
                order = await self.exchange.private.market_order(
                    symbol=symbol,
                    side=Side.BUY,
                    quote_quantity=action.value_usdt
                )
            else:  # SELL
                # Market sell using base quantity
                order = await self.exchange.private.market_order(
                    symbol=symbol,
                    side=Side.SELL,
                    quantity=action.quantity
                )
            
            print(f"  Executed: {action}")
            return order
            
        except Exception as e:
            print(f"  Failed to execute {action.side} {action.symbol}: {e}")
            return None
    
    async def run_forever(self, check_interval: int = 60):
        """
        Run rebalancing loop forever.
        
        Args:
            check_interval: Seconds between rebalance checks
        """
        self.is_running = True
        print(f"Starting rebalancing loop (checking every {check_interval}s)...")
        
        while self.is_running:
            try:
                # Check and rebalance
                await self.check_and_rebalance()
                
                # Display portfolio status
                if datetime.now().minute % 5 == 0:  # Every 5 minutes
                    self._print_portfolio_status()
                
                # Wait for next check
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                print(f"Error in rebalancing loop: {e}")
                await asyncio.sleep(check_interval)
    
    def _print_portfolio_status(self):
        """Print current portfolio status."""
        if not self.tracker.portfolio_history:
            return
        
        state = self.tracker.portfolio_history[-1]
        metrics = self.tracker.get_portfolio_metrics()
        
        print(f"\n=== Portfolio Status [{datetime.now().strftime('%H:%M:%S')}] ===")
        print(f"Total Value: ${state.total_value:.2f} ({metrics['total_return']:+.2%})")
        print(f"USDT Reserve: ${self.tracker.usdt_balance:.2f}")
        
        print("\nAsset Positions:")
        for asset, asset_state in state.assets.items():
            print(f"  {asset}: {asset_state.quantity:.6f} @ ${asset_state.current_price:.4f} "
                  f"= ${asset_state.value_usdt:.2f} ({asset_state.weight:.1%}) "
                  f"[{asset_state.deviation:+.1%}]")
        
        stats = self.rebalancer.get_statistics()
        print(f"\nRebalancing Stats:")
        print(f"  Total Events: {stats['total_events']}")
        print(f"  Total Volume: ${stats['total_volume']:.2f}")
        print(f"  Total Fees: ${stats['total_fees']:.2f}")
    
    async def stop(self):
        """Stop the rebalancing loop."""
        self.is_running = False
        await self.exchange.close()
        print("Rebalancer stopped.")
    
    async def initialize_portfolio(self):
        """
        Initialize portfolio with equal weights.
        
        This should be called once when starting with a new portfolio.
        """
        print("\n=== Initializing Portfolio with Equal Weights ===")
        
        # Get current prices
        for symbol in self.symbols:
            orderbook = await self.exchange.public.get_orderbook(symbol, limit=5)
            mid_price = (orderbook.bids[0].price + orderbook.asks[0].price) / 2
            self.current_prices[symbol.base] = mid_price
            print(f"  {symbol.base}: ${mid_price:.4f}")
        
        # Calculate allocation
        usdt_balance = self.tracker.usdt_balance
        usdt_reserve = usdt_balance * self.config.usdt_reserve
        available_capital = usdt_balance - usdt_reserve
        per_asset_value = available_capital / len(self.assets)
        
        print(f"\nAllocation Plan:")
        print(f"  Total USDT: ${usdt_balance:.2f}")
        print(f"  Reserve (30%): ${usdt_reserve:.2f}")
        print(f"  To Invest: ${available_capital:.2f}")
        print(f"  Per Asset: ${per_asset_value:.2f}")
        
        # Execute initial purchases
        for asset in self.assets:
            symbol = Symbol(base=AssetName(asset), quote=AssetName('USDT'))
            
            try:
                order = await self.exchange.private.market_order(
                    symbol=symbol,
                    side=Side.BUY,
                    quote_quantity=per_asset_value
                )
                print(f"  Bought {asset}: Order {order.order_id}")
                
            except Exception as e:
                print(f"  Failed to buy {asset}: {e}")
            
            await asyncio.sleep(1)  # Small delay between orders
        
        # Sync final state
        await asyncio.sleep(3)
        await self._sync_portfolio_state()
        
        print("\nPortfolio initialization complete!")