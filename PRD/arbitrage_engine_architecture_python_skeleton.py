# High-Performance CEX Arbitrage Engine
# File: arb_engine_skeleton.py
# Purpose: architecture overview + Python skeleton showing connection manager,
# parser (msgspec + fastfloat), simple in-memory orderbook, arbitrage detector,
# and execution stubs. This is a starting point — optimize data-structures and
# replace stubs with exchange-specific implementations.

"""
Quick architecture diagram (textual):

+-----------------+    +---------------+    +------------------+
| Exchange WS 1   |    | Exchange WS 2 |    | Exchange WS N    |
+--------+--------+    +-------+-------+    +--------+---------+
         |                     |                     |
         |                     |                     |
   +-----v---------------------v---------------------v------+
   |              Connection Manager (uvloop + asyncio)      |
   |  - Manages reconnection/backoff, rate limits, auth      |
   +-----+--------------------+--------------------+--------+
         |                    |                    |
         |                    |                    |
   +-----v---------+    +-----v---------+   +------v--------+
   | Data Parser   |    | Data Parser   |   | Data Parser   |
   | (msgspec +    |    | (msgspec +    |   | (msgspec +    |
   |  fastfloat)   |    |  fastfloat)   |   |  fastfloat)   |
   +-----+---------+    +-----+---------+   +------^--------+
         |                    |                    |
         |                    |                    |
   +-----v-------------------------------------------------+
   |  Order Book Store (high-performance in-memory store)  |
   |  - incremental updates (apply diffs), snapshots       |
   |  - minimal locks: single-threaded async updates       |
   +-----+----------------------+--------------------------+
         |                      |
         |                      |
   +-----v---------+    +-------v---------+
   | Arbitrage     |    | Execution Layer | -> REST/WS order placement
   | Detector      |    | (async, rate-limited, retries)
   +---------------+    +-----------------+


Notes & recommendations:
- Use Python 3.11+ (TaskGroup, faster asyncio primitives).
- Use uvloop as event loop replacement for low-level scheduling gains.
- Use msgspec for zero-copy JSON decoding into typed structs where possible.
- Use fastfloat.fast_float for fast numeric parsing from strings.
- Critical code paths (parsing, best-price scanning) can be ported to Rust
  via PyO3 if Python becomes the bottleneck.
"""

# -----------------------------
# Dependencies (install):
# pip install uvloop msgspec fastfloat aiohttp anyio
# (you may use websockets or other WS libs; aiohttp is used for example)
# -----------------------------

import asyncio
import uvloop
import msgspec
from msgspec import Struct
import fastfloat
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import aiohttp

# Switch event loop to uvloop for improved performance
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# -----------------------------
# Typed message schemas using msgspec.Struct
# -----------------------------

class RawDepthUpdate(Struct):
    # Example schema — different exchanges need different schemas
    # Use exchange-specific handlers to decode into this normalized shape.
    asks: List[list[str]]  # list of [price_str, size_str]
    bids: List[list[str]]
    ts: Optional[int] = None


# Normalized order entry for internal use
@dataclass(slots=True)
class OrderEntry:
    price: float
    size: float


# -----------------------------
# Simple in-memory order book (single side maps)
# This is a reasonably fast structure for a prototype. For production,
# replace price->size dict with a sorted structure (skiplist, btree, or
# use `sortedcontainers`), or keep top-K heap for best bid/ask queries.
# -----------------------------

class InMemoryOrderBook:
    def __init__(self):
        # price -> size
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.last_update_ts = 0.0

    def apply_snapshot(self, bids: List[OrderEntry], asks: List[OrderEntry], ts: float):
        # Overwrite whole book (used on initial sync)
        self.bids.clear()
        self.asks.clear()
        for o in bids:
            self.bids[o.price] = o.size
        for o in asks:
            self.asks[o.price] = o.size
        self.last_update_ts = ts

    def apply_diff(self, bids: List[OrderEntry], asks: List[OrderEntry], ts: float):
        # Apply incremental updates
        for o in bids:
            if o.size == 0:
                self.bids.pop(o.price, None)
            else:
                self.bids[o.price] = o.size
        for o in asks:
            if o.size == 0:
                self.asks.pop(o.price, None)
            else:
                self.asks[o.price] = o.size
        self.last_update_ts = ts

    def best_bid(self) -> Optional[OrderEntry]:
        if not self.bids:
            return None
        # NOTE: calling max on keys is O(n). Replace with a sorted structure
        # or cached best price updated on every diff for O(1) reads.
        best = max(self.bids.keys())
        return OrderEntry(price=best, size=self.bids[best])

    def best_ask(self) -> Optional[OrderEntry]:
        if not self.asks:
            return None
        best = min(self.asks.keys())
        return OrderEntry(price=best, size=self.asks[best])


# -----------------------------
# Parser helpers
# -----------------------------

def parse_price_size_list(raw_list: List[List[str]]) -> List[OrderEntry]:
    # Convert list of [price_str, size_str] into OrderEntry using fastfloat
    out: List[OrderEntry] = []
    for price_s, size_s in raw_list:
        # fastfloat.fast_float is very fast for str -> float conversion
        try:
            p = fastfloat.fast_float(price_s)
            s = fastfloat.fast_float(size_s)
        except Exception:
            # fallback - should rarely happen if exchange sends clean data
            p = float(price_s)
            s = float(size_s)
        out.append(OrderEntry(price=p, size=s))
    return out


# Example: decode raw JSON payload into normalized RawDepthUpdate
# In practice each exchange has different payloads; write small adapter functions
# that decode exchange payloads into RawDepthUpdate or directly into OrderEntry lists.

def decode_msgspec_array_payload(payload: bytes) -> List[str]:
    # Example of decoding a JSON array of strings fast using msgspec
    # returns list[str]
    return msgspec.json.decode(payload, type=list[str])


# -----------------------------
# Connection manager and exchange handler skeleton
# -----------------------------

class ExchangeConnection:
    def __init__(self, name: str, ws_url: str, symbol: str):
        self.name = name
        self.ws_url = ws_url
        self.symbol = symbol
        self.orderbook = InMemoryOrderBook()
        self.session = aiohttp.ClientSession()
        self._task: Optional[asyncio.Task] = None
        self._alive = False

    async def connect_and_listen(self):
        # Basic retry/backoff loop
        backoff = 0.5
        while True:
            try:
                async with self.session.ws_connect(self.ws_url, heartbeat=30) as ws:
                    self._alive = True
                    backoff = 0.5
                    await self._subscribe(ws)
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._on_text(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await self._on_binary(msg.data)
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            break
            except Exception as e:
                # logging with proper logger in real code
                print(f"[{self.name}] connection error: {e}")
            self._alive = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 10)

    async def _subscribe(self, ws):
        # Exchange-specific subscribe message
        # e.g. ws.send_json({"op": "subscribe", "args": [f"depth:{self.symbol}"]})
        pass

    async def _on_text(self, data: str):
        # Common case: textual JSON messages
        # Convert to bytes and handle via msgspec or exchange-specific decoder
        await self._handle_raw_payload(data.encode())

    async def _on_binary(self, data: bytes):
        # Some exchanges compress or use binary payloads
        await self._handle_raw_payload(data)

    async def _handle_raw_payload(self, payload: bytes):
        # Decode / parse and apply to orderbook
        # Here we assume payload is already JSON matching RawDepthUpdate for demo
        try:
            # decode into RawDepthUpdate if possible
            parsed = msgspec.json.decode(payload, type=RawDepthUpdate)
            bids = parse_price_size_list(parsed.bids)
            asks = parse_price_size_list(parsed.asks)
            ts = parsed.ts or time.time()
            self.orderbook.apply_diff(bids=bids, asks=asks, ts=ts)
        except msgspec.DecodeError:
            # fallback — implement exchange-specific parsing here
            # e.g. if exchange sends arrays: [ ["price","size"], ... ]
            # or compressed payloads
            pass

    async def start(self):
        self._task = asyncio.create_task(self.connect_and_listen())

    async def stop(self):
        if self._task:
            self._task.cancel()
        await self.session.close()


# -----------------------------
# Arbitrage detection
# -----------------------------

@dataclass
class ArbOpportunity:
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    size: float
    spread: float
    timestamp: float


class ArbitrageDetector:
    def __init__(self, exchanges: Dict[str, ExchangeConnection], fee_model=None):
        self.exchanges = exchanges
        self.fee_model = fee_model or (lambda ex, side, price: 0.0005)  # simple fee

    def scan_once(self) -> Optional[ArbOpportunity]:
        # Naive O(N^2) scan: check best asks vs best bids across exchanges
        best_ask = None
        best_ask_ex = None
        best_bid = None
        best_bid_ex = None

        for name, ex in self.exchanges.items():
            a = ex.orderbook.best_ask()
            b = ex.orderbook.best_bid()
            if a:
                if (best_ask is None) or (a.price < best_ask.price):
                    best_ask = a
                    best_ask_ex = name
            if b:
                if (best_bid is None) or (b.price > best_bid.price):
                    best_bid = b
                    best_bid_ex = name

        if not best_ask or not best_bid:
            return None

        # Compute gross spread
        spread = best_bid.price - best_ask.price
        if spread <= 0:
            return None

        # Estimate fees
        fee_buy = self.fee_model(best_ask_ex, 'buy', best_ask.price)
        fee_sell = self.fee_model(best_bid_ex, 'sell', best_bid.price)
        # naive net spread after fees
        net_spread = spread - (best_ask.price * fee_buy + best_bid.price * fee_sell)
        # size constrained by both sides
        size = min(best_ask.size, best_bid.size)

        if net_spread > 0:
            return ArbOpportunity(
                buy_exchange=best_ask_ex,
                sell_exchange=best_bid_ex,
                buy_price=best_ask.price,
                sell_price=best_bid.price,
                size=size,
                spread=net_spread,
                timestamp=time.time(),
            )
        return None


# -----------------------------
# Execution layer (stub)
# -----------------------------

class ExecutionEngine:
    def __init__(self):
        # store API clients / credentials here
        pass

    async def execute_arbitrage(self, arb: ArbOpportunity):
        # This must be highly optimized and handle partial fills,
        # race conditions, cancellations, and idempotency.
        print(f"EXECUTE ARB: {arb}")
        # 1) Place buy on buy_exchange
        # 2) After buy filled (or immediately if market), place sell on sell_exchange
        # 3) Track fills and rebalances
        # Implement retry, order tracking, and hedging paths.
        return True


# -----------------------------
# Orchestration / main loop
# -----------------------------

async def main():
    # Create exchange connections (example placeholders)
    ex_a = ExchangeConnection(name="EX_A", ws_url="wss://example-a/ws", symbol="BTC-USDT")
    ex_b = ExchangeConnection(name="EX_B", ws_url="wss://example-b/ws", symbol="BTC-USDT")

    exchanges = {ex_a.name: ex_a, ex_b.name: ex_b}

    # Start connections
    await asyncio.gather(*(ex.start() for ex in exchanges.values()))

    detector = ArbitrageDetector(exchanges)
    exec_engine = ExecutionEngine()

    try:
        while True:
            arb = detector.scan_once()
            if arb:
                # In production, push to an async queue consumed by execution workers
                await exec_engine.execute_arbitrage(arb)
            # Sleep short interval -- tune to your throughput/latency needs
            await asyncio.sleep(0.001)
    except asyncio.CancelledError:
        pass
    finally:
        await asyncio.gather(*(ex.stop() for ex in exchanges.values()))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('shutting down')
