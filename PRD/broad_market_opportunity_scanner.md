# Broad Market Opportunity Scanner - Product Requirements Document

## Executive Summary

The Broad Market Opportunity Scanner is a comprehensive analytical tool designed to identify cross-exchange arbitrage opportunities in low-cap cryptocurrency markets. Unlike traditional HFT systems that focus on high-liquidity pairs on major exchanges, this tool specifically targets emerging tokens and lesser-known exchanges where market inefficiencies are more prevalent.

**Value Proposition:**
- Discovers hidden arbitrage opportunities in low-cap altcoin markets
- Covers 10+ non-mainstream exchanges through CCXT's unified interface
- Identifies cross-exchange price discrepancies before they become mainstream
- Provides data-driven insights for expanding trading operations into new markets

**Key Differentiators:**
- Focus on sub-$100M market cap tokens excluded by mainstream arbitrage systems
- Coverage of second and third-tier exchanges with lower competition
- Intelligent filtering to identify genuine opportunities vs. liquidity traps
- Historical pattern analysis to validate opportunity persistence

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    CCXT Library Layer                        │
│  (Unified Exchange Interface - 100+ Exchange Support)        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Exchange Manager Service                    │
│  - Connection pooling and lifecycle management               │
│  - Rate limit tracking and request throttling                │
│  - Error handling and retry logic                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Symbol Discovery Engine                     │
│  - Multi-exchange symbol fetching                            │
│  - Cross-reference and normalization                         │
│  - Availability matrix construction                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Filter Pipeline                           │
│  - Market cap filtering (exclude top 50)                     │
│  - Volume threshold validation                               │
│  - Cross-exchange presence verification                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Data Collection Service                     │
│  - Parallel OHLCV data fetching                             │
│  - 3-day historical data aggregation                         │
│  - Real-time orderbook snapshots                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Analysis Engine                            │
│  - Spread calculation and tracking                           │
│  - Fee-adjusted profit computation                           │
│  - Opportunity ranking and scoring                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Output Layer                              │
│  - JSON/CSV export capabilities                              │
│  - Real-time dashboard API                                   │
│  - Alert system for high-value opportunities                 │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Architecture

```python
# Core data structures
@dataclass
class ExchangeConfig:
    name: str
    ccxt_id: str
    rate_limit: int  # requests per second
    has_fetchOHLCV: bool
    has_fetchOrderBook: bool
    fees: Dict[str, float]
    
@dataclass
class SymbolInfo:
    symbol: str  # Unified symbol (e.g., "PEPE/USDT")
    exchanges: List[str]  # Exchanges where available
    base_currency: str
    quote_currency: str
    min_volume_24h: float
    market_cap_estimate: float
    
@dataclass
class ArbitrageOpportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    spread_percentage: float
    profit_after_fees: float
    volume_available: float
    confidence_score: float
    historical_persistence: float  # Hours this opportunity existed
```

## Detailed Logic Flow

### Phase 1: Exchange Initialization

```python
async def initialize_exchanges():
    """
    Initialize CCXT exchange connections with proper configuration
    """
    target_exchanges = [
        'kucoin', 'mexc', 'gateio', 'bitget', 'bingx',
        'phemex', 'okx', 'bybit', 'huobi', 'bitmart',
        'poloniex', 'ascendex', 'probit', 'lbank', 'xt'
    ]
    
    exchanges = {}
    for exchange_id in target_exchanges:
        try:
            # Initialize with rate limiting
            exchange_class = getattr(ccxt, exchange_id)
            exchange = exchange_class({
                'enableRateLimit': True,
                'rateLimit': 100,  # Override with conservative limit
                'timeout': 10000,
                'options': {
                    'adjustForTimeDifference': True,
                    'recvWindow': 10000
                }
            })
            
            # Load markets to validate connection
            await exchange.load_markets()
            
            # Store exchange with metadata
            exchanges[exchange_id] = {
                'instance': exchange,
                'symbols': list(exchange.symbols),
                'fees': exchange.fees,
                'rate_limit': exchange.rateLimit,
                'has_ohlcv': exchange.has['fetchOHLCV'],
                'has_orderbook': exchange.has['fetchOrderBook']
            }
        except Exception as e:
            logger.warning(f"Failed to initialize {exchange_id}: {e}")
            
    return exchanges
```

### Phase 2: Symbol Discovery and Filtering

```python
async def discover_symbols(exchanges):
    """
    Discover and filter tradable symbols across exchanges
    """
    # Step 1: Collect all symbols
    symbol_exchange_map = defaultdict(set)
    
    for exchange_id, exchange_data in exchanges.items():
        for symbol in exchange_data['symbols']:
            # Only consider spot markets
            market = exchange_data['instance'].market(symbol)
            if market['spot'] and market['active']:
                # Normalize quote currency
                normalized_symbol = normalize_symbol(symbol)
                symbol_exchange_map[normalized_symbol].add(exchange_id)
    
    # Step 2: Filter symbols
    filtered_symbols = {}
    
    # Exclude top market cap coins
    TOP_COINS = {
        'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'DOGE', 'MATIC', 
        'SOL', 'DOT', 'SHIB', 'TRX', 'AVAX', 'UNI', 'LINK',
        # ... (top 50 by market cap)
    }
    
    for symbol, exchange_set in symbol_exchange_map.items():
        base, quote = symbol.split('/')
        
        # Apply filters
        if (base not in TOP_COINS and
            len(exchange_set) >= 2 and  # Available on 2+ exchanges
            quote in ['USDT', 'USDC', 'USD']):  # USD-stable quotes
            
            filtered_symbols[symbol] = {
                'exchanges': list(exchange_set),
                'cex': base,
                'quote': normalize_quote(quote),  # USDT/USDC -> USD_STABLE
                'exchange_count': len(exchange_set)
            }
    
    return filtered_symbols

def normalize_symbol(symbol):
    """Normalize symbol format across exchanges"""
    # Handle different naming conventions
    symbol = symbol.replace('USDT', 'USD_STABLE')
    symbol = symbol.replace('USDC', 'USD_STABLE')
    return symbol
```

### Phase 3: Data Collection Pipeline

```python
async def collect_historical_data(exchanges, symbols, days=3):
    """
    Collect historical OHLCV data for analysis
    """
    data_collection = {}
    timeframe = '1m'  # 1-minute candles
    since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    
    # Batch processing with rate limit management
    async def fetch_symbol_data(exchange_id, symbol):
        exchange = exchanges[exchange_id]['instance']
        
        try:
            # Check if exchange supports OHLCV
            if not exchanges[exchange_id]['has_ohlcv']:
                return None
                
            # Fetch OHLCV data with pagination
            all_candles = []
            limit = 1000  # Most exchanges limit
            
            while True:
                candles = await exchange.fetch_ohlcv(
                    symbol, 
                    timeframe, 
                    since=since,
                    limit=limit
                )
                
                if not candles:
                    break
                    
                all_candles.extend(candles)
                
                # Update since for next batch
                if len(candles) == limit:
                    since = candles[-1][0] + 1
                else:
                    break
                    
                # Rate limit compliance
                await asyncio.sleep(exchange.rateLimit / 1000)
            
            return all_candles
            
        except Exception as e:
            logger.error(f"Failed to fetch {symbol} from {exchange_id}: {e}")
            return None
    
    # Parallel data collection with semaphore for rate limiting
    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests
    
    async def fetch_with_semaphore(exchange_id, symbol):
        async with semaphore:
            return await fetch_symbol_data(exchange_id, symbol)
    
    tasks = []
    for symbol, symbol_info in symbols.items():
        for exchange_id in symbol_info['exchanges']:
            task = fetch_with_semaphore(exchange_id, symbol)
            tasks.append((symbol, exchange_id, task))
    
    # Execute all tasks
    results = await asyncio.gather(*[t[2] for t in tasks])
    
    # Organize results
    for (symbol, exchange_id, _), result in zip(tasks, results):
        if result:
            if symbol not in data_collection:
                data_collection[symbol] = {}
            data_collection[symbol][exchange_id] = result
    
    return data_collection
```

### Phase 4: Spread Analysis Engine

```python
class SpreadAnalyzer:
    """
    Analyze price spreads and identify arbitrage opportunities
    """
    
    def __init__(self, exchanges):
        self.exchanges = exchanges
        self.opportunities = []
        
    async def analyze_spreads(self, historical_data, symbols):
        """
        Perform comprehensive spread analysis
        """
        for symbol, exchange_data in historical_data.items():
            if len(exchange_data) < 2:
                continue  # Need at least 2 exchanges
                
            # Get latest prices from each exchange
            latest_prices = {}
            for exchange_id, candles in exchange_data.items():
                if candles:
                    latest_prices[exchange_id] = {
                        'price': candles[-1][4],  # Close price
                        'volume': sum(c[5] for c in candles[-60:]),  # 1hr volume
                        'timestamp': candles[-1][0]
                    }
            
            # Calculate all possible spreads
            exchanges_list = list(latest_prices.keys())
            for i, buy_exchange in enumerate(exchanges_list):
                for sell_exchange in exchanges_list[i+1:]:
                    spread = self.calculate_spread(
                        buy_exchange,
                        sell_exchange,
                        latest_prices,
                        symbol
                    )
                    
                    if spread and spread['profit_after_fees'] > 0:
                        self.opportunities.append(spread)
        
        # Rank opportunities
        self.opportunities.sort(key=lambda x: x['profit_after_fees'], reverse=True)
        return self.opportunities
    
    def calculate_spread(self, buy_exchange, sell_exchange, prices, symbol):
        """
        Calculate spread with fee adjustment
        """
        buy_price = prices[buy_exchange]['price']
        sell_price = prices[sell_exchange]['price']
        
        # Get fees
        buy_fee = self.exchanges[buy_exchange]['fees']['trading']['taker']
        sell_fee = self.exchanges[sell_exchange]['fees']['trading']['taker']
        
        # Calculate spread
        spread_pct = ((sell_price - buy_price) / buy_price) * 100
        
        # Adjust for fees
        total_fees = buy_fee + sell_fee
        profit_after_fees = spread_pct - total_fees
        
        # Calculate available volume (min of both sides)
        volume = min(
            prices[buy_exchange]['volume'],
            prices[sell_exchange]['volume']
        )
        
        # Calculate confidence score based on multiple factors
        confidence = self.calculate_confidence(
            spread_pct,
            volume,
            prices[buy_exchange]['timestamp'],
            prices[sell_exchange]['timestamp']
        )
        
        return {
            'symbol': symbol,
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'spread_percentage': spread_pct,
            'profit_after_fees': profit_after_fees,
            'volume_available': volume,
            'confidence_score': confidence,
            'timestamp': datetime.now().isoformat()
        }
    
    def calculate_confidence(self, spread, volume, ts1, ts2):
        """
        Calculate confidence score for opportunity
        """
        # Time synchronization factor
        time_diff = abs(ts1 - ts2) / 1000  # seconds
        time_factor = max(0, 1 - (time_diff / 60))  # Decay over 1 minute
        
        # Volume factor (higher volume = higher confidence)
        volume_factor = min(1, volume / 10000)  # Normalize to $10k
        
        # Spread factor (extreme spreads may indicate stale data)
        spread_factor = 1 if 0.5 < spread < 10 else 0.5
        
        return time_factor * volume_factor * spread_factor
```

## Exchange Selection Strategy

### Primary Selection Criteria

1. **API Quality and CCXT Support**
   - Full CCXT implementation with OHLCV and orderbook support
   - Reliable WebSocket feeds for real-time updates
   - Reasonable rate limits (>10 requests/second)

2. **Market Coverage**
   - High number of low-cap altcoin listings
   - Active new token listings (>5 per week)
   - Support for emerging blockchain ecosystems

3. **Liquidity Profile**
   - Medium liquidity (avoid both extremes)
   - $10M-$500M daily volume range
   - Active market makers but not dominated by bots

### Recommended Exchange List

| Exchange | CCXT ID | Priority | Rationale |
|----------|---------|----------|-----------|
| KuCoin | kucoin | HIGH | Extensive altcoin selection, good API |
| MEXC | mexc | HIGH | Leading in new listings, decent liquidity |
| Gate.io | gateio | HIGH | Broad token coverage, reliable API |
| Bitget | bitget | HIGH | Growing altcoin presence |
| BingX | bingx | MEDIUM | Emerging exchange with unique listings |
| Phemex | phemex | MEDIUM | Good for Asian market tokens |
| OKX | okx | MEDIUM | Balance of mainstream and emerging |
| Bybit | bybit | MEDIUM | Expanding spot offerings |
| HTX (Huobi) | huobi | MEDIUM | Strong in Asian tokens |
| Bitmart | bitmart | LOW | Many exclusive listings but lower liquidity |
| Poloniex | poloniex | LOW | Historical data availability |
| AscendEX | ascendex | LOW | Early listings for new projects |
| ProBit | probit | LOW | Korean market focus |
| LBank | lbank | LOW | Aggressive new listings |
| XT.com | xt | LOW | Emerging tokens focus |

## Symbol Filtering Logic

### Multi-Stage Filtering Pipeline

```python
class SymbolFilter:
    def __init__(self):
        self.filters = [
            self.market_cap_filter,
            self.volume_filter,
            self.exchange_presence_filter,
            self.liquidity_filter,
            self.stability_filter
        ]
        
    async def apply_filters(self, symbol_data):
        """
        Apply all filters in sequence
        """
        filtered = symbol_data
        for filter_func in self.filters:
            filtered = await filter_func(filtered)
        return filtered
    
    async def market_cap_filter(self, symbols):
        """
        Exclude top 50 market cap coins
        """
        # Use CoinGecko API or maintained list
        TOP_50_COINS = await self.fetch_top_coins()
        
        return {
            symbol: data for symbol, data in symbols.items()
            if data['cex'] not in TOP_50_COINS
        }
    
    async def volume_filter(self, symbols):
        """
        Filter by 24h volume thresholds
        """
        MIN_VOLUME = 10000  # $10k minimum
        MAX_VOLUME = 10000000  # $10M maximum (avoid mainstream)
        
        filtered = {}
        for symbol, data in symbols.items():
            # Fetch volume data
            total_volume = await self.get_total_volume(symbol, data['exchanges'])
            if MIN_VOLUME < total_volume < MAX_VOLUME:
                data['total_volume_24h'] = total_volume
                filtered[symbol] = data
                
        return filtered
    
    async def exchange_presence_filter(self, symbols):
        """
        Require presence on multiple exchanges
        """
        MIN_EXCHANGES = 2
        MAX_EXCHANGES = 8  # Too many = mainstream
        
        return {
            symbol: data for symbol, data in symbols.items()
            if MIN_EXCHANGES <= len(data['exchanges']) <= MAX_EXCHANGES
        }
    
    async def liquidity_filter(self, symbols):
        """
        Ensure minimum orderbook depth
        """
        MIN_SPREAD = 0.1  # 0.1% minimum (too tight = mainstream)
        MAX_SPREAD = 5.0  # 5% maximum (too wide = illiquid)
        
        filtered = {}
        for symbol, data in symbols.items():
            spreads = await self.get_spreads(symbol, data['exchanges'])
            avg_spread = sum(spreads.values()) / len(spreads)
            
            if MIN_SPREAD < avg_spread < MAX_SPREAD:
                data['average_spread'] = avg_spread
                filtered[symbol] = data
                
        return filtered
    
    async def stability_filter(self, symbols):
        """
        Filter out extremely volatile or manipulated coins
        """
        MAX_DAILY_VOLATILITY = 50  # 50% daily move maximum
        
        filtered = {}
        for symbol, data in symbols.items():
            volatility = await self.calculate_volatility(symbol, data['exchanges'])
            if volatility < MAX_DAILY_VOLATILITY:
                data['volatility'] = volatility
                filtered[symbol] = data
                
        return filtered
```

## Data Collection Pipeline

### CCXT-Based Multi-Exchange Data Gathering

```python
class DataCollectionPipeline:
    def __init__(self, exchanges):
        self.exchanges = exchanges
        self.data_store = {}
        self.rate_limiter = RateLimiter()
        
    async def collect_all_data(self, symbols, timeframe='1m', days=3):
        """
        Comprehensive data collection across all exchanges
        """
        # Phase 1: Historical OHLCV
        historical_data = await self.collect_historical_ohlcv(
            symbols, timeframe, days
        )
        
        # Phase 2: Current orderbooks
        orderbook_data = await self.collect_orderbooks(symbols)
        
        # Phase 3: Recent trades
        trades_data = await self.collect_recent_trades(symbols)
        
        # Phase 4: Ticker data for supplementary info
        ticker_data = await self.collect_tickers(symbols)
        
        # Combine all data
        combined_data = self.combine_data_sources(
            historical_data,
            orderbook_data,
            trades_data,
            ticker_data
        )
        
        return combined_data
    
    async def collect_historical_ohlcv(self, symbols, timeframe, days):
        """
        Collect OHLCV data with intelligent batching
        """
        data = {}
        
        # Calculate optimal batch size per exchange
        batch_sizes = self.calculate_batch_sizes()
        
        for symbol, symbol_info in symbols.items():
            data[symbol] = {}
            
            # Create tasks for parallel fetching
            tasks = []
            for exchange_id in symbol_info['exchanges']:
                if self.exchanges[exchange_id]['has_ohlcv']:
                    task = self.fetch_ohlcv_batch(
                        exchange_id, 
                        symbol, 
                        timeframe, 
                        days,
                        batch_sizes[exchange_id]
                    )
                    tasks.append((exchange_id, task))
            
            # Execute with rate limiting
            results = await self.execute_with_rate_limit(tasks)
            
            for exchange_id, result in results:
                if result:
                    data[symbol][exchange_id] = result
                    
        return data
    
    async def fetch_ohlcv_batch(self, exchange_id, symbol, timeframe, days, batch_size):
        """
        Fetch OHLCV data in optimized batches
        """
        exchange = self.exchanges[exchange_id]['instance']
        
        # Calculate time range
        since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        now = int(datetime.now().timestamp() * 1000)
        
        all_candles = []
        current_since = since
        
        while current_since < now:
            try:
                # Fetch batch
                candles = await exchange.fetch_ohlcv(
                    symbol,
                    timeframe,
                    since=current_since,
                    limit=batch_size
                )
                
                if not candles:
                    break
                    
                all_candles.extend(candles)
                
                # Update position
                current_since = candles[-1][0] + 60000  # Next minute
                
                # Rate limit compliance
                await self.rate_limiter.wait(exchange_id)
                
            except ccxt.RateLimitExceeded:
                await asyncio.sleep(60)  # Back off on rate limit
            except Exception as e:
                logger.error(f"Error fetching OHLCV: {e}")
                break
                
        return all_candles
    
    async def collect_orderbooks(self, symbols):
        """
        Collect current orderbook snapshots
        """
        data = {}
        
        for symbol, symbol_info in symbols.items():
            data[symbol] = {}
            
            for exchange_id in symbol_info['exchanges']:
                if self.exchanges[exchange_id]['has_orderbook']:
                    try:
                        orderbook = await self.exchanges[exchange_id]['instance'].fetch_order_book(
                            symbol,
                            limit=20  # Top 20 levels
                        )
                        
                        data[symbol][exchange_id] = {
                            'bids': orderbook['bids'][:10],
                            'asks': orderbook['asks'][:10],
                            'timestamp': orderbook['timestamp'],
                            'spread': self.calculate_spread(orderbook)
                        }
                        
                        await self.rate_limiter.wait(exchange_id)
                        
                    except Exception as e:
                        logger.error(f"Error fetching orderbook: {e}")
                        
        return data
    
    def calculate_spread(self, orderbook):
        """
        Calculate bid-ask spread metrics
        """
        if orderbook['bids'] and orderbook['asks']:
            best_bid = orderbook['bids'][0][0]
            best_ask = orderbook['asks'][0][0]
            spread = best_ask - best_bid
            spread_pct = (spread / best_bid) * 100
            return {
                'absolute': spread,
                'percentage': spread_pct
            }
        return None
```

## Analysis Methodology

### Comprehensive Arbitrage Opportunity Analysis

```python
class ArbitrageAnalyzer:
    def __init__(self, fee_structure):
        self.fee_structure = fee_structure
        self.opportunities = []
        
    async def analyze_opportunities(self, data):
        """
        Multi-dimensional arbitrage analysis
        """
        # 1. Simple spread arbitrage
        simple_arbs = await self.find_simple_arbitrage(data)
        
        # 2. Triangular arbitrage within exchanges
        triangular_arbs = await self.find_triangular_arbitrage(data)
        
        # 3. Statistical arbitrage patterns
        stat_arbs = await self.find_statistical_arbitrage(data)
        
        # 4. Cross-stable arbitrage (USDT/USDC)
        stable_arbs = await self.find_stablecoin_arbitrage(data)
        
        # Combine and rank all opportunities
        all_opportunities = simple_arbs + triangular_arbs + stat_arbs + stable_arbs
        
        # Apply scoring algorithm
        scored_opportunities = self.score_opportunities(all_opportunities)
        
        # Filter by minimum thresholds
        filtered = self.apply_minimum_thresholds(scored_opportunities)
        
        return filtered
    
    async def find_simple_arbitrage(self, data):
        """
        Identify direct cross-exchange arbitrage
        """
        opportunities = []
        
        for symbol, symbol_data in data.items():
            exchanges = list(symbol_data.keys())
            
            # Compare all exchange pairs
            for i, exchange_a in enumerate(exchanges):
                for exchange_b in exchanges[i+1:]:
                    opp = self.calculate_simple_arbitrage(
                        symbol,
                        exchange_a,
                        exchange_b,
                        symbol_data
                    )
                    
                    if opp and opp['net_profit'] > 0:
                        opportunities.append(opp)
                        
        return opportunities
    
    def calculate_simple_arbitrage(self, symbol, ex_a, ex_b, data):
        """
        Calculate profit including all costs
        """
        # Get prices
        price_a = data[ex_a]['last_price']
        price_b = data[ex_b]['last_price']
        
        # Determine direction
        if price_a < price_b:
            buy_ex, sell_ex = ex_a, ex_b
            buy_price, sell_price = price_a, price_b
        else:
            buy_ex, sell_ex = ex_b, ex_a
            buy_price, sell_price = price_b, price_a
        
        # Calculate gross spread
        gross_spread = ((sell_price - buy_price) / buy_price) * 100
        
        # Deduct costs
        buy_fee = self.fee_structure[buy_ex]['taker']
        sell_fee = self.fee_structure[sell_ex]['taker']
        withdrawal_fee = self.estimate_withdrawal_fee(symbol)
        
        total_costs = buy_fee + sell_fee + withdrawal_fee
        net_profit = gross_spread - total_costs
        
        # Calculate executable volume
        buy_volume = data[buy_ex]['orderbook']['asks'][0][1]
        sell_volume = data[sell_ex]['orderbook']['bids'][0][1]
        executable_volume = min(buy_volume, sell_volume)
        
        # Calculate slippage impact
        slippage = self.calculate_slippage(
            data[buy_ex]['orderbook'],
            data[sell_ex]['orderbook'],
            executable_volume
        )
        
        net_profit_after_slippage = net_profit - slippage
        
        return {
            'symbol': symbol,
            'buy_exchange': buy_ex,
            'sell_exchange': sell_ex,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'gross_spread': gross_spread,
            'total_costs': total_costs,
            'net_profit': net_profit,
            'slippage_impact': slippage,
            'final_profit': net_profit_after_slippage,
            'executable_volume': executable_volume,
            'profit_usd': executable_volume * buy_price * (net_profit_after_slippage / 100)
        }
    
    def calculate_slippage(self, buy_orderbook, sell_orderbook, volume):
        """
        Calculate price impact of executing volume
        """
        # Calculate average execution price through orderbook levels
        buy_avg = self.walk_orderbook(buy_orderbook['asks'], volume)
        sell_avg = self.walk_orderbook(sell_orderbook['bids'], volume, reverse=True)
        
        # Compare to best prices
        buy_slippage = ((buy_avg - buy_orderbook['asks'][0][0]) / buy_orderbook['asks'][0][0]) * 100
        sell_slippage = ((sell_orderbook['bids'][0][0] - sell_avg) / sell_orderbook['bids'][0][0]) * 100
        
        return buy_slippage + sell_slippage
    
    def score_opportunities(self, opportunities):
        """
        Multi-factor scoring algorithm
        """
        for opp in opportunities:
            # Profit score (0-40 points)
            profit_score = min(40, opp['final_profit'] * 10)
            
            # Volume score (0-30 points)
            volume_score = min(30, (opp['profit_usd'] / 100) * 30)
            
            # Risk score (0-20 points)
            risk_score = 20 - (opp['slippage_impact'] * 4)
            
            # Execution score (0-10 points)
            exec_score = 10 if opp['executable_volume'] > 1000 else 5
            
            opp['total_score'] = profit_score + volume_score + risk_score + exec_score
            opp['score_breakdown'] = {
                'profit': profit_score,
                'volume': volume_score,
                'risk': risk_score,
                'execution': exec_score
            }
        
        # Sort by total score
        opportunities.sort(key=lambda x: x['total_score'], reverse=True)
        
        return opportunities
```

## Technical Implementation Plan

### Project Structure

```
broad_market_scanner/
├── config/
│   ├── exchanges.yaml          # Exchange configurations
│   ├── filters.yaml            # Filter parameters
│   └── credentials.yaml        # API keys (gitignored)
├── src/
│   ├── __init__.py
│   ├── exchange_manager.py     # CCXT exchange management
│   ├── symbol_discovery.py     # Symbol discovery and filtering
│   ├── data_collector.py       # Data collection pipeline
│   ├── spread_analyzer.py      # Spread analysis engine
│   ├── opportunity_ranker.py   # Opportunity scoring
│   ├── utils/
│   │   ├── rate_limiter.py    # Rate limiting utilities
│   │   ├── cache.py           # Caching layer
│   │   └── logger.py          # Logging configuration
│   └── models/
│       ├── opportunity.py      # Data models
│       └── symbol.py           # Symbol models
├── output/
│   ├── opportunities/          # Opportunity reports
│   ├── logs/                   # Application logs
│   └── data/                   # Raw data storage
├── tests/
│   ├── test_exchanges.py
│   ├── test_analysis.py
│   └── test_integration.py
├── requirements.txt
├── main.py                     # Entry point
└── README.md
```

### Implementation Steps

#### Step 1: Environment Setup (Day 1)

```python
# requirements.txt
ccxt>=4.0.0
asyncio
aiohttp
pandas
numpy
pyyaml
python-dotenv
coloredlogs
msgspec  # For performance-critical parsing
redis  # For caching layer
asyncio-throttle  # Rate limiting

# Setup script
async def setup_environment():
    # 1. Install dependencies
    # 2. Configure logging
    # 3. Validate CCXT installation
    # 4. Test exchange connections
    # 5. Initialize cache layer
```

#### Step 2: Exchange Integration (Days 2-3)

```python
class ExchangeManager:
    def __init__(self, config_path):
        self.config = self.load_config(config_path)
        self.exchanges = {}
        self.connection_pool = {}
        
    async def initialize_all(self):
        """Initialize all configured exchanges"""
        tasks = []
        for exchange_config in self.config['exchanges']:
            task = self.initialize_exchange(exchange_config)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log initialization results
        for config, result in zip(self.config['exchanges'], results):
            if isinstance(result, Exception):
                logger.error(f"Failed to initialize {config['id']}: {result}")
            else:
                self.exchanges[config['id']] = result
                
    async def initialize_exchange(self, config):
        """Initialize single exchange with CCXT"""
        exchange_class = getattr(ccxt, config['id'])
        
        exchange = exchange_class({
            'apiKey': config.get('apiKey'),
            'secret': config.get('secret'),
            'enableRateLimit': True,
            'rateLimit': config.get('rateLimit', 100),
            'options': config.get('options', {})
        })
        
        # Load markets
        await exchange.load_markets()
        
        # Validate capabilities
        required_features = ['fetchOHLCV', 'fetchOrderBook', 'fetchTicker']
        for feature in required_features:
            if not exchange.has.get(feature):
                logger.warning(f"{config['id']} missing {feature}")
        
        return exchange
```

#### Step 3: Symbol Discovery Implementation (Days 4-5)

```python
class SymbolDiscoveryEngine:
    def __init__(self, exchange_manager, filters):
        self.exchange_manager = exchange_manager
        self.filters = filters
        self.symbol_matrix = {}
        
    async def discover(self):
        """Complete symbol discovery process"""
        # 1. Fetch all symbols
        raw_symbols = await self.fetch_all_symbols()
        
        # 2. Build availability matrix
        self.build_availability_matrix(raw_symbols)
        
        # 3. Apply filters
        filtered = await self.apply_filter_pipeline()
        
        # 4. Enrich with metadata
        enriched = await self.enrich_symbols(filtered)
        
        return enriched
    
    async def fetch_all_symbols(self):
        """Fetch symbols from all exchanges"""
        all_symbols = {}
        
        for exchange_id, exchange in self.exchange_manager.exchanges.items():
            try:
                markets = exchange.markets
                
                for symbol, market in markets.items():
                    # Only spot markets with USD-stable quotes
                    if (market['spot'] and 
                        market['active'] and
                        market['quote'] in ['USDT', 'USDC', 'USD']):
                        
                        normalized = self.normalize_symbol(symbol)
                        
                        if normalized not in all_symbols:
                            all_symbols[normalized] = {
                                'cex': market['cex'],
                                'quote': market['quote'],
                                'exchanges': set()
                            }
                        
                        all_symbols[normalized]['exchanges'].add(exchange_id)
                        
            except Exception as e:
                logger.error(f"Error fetching symbols from {exchange_id}: {e}")
                
        return all_symbols
```

#### Step 4: Data Collection Implementation (Days 6-7)

```python
class DataCollector:
    def __init__(self, exchange_manager):
        self.exchange_manager = exchange_manager
        self.rate_limiter = RateLimiter()
        
    async def collect_comprehensive_data(self, symbols, config):
        """
        Collect all required data for analysis
        """
        collection_tasks = {
            'ohlcv': self.collect_ohlcv_data(symbols, config),
            'orderbooks': self.collect_orderbook_data(symbols),
            'tickers': self.collect_ticker_data(symbols),
            'trades': self.collect_recent_trades(symbols)
        }
        
        # Execute all collection tasks in parallel
        results = await asyncio.gather(
            *collection_tasks.values(),
            return_exceptions=True
        )
        
        # Combine results
        combined_data = {}
        for task_name, result in zip(collection_tasks.keys(), results):
            if not isinstance(result, Exception):
                combined_data[task_name] = result
            else:
                logger.error(f"Collection failed for {task_name}: {result}")
                
        return combined_data
```

#### Step 5: Analysis Engine (Days 8-9)

```python
class AnalysisEngine:
    def __init__(self, fee_calculator):
        self.fee_calculator = fee_calculator
        self.analyzer = ArbitrageAnalyzer(fee_calculator)
        
    async def run_analysis(self, data):
        """
        Run complete analysis pipeline
        """
        # 1. Prepare data
        prepared_data = self.prepare_data(data)
        
        # 2. Find opportunities
        opportunities = await self.analyzer.analyze_opportunities(prepared_data)
        
        # 3. Calculate detailed metrics
        detailed_opportunities = self.calculate_detailed_metrics(opportunities)
        
        # 4. Generate report
        report = self.generate_report(detailed_opportunities)
        
        return report
```

#### Step 6: Output and Monitoring (Day 10)

```python
class OutputManager:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        
    async def export_opportunities(self, opportunities, format='json'):
        """
        Export opportunities in various formats
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if format == 'json':
            filename = f"opportunities_{timestamp}.json"
            filepath = os.path.join(self.output_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(opportunities, f, indent=2, default=str)
                
        elif format == 'csv':
            filename = f"opportunities_{timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename)
            
            df = pd.DataFrame(opportunities)
            df.to_csv(filepath, index=False)
            
        return filepath
```

### Main Execution Loop

```python
async def main():
    """
    Main execution loop for the scanner
    """
    # 1. Initialize components
    config = load_config('config/config.yaml')
    exchange_manager = ExchangeManager(config)
    await exchange_manager.initialize_all()
    
    # 2. Discover symbols
    discovery_engine = SymbolDiscoveryEngine(exchange_manager, config['filters'])
    symbols = await discovery_engine.discover()
    logger.info(f"Discovered {len(symbols)} eligible symbols")
    
    # 3. Collect data
    collector = DataCollector(exchange_manager)
    data = await collector.collect_comprehensive_data(symbols, config['collection'])
    
    # 4. Analyze opportunities
    analyzer = AnalysisEngine(config['fees'])
    opportunities = await analyzer.run_analysis(data)
    
    # 5. Export results
    output_manager = OutputManager(config['output_dir'])
    report_path = await output_manager.export_opportunities(opportunities)
    logger.info(f"Report saved to {report_path}")
    
    # 6. Optional: Send alerts for high-value opportunities
    alert_manager = AlertManager(config['alerts'])
    await alert_manager.send_alerts(opportunities)
    
    return opportunities

if __name__ == "__main__":
    # Run with proper event loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
```

## Performance Considerations

### Rate Limiting Strategy

```python
class IntelligentRateLimiter:
    def __init__(self):
        self.limits = {}  # Per-exchange limits
        self.request_history = defaultdict(deque)
        self.backoff_states = {}
        
    async def acquire(self, exchange_id):
        """
        Acquire permission to make request
        """
        # Check if in backoff
        if exchange_id in self.backoff_states:
            backoff_until = self.backoff_states[exchange_id]
            if datetime.now() < backoff_until:
                wait_time = (backoff_until - datetime.now()).total_seconds()
                await asyncio.sleep(wait_time)
        
        # Check rate limit
        limit = self.limits.get(exchange_id, 10)  # Default 10 req/s
        
        # Clean old requests
        cutoff = datetime.now() - timedelta(seconds=1)
        self.request_history[exchange_id] = deque(
            t for t in self.request_history[exchange_id] if t > cutoff
        )
        
        # Wait if at limit
        if len(self.request_history[exchange_id]) >= limit:
            wait_time = 1.0 / limit
            await asyncio.sleep(wait_time)
        
        # Record request
        self.request_history[exchange_id].append(datetime.now())
    
    def trigger_backoff(self, exchange_id, duration=60):
        """
        Trigger backoff on rate limit error
        """
        self.backoff_states[exchange_id] = datetime.now() + timedelta(seconds=duration)
        logger.warning(f"Backoff triggered for {exchange_id}: {duration}s")
```

### Caching Architecture

```python
class CacheLayer:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.cache_ttls = {
            'symbol_info': 3600,      # 1 hour
            'exchange_fees': 86400,   # 24 hours
            'market_cap_list': 1800,  # 30 minutes
            'orderbook': 0,           # Never cache
            'ohlcv': 60,             # 1 minute for recent
        }
        
    async def get_or_fetch(self, key, fetch_func, ttl=None):
        """
        Cache-aside pattern implementation
        """
        # Check cache
        cached = await self.redis.get(key)
        if cached:
            return msgspec.json.decode(cached)
        
        # Fetch fresh data
        data = await fetch_func()
        
        # Store in cache with TTL
        ttl = ttl or self.cache_ttls.get(key.split(':')[0], 300)
        if ttl > 0:  # Only cache if TTL > 0
            await self.redis.setex(
                key,
                ttl,
                msgspec.json.encode(data)
            )
        
        return data
```

### Parallel Processing Optimization

```python
class ParallelProcessor:
    def __init__(self, max_workers=10):
        self.semaphore = asyncio.Semaphore(max_workers)
        self.results = {}
        
    async def process_batch(self, items, process_func):
        """
        Process items in parallel with controlled concurrency
        """
        async def process_with_semaphore(item):
            async with self.semaphore:
                try:
                    return await process_func(item)
                except Exception as e:
                    logger.error(f"Error processing {item}: {e}")
                    return None
        
        # Create all tasks
        tasks = [process_with_semaphore(item) for item in items]
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        return [r for r in results if r and not isinstance(r, Exception)]
```

## Risk Analysis

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| API Rate Limiting | HIGH | HIGH | Intelligent rate limiter with backoff |
| Exchange API Changes | HIGH | MEDIUM | CCXT abstraction layer, version pinning |
| Data Quality Issues | HIGH | MEDIUM | Multi-source validation, outlier detection |
| Network Latency | MEDIUM | HIGH | Parallel processing, aggressive timeouts |
| Memory Overflow | MEDIUM | LOW | Streaming processing, bounded buffers |

### Market Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| False Arbitrage (Stale Data) | HIGH | MEDIUM | Real-time validation before execution |
| Liquidity Traps | HIGH | HIGH | Volume validation, slippage calculation |
| Withdrawal Suspensions | HIGH | LOW | Monitor exchange status, diversify |
| Fee Changes | MEDIUM | MEDIUM | Regular fee updates, conservative estimates |
| Market Manipulation | HIGH | MEDIUM | Statistical anomaly detection |

### Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| System Downtime | MEDIUM | LOW | Health checks, automatic restart |
| Data Loss | LOW | LOW | Regular backups, persistent storage |
| Configuration Errors | MEDIUM | MEDIUM | Validation layer, dry-run mode |
| Resource Exhaustion | MEDIUM | LOW | Resource monitoring, auto-scaling |

### Mitigation Strategies

```python
class RiskManager:
    def __init__(self):
        self.risk_thresholds = {
            'max_spread': 50,  # 50% maximum spread
            'min_volume': 1000,  # $1000 minimum volume
            'max_slippage': 5,  # 5% maximum slippage
            'confidence_threshold': 0.7  # 70% minimum confidence
        }
        
    async def validate_opportunity(self, opportunity):
        """
        Validate opportunity against risk thresholds
        """
        validations = [
            self.validate_spread(opportunity),
            self.validate_volume(opportunity),
            self.validate_slippage(opportunity),
            self.validate_confidence(opportunity),
            await self.validate_exchange_status(opportunity),
            await self.validate_liquidity(opportunity)
        ]
        
        return all(validations)
    
    async def validate_exchange_status(self, opportunity):
        """
        Check if exchanges are operational
        """
        # Check withdrawal status
        # Check maintenance windows
        # Verify API connectivity
        return True
```

## Conclusion

This Broad Market Opportunity Scanner provides a comprehensive solution for identifying arbitrage opportunities in low-cap cryptocurrency markets. By leveraging CCXT's unified interface across 15+ exchanges, the system can discover and analyze thousands of potential arbitrage opportunities that are typically overlooked by mainstream trading systems.

The architecture emphasizes:
- **Scalability** through parallel processing and intelligent rate limiting
- **Reliability** through comprehensive error handling and retry logic
- **Accuracy** through multi-source validation and real-time data
- **Extensibility** through modular design and CCXT abstraction

With proper implementation following this PRD, the system will provide valuable insights into emerging market inefficiencies, enabling profitable arbitrage strategies in the rapidly evolving cryptocurrency ecosystem.