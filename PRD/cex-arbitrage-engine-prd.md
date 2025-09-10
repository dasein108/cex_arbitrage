# PRD: High-Performance CEX Arbitrage Engine

## 1. Goal

Build an ultra-low-latency arbitrage engine that:
* Connects to multiple CEX WebSocket feeds simultaneously.
* Listens to order book updates in real-time.
* Parses, normalizes, and stores data efficiently.
* Detects arbitrage opportunities across exchanges.
* Executes buy/sell orders with minimal delay.

## 2. Requirements

### Functional

1. **WebSocket Connections**
   * Maintain concurrent connections to multiple exchanges (Binance, OKX, Bybit, etc.).
   * Auto-reconnect and handle throttling limits.

2. **Order Book Processing**
   * Parse incremental/depth updates.
   * Maintain local snapshots with minimal overhead.
   * Normalize different exchange formats into a common schema.

3. **Arbitrage Detection**
   * Continuously check best bid/ask across exchanges.
   * Support configurable thresholds (spread %, fees, slippage).

4. **Order Execution**
   * Place trades via REST/WS APIs.
   * Enforce risk controls: balance checks, limits, cooldowns.

5. **Monitoring**
   * Metrics: latency (ms), throughput (messages/sec), PnL.
   * Logging and error reporting.

### Non-Functional

* **Performance:** Sub-millisecond parsing per message, <50ms end-to-end decision loop.
* **Scalability:** Support 10–20 exchanges simultaneously.
* **Reliability:** Automatic reconnect, graceful degradation.
* **Security:** Secure API key storage, signed requests.

## 3. Architecture

### Core Components

1. **Connection Manager**
   * Async WebSocket pool with **uvloop**.
   * Resilient reconnect/backoff strategy.

2. **Data Parser**
   * Use **msgspec** for JSON decoding.
   * Use **fastfloat** for float parsing (strings → float).
   * Define schemas with `msgspec.Struct` for type safety.

```python
import msgspec, fastfloat

class Order(msgspec.Struct):
    price: float
    size: float

raw = b'["123.45","0.01"]'
arr = msgspec.json.decode(raw, type=list[str])
order = Order(fastfloat.fast_float(arr[0]), fastfloat.fast_float(arr[1]))
```

3. **Order Book Store**
   * Optimized in-memory structure (arrays or heapq) for bids/asks.
   * Minimal locking (single-threaded async loop).

4. **Arbitrage Engine**
   * Scans best bid/ask pairs across exchanges.
   * Computes profit after fees, latency penalty, slippage model.

5. **Execution Layer**
   * Async REST calls with session pooling.
   * Rate limit aware.
   * Retry with idempotency.

6. **Monitoring & Metrics**
   * Use Prometheus / OpenTelemetry.
   * Expose REST/WS API for dashboard.

## 4. Optimization Strategies

* **Event Loop:** Replace default asyncio with **uvloop**.
* **Serialization:** Replace built-in `json` with **orjson** / **msgspec**.
* **Float Parsing:** Use **fastfloat** for direct str→float conversion.
* **Data Structures:**
  * Replace Python dicts with `msgspec.Struct` or `namedtuple` for fixed schemas.
  * Use `array` / `numpy` for numeric operations instead of Python lists.
* **Concurrency:**
  * Use task groups (`asyncio.TaskGroup`) for managing exchange streams.
  * Minimize context switching.
* **Batching:** Process multiple updates in micro-batches (1–5ms windows) if throughput > latency.
* **GIL Pressure:** Offload CPU-heavy ops (PnL calculations, risk models) to Cython / Rust (via PyO3) if bottlenecked.

## 5. Success Criteria

* Stable connections to 10+ exchanges for >24h.
* Order book latency < 50ms end-to-end (WS → detection).
* Ability to detect arbitrage opportunities ≥0.1% spread.
* Trade execution success >95%.
