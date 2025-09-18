# CEX Arbitrage Engine - Architecture Diagrams

Visual representations of the factory-pattern-based architecture with SOLID principles compliance.

## Overall System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CEX ARBITRAGE ENGINE                             │
│                         Factory Pattern Architecture                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Client/Consumer │───▶│ ExchangeFactory │───▶│ ExchangeEnum    │
│                 │    │                 │    │ (Type Safety)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Interface Layer │
                       │ BasePrivate     │
                       │ ExchangeInterface│
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Core Base       │
                       │ Classes         │
                       │ src/core/cex/   │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Exchange        │
                       │ Implementation  │
                       │ (MEXC/Gate.io)  │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Common Data     │
                       │ Structures      │
                       │ src/structs/    │
                       └─────────────────┘
```

## Interface Hierarchy

```
                    BaseExchangeInterface
                           │
                  ┌────────┴────────┐
                  │                 │
                  ▼                 ▼
     BasePublicExchangeInterface    │
          (Market Data Only)        │
                  │                 │
                  └────────┬────────┘
                           │
                           ▼
              BasePrivateExchangeInterface
                (Trading + Market Data)
                           │
                  ┌────────┴────────┐
                  │                 │
                  ▼                 ▼
        MexcPrivateExchange   GateioPrivateExchange
```

## Factory Pattern Data Flow

```
ExchangeEnum.MEXC ───┐
                     │
ExchangeConfig ──────┼──▶ ExchangeFactory.create_private_exchange()
                     │                     │
Symbols List ────────┘                     │
                                           ▼
                              ┌─────────────────────────┐
                              │   Dependency Injection  │
                              │                         │
                              │ ┌─────────────────────┐ │
                              │ │ REST Client Setup   │ │
                              │ └─────────────────────┘ │
                              │ ┌─────────────────────┐ │
                              │ │ WebSocket Client    │ │
                              │ │ Configuration       │ │
                              │ └─────────────────────┘ │
                              │ ┌─────────────────────┐ │
                              │ │ Symbol Mapper       │ │
                              │ │ Registration        │ │
                              │ └─────────────────────┘ │
                              └─────────────────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────┐
                              │ Configured Exchange     │
                              │ Instance Ready for Use  │
                              └─────────────────────────┘
```

## Component Composition Pattern

```
                    MexcPrivateExchange
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
    ┌───────────────┐ ┌──────────┐ ┌──────────────┐
    │ REST Clients  │ │ WebSocket│ │ Symbol       │
    │               │ │ Clients  │ │ Mapper       │
    │ ┌───────────┐ │ │          │ │              │
    │ │ Public    │ │ │ ┌──────┐ │ │ ┌──────────┐ │
    │ │ REST      │ │ │ │Public│ │ │ │Exchange  │ │
    │ └───────────┘ │ │ │WS    │ │ │ │Format    │ │
    │ ┌───────────┐ │ │ └──────┘ │ │ │Converter │ │
    │ │ Private   │ │ │ ┌──────┐ │ │ └──────────┘ │
    │ │ REST      │ │ │ │Private│ │ │              │
    │ └───────────┘ │ │ │WS    │ │ │              │
    └───────────────┘ │ └──────┘ │ └──────────────┘
                      └──────────┘
             │             │             │
             └─────────────┼─────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Unified Data        │
                │ Structures          │
                │ (src/structs/       │
                │  common.py)         │
                │                     │
                │ ┌─────────────────┐ │
                │ │ Symbol          │ │
                │ │ OrderBook       │ │
                │ │ Order           │ │
                │ │ AssetBalance    │ │
                │ │ Position        │ │
                │ │ Trade           │ │
                │ │ Ticker          │ │
                │ │ Kline           │ │
                │ └─────────────────┘ │
                └─────────────────────┘
```

## SOLID Principles Implementation

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SOLID PRINCIPLES                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐  Single Responsibility Principle (SRP)
│ ExchangeFactory │  ▶ Creates exchange instances only
│                 │
│ BasePublic      │  ▶ Market data operations only  
│ Interface       │
│                 │
│ BasePrivate     │  ▶ Trading operations + market data
│ Interface       │
│                 │
│ REST Clients    │  ▶ HTTP operations only
│                 │
│ WebSocket       │  ▶ Real-time streaming only
│ Clients         │
└─────────────────┘

┌─────────────────┐  Open/Closed Principle (OCP)
│ Interfaces      │  ▶ Closed for modification
│ Closed for      │
│ Modification    │
│                 │
│ New Exchanges   │  ▶ Open for extension via interfaces
│ Open for        │
│ Extension       │
└─────────────────┘

┌─────────────────┐  Liskov Substitution Principle (LSP)
│ All Exchange    │  ▶ Fully interchangeable
│ Implementations │
│ Substitutable   │
└─────────────────┘

┌─────────────────┐  Interface Segregation Principle (ISP)
│ Public Interface│  ▶ Market data components
│ (No Auth)       │
│                 │
│ Private         │  ▶ Trading components
│ Interface       │
│ (Auth Required) │
└─────────────────┘

┌─────────────────┐  Dependency Inversion Principle (DIP)
│ High-level      │  ▶ Depend on abstractions
│ Modules         │
│                 │
│ Factory         │  ▶ Provides concrete implementations
│ Injection       │
└─────────────────┘
```

## HFT Data Flow (Real-time Trading)

```
Exchange API ──▶ REST/WebSocket ──▶ Parse JSON ──▶ Transform to ──▶ No Caching ──▶ Arbitrage
    │               Clients           (msgspec)     Common Structs    (HFT Rule)     Engine
    │                                                     │
    │                                                     ▼
    │                                            ┌─────────────────┐
    │                                            │ Real-time Data  │
    │                                            │                 │
    │                                            │ • OrderBook     │
    │                                            │ • AssetBalance  │
    │                                            │ • Order Status  │
    │                                            │ • Position Data │
    │                                            │ • Trade Records │
    │                                            └─────────────────┘
    │                                                     │
    │                                                     ▼
    │                                            ┌─────────────────┐
    │                                            │ NEVER CACHED    │
    │                                            │ (HFT Compliance)│
    │                                            └─────────────────┘
    │
    ▼
┌─────────────────┐           ┌─────────────────┐
│ Static Config   │ ────────▶ │ SAFE TO CACHE   │
│ Data            │           │                 │
│                 │           │ • Symbol Maps   │
│ • Symbol Info   │           │ • Exchange Info │
│ • Trading Rules │           │ • Trading Rules │
│ • Fee Schedules │           │ • Fee Schedules │
│ • Market Hours  │           │ • Market Hours  │
└─────────────────┘           └─────────────────┘
```

## Directory Structure

```
src/
├── cex/
│   ├── factories/
│   │   ├── __init__.py
│   │   └── exchange_factory.py          ◀── Factory Pattern
│   ├── mexc/                           ◀── MEXC Implementation
│   │   ├── mexc_exchange.py
│   │   ├── rest/
│   │   ├── ws/
│   │   └── services/
│   └── gateio/                         ◀── Gate.io Implementation
│       ├── gateio_exchange.py
│       ├── rest/
│       ├── ws/
│       └── services/
├── interfaces/
│   └── cex/
│       └── base/                       ◀── Interface Layer
│           ├── base_exchange.py
│           ├── base_public_exchange.py
│           └── base_private_exchange.py
├── core/
│   └── cex/                           ◀── Core Base Classes
│       ├── rest/
│       │   ├── spot/
│       │   └── futures/
│       ├── websocket/
│       │   └── spot/
│       └── services/
│           ├── symbol_mapper/
│           └── unified_mapper/
└── structs/
    └── common.py                      ◀── Unified Data Structures
```

## Performance Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PERFORMANCE TARGETS                         │
└─────────────────────────────────────────────────────────────────────┘

Symbol Resolution:     <1μs     ┌─────────────────┐
                                │ Hash-based O(1) │
Exchange Formatting:   <1μs     │ Lookup Tables   │
                                │                 │
Common Symbols:       <0.1μs    │ Pre-computed    │
                                │ Caches          │
JSON Parsing:          <1ms     │                 │
                                │ msgspec         │
HTTP Requests:        <50ms     │ Zero-copy       │
                                │                 │
Order Placement:     <100ms     │ Connection      │
                                │ Pooling         │
WebSocket Process:     <5ms     │                 │
                                │ Aggressive      │
Cache Build:          <50ms     │ Timeouts        │
                                └─────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      ACHIEVED BENCHMARKS                           │
└─────────────────────────────────────────────────────────────────────┘

Symbol Resolution:   0.947μs    ┌─────────────────┐
                                │ 1,056,338 ops/s │
Exchange Formatting: 0.306μs    │                 │
                                │ 3,267,974 ops/s │
Common Symbols:      0.035μs    │                 │
                                │ 28,571,429 ops/s│
Cache Build:         8.7ms      │                 │
                                │ 3,603 symbols   │
95th Percentile:     <2μs       │                 │
                                │ Sub-microsecond │
99th Percentile:     <5μs       │ Performance     │
                                └─────────────────┘
```

## Trading Safety Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      HFT CACHING POLICY                            │
│                    (CRITICAL TRADING SAFETY)                       │
└─────────────────────────────────────────────────────────────────────┘

NEVER CACHE:                    SAFE TO CACHE:
┌─────────────────┐            ┌─────────────────┐
│ Real-time Data  │            │ Static Config   │
│                 │            │ Data            │
│ • OrderBook     │            │                 │
│ • Balances      │            │ • Symbol Maps   │
│ • Order Status  │            │ • Exchange Info │
│ • Positions     │            │ • Trading Rules │
│ • Recent Trades │            │ • Fee Schedules │
│ • Market Data   │            │ • Market Hours  │
│                 │            │ • API Endpoints │
│ ┌─────────────┐ │            │                 │
│ │ RATIONALE:  │ │            │ ┌─────────────┐ │
│ │             │ │            │ │ RATIONALE:  │ │
│ │ • Stale     │ │            │ │             │ │
│ │   Prices    │ │            │ │ • Static    │ │
│ │ • Failed    │ │            │ │   Data      │ │
│ │   Arbitrage │ │            │ │ • No Price  │ │
│ │ • Phantom   │ │            │ │   Impact    │ │
│ │   Liquidity │ │            │ │ • Config    │ │
│ │ • Regulatory│ │            │ │   Only      │ │
│ │   Violations│ │            │ └─────────────┘ │
│ └─────────────┘ │            └─────────────────┘
└─────────────────┘

THIS RULE SUPERSEDES ALL OTHER PERFORMANCE CONSIDERATIONS
```