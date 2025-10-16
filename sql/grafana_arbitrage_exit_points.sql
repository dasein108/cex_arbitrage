-- Grafana Query: Real-Time Arbitrage Exit Points
-- Monitors exit opportunities based on min_profit_pct threshold
-- Requires manual position tracking or integration with trading system
-- Usage: Set position variables when trades are active

WITH exchange_prices AS (
  SELECT
    DATE_TRUNC('second', bts.timestamp) as time_bucket,
    e.enum_value as exchange,
    e.market_type,
    s.symbol_base,
    s.symbol_quote,
    AVG(bts.bid_price) as bid_price,
    AVG(bts.ask_price) as ask_price,
    AVG(bts.bid_qty) as bid_quantity,
    AVG(bts.ask_qty) as ask_quantity
  FROM book_ticker_snapshots bts
  JOIN symbols s ON bts.symbol_id = s.id
  JOIN exchanges e ON s.exchange_id = e.id
  WHERE
    bts.timestamp > NOW() - INTERVAL '5 minutes'
    AND s.symbol_base = '$symbol_base'
    AND s.symbol_quote = 'USDT'
    AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_FUTURES')
    AND bts.bid_price > 0 
    AND bts.ask_price > 0
    AND bts.bid_qty > 0
    AND bts.ask_qty > 0
  GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value, e.market_type, s.symbol_base, s.symbol_quote
),
position_pnl AS (
  SELECT
    spot.time_bucket as time,
    'EXIT_OPPORTUNITY' as series,
    -- Simulated position entry prices (replace with actual position data)
    COALESCE($entry_spot_ask, 50000.0) as entry_spot_ask,
    COALESCE($entry_futures_bid, 49750.0) as entry_futures_bid,
    COALESCE($spot_fee, 0.0005) as spot_fee,
    COALESCE($futures_fee, 0.0005) as futures_fee,
    
    -- Current exit prices
    spot.bid_price as exit_spot_bid,
    futures.ask_price as exit_futures_ask,
    
    -- P&L calculation with fees (matches backtesting logic)
    -- Entry costs (what we paid)
    COALESCE($entry_spot_ask, 50000.0) * (1 + COALESCE($spot_fee, 0.0005)) as entry_spot_cost,
    COALESCE($entry_futures_bid, 49750.0) * (1 - COALESCE($futures_fee, 0.0005)) as entry_futures_receive,
    
    -- Exit revenues (what we get)
    spot.bid_price * (1 - COALESCE($spot_fee, 0.0005)) as exit_spot_receive,
    futures.ask_price * (1 + COALESCE($futures_fee, 0.0005)) as exit_futures_cost
    
  FROM exchange_prices spot
  JOIN exchange_prices futures 
    ON spot.time_bucket = futures.time_bucket
    AND spot.symbol_base = futures.symbol_base
    AND spot.symbol_quote = futures.symbol_quote
  WHERE 
    spot.market_type = 'SPOT'
    AND futures.market_type = 'FUTURES'
    AND spot.exchange != futures.exchange
),
exit_signals AS (
  SELECT
    time,
    series,
    -- Calculate net P&L percentage
    ((exit_spot_receive - entry_spot_cost) + (entry_futures_receive - exit_futures_cost)) / entry_spot_cost * 100 as net_pnl_pct,
    
    -- Exit cost calculation for reference
    ((exit_futures_ask - exit_spot_bid) / exit_futures_ask * 100) as exit_cost_pct,
    
    entry_spot_ask,
    entry_futures_bid,
    exit_spot_bid,
    exit_futures_ask,
    
    -- Position details
    entry_spot_cost,
    entry_futures_receive,
    exit_spot_receive,
    exit_futures_cost
  FROM position_pnl
)
SELECT
  time,
  series,
  net_pnl_pct as value,
  CASE 
    WHEN net_pnl_pct >= COALESCE($min_profit_pct, 0.58) THEN 'EXIT_SIGNAL'
    WHEN net_pnl_pct >= 0 THEN 'PROFITABLE'
    ELSE 'LOSING'
  END as signal_type,
  exit_cost_pct,
  entry_spot_ask,
  entry_futures_bid,
  exit_spot_bid,
  exit_futures_ask,
  net_pnl_pct as profit_pct
FROM exit_signals
ORDER BY time DESC;