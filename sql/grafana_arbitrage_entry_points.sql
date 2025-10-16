-- Grafana Query: Real-Time Arbitrage Entry Points
-- Monitors opportunities based on max_entry_cost_pct threshold
-- Usage: Set $symbol_base variable in Grafana (e.g., 'BTC', 'ETH')
-- Set $max_entry_cost_pct variable (default: 0.5)

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
    AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_FUTURES')  -- Spot-Futures arbitrage
    AND bts.bid_price > 0 
    AND bts.ask_price > 0
    AND bts.bid_qty > 0
    AND bts.ask_qty > 0
  GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value, e.market_type, s.symbol_base, s.symbol_quote
),
arbitrage_opportunities AS (
  SELECT
    spot.time_bucket as time,
    'ENTRY_OPPORTUNITY' as series,
    -- Entry cost calculation: ((spot_ask - fut_bid) / spot_ask) * 100
    ((spot.ask_price - futures.bid_price) / spot.ask_price * 100) as entry_cost_pct,
    spot.ask_price as spot_ask,
    futures.bid_price as futures_bid,
    LEAST(spot.ask_quantity, futures.bid_quantity) as max_quantity,
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
    AND spot.exchange != futures.exchange
)
SELECT
  time,
  series,
  entry_cost_pct as value,
  CASE 
    WHEN entry_cost_pct <= COALESCE($max_entry_cost_pct, 0.5) THEN 'ENTER_SIGNAL'
    ELSE 'MONITORING'
  END as signal_type,
  spot_ask,
  futures_bid,
  max_quantity,
  spot_exchange,
  futures_exchange
FROM arbitrage_opportunities
WHERE entry_cost_pct > 0  -- Only positive spreads
ORDER BY time DESC, entry_cost_pct DESC;