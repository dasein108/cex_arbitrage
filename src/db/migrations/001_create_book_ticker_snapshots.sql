-- Migration 001: Create book_ticker_snapshots table
-- Purpose: Store real-time book ticker snapshots from exchanges
-- Performance: Optimized for high-frequency inserts and time-based queries

-- Create book_ticker_snapshots table
CREATE TABLE IF NOT EXISTS book_ticker_snapshots (
    id BIGSERIAL PRIMARY KEY,
    
    -- Exchange and symbol identification
    exchange VARCHAR(20) NOT NULL,
    symbol_base VARCHAR(20) NOT NULL,
    symbol_quote VARCHAR(20) NOT NULL,
    
    -- Book ticker data (best bid/ask)
    bid_price NUMERIC(20,8) NOT NULL,
    bid_qty NUMERIC(20,8) NOT NULL,
    ask_price NUMERIC(20,8) NOT NULL,
    ask_qty NUMERIC(20,8) NOT NULL,
    
    -- Timing information
    timestamp TIMESTAMPTZ NOT NULL,              -- Exchange timestamp
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL, -- Insert timestamp
    
    -- Constraints
    CONSTRAINT chk_positive_prices CHECK (bid_price > 0 AND ask_price > 0),
    CONSTRAINT chk_positive_quantities CHECK (bid_qty > 0 AND ask_qty > 0),
    CONSTRAINT chk_bid_ask_spread CHECK (ask_price >= bid_price)
);

-- Performance indexes for HFT queries
CREATE INDEX IF NOT EXISTS idx_book_ticker_exchange_symbol 
    ON book_ticker_snapshots(exchange, symbol_base, symbol_quote);

CREATE INDEX IF NOT EXISTS idx_book_ticker_timestamp 
    ON book_ticker_snapshots(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_book_ticker_created_at 
    ON book_ticker_snapshots(created_at DESC);

-- Composite index for latest snapshots query
CREATE INDEX IF NOT EXISTS idx_book_ticker_latest 
    ON book_ticker_snapshots(exchange, symbol_base, symbol_quote, timestamp DESC);

-- Note: Partial indexes with NOW() are not supported as NOW() is not immutable
-- Instead, we rely on the idx_book_ticker_latest index for recent data queries
-- Applications should use explicit timestamp filters in WHERE clauses

-- Add table comment for documentation
COMMENT ON TABLE book_ticker_snapshots IS 
    'Real-time book ticker snapshots from cryptocurrency exchanges. Optimized for HFT data storage and retrieval.';

COMMENT ON COLUMN book_ticker_snapshots.exchange IS 
    'Exchange identifier (MEXC, GATEIO, etc.)';

COMMENT ON COLUMN book_ticker_snapshots.symbol_base IS 
    'Base asset symbol (BTC, ETH, etc.)';

COMMENT ON COLUMN book_ticker_snapshots.symbol_quote IS 
    'Quote asset symbol (USDT, USD, etc.)';

COMMENT ON COLUMN book_ticker_snapshots.timestamp IS 
    'Exchange-provided timestamp for the snapshot';

COMMENT ON COLUMN book_ticker_snapshots.created_at IS 
    'Server timestamp when the record was inserted';