# Component Diagrams & System Architecture

## System Component Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        CEX ARBITRAGE ENGINE - COMPONENT ARCHITECTURE                │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                 ┌─────────────────────┐
                                 │    Main Entry       │
                                 │   (src/main.py)     │
                                 │  CLI & Lifecycle    │
                                 └──────────┬──────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│                              APPLICATION LAYER                                     │
│                                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│  │ ArbitrageController │  │PerformanceMonitor │  │ ShutdownManager │  │ SimpleEngine  │ │
│  │                 │  │                 │  │                 │  │               │ │
│  │ • Orchestrates  │  │ • HFT Monitoring│  │ • Graceful      │  │ • Trading     │ │
│  │   all components│  │ • Latency Tracking│  │   Shutdown     │  │   Logic       │ │
│  │ • SOLID compliant│  │ • Compliance    │  │ • Resource     │  │ • Opportunity │ │
│  │ • DI Pattern    │  │   Alerting      │  │   Cleanup      │  │   Detection   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └───────────────┘ │
└────────────────────────────────────┬───────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│                            CONFIGURATION LAYER                                    │
│                                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│  │ConfigurationMgr │  │ ExchangeFactory │  │  SymbolResolver │  │ HftConfig     │ │
│  │                 │  │                 │  │                 │  │               │ │
│  │ • SRP Compliant │  │ • Factory Pattern│  │ • O(1) Symbol  │  │ • Singleton   │ │
│  │ • Config Loading│  │ • Dynamic       │  │   Resolution    │  │ • Environment │ │
│  │ • Validation    │  │   Creation      │  │ • <1μs Latency  │  │   Variables   │ │
│  │ • Pair Resolution│  │ • Error Recovery│  │ • HFT Optimized │  │ • YAML Config │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └───────────────┘ │
└────────────────────────────────────┬───────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│                              EXCHANGE LAYER                                       │
│                                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│  │  MEXC Exchange  │  │ Gate.io Exchange│  │Future Exchanges │  │ BaseInterface │ │
│  │ (BaseExchange)  │  │ (BaseExchange)  │  │ (BaseExchange)  │  │ (Abstract)    │ │
│  │ • REST Client   │  │ • REST Client   │  │ • Pluggable     │  │ • All inherit │ │
│  │ • WebSocket     │  │ • WebSocket     │  │   Architecture  │  │   from THIS   │ │
│  │ • Private/Public│  │ • Private/Public│  │ • Zero Code     │  │ • Type Safety │ │
│  │ • Composition   │  │ • Composition   │  │   Changes       │  │ • SOLID       │ │
│  │   Pattern       │  │   Pattern       │  │                 │  │   Compliance  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └───────────────┘ │
└────────────────────────────────────┬───────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│                           INFRASTRUCTURE LAYER                                    │
│                                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│  │   RestClient    │  │ WebSocketClient │  │   Exceptions    │  │    Utils      │ │
│  │                 │  │                 │  │                 │  │               │ │
│  │ • HTTP/2 Support│  │ • Auto Reconnect│  │ • Unified       │  │ • Logging     │ │
│  │ • Connection    │  │ • Heartbeat     │  │   Hierarchy     │  │ • Validation  │ │
│  │   Pooling       │  │ • Real-time     │  │ • Error         │  │ • Performance │ │
│  │ • Rate Limiting │  │   Data Streams  │  │   Propagation   │  │   Utilities   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └───────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────┘
```

## SOLID Principles Component Design

### Single Responsibility Principle (SRP)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        SINGLE RESPONSIBILITY COMPONENTS                             │
└─────────────────────────────────────────────────────────────────────────────────────┘

ConfigurationManager              ExchangeFactory                PerformanceMonitor
┌─────────────────┐              ┌─────────────────┐            ┌─────────────────┐
│ ONLY HANDLES:   │              │ ONLY HANDLES:   │            │ ONLY HANDLES:   │
│ • Config loading│              │ • Exchange      │            │ • Performance   │
│ • Validation    │──────────────│   creation      │────────────│   tracking      │
│ • Environment   │              │ • Credential    │            │ • HFT monitoring│
│   management    │              │   management    │            │ • Alerting      │
│ • Pair resolution│             │ • Initialization│            │ • Compliance    │
└─────────────────┘              └─────────────────┘            └─────────────────┘
        │                                │                              │
        ▼                                ▼                              ▼
ShutdownManager                  ArbitrageController            SymbolResolver
┌─────────────────┐              ┌─────────────────┐            ┌─────────────────┐
│ ONLY HANDLES:   │              │ ONLY HANDLES:   │            │ ONLY HANDLES:   │
│ • Graceful      │              │ • Component     │            │ • O(1) Symbol   │
│   shutdown      │              │   orchestration │            │   lookups       │
│ • Resource      │              │ • Dependency    │            │ • Formatting    │
│   cleanup       │              │   injection     │            │ • Cache         │
│ • Signal        │              │ • System        │            │   management    │
│   handling      │              │   coordination  │            │ • Performance   │
└─────────────────┘              └─────────────────┘            └─────────────────┘
```

### Dependency Inversion Principle (DIP)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                       DEPENDENCY INVERSION ARCHITECTURE                             │
└─────────────────────────────────────────────────────────────────────────────────────┘

HIGH-LEVEL MODULES (Application Layer)
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         ArbitrageController                                         │
│                                                                                     │
│  Depends on ABSTRACTIONS (interfaces), not concrete implementations                │
│                                                                                     │
│  constructor(                                                                       │
│      configuration_manager: ConfigurationManagerInterface,    # Abstract interface │
│      exchange_factory: ExchangeFactoryInterface,             # Abstract interface │
│      performance_monitor: PerformanceMonitorInterface,       # Abstract interface │
│      shutdown_manager: ShutdownManagerInterface              # Abstract interface │
│  )                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                 DEPENDS ON ABSTRACTIONS
                                        │
                                        ▼
ABSTRACTIONS LAYER (Interfaces)
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  BaseExchangeInterface    ConfigManagerInterface    PerformanceInterface           │
│  ┌─────────────────┐     ┌─────────────────┐       ┌─────────────────┐            │
│  │ • init()        │     │ • load_config() │       │ • start()       │            │
│  │ • get_orderbook()│     │ • validate()    │       │ • record()      │            │
│  │ • close()       │     │ • get_config()  │       │ • alert()       │            │
│  └─────────────────┘     └─────────────────┘       └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                 IMPLEMENTED BY
                                        │
                                        ▼
LOW-LEVEL MODULES (Implementations)
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  MexcExchange        ConfigurationManager         HFTPerformanceMonitor            │
│  GateioExchange      ExchangeFactory              SimpleArbitrageEngine            │
│  FutureExchange      SymbolResolver               ShutdownManager                  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Configuration Architecture Diagram

### Unified Configuration Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        UNIFIED CONFIGURATION ARCHITECTURE                           │
└─────────────────────────────────────────────────────────────────────────────────────┘

CONFIGURATION SOURCES
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   config.yaml   │    │   .env file     │    │   Environment   │
│                 │    │                 │    │   Variables     │
│ exchanges:      │    │ MEXC_API_KEY=   │    │ Override .env   │
│   mexc:         │    │ MEXC_SECRET=    │    │ if present      │
│     api_key: ${...} │ │ GATEIO_API_KEY= │    │                 │
│   gateio:       │    │ GATEIO_SECRET=  │    │                 │
│     api_key: ${...} │ └─────────────────┘    └─────────────────┘
└─────────────────┘              │                        │
         │                       │                        │
         └───────────────────────┼────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────┐
                    │ Environment Variable│
                    │    Substitution     │
                    │                     │
                    │ ${VAR_NAME}         │
                    │ ${VAR_NAME:default} │
                    └─────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────┐
                    │    HftConfig       │
                    │   (Singleton)      │
                    │                    │
                    │ • Unified methods  │
                    │ • Dynamic lookup   │
                    │ • Validation       │
                    └─────────────────────┘
                                 │
                                 ▼
          ┌─────────────────────────────────────────────┐
          │        UNIFIED ACCESS METHODS               │
          │                                             │
          │ get_exchange_config(name) → Dict[str, Any]  │
          │ get_exchange_credentials(name) → Dict       │
          │ has_exchange_credentials(name) → bool       │
          └─────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              CONSUMERS                                              │
│                                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│  │ConfigurationMgr │  │ ExchangeFactory │  │    Exchanges    │  │   Any New     │ │
│  │                 │  │                 │  │                 │  │  Component    │ │
│  │ Uses unified    │  │ Dynamic         │  │ Get exchange-   │  │ Automatic     │ │
│  │ methods for     │  │ credential      │  │ specific config │  │ integration   │ │
│  │ arbitrage config│  │ lookup          │  │ via unified API │  │ via unified   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │   methods     │ │
│                                                                  └───────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Architecture

### Symbol Resolution Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                       O(1) SYMBOL RESOLUTION FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘

INITIALIZATION PHASE (Startup)
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Exchange A    │    │   Exchange B    │    │   Exchange C    │
│                 │    │                 │    │                 │
│ active_symbols: │    │ active_symbols: │    │ active_symbols: │
│ [SymbolInfo...] │    │ [SymbolInfo...] │    │ [SymbolInfo...] │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────┐
                    │  SymbolResolver     │
                    │  initialize()       │
                    │                     │
                    │ Build hash tables:  │
                    │ • _symbol_lookup    │
                    │ • _common_cache     │
                    │ • _format_cache     │
                    └─────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────┐
              │         O(1) LOOKUP TABLES           │
              │                                      │
              │ _symbol_lookup: Dict[               │
              │   Tuple[str, str],                  │ <- (base, quote) key
              │   Dict[str, SymbolInfo]             │ <- exchange → SymbolInfo
              │ ]                                   │
              │                                     │
              │ _common_symbols_cache: Dict[        │
              │   FrozenSet[str],                   │ <- exchange set key  
              │   Set[Symbol]                       │ <- common symbols
              │ ]                                   │
              │                                     │
              │ _exchange_formatting_cache: Dict[   │
              │   str,                              │ <- exchange name
              │   Dict[Symbol, str]                 │ <- symbol → format
              │ ]                                   │
              └──────────────────────────────────────┘

RUNTIME PHASE (Trading)
┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
│ get_symbol_info │─────────────→│   Hash Lookup   │─────────────→│   SymbolInfo    │
│ (symbol, exch)  │   0.947μs    │   O(1) access   │   <1μs       │   (result)      │
└─────────────────┘              └─────────────────┘              └─────────────────┘

┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
│get_common_symbols│─────────────→│   Cache Lookup  │─────────────→│   Set[Symbol]   │
│ (exchange_set)  │   0.035μs    │   O(1) access   │   <0.1μs     │   (result)      │
└─────────────────┘              └─────────────────┘              └─────────────────┘

┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
│ format_symbol   │─────────────→│  Format Lookup  │─────────────→│ Formatted String│
│ (symbol, exch)  │   0.306μs    │   O(1) access   │   <1μs       │   (result)      │
└─────────────────┘              └─────────────────┘              └─────────────────┘
```

### Exchange Integration Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                       EXCHANGE INTEGRATION FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘

NEW EXCHANGE ADDITION
┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
│ Add to config.  │─────────────→│ Environment     │─────────────→│ Unified Config  │
│ yaml exchanges: │              │ Variables       │              │ System          │
│ newexchange:    │              │ NEW_API_KEY=... │              │ Recognizes      │
│   api_key: ${...} │            │ NEW_SECRET=...  │              │ New Exchange    │
└─────────────────┘              └─────────────────┘              └─────────────────┘
                                                                           │
                                                                           ▼
┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
│ Implement       │─────────────→│ Register in     │─────────────→│ Factory Creates │
│ BaseExchange    │              │ ExchangeFactory │              │ New Instance    │
│ Interface       │              │ EXCHANGE_CLASSES│              │ Automatically   │
└─────────────────┘              └─────────────────┘              └─────────────────┘
                                                                           │
                                                                           ▼
                              ┌──────────────────────────────────────┐
                              │         ZERO CODE CHANGES            │
                              │                                      │
                              │ • ConfigurationManager: works       │
                              │ • SymbolResolver: integrates        │
                              │ • PerformanceMonitor: tracks        │
                              │ • ArbitrageController: orchestrates │
                              │                                      │
                              │ All existing components work with    │
                              │ new exchange automatically!          │
                              └──────────────────────────────────────┘
```

## Performance Monitoring Components

### HFT Performance Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                       HFT PERFORMANCE MONITORING SYSTEM                            │
└─────────────────────────────────────────────────────────────────────────────────────┘

                               ┌─────────────────┐
                               │ HFTPerformance  │
                               │    Monitor      │
                               │                 │
                               │ Target: <50ms   │
                               │ Alert: >30ms    │
                               └─────────┬───────┘
                                        │
                  ┌─────────────────────┼─────────────────────┐
                  │                     │                     │
                  ▼                     ▼                     ▼
        ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
        │  Latency        │   │   Memory        │   │   Throughput    │
        │  Tracking       │   │   Monitor       │   │   Monitor       │
        │                 │   │                 │   │                 │
        │ • Request times │   │ • Memory usage  │   │ • Ops/second    │
        │ • Symbol lookup │   │ • GC pressure   │   │ • Success rate  │
        │ • Config access │   │ • Pool status   │   │ • Error rate    │
        └─────────────────┘   └─────────────────┘   └─────────────────┘
                  │                     │                     │
                  └─────────────────────┼─────────────────────┘
                                        │
                                        ▼
                          ┌─────────────────────┐
                          │  Compliance         │
                          │  Validator          │
                          │                     │
                          │ HFT Requirements:   │
                          │ ✅ <50ms latency    │
                          │ ✅ <1μs symbol res  │
                          │ ✅ <200MB memory    │
                          │ ✅ >95% success     │
                          └─────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
          ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
          │   Alerting      │ │   Reporting     │ │   Auto-Recovery │
          │                 │ │                 │ │                 │
          │ • Email alerts  │ │ • Metrics dash  │ │ • Conn refresh  │
          │ • Webhook       │ │ • Performance   │ │ • Rate limiting │
          │ • Slack notify  │ │   reports       │ │ • Circuit break │
          └─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Error Handling & Resilience

### Fail-Fast Error Propagation

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         ERROR HANDLING ARCHITECTURE                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

ERROR SOURCES
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌───────────────┐
│ Network Errors  │    │ Config Errors   │    │ Exchange Errors │    │ System Errors │
│                 │    │                 │    │                 │    │               │
│ • Timeout       │    │ • Invalid YAML  │    │ • API limits    │    │ • Memory      │
│ • Connection    │    │ • Missing keys  │    │ • Auth failure  │    │ • CPU spike   │
│ • DNS failure   │    │ • Bad format    │    │ • Market closed │    │ • Disk space  │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └───────────────┘
         │                       │                       │                       │
         └───────────────────────┼───────────────────────┼───────────────────────┘
                                 │                       │
                                 ▼                       ▼
                    ┌─────────────────────────┐
                    │   Unified Exception     │
                    │     Hierarchy           │
                    │                         │
                    │ ExchangeAPIError        │
                    │ ConfigurationError      │
                    │ NetworkError            │
                    │ ValidationError         │
                    └─────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
          ┌─────────────────┐ ┌──────────┐ ┌─────────────────┐
          │  FAIL-FAST      │ │ LOGGING  │ │   RECOVERY      │
          │                 │ │          │ │                 │
          │ • No silent     │ │ • Struct │ │ • Retry logic   │
          │   failures      │ │   logging│ │ • Circuit break │
          │ • Immediate     │ │ • Context│ │ • Graceful      │
          │   propagation   │ │   preserv│ │   degradation   │
          │ • Clear errors  │ │ • Audit  │ │ • Auto-recovery │
          └─────────────────┘ └──────────┘ └─────────────────┘
```

## Testing Architecture

### Component Testing Strategy

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           TESTING ARCHITECTURE                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

UNIT TESTS
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌───────────────┐
│ Component Tests │    │Interface Tests  │    │Performance Tests│    │ Config Tests  │
│                 │    │                 │    │                 │    │               │
│ • Individual    │    │ • Contract      │    │ • Latency       │    │ • Validation  │
│   component     │    │   compliance    │    │ • Throughput    │    │ • Environment │
│ • Mock          │    │ • Type safety   │    │ • Memory usage  │    │ • Substitution│
│   dependencies  │    │ • Error         │    │ • HFT targets   │    │ • Edge cases  │
└─────────────────┘    │   handling      │    └─────────────────┘    └───────────────┘
                       └─────────────────┘
                                 │
                                 ▼
INTEGRATION TESTS
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│ │Exchange Factory │  │Symbol Resolution│  │Config Loading   │  │ Full System   │  │
│ │Integration      │  │Integration      │  │Integration      │  │ Integration   │  │
│ │                 │  │                 │  │                 │  │               │  │
│ │ • Multi-exchange│  │ • Cross-exchange│  │ • Environment   │  │ • End-to-end  │  │
│ │   creation      │  │   symbol lookup │  │   integration   │  │   workflow    │  │
│ │ • Error recovery│  │ • Performance   │  │ • Validation    │  │ • Performance │  │
│ │ • Credentials   │  │   validation    │  │   flow          │  │   compliance  │  │
│ └─────────────────┘  └─────────────────┘  └─────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘

SYSTEM TESTS
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│ │  HFT Compliance │  │ Multi-Exchange  │  │  Configuration  │  │  Resilience   │  │
│ │     Testing     │  │    Trading      │  │    Scenarios    │  │   Testing     │  │
│ │                 │  │                 │  │                 │  │               │  │
│ │ • <50ms latency │  │ • Cross-exchange│  │ • Various envs  │  │ • Network     │  │
│ │ • <1μs symbols  │  │   arbitrage     │  │ • Missing creds │  │   failures    │  │
│ │ • Memory limits │  │ • Opportunity   │  │ • Invalid config│  │ • Exchange    │  │
│ │ • Throughput    │  │   detection     │  │ • Edge cases    │  │   downtime    │  │
│ └─────────────────┘  └─────────────────┘  └─────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

*This component architecture ensures clean separation of concerns, SOLID principles compliance, and HFT-ready performance while maintaining the unified configuration system that enables seamless exchange integration.*