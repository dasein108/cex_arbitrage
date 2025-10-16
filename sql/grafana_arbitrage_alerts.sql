-- Grafana Alert Queries: Arbitrage Entry/Exit Signals
-- Use these for Grafana alerting rules and notifications

-- ==========================================
-- ALERT 1: Entry Signal Alert
-- Triggers when entry opportunity meets threshold
-- ==========================================
WITH entry_opportunities AS (
  SELECT
    DATE_TRUNC('second', bts.timestamp) as time_bucket,
    e.enum_value as exchange,
    e.market_type,
    AVG(bts.bid_price) as bid_price,
    AVG(bts.ask_price) as ask_price,
    AVG(bts.bid_qty) as bid_quantity,
    AVG(bts.ask_qty) as ask_quantity
  FROM book_ticker_snapshots bts
  JOIN symbols s ON bts.symbol_id = s.id
  JOIN exchanges e ON s.exchange_id = e.id
  WHERE
    bts.timestamp > NOW() - INTERVAL '2 minutes'
    AND s.symbol_base = '$symbol_base'
    AND s.symbol_quote = 'USDT'
    AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_FUTURES')
    AND bts.bid_price > 0 AND bts.ask_price > 0
  GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value, e.market_type
)
SELECT
  MAX(time_bucket) as time,
  COUNT(*) as entry_signals_count,
  AVG(((spot.ask_price - futures.bid_price) / spot.ask_price * 100)) as avg_entry_cost_pct,
  MIN(((spot.ask_price - futures.bid_price) / spot.ask_price * 100)) as best_entry_cost_pct,
  AVG(LEAST(spot.ask_quantity, futures.bid_quantity)) as avg_max_quantity
FROM entry_opportunities spot
JOIN entry_opportunities futures 
  ON spot.time_bucket = futures.time_bucket
WHERE 
  spot.market_type = 'SPOT'
  AND futures.market_type = 'FUTURES'
  AND ((spot.ask_price - futures.bid_price) / spot.ask_price * 100) <= COALESCE($max_entry_cost_pct, 0.5)
  AND ((spot.ask_price - futures.bid_price) / spot.ask_price * 100) > 0
HAVING COUNT(*) > 0;

-- ==========================================
-- ALERT 2: Exit Signal Alert (for active positions)
-- Triggers when exit profit target is reached
-- ==========================================
WITH exit_opportunities AS (
  SELECT
    DATE_TRUNC('second', bts.timestamp) as time_bucket,
    e.enum_value as exchange,
    e.market_type,
    AVG(bts.bid_price) as bid_price,
    AVG(bts.ask_price) as ask_price
  FROM book_ticker_snapshots bts
  JOIN symbols s ON bts.symbol_id = s.id
  JOIN exchanges e ON s.exchange_id = e.id
  WHERE
    bts.timestamp > NOW() - INTERVAL '2 minutes'
    AND s.symbol_base = '$symbol_base'
    AND s.symbol_quote = 'USDT'
    AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_FUTURES')
    AND bts.bid_price > 0 AND bts.ask_price > 0
  GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value, e.market_type
)
SELECT
  MAX(time_bucket) as time,
  COUNT(*) as exit_signals_count,
  AVG(
    -- P&L calculation with simulated entry prices
    (((spot.bid_price * (1 - COALESCE($spot_fee, 0.0005))) - (COALESCE($entry_spot_ask, 50000) * (1 + COALESCE($spot_fee, 0.0005)))) +
     ((COALESCE($entry_futures_bid, 49750) * (1 - COALESCE($futures_fee, 0.0005))) - (futures.ask_price * (1 + COALESCE($futures_fee, 0.0005))))) /
    (COALESCE($entry_spot_ask, 50000) * (1 + COALESCE($spot_fee, 0.0005))) * 100
  ) as avg_pnl_pct,
  MAX(
    (((spot.bid_price * (1 - COALESCE($spot_fee, 0.0005))) - (COALESCE($entry_spot_ask, 50000) * (1 + COALESCE($spot_fee, 0.0005)))) +
     ((COALESCE($entry_futures_bid, 49750) * (1 - COALESCE($futures_fee, 0.0005))) - (futures.ask_price * (1 + COALESCE($futures_fee, 0.0005))))) /
    (COALESCE($entry_spot_ask, 50000) * (1 + COALESCE($spot_fee, 0.0005))) * 100
  ) as best_pnl_pct
FROM exit_opportunities spot
JOIN exit_opportunities futures 
  ON spot.time_bucket = futures.time_bucket
WHERE 
  spot.market_type = 'SPOT'
  AND futures.market_type = 'FUTURES'
  AND COALESCE($has_position, false) = true
  AND (((spot.bid_price * (1 - COALESCE($spot_fee, 0.0005))) - (COALESCE($entry_spot_ask, 50000) * (1 + COALESCE($spot_fee, 0.0005)))) +
       ((COALESCE($entry_futures_bid, 49750) * (1 - COALESCE($futures_fee, 0.0005))) - (futures.ask_price * (1 + COALESCE($futures_fee, 0.0005))))) /
      (COALESCE($entry_spot_ask, 50000) * (1 + COALESCE($spot_fee, 0.0005))) * 100 >= COALESCE($min_profit_pct, 0.58)
HAVING COUNT(*) > 0;

-- ==========================================
-- ALERT 3: Timeout Alert (position held too long)
-- Triggers when position exceeds max_hours threshold
-- ==========================================
SELECT
  NOW() as time,
  1 as timeout_alert,
  EXTRACT(EPOCH FROM (NOW() - TO_TIMESTAMP(COALESCE($position_start_time, EXTRACT(EPOCH FROM NOW()))))) / 3600 as hours_held,
  COALESCE($max_hours, 6.0) as max_hours_threshold,
  'TIMEOUT_WARNING' as alert_type
WHERE
  COALESCE($has_position, false) = true
  AND EXTRACT(EPOCH FROM (NOW() - TO_TIMESTAMP(COALESCE($position_start_time, EXTRACT(EPOCH FROM NOW()))))) / 3600 >= COALESCE($max_hours, 6.0) * 0.8  -- Alert at 80% of timeout
LIMIT 1;

-- ==========================================
-- ALERT 4: Volume Constraint Alert
-- Triggers when available volume drops below minimum
-- ==========================================
WITH volume_check AS (
  SELECT
    DATE_TRUNC('second', bts.timestamp) as time_bucket,
    e.enum_value as exchange,
    e.market_type,
    AVG(bts.bid_qty) as bid_quantity,
    AVG(bts.ask_qty) as ask_quantity,
    AVG(bts.ask_price) as ask_price,
    AVG(bts.bid_price) as bid_price
  FROM book_ticker_snapshots bts
  JOIN symbols s ON bts.symbol_id = s.id
  JOIN exchanges e ON s.exchange_id = e.id
  WHERE
    bts.timestamp > NOW() - INTERVAL '1 minute'
    AND s.symbol_base = '$symbol_base'
    AND s.symbol_quote = 'USDT'
    AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_FUTURES')
  GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value, e.market_type
)
SELECT
  MAX(time_bucket) as time,
  AVG(LEAST(spot.ask_quantity, futures.bid_quantity)) as avg_entry_volume,
  AVG(LEAST(spot.bid_quantity, futures.ask_quantity)) as avg_exit_volume,
  COALESCE($min_order_size_usdt, 100) / AVG(spot.ask_price) as min_required_quantity,
  'LOW_VOLUME_WARNING' as alert_type
FROM volume_check spot
JOIN volume_check futures 
  ON spot.time_bucket = futures.time_bucket
WHERE 
  spot.market_type = 'SPOT'
  AND futures.market_type = 'FUTURES'
  AND LEAST(spot.ask_quantity, futures.bid_quantity) < (COALESCE($min_order_size_usdt, 100) / spot.ask_price)
HAVING COUNT(*) > 0;