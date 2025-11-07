
import pickle
from datetime import datetime, UTC
from pathlib import Path
from typing import  List, Optional
import pandas as pd

# Import exchange factory for simplified factory pattern
from config.config_manager import HftConfig
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from exchanges.structs.common import Symbol, Kline
from exchanges.exchange_factory import get_rest_implementation
from infrastructure.logging import HFTLoggerInterface
from infrastructure.logging.factory import get_logger
from utils.kline_utils import kline_interval_to_timeframe, round_datetime_to_interval
import asyncio
from trading.data_sources.column_utils import get_column_key
# Import exchange modules to trigger auto-registration


class CandlesLoader:
    """
    Multi-exchange candles downloader with unified CSV output format.
    
    Supports downloading historical candlestick data from multiple exchanges
    with consistent output format and comprehensive error handling.
    """
    
    def __init__(self, output_dir: str = "klines", logger: HFTLoggerInterface = None):
        """
        Initialize the candles downloader.
        
        Args:
            output_dir: Directory to save CSV files (default: data)
        """
        self.cache_dir = HftConfig.cache_dir / output_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or get_logger(__name__)
        # Initialize configuration manager
        self.config = HftConfig()
        
        self.logger.info(f"CandlesDownloader initialized with output directory: {self.cache_dir}")

    def _generate_filename(self, exchange: str, symbol: Symbol, timeframe: KlineInterval,
                          start_date: datetime, end_date: datetime) -> str:
        """
        Generate pickle filename based on parameters.
        
        Format: {exchange}_{symbol}_{timeframe}_{start}_{end}.pkl
        Example: mexc_BTC_USDT_1h_20240101_20240201.pkl
        """
        start_str = start_date.strftime('%Y%m%d%H%M')
        end_str = end_date.strftime('%Y%m%d%H%M')
        tf = kline_interval_to_timeframe(timeframe)

        return f"{exchange}_{symbol.base}_{symbol.quote}_{tf}_{start_str}_{end_str}.pkl"
    
    def _klines_to_dataframe(self, klines: List[Kline]) -> pd.DataFrame:
        """
        Convert list of Kline objects to pandas DataFrame.
        
        Args:
            klines: List of Kline objects from exchange

        Returns:
            DataFrame with klines data
        """
        data = []
        for kline in klines:
            # Convert timestamp to datetime for human readability
            dt = datetime.fromtimestamp(kline.open_time / 1000)
            
            row = {
                'timestamp': kline.open_time,
                'open': kline.open_price,
                'high': kline.high_price,
                'low': kline.low_price,
                'close': kline.close_price,
                'volume': kline.volume,
            }
            data.append(row)
        
        return pd.DataFrame(data)
    
    async def download_candles(
        self,
        exchange: ExchangeEnum,
        symbol: Symbol,
        timeframe: KlineInterval,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        filename: Optional[str] = None,
        force_download: bool = False
    ) -> pd.DataFrame:
        """
        Download candles data from specified exchange and return as DataFrame.
        Checks cache first and only downloads if data doesn't exist or force_download=True.
        
        Args:
            exchange: Exchange enum (ExchangeEnum.MEXC, ExchangeEnum.GATEIO, etc.)
            symbol: Symbol object
            timeframe: KlineInterval enum
            start_date: Start date for data download
            end_date: End date for data download
            filename: Custom filename (optional, auto-generated if None)
            force_download: Force download even if cached data exists
            
        Returns:
            DataFrame with candles data
            
        Raises:
            ValueError: If invalid parameters provided
            Exception: If download fails
        """
        # Parameter validation and preparation
        start_date = round_datetime_to_interval(start_date, timeframe)
        end_date = round_datetime_to_interval(end_date, timeframe)
        
        # Generate paths
        filename = filename or self._generate_filename(exchange.value, symbol, timeframe, start_date, end_date)
        pickle_path = self.cache_dir / filename
        
        # Check cache first
        if not force_download and pickle_path.exists():
            self.logger.info(f"Loading cached data from {pickle_path}")
            try:
                with open(pickle_path, 'rb') as f:
                    df = pickle.load(f)
                self.logger.info(f"Loaded {len(df)} cached candles from {pickle_path}")
                return df
            except Exception as e:
                self.logger.warning(f"Failed to load cached data: {e}, downloading fresh data")
        
        self.logger.info(f"Downloading {exchange.value.upper()} {symbol} {kline_interval_to_timeframe(timeframe)}"
                         f" candles from {start_date} to {end_date}")
        
        # Perform download with simplified error handling
        return await self._execute_download(exchange, symbol, timeframe, start_date, end_date, pickle_path)

    async def _execute_download(self, exchange: ExchangeEnum, symbol_obj: Symbol, timeframe_enum: KlineInterval,
                                start_date: datetime, end_date: datetime, pickle_path: Path) -> pd.DataFrame:
        """Execute the download operation with simplified error handling."""
        # Create exchange client using standard constructors
        exchange_config = self.config.get_exchange_config(exchange.value)
        client = get_rest_implementation(exchange_config, False)
        
        try:
            klines = await client.get_klines_batch(symbol_obj, timeframe_enum, date_from=start_date, date_to=end_date)

            if not klines:
                self.logger.warning(f"No data received from exchange for {symbol_obj}")
                # Return empty DataFrame with correct structure
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Convert to DataFrame
            df = self._klines_to_dataframe(klines)
            
            # Save to cache
            await self._save_to_pickle(df, pickle_path)
            self._log_completion_stats(df, pickle_path)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Download failed for {exchange.value} {symbol_obj}: {e}")
            raise
        finally:
            if client:
                await client.close()
    
    async def _save_to_pickle(self, df: pd.DataFrame, pickle_path: Path) -> None:
        """Save DataFrame to pickle file."""
        with open(pickle_path, 'wb') as f:
            pickle.dump(df, f)

    def _log_completion_stats(self, df: pd.DataFrame, pickle_path: Path) -> None:
        """Log completion statistics."""
        file_size = pickle_path.stat().st_size
        self.logger.info(f"Successfully saved {len(df)} candles to {pickle_path}")
        self.logger.info(f"File size: {file_size / 1024:.1f} KB")

    async def get_multi_candles_df(
            self,
            exchanges: list[ExchangeEnum],
            symbol: Symbol,
            date_to: Optional[datetime] = None,
            hours: int = 24,
            timeframe: KlineInterval = KlineInterval.MINUTE_1
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""
        end_time = datetime.now(UTC) if date_to is None else date_to
        start_time = end_time - pd.Timedelta(hours=hours)
        tasks = [
            self.download_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_time,
                end_date=end_time,
            )
            for exchange in exchanges
        ]
        results = await asyncio.gather(*tasks)

        exchange_df_map: dict[ExchangeEnum, Optional[pd.DataFrame]] = {}

        for exchange, df in zip(exchanges, results):
            if df is None or df.empty:
                exchange_df_map[exchange] = None
                continue
            # Prefix all column names with the exchange key (use enum name)
            prefixed = df[['open', 'high', 'low', 'close', 'volume']].copy()
            prefixed.columns = [get_column_key(exchange, col) for col in prefixed.columns]
            exchange_df_map[exchange] = prefixed

        # Merge all available dataframes into a single dataframe (outer join on index)
        available = [df for df in exchange_df_map.values() if df is not None]
        merged_df = pd.concat(available, axis=1, join="outer") if available else pd.DataFrame()
        merged_df.sort_index(inplace=True)

        return merged_df
