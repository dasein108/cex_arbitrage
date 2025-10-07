# Database Schema Design - Normalized Architecture

## Current Schema Analysis

### Issues with Current Design
1. **Denormalized Storage**: Exchange names stored as strings in every record
2. **Symbol Fragmentation**: Base/quote assets stored separately without relationships
3. **No Reference Integrity**: Missing foreign key constraints
4. **Data Redundancy**: Exchange/symbol info duplicated across all snapshots
5. **Limited Extensibility**: Difficult to add balance/execution tracking

### Current Tables
```sql
-- Current book_ticker_snapshots structure
CREATE TABLE book_ticker_snapshots (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,           -- Denormalized string
    symbol_base VARCHAR(20) NOT NULL,        -- Denormalized string  
    symbol_quote VARCHAR(20) NOT NULL,       -- Denormalized string
    bid_price NUMERIC(20,8) NOT NULL,
    bid_qty NUMERIC(20,8) NOT NULL,
    ask_price NUMERIC(20,8) NOT NULL,
    ask_qty NUMERIC(20,8) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## New Normalized Schema

### 1. Exchanges Reference Table
```sql
CREATE TABLE exchanges (
    id SMALLINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name VARCHAR(50) UNIQUE NOT NULL,              -- MEXC_SPOT, GATEIO_SPOT, GATEIO_FUTURES
    enum_value VARCHAR(50) UNIQUE NOT NULL,        -- Maps to ExchangeEnum values
    display_name VARCHAR(100) NOT NULL,            -- User-friendly display name
    market_type VARCHAR(20) NOT NULL,              -- SPOT, FUTURES, OPTIONS
    is_active BOOLEAN NOT NULL DEFAULT true,
    base_url VARCHAR(255),                         -- REST API base URL
    websocket_url VARCHAR(255),                    -- WebSocket URL
    rate_limit_requests_per_second INTEGER,        -- API rate limits
    precision_default SMALLINT DEFAULT 8,          -- Default precision
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Performance indexes
CREATE INDEX idx_exchanges_enum_value ON exchanges(enum_value);
CREATE INDEX idx_exchanges_active ON exchanges(is_active) WHERE is_active = true;
CREATE INDEX idx_exchanges_market_type ON exchanges(market_type);

-- Populate with current exchanges
INSERT INTO exchanges (name, enum_value, display_name, market_type, base_url, websocket_url) VALUES
('MEXC_SPOT', 'MEXC_SPOT', 'MEXC Spot', 'SPOT', 'https://api.mexc.com', 'wss://wbs.mexc.com/ws'),
('GATEIO_SPOT', 'GATEIO_SPOT', 'Gate.io Spot', 'SPOT', 'https://api.gateio.ws', 'wss://api.gateio.ws/ws/v4/'),
('GATEIO_FUTURES', 'GATEIO_FUTURES', 'Gate.io Futures', 'FUTURES', 'https://api.gateio.ws', 'wss://fx-ws.gateio.ws/v4/ws/');
```

### 2. Symbols Reference Table
```sql
CREATE TABLE symbols (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    exchange_id SMALLINT NOT NULL REFERENCES exchanges(id) ON DELETE CASCADE,
    base_asset VARCHAR(20) NOT NULL,               -- BTC, ETH, etc.
    quote_asset VARCHAR(20) NOT NULL,              -- USDT, USD, etc.
    symbol_string VARCHAR(50) NOT NULL,            -- Exchange-specific format (BTCUSDT)
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Trading rules
    precision_base SMALLINT NOT NULL DEFAULT 8,    -- Base asset precision
    precision_quote SMALLINT NOT NULL DEFAULT 8,   -- Quote asset precision
    precision_price SMALLINT NOT NULL DEFAULT 8,   -- Price precision
    min_order_size NUMERIC(20,8),                  -- Minimum order size
    max_order_size NUMERIC(20,8),                  -- Maximum order size
    tick_size NUMERIC(20,8),                       -- Minimum price increment
    step_size NUMERIC(20,8),                       -- Minimum quantity increment
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_seen TIMESTAMPTZ DEFAULT NOW() NOT NULL,  -- Last time symbol was active
    
    -- Constraints
    UNIQUE(exchange_id, base_asset, quote_asset),
    UNIQUE(exchange_id, symbol_string),
    
    -- Validation
    CONSTRAINT chk_assets_different CHECK (base_asset != quote_asset),
    CONSTRAINT chk_positive_precision CHECK (precision_base > 0 AND precision_quote > 0),
    CONSTRAINT chk_valid_order_sizes CHECK (min_order_size IS NULL OR max_order_size IS NULL OR min_order_size <= max_order_size)
);

-- Performance indexes for HFT operations
CREATE INDEX idx_symbols_exchange_assets ON symbols(exchange_id, base_asset, quote_asset);
CREATE INDEX idx_symbols_exchange_string ON symbols(exchange_id, symbol_string);
CREATE INDEX idx_symbols_active ON symbols(exchange_id, is_active) WHERE is_active = true;
CREATE INDEX idx_symbols_base_quote ON symbols(base_asset, quote_asset); -- Cross-exchange queries
CREATE INDEX idx_symbols_last_seen ON symbols(last_seen DESC);

-- Covering index for cache loading
CREATE INDEX idx_symbols_cache_load ON symbols(id, exchange_id, base_asset, quote_asset, symbol_string, is_active) 
    WHERE is_active = true;
```

### 3. Normalized Market Data Tables

#### Book Ticker Snapshots (Normalized)
```sql
CREATE TABLE book_ticker_snapshots_v2 (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- Market data
    bid_price NUMERIC(20,8) NOT NULL,
    bid_qty NUMERIC(20,8) NOT NULL,
    ask_price NUMERIC(20,8) NOT NULL,
    ask_qty NUMERIC(20,8) NOT NULL,
    
    -- Timing
    timestamp TIMESTAMPTZ NOT NULL,              -- Exchange timestamp
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL, -- Insert timestamp
    
    -- Constraints
    CONSTRAINT chk_positive_prices_v2 CHECK (bid_price > 0 AND ask_price > 0),
    CONSTRAINT chk_positive_quantities_v2 CHECK (bid_qty > 0 AND ask_qty > 0),
    CONSTRAINT chk_bid_ask_spread_v2 CHECK (ask_price >= bid_price)
);

-- HFT-optimized indexes
CREATE INDEX idx_book_ticker_v2_symbol_time ON book_ticker_snapshots_v2(symbol_id, timestamp DESC);
CREATE INDEX idx_book_ticker_v2_timestamp ON book_ticker_snapshots_v2(timestamp DESC);
CREATE INDEX idx_book_ticker_v2_created_at ON book_ticker_snapshots_v2(created_at DESC);

-- Composite index for latest snapshots
CREATE INDEX idx_book_ticker_v2_latest ON book_ticker_snapshots_v2(symbol_id, timestamp DESC);
```

#### Trade Snapshots (Normalized)
```sql
CREATE TABLE trade_snapshots_v2 (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- Trade data
    price NUMERIC(20,8) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    side SMALLINT NOT NULL,                      -- 1=BUY, 2=SELL (from Side enum)
    
    -- Optional fields
    trade_id VARCHAR(100),                       -- Exchange trade ID
    quote_quantity NUMERIC(20,8),               -- Quote asset quantity
    is_buyer BOOLEAN,                            -- Is buyer maker
    is_maker BOOLEAN,                            -- Is maker trade
    
    -- Timing
    timestamp TIMESTAMPTZ NOT NULL,              -- Exchange timestamp
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL, -- Insert timestamp
    
    -- Constraints
    CONSTRAINT chk_positive_price_v2 CHECK (price > 0),
    CONSTRAINT chk_positive_quantity_v2 CHECK (quantity > 0),
    CONSTRAINT chk_valid_side_v2 CHECK (side IN (1, 2))
);

-- Performance indexes
CREATE INDEX idx_trade_v2_symbol_time ON trade_snapshots_v2(symbol_id, timestamp DESC);
CREATE INDEX idx_trade_v2_timestamp ON trade_snapshots_v2(timestamp DESC);
CREATE INDEX idx_trade_v2_trade_id ON trade_snapshots_v2(trade_id) WHERE trade_id IS NOT NULL;
```

## Performance Optimizations

### 1. Materialized Views for Latest Data
```sql
-- Latest book ticker per symbol (for ultra-fast latest price access)
CREATE MATERIALIZED VIEW latest_book_ticker_snapshots AS
SELECT DISTINCT ON (symbol_id) 
       symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
FROM book_ticker_snapshots_v2 
ORDER BY symbol_id, timestamp DESC;

CREATE UNIQUE INDEX idx_latest_book_ticker_symbol ON latest_book_ticker_snapshots(symbol_id);

-- Refresh strategy: Updated by trigger or periodic refresh
-- For HFT: Consider trigger-based updates for real-time accuracy
```

### 2. Partitioning Strategy (Future)
```sql
-- Time-based partitioning for large data volumes
-- Partition by month for optimal query performance and maintenance

CREATE TABLE book_ticker_snapshots_v2_template (
    LIKE book_ticker_snapshots_v2 INCLUDING ALL
) PARTITION BY RANGE (created_at);

-- Example partition for January 2025
CREATE TABLE book_ticker_snapshots_v2_202501 
PARTITION OF book_ticker_snapshots_v2_template
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

## Storage Impact Analysis

### Before Normalization (per record)
```
Exchange string: ~20 bytes
Symbol base: ~10 bytes  
Symbol quote: ~10 bytes
Total metadata: ~40 bytes per record
```

### After Normalization (per record)
```
Symbol ID (INTEGER): 4 bytes
Total metadata: 4 bytes per record
Space savings: ~90% reduction in metadata storage
```

### Projected Storage Savings
- **1M records/day**: Save ~36MB/day in metadata
- **Annual savings**: ~13GB less storage
- **Index efficiency**: 10x faster integer joins vs string comparisons
- **Cache efficiency**: 4-byte symbol IDs vs 40-byte strings in memory

## Migration Compatibility

### Backward Compatibility Functions
```sql
-- Function to get exchange name from symbol_id
CREATE OR REPLACE FUNCTION get_exchange_name(p_symbol_id INTEGER)
RETURNS TEXT AS $$
BEGIN
    RETURN (
        SELECT e.name 
        FROM symbols s 
        JOIN exchanges e ON s.exchange_id = e.id 
        WHERE s.id = p_symbol_id
    );
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to get symbol info from symbol_id
CREATE OR REPLACE FUNCTION get_symbol_info(p_symbol_id INTEGER)
RETURNS TABLE(exchange_name TEXT, base_asset TEXT, quote_asset TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT e.name, s.base_asset, s.quote_asset
    FROM symbols s 
    JOIN exchanges e ON s.exchange_id = e.id 
    WHERE s.id = p_symbol_id;
END;
$$ LANGUAGE plpgsql STABLE;
```

### Migration Views (Temporary)
```sql
-- View that mimics old table structure during transition
CREATE VIEW book_ticker_snapshots_legacy AS
SELECT 
    bts.id,
    e.name as exchange,
    s.base_asset as symbol_base,
    s.quote_asset as symbol_quote,
    bts.bid_price,
    bts.bid_qty,
    bts.ask_price,
    bts.ask_qty,
    bts.timestamp,
    bts.created_at
FROM book_ticker_snapshots_v2 bts
JOIN symbols s ON bts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id;
```

---

**Next Steps**: Review `phases/phase1_foundation.md` for implementation plan.