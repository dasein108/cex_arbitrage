# AMIA Strategy Workflow Diagrams

## Table of Contents
1. [High-Level Strategy Flow](#high-level-strategy-flow)
2. [Signal Generation Workflow](#signal-generation-workflow)
3. [Risk Management Decision Tree](#risk-management-decision-tree)
4. [Data Processing Pipeline](#data-processing-pipeline)
5. [Position Lifecycle Management](#position-lifecycle-management)
6. [Performance Monitoring Workflow](#performance-monitoring-workflow)

## High-Level Strategy Flow

```mermaid
graph TD
    A[Market Data Feed] --> B{Data Quality Check}
    B -->|Pass| C[Preprocess Data]
    B -->|Fail| D[Log Error & Skip]
    C --> E[Calculate Mid-Price Deviations]
    E --> F[Compute Opportunity Scores]
    F --> G[Generate Trading Signals]
    G --> H{Entry Signal?}
    H -->|Yes| I[Risk Assessment]
    H -->|No| J{Exit Signal?}
    I --> K{Risk Approved?}
    K -->|Yes| L[Execute Entry Trade]
    K -->|No| M[Risk Rejection Log]
    J -->|Yes| N[Execute Exit Trade]
    J -->|No| O[Continue Monitoring]
    L --> P[Position Tracking]
    N --> Q[P&L Calculation]
    P --> R{Force Close Check}
    R -->|Yes| S[Force Close Position]
    R -->|No| J
    S --> Q
    Q --> T[Performance Recording]
    T --> U[Strategy Metrics Update]
    U --> O
    M --> O
    D --> O
    O --> A

    style A fill:#e1f5fe
    style L fill:#c8e6c9
    style N fill:#ffcdd2
    style S fill:#fff3e0
```

## Signal Generation Workflow

```mermaid
graph LR
    A[Spot Exchange Data] --> C[Mid-Price Calculation]
    B[Futures Exchange Data] --> D[Mid-Price Calculation]
    C --> E[Spot Bid/Ask Deviations]
    D --> F[Futures Bid/Ask Deviations]
    E --> G[Entry Opportunity Score]
    F --> G
    E --> H[Exit Opportunity Score]
    F --> H
    G --> I{Entry Threshold Check}
    H --> J{Exit Threshold Check}
    I --> K{Individual Leg Check}
    J --> L{Individual Leg Check}
    K -->|Pass| M[Entry Signal Generated]
    K -->|Fail| N[No Entry Signal]
    L -->|Pass| O[Exit Signal Generated]
    L -->|Fail| P[No Exit Signal]

    subgraph "Entry Conditions"
        I
        K
        M
        N
    end

    subgraph "Exit Conditions"
        J
        L
        O
        P
    end

    style M fill:#c8e6c9
    style O fill:#ffcdd2
    style N fill:#f5f5f5
    style P fill:#f5f5f5
```

## Risk Management Decision Tree

```mermaid
graph TD
    A[Trading Signal Generated] --> B{Position Limit Check}
    B -->|Exceed Limit| C[Reject - Log Max Positions]
    B -->|Within Limit| D{Capital Allocation Check}
    D -->|Insufficient Capital| E[Reject - Log Insufficient Funds]
    D -->|Sufficient Capital| F{Volatility Check}
    F -->|High Volatility| G[Adjust Position Size]
    F -->|Normal Volatility| H{Correlation Check}
    G --> H
    H -->|High Correlation| I[Reduce Position Size]
    H -->|Normal Correlation| J{Drawdown Check}
    I --> J
    J -->|High Drawdown| K[Pause Strategy]
    J -->|Normal Drawdown| L{Liquidity Check}
    L -->|Low Liquidity| M[Reduce Size/Skip]
    L -->|Adequate Liquidity| N[Approve Trade]
    
    C --> O[Risk Metrics Update]
    E --> O
    K --> O
    M --> O
    N --> P[Execute Trade]
    P --> Q[Monitor Position]

    style N fill:#c8e6c9
    style C fill:#ffcdd2
    style E fill:#ffcdd2
    style K fill:#fff3e0
    style M fill:#fff9c4
```

## Data Processing Pipeline

```mermaid
graph TB
    subgraph "Data Ingestion Layer"
        A1[Spot Exchange WebSocket]
        A2[Futures Exchange WebSocket]
        A3[REST API Backup]
    end

    subgraph "Data Validation Layer"
        B1[Price Validation]
        B2[Timestamp Sync]
        B3[Outlier Detection]
        B4[Missing Data Handler]
    end

    subgraph "Calculation Layer"
        C1[Mid-Price Calculation]
        C2[Spread Calculation]
        C3[Deviation Calculation]
        C4[Opportunity Scoring]
    end

    subgraph "Signal Processing Layer"
        D1[Signal Generation]
        D2[Signal Filtering]
        D3[Signal Validation]
    end

    subgraph "Execution Layer"
        E1[Risk Assessment]
        E2[Position Management]
        E3[Order Execution]
        E4[Fill Confirmation]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    B1 --> B2
    B2 --> B3
    B3 --> B4
    B4 --> C1
    C1 --> C2
    C2 --> C3
    C3 --> C4
    C4 --> D1
    D1 --> D2
    D2 --> D3
    D3 --> E1
    E1 --> E2
    E2 --> E3
    E3 --> E4

    style A1 fill:#e3f2fd
    style A2 fill:#e3f2fd
    style C4 fill:#f3e5f5
    style D3 fill:#e8f5e8
    style E4 fill:#fff3e0
```

## Position Lifecycle Management

```mermaid
stateDiagram-v2
    [*] --> Monitoring: Strategy Active
    
    Monitoring --> SignalDetection: Market Data Update
    SignalDetection --> Monitoring: No Signal
    SignalDetection --> RiskCheck: Entry Signal
    
    RiskCheck --> Monitoring: Risk Rejected
    RiskCheck --> EntryExecution: Risk Approved
    
    EntryExecution --> PositionOpen: Trade Executed
    EntryExecution --> Monitoring: Execution Failed
    
    PositionOpen --> PositionMonitoring: Position Active
    
    PositionMonitoring --> ExitSignalCheck: Market Update
    ExitSignalCheck --> PositionMonitoring: No Exit Signal
    ExitSignalCheck --> ExitExecution: Exit Signal
    
    PositionMonitoring --> ForceClose: Max Hold Time
    PositionMonitoring --> StopLoss: Stop Loss Triggered
    
    ExitExecution --> PositionClosed: Exit Executed
    ForceClose --> PositionClosed: Force Close Executed
    StopLoss --> PositionClosed: Stop Loss Executed
    
    PositionClosed --> PnLCalculation: Calculate P&L
    PnLCalculation --> PerformanceUpdate: Update Metrics
    PerformanceUpdate --> Monitoring: Ready for Next Trade

    note right of PositionOpen
        Max 1 concurrent position
        6 hour maximum hold time
    end note

    note right of PositionClosed
        Record trade details
        Update performance metrics
    end note
```

## Performance Monitoring Workflow

```mermaid
graph TD
    A[Trade Completed] --> B[Calculate Trade P&L]
    B --> C[Update Running Metrics]
    C --> D[Calculate Sharpe Ratio]
    C --> E[Calculate Max Drawdown]
    C --> F[Calculate Hit Rate]
    C --> G[Calculate Profit Factor]
    
    D --> H{Performance Threshold Check}
    E --> H
    F --> H
    G --> H
    
    H -->|Below Threshold| I[Generate Alert]
    H -->|Above Threshold| J[Continue Normal Operation]
    
    I --> K{Critical Threshold?}
    K -->|Yes| L[Pause Strategy]
    K -->|No| M[Adjust Parameters]
    
    L --> N[Manual Review Required]
    M --> O[Parameter Optimization]
    O --> P[Backtest New Parameters]
    P --> Q{Backtest Results Good?}
    Q -->|Yes| R[Deploy New Parameters]
    Q -->|No| S[Revert to Previous]
    
    R --> J
    S --> J
    J --> T[Wait for Next Trade]
    T --> A

    style I fill:#fff3e0
    style L fill:#ffcdd2
    style N fill:#f8bbd9
    style R fill:#c8e6c9
```

## Real-Time Decision Flow

```mermaid
sequenceDiagram
    participant MD as Market Data
    participant SP as Signal Processor
    participant RM as Risk Manager
    participant PM as Position Manager
    participant EX as Exchange Executor
    participant DB as Database

    loop Every 100ms
        MD->>SP: Market Data Update
        SP->>SP: Calculate Deviations
        SP->>SP: Generate Signals
        
        alt Entry Signal Generated
            SP->>RM: Request Risk Assessment
            RM->>RM: Check Risk Limits
            alt Risk Approved
                RM->>PM: Approve Position Opening
                PM->>EX: Execute Entry Orders
                EX->>EX: Send Orders to Exchanges
                EX->>PM: Confirm Execution
                PM->>DB: Record Trade Entry
            else Risk Rejected
                RM->>DB: Log Risk Rejection
            end
        else Exit Signal Generated
            SP->>PM: Request Position Exit
            PM->>EX: Execute Exit Orders
            EX->>EX: Send Orders to Exchanges
            EX->>PM: Confirm Execution
            PM->>PM: Calculate P&L
            PM->>DB: Record Trade Exit
        else No Signal
            SP->>PM: Check Force Close
            alt Force Close Required
                PM->>EX: Execute Force Close
                EX->>PM: Confirm Execution
                PM->>DB: Record Force Close
            end
        end
    end
```

## Error Handling and Recovery Workflow

```mermaid
graph TD
    A[Error Detected] --> B{Error Type Classification}
    
    B -->|Data Error| C[Data Quality Issue]
    B -->|Network Error| D[Connectivity Issue]
    B -->|Exchange Error| E[Exchange API Issue]
    B -->|Strategy Error| F[Logic/Calculation Error]
    
    C --> C1[Log Data Issue]
    C1 --> C2[Skip Current Update]
    C2 --> C3[Continue with Backup Data]
    
    D --> D1[Log Network Issue]
    D1 --> D2[Attempt Reconnection]
    D2 --> D3{Reconnection Successful?}
    D3 -->|Yes| D4[Resume Normal Operation]
    D3 -->|No| D5[Switch to Backup Connection]
    
    E --> E1[Log Exchange Error]
    E1 --> E2[Check Exchange Status]
    E2 --> E3{Exchange Operational?}
    E3 -->|Yes| E4[Retry Request]
    E3 -->|No| E5[Pause Strategy]
    
    F --> F1[Log Strategy Error]
    F1 --> F2[Emergency Position Close]
    F2 --> F3[Strategy Shutdown]
    F3 --> F4[Manual Review Required]

    C3 --> G[Return to Normal Flow]
    D4 --> G
    D5 --> G
    E4 --> G
    E5 --> H[Wait for Manual Intervention]
    F4 --> H

    style F2 fill:#ffcdd2
    style F3 fill:#f8bbd9
    style E5 fill:#fff3e0
    style H fill:#ffebee
```

## Configuration and Parameter Management

```mermaid
graph LR
    A[Configuration File] --> B[Parameter Loader]
    B --> C[Validation Engine]
    C --> D{Valid Parameters?}
    D -->|Yes| E[Strategy Initialization]
    D -->|No| F[Default Parameters]
    F --> E
    
    E --> G[Runtime Parameter Monitor]
    G --> H{Performance Degradation?}
    H -->|Yes| I[Parameter Optimization Trigger]
    H -->|No| J[Continue Current Parameters]
    
    I --> K[Backtesting Engine]
    K --> L[Optimization Algorithm]
    L --> M[New Parameter Set]
    M --> N[Validation Testing]
    N --> O{Validation Passed?}
    O -->|Yes| P[Deploy New Parameters]
    O -->|No| Q[Revert to Previous]
    
    P --> R[Update Configuration]
    Q --> R
    R --> G

    style D fill:#e1f5fe
    style O fill:#e8f5e8
    style P fill:#c8e6c9
    style Q fill:#ffcdd2
```

---

These workflow diagrams provide comprehensive visual representations of the AMIA strategy's operational flow, decision-making processes, and system interactions. They serve as both implementation guides and operational references for understanding the strategy's behavior in various scenarios.

**Next**: See [Risk Management Framework](AMIA_risk_management.md) for detailed risk controls and [Example Implementation](AMIA_example_implementation.py) for complete working code.