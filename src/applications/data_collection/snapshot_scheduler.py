import asyncio
import logging


class SnapshotScheduler:
    """Simple scheduler for saving cached data periodically."""

    def __init__(self, ws_manager, interval_seconds: int = 5):
        self.ws_manager = ws_manager
        self.interval_seconds = interval_seconds
        self.logger = logging.getLogger('data_collector')
        self._running = False

    async def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        self.logger.info(f"Starting scheduler with {self.interval_seconds}s interval")

        try:
            while self._running:
                await self._save_data()
                await asyncio.sleep(self.interval_seconds)
        except Exception as e:
            self.logger.error(f"Scheduler error: {e}")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False

    async def _save_data(self) -> None:
        """Save all cached data to database."""
        try:
            cache = self.ws_manager.cache

            # Save book tickers
            if cache.book_tickers:
                try:
                    from db.operations import insert_book_ticker_snapshots_batch
                    result = await insert_book_ticker_snapshots_batch(cache.book_tickers)
                    self.logger.info(f"Saved {result} book ticker snapshots (cached: {len(cache.book_tickers)})")
                    cache.book_tickers.clear()
                except Exception as e:
                    self.logger.error(f"Failed to save book ticker snapshots: {e}")
                    if cache.book_tickers:
                        sample = cache.book_tickers[0]
                        self.logger.debug(f"Book ticker sample: symbol_id={getattr(sample, 'symbol_id', 'N/A')}, timestamp={getattr(sample, 'timestamp', 'N/A')}")
                    # Clear problematic data to prevent repeated failures
                    cache.book_tickers.clear()

            # Save trades
            if cache.trades:
                try:
                    from db.operations import insert_trade_snapshots_batch
                    result = await insert_trade_snapshots_batch(cache.trades)
                    self.logger.info(f"Saved {result} trade snapshots (cached: {len(cache.trades)})")
                    cache.trades.clear()
                except Exception as e:
                    self.logger.error(f"Failed to save trade snapshots: {e}")
                    if cache.trades:
                        sample = cache.trades[0]
                        self.logger.debug(f"Trade sample: symbol_id={getattr(sample, 'symbol_id', 'N/A')}, trade_id={getattr(sample, 'trade_id', 'N/A')}, timestamp={getattr(sample, 'timestamp', 'N/A')}")
                    # Clear problematic data to prevent repeated failures
                    cache.trades.clear()

            # Save funding rates
            if cache.funding_rates:
                try:
                    from db.operations import insert_funding_rate_snapshots_batch
                    result = await insert_funding_rate_snapshots_batch(cache.funding_rates)
                    self.logger.info(f"Saved {result} funding rate snapshots (cached: {len(cache.funding_rates)})")
                    cache.funding_rates.clear()
                except Exception as e:
                    self.logger.error(f"Failed to save funding rate snapshots: {e}")
                    if cache.funding_rates:
                        sample = cache.funding_rates[0]
                        self.logger.debug(f"Funding rate sample: symbol_id={getattr(sample, 'symbol_id', 'N/A')}, timestamp={getattr(sample, 'timestamp', 'N/A')}")
                    # Clear problematic data to prevent repeated failures
                    cache.funding_rates.clear()

        except Exception as e:
            self.logger.error(f"Unexpected error in data saving loop: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
