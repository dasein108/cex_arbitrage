-- Grafana Query: Complete Arbitrage Monitoring Dashboard
-- Combines entry opportunities, exit signals, and spread analysis
-- Shows real-time arbitrage landscape with actionable signals

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
    bts.timestamp > NOW() - INTERVAL '10 minutes'
    AND s.symbol_base = '$symbol_base'
    AND s.symbol_quote = 'USDT'
    AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_FUTURES')
    AND bts.bid_price > 0 
    AND bts.ask_price > 0
  GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value, e.market_type, s.symbol_base, s.symbol_quote
),
arbitrage_metrics AS (
  SELECT
    spot.time_bucket as time,
    
    -- Entry opportunity analysis
    ((spot.ask_price - futures.bid_price) / spot.ask_price * 100) as entry_cost_pct,
    
    -- Exit opportunity analysis (reverse spread)
    ((futures.ask_price - spot.bid_price) / futures.ask_price * 100) as exit_cost_pct,
    
    -- Price data
    spot.ask_price as spot_ask,
    spot.bid_price as spot_bid,
    futures.ask_price as futures_ask,
    futures.bid_price as futures_bid,
    
    -- Volume constraints
    LEAST(spot.ask_quantity, futures.bid_quantity) as entry_max_quantity,
    LEAST(spot.bid_quantity, futures.ask_quantity) as exit_max_quantity,
    
    -- Exchange info
    spot.exchange as spot_exchange,
    futures.exchange as futures_exchange
    
  FROM exchange_prices spot
  JOIN exchange_prices futures 
    ON spot.time_bucket = futures.time_bucket
    AND spot.symbol_base = futures.symbol_base
    AND spot.symbol_quote = futures.symbol_quote
  WHERE 
    spot.market_type = 'SPOT'
    AND futures.market_type = 'FUTURES'
)

SELECT * FROM (
  -- Entry Opportunities
  SELECT
    time,
    'ENTRY_SPREAD' as series,
    entry_cost_pct as value,
    CASE 
      WHEN entry_cost_pct <= COALESCE($max_entry_cost_pct, 0.5) AND entry_cost_pct > 0 THEN 1
      ELSE 0
    END as entry_signal,
    spot_ask,
    futures_bid,
    entry_max_quantity as max_quantity,
    'ENTRY' as signal_type
  FROM arbitrage_metrics
  WHERE entry_cost_pct > 0
  
  UNION ALL
  
  -- Exit Opportunities (for visualization)
  SELECT
    time,
    'EXIT_SPREAD' as series,
    exit_cost_pct as value,
    CASE 
      WHEN exit_cost_pct <= 0.2 THEN 1  -- Good exit opportunity
      ELSE 0
    END as entry_signal,
    futures_ask,
    spot_bid,
    exit_max_quantity as max_quantity,
    'EXIT' as signal_type
  FROM arbitrage_metrics
  WHERE exit_cost_pct >= 0
  
  UNION ALL
  
  -- Spread Difference (Entry - Exit costs)
  SELECT
    time,
    'SPREAD_ADVANTAGE' as series,
    (entry_cost_pct - exit_cost_pct) as value,
    CASE 
      WHEN (entry_cost_pct - exit_cost_pct) >= COALESCE($min_profit_pct, 0.58) THEN 1
      ELSE 0
    END as entry_signal,
    (spot_ask + futures_ask) / 2 as spot_ask,
    (spot_bid + futures_bid) / 2 as futures_bid,
    LEAST(entry_max_quantity, exit_max_quantity) as max_quantity,
    'ADVANTAGE' as signal_type
  FROM arbitrage_metrics
  WHERE entry_cost_pct > 0 AND exit_cost_pct >= 0
  
  UNION ALL
  
  -- Current Position P&L (if position exists)
  SELECT
    time,
    'POSITION_PNL' as series,
    CASE 
      WHEN COALESCE($has_position, false) = true THEN
        -- Calculate P&L with current prices and entry prices
        (((spot_bid * (1 - COALESCE($spot_fee, 0.0005))) - (COALESCE($entry_spot_ask, spot_ask) * (1 + COALESCE($spot_fee, 0.0005)))) +
         ((COALESCE($entry_futures_bid, futures_bid) * (1 - COALESCE($futures_fee, 0.0005))) - (futures_ask * (1 + COALESCE($futures_fee, 0.0005))))) /
        (COALESCE($entry_spot_ask, spot_ask) * (1 + COALESCE($spot_fee, 0.0005))) * 100
      ELSE NULL
    END as value,
    CASE 
      WHEN COALESCE($has_position, false) = true AND 
           (((spot_bid * (1 - COALESCE($spot_fee, 0.0005))) - (COALESCE($entry_spot_ask, spot_ask) * (1 + COALESCE($spot_fee, 0.0005)))) +
            ((COALESCE($entry_futures_bid, futures_bid) * (1 - COALESCE($futures_fee, 0.0005))) - (futures_ask * (1 + COALESCE($futures_fee, 0.0005))))) /
           (COALESCE($entry_spot_ask, spot_ask) * (1 + COALESCE($spot_fee, 0.0005))) * 100 >= COALESCE($min_profit_pct, 0.58) THEN 1
      ELSE 0
    END as entry_signal,
    spot_bid,
    futures_ask,
    exit_max_quantity as max_quantity,
    'POSITION' as signal_type
  FROM arbitrage_metrics
  WHERE COALESCE($has_position, false) = true

) all_metrics
WHERE value IS NOT NULL
ORDER BY time DESC, series;