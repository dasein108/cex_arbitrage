"""
Arbitrage Data Loader - Pure data management without external dependencies.

Handles data loading for both backtesting and live trading modes.
All external data is passed as parameters to maintain zero dependencies.
"""

import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from exchanges.structs import Symbol, BookTicker


class ArbitrageDataLoader:
    """
    Pure data loader without external dependencies.
    Accepts all necessary data as parameters from calling code.
    """
    
    def __init__(self, symbol: Symbol, is_live_mode: bool = False):
        """
        Initialize data loader.
        
        Args:
            symbol: Trading symbol
            is_live_mode: True for live trading, False for backtesting
        """
        self.symbol = symbol
        self.is_live_mode = is_live_mode
        # No external dependencies stored
    
    async def load_initial_data(self, days: int = 7) -> pd.DataFrame:
        """
        Load historical data from database for initial context.
        
        Args:
            days: Number of days of historical data to load
            
        Returns:
            Historical DataFrame with market data
        """
        try:
            # Use existing database operations - no external dependencies
            from trading.research.cross_arbitrage.book_ticker_source import BookTickerDbSource
            from exchanges.structs.enums import ExchangeEnum, KlineInterval
            
            # Initialize database connection
            from db import initialize_database_manager
            await initialize_database_manager()
            
            # Create book ticker source
            exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
            book_ticker_source = BookTickerDbSource()
            
            # Load multi-exchange data
            df = await book_ticker_source.get_multi_exchange_data(
                exchanges=exchanges,
                symbol=self.symbol,
                hours=round(days * 24),
                timeframe=KlineInterval.MINUTE_5
            )
            
            if df.empty:
                print(f"⚠️ No historical data found for {self.symbol} (last {days} days)")
                return pd.DataFrame()
            
            # Ensure consistent column naming
            df = self._standardize_columns(df)
            # df.fillna(method='ffill', inplace=True)
            df.dropna(inplace=True)
            print(f"✅ Loaded {len(df)} historical data points for {self.symbol}")
            return df
            
        except Exception as e:
            print(f"❌ Error loading historical data: {e}")
            return pd.DataFrame()
    
    def update_live_data(self, 
                        spot_book_tickers: Dict[str, BookTicker],
                        futures_book_ticker: BookTicker,
                        current_positions: Optional[Dict[str, float]] = None,
                        current_balances: Optional[Dict[str, float]] = None) -> dict:
        """
        Process live market data passed from outside.
        
        Args:
            spot_book_tickers: Dict of exchange_name -> BookTicker
            futures_book_ticker: Futures exchange BookTicker
            current_positions: Optional position data
            current_balances: Optional balance data
            
        Returns:
            Processed market data dict for signal generation
        """
        current_data = {
            'timestamp': pd.Timestamp.now(tz=timezone.utc),
            'spot_exchanges': {},
            'futures_exchange': {},
            'positions': current_positions or {},
            'balances': current_balances or {}
        }
        
        # Process spot exchanges
        for exchange_name, book_ticker in spot_book_tickers.items():
            if book_ticker:
                current_data['spot_exchanges'][exchange_name] = {
                    'bid_price': float(book_ticker.bid_price),
                    'ask_price': float(book_ticker.ask_price),
                    'bid_qty': float(book_ticker.bid_quantity),
                    'ask_qty': float(book_ticker.ask_quantity),
                    'spread_pct': self._calculate_spread_pct(book_ticker.bid_price, book_ticker.ask_price)
                }
        
        # Process futures exchange
        if futures_book_ticker:
            current_data['futures_exchange'] = {
                'bid_price': float(futures_book_ticker.bid_price),
                'ask_price': float(futures_book_ticker.ask_price),
                'bid_qty': float(futures_book_ticker.bid_quantity),
                'ask_qty': float(futures_book_ticker.ask_quantity),
                'spread_pct': self._calculate_spread_pct(futures_book_ticker.bid_price, futures_book_ticker.ask_price)
            }
        
        return current_data
    
    def format_for_indicators(self, market_data: dict) -> pd.Series:
        """
        Convert market data dict to pandas Series for indicator calculations.
        
        Args:
            market_data: Market data dict from update_live_data
            
        Returns:
            Flattened pandas Series suitable for indicator calculations
        """
        flattened_data = {}
        
        # Flatten nested dictionaries with prefixes
        for key, value in market_data.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, dict):
                        # Handle double nesting (like spot_exchanges)
                        for subsubkey, subsubvalue in subvalue.items():
                            flattened_data[f"{key}_{subkey}_{subsubkey}"] = subsubvalue
                    else:
                        flattened_data[f"{key}_{subkey}"] = subvalue
            else:
                flattened_data[key] = value
        
        return pd.Series(flattened_data)
    
    def _calculate_spread_pct(self, bid_price: float, ask_price: float) -> float:
        """Calculate spread percentage."""
        if bid_price <= 0:
            return 0.0
        return ((ask_price - bid_price) / bid_price) * 100
    
    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column naming for consistent processing.
        
        Args:
            df: Raw DataFrame from database
            
        Returns:
            DataFrame with standardized column names
        """
        # Map common column variations to standard names
        column_mapping = {
            # Timestamp columns
            'time': 'timestamp',
            'datetime': 'timestamp',
            
            # Price columns (spot exchanges)
            'mexc_bid': 'mexc_bid_price',
            'mexc_ask': 'mexc_ask_price',
            'gateio_bid': 'gateio_bid_price', 
            'gateio_ask': 'gateio_ask_price',
            
            # Quantity columns
            'mexc_bid_size': 'mexc_bid_qty',
            'mexc_ask_size': 'mexc_ask_qty',
            'gateio_bid_size': 'gateio_bid_qty',
            'gateio_ask_size': 'gateio_ask_qty',
            
            # Futures columns
            'futures_bid': 'futures_bid_price',
            'futures_ask': 'futures_ask_price',
            'futures_bid_size': 'futures_bid_qty',
            'futures_ask_size': 'futures_ask_qty'
        }
        
        # Apply mapping
        df = df.rename(columns=column_mapping)
        
        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    
    def validate_data_quality(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Validate data quality and return statistics.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Dict with data quality metrics
        """
        if df.empty:
            return {'valid': False, 'reason': 'Empty DataFrame'}
        
        quality_metrics = {
            'valid': True,
            'total_rows': len(df),
            'date_range': {
                'start': df['timestamp'].min() if 'timestamp' in df.columns else None,
                'end': df['timestamp'].max() if 'timestamp' in df.columns else None
            },
            'missing_data': df.isnull().sum().to_dict(),
            'zero_prices': {}
        }
        
        # Check for zero prices (data quality issue)
        price_columns = [col for col in df.columns if 'price' in col.lower()]
        for col in price_columns:
            if col in df.columns:
                zero_count = (df[col] == 0).sum()
                if zero_count > 0:
                    quality_metrics['zero_prices'][col] = zero_count
        
        # Overall validation
        total_missing = sum(quality_metrics['missing_data'].values())
        total_zeros = sum(quality_metrics['zero_prices'].values())
        
        if total_missing > len(df) * 0.1:  # More than 10% missing
            quality_metrics['valid'] = False
            quality_metrics['reason'] = f'Too much missing data: {total_missing} missing values'
        elif total_zeros > len(df) * 0.05:  # More than 5% zero prices
            quality_metrics['valid'] = False
            quality_metrics['reason'] = f'Too many zero prices: {total_zeros} zero price points'
        
        return quality_metrics