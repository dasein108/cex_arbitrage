# AMIA Mathematical Framework

## Table of Contents
1. [Core Mathematical Definitions](#core-mathematical-definitions)
2. [Signal Generation Mathematics](#signal-generation-mathematics)
3. [Risk Metrics and Calculations](#risk-metrics-and-calculations)
4. [Performance Measurement Framework](#performance-measurement-framework)
5. [Optimization Theory](#optimization-theory)
6. [Proofs and Derivations](#proofs-and-derivations)

## Core Mathematical Definitions

### 1. Market Data Notation

For exchange $i$ and time $t$:
- $B_{i,t}$ = bid price
- $A_{i,t}$ = ask price  
- $M_{i,t}$ = mid price = $\frac{B_{i,t} + A_{i,t}}{2}$
- $S_{i,t}$ = spread = $A_{i,t} - B_{i,t}$
- $Q_{i,t}^{bid}$ = bid quantity
- $Q_{i,t}^{ask}$ = ask quantity

### 2. Mid-Price Deviation Calculations

**Bid Deviation** (opportunity to sell at favorable price):
$$\delta_{i,t}^{bid} = \frac{B_{i,t} - M_{i,t}}{M_{i,t}} = \frac{B_{i,t} - \frac{B_{i,t} + A_{i,t}}{2}}{\frac{B_{i,t} + A_{i,t}}{2}} = \frac{B_{i,t} - A_{i,t}}{B_{i,t} + A_{i,t}}$$

**Ask Deviation** (opportunity to buy at favorable price):
$$\delta_{i,t}^{ask} = \frac{A_{i,t} - M_{i,t}}{M_{i,t}} = \frac{A_{i,t} - \frac{B_{i,t} + A_{i,t}}{2}}{\frac{B_{i,t} + A_{i,t}}{2}} = \frac{A_{i,t} - B_{i,t}}{B_{i,t} + A_{i,t}}$$

**Key Property**: $\delta_{i,t}^{bid} = -\delta_{i,t}^{ask}$ and both are always negative when $B_{i,t} < A_{i,t}$

## Signal Generation Mathematics

### 3. Aggregated Opportunity Scoring

For a two-exchange arbitrage (spot exchange $s$, futures exchange $f$):

**Entry Opportunity Score** (Long Spot, Short Futures):
$$O_t^{entry} = \delta_{s,t}^{ask} + \delta_{f,t}^{bid}$$

**Exit Opportunity Score** (Short Spot, Long Futures):
$$O_t^{exit} = \delta_{s,t}^{bid} + \delta_{f,t}^{ask}$$

### 4. Signal Generation Functions

**Entry Signal**:
$$\mathcal{S}_t^{entry} = \mathbb{1}\{O_t^{entry} < \theta^{entry}\} \cap \mathbb{1}\{\delta_{s,t}^{ask} < \theta^{min}\} \cap \mathbb{1}\{\delta_{f,t}^{bid} < \theta^{min}\}$$

**Exit Signal**:
$$\mathcal{S}_t^{exit} = \mathbb{1}\{O_t^{exit} < \theta^{exit}\} \cap \mathbb{1}\{\delta_{s,t}^{bid} < \theta^{min}\} \cap \mathbb{1}\{\delta_{f,t}^{ask} < \theta^{min}\}$$

Where:
- $\theta^{entry}$ = entry threshold (typically -0.001 or -0.1%)
- $\theta^{exit}$ = exit threshold (typically -0.0005 or -0.05%)
- $\theta^{min}$ = minimum individual leg opportunity (typically -0.0002 or -0.02%)
- $\mathbb{1}\{\cdot\}$ = indicator function

### 5. Trade Execution Mathematics

**Entry Execution** (at time $t_0$):
- Buy spot at price $A_{s,t_0}$ 
- Sell futures at price $B_{f,t_0}$
- Net position value: $N_{t_0} = B_{f,t_0} - A_{s,t_0}$

**Exit Execution** (at time $t_1$):
- Sell spot at price $B_{s,t_1}$
- Buy futures at price $A_{f,t_1}$
- Net position value: $N_{t_1} = B_{s,t_1} - A_{f,t_1}$

**Trade P&L**:
$$PnL = N_{t_1} - N_{t_0} = (B_{s,t_1} - A_{f,t_1}) - (B_{f,t_0} - A_{s,t_0})$$

**Decomposed P&L**:
$$PnL = \underbrace{(B_{s,t_1} - A_{s,t_0})}_{Spot\ Leg} + \underbrace{(B_{f,t_0} - A_{f,t_1})}_{Futures\ Leg}$$

## Risk Metrics and Calculations

### 6. Individual Leg Risk Metrics

**Spot Leg Expected Return**:
$$\mathbb{E}[R_s] = \mathbb{E}\left[\frac{B_{s,t_1} - A_{s,t_0}}{A_{s,t_0}}\right]$$

**Futures Leg Expected Return**:
$$\mathbb{E}[R_f] = \mathbb{E}\left[\frac{B_{f,t_0} - A_{f,t_1}}{B_{f,t_0}}\right]$$

**Cross-Leg Correlation**:
$$\rho_{sf} = \text{Corr}(R_s, R_f)$$

### 7. Portfolio Risk Metrics

**Portfolio Return**:
$$R_p = w_s \cdot R_s + w_f \cdot R_f$$

Where $w_s = \frac{A_{s,t_0}}{A_{s,t_0} + B_{f,t_0}}$ and $w_f = \frac{B_{f,t_0}}{A_{s,t_0} + B_{f,t_0}}$

**Portfolio Variance**:
$$\text{Var}(R_p) = w_s^2 \sigma_s^2 + w_f^2 \sigma_f^2 + 2w_s w_f \sigma_s \sigma_f \rho_{sf}$$

**Value at Risk (95% confidence)**:
$$VaR_{0.05} = \mu_p - 1.645 \sigma_p$$

### 8. Maximum Drawdown Calculation

For a sequence of cumulative returns $\{R_1, R_2, ..., R_T\}$:

$$DD_t = \max_{0 \leq s \leq t} \left(\prod_{i=1}^{s}(1 + R_i)\right) - \prod_{i=1}^{t}(1 + R_i)$$

$$MDD = \max_{1 \leq t \leq T} DD_t$$

## Performance Measurement Framework

### 9. Risk-Adjusted Performance Metrics

**Sharpe Ratio**:
$$SR = \frac{\mathbb{E}[R_p] - r_f}{\sigma_p}$$

**Information Ratio**:
$$IR = \frac{\mathbb{E}[R_p - R_b]}{\sigma_{p-b}}$$

**Calmar Ratio**:
$$CR = \frac{\text{Annual Return}}{MDD}$$

### 10. Trade-Level Performance Metrics

**Hit Rate**:
$$HR = \frac{\text{Number of Profitable Trades}}{\text{Total Number of Trades}}$$

**Profit Factor**:
$$PF = \frac{\sum_{i: PnL_i > 0} PnL_i}{|\sum_{i: PnL_i < 0} PnL_i|}$$

**Average Trade P&L**:
$$\bar{PnL} = \frac{1}{N} \sum_{i=1}^{N} PnL_i$$

**Trade P&L Standard Deviation**:
$$\sigma_{PnL} = \sqrt{\frac{1}{N-1} \sum_{i=1}^{N} (PnL_i - \bar{PnL})^2}$$

## Optimization Theory

### 11. Threshold Optimization

**Objective Function** (maximize Sharpe ratio):
$$\max_{\theta^{entry}, \theta^{exit}, \theta^{min}} \frac{\mathbb{E}[R_p(\theta^{entry}, \theta^{exit}, \theta^{min})]}{\sigma_p(\theta^{entry}, \theta^{exit}, \theta^{min})}$$

**Constraints**:
- $\theta^{entry} < \theta^{exit} < 0$ (entry more restrictive than exit)
- $\theta^{min} < \min(\theta^{entry}/2, \theta^{exit}/2)$ (individual legs less restrictive)
- Trade frequency constraints: $f_{min} \leq f(\theta) \leq f_{max}$

### 12. Dynamic Threshold Adjustment

**Volatility-Adjusted Thresholds**:
$$\theta_t^{entry} = \theta_0^{entry} \cdot \left(1 + \alpha \cdot \frac{\sigma_{t-h:t}}{\sigma_0}\right)$$

Where:
- $\sigma_{t-h:t}$ = rolling volatility over lookback period $h$
- $\sigma_0$ = baseline volatility
- $\alpha$ = volatility adjustment factor

## Proofs and Derivations

### 13. Theorem: AMIA Entry Condition Optimality

**Theorem**: Under the AMIA framework, the entry condition $O_t^{entry} < \theta^{entry}$ with individual leg constraints maximizes expected trade profitability given execution constraints.

**Proof Sketch**:
1. Individual leg profitability ensures $\mathbb{E}[R_s] > 0$ and $\mathbb{E}[R_f] > 0$
2. Aggregated condition $O_t^{entry} < \theta^{entry}$ ensures $\mathbb{E}[R_s + R_f] > \mathbb{E}[\text{costs}]$
3. Combined conditions minimize correlation risk while maintaining positive expected returns

### 14. Lemma: Spread Decomposition

**Lemma**: The aggregated opportunity score can be decomposed as:
$$O_t^{entry} = -\frac{S_{s,t}}{2M_{s,t}} - \frac{S_{f,t}}{2M_{f,t}}$$

**Proof**:
$$O_t^{entry} = \delta_{s,t}^{ask} + \delta_{f,t}^{bid} = \frac{A_{s,t} - B_{s,t}}{A_{s,t} + B_{s,t}} + \frac{B_{f,t} - A_{f,t}}{A_{f,t} + B_{f,t}}$$

$$= \frac{S_{s,t}}{2M_{s,t}} - \frac{S_{f,t}}{2M_{f,t}} = -\frac{S_{s,t}}{2M_{s,t}} - \frac{S_{f,t}}{2M_{f,t}}$$

This shows that AMIA effectively trades the sum of normalized spreads across exchanges.

### 15. Central Limit Theorem Application

For large $N$ trades, the normalized P&L distribution converges:
$$\frac{\sqrt{N}(\bar{PnL} - \mu_{PnL})}{\sigma_{PnL}} \xrightarrow{d} \mathcal{N}(0,1)$$

This enables construction of confidence intervals for strategy performance:
$$CI_{1-\alpha} = \bar{PnL} \pm z_{\alpha/2} \frac{\sigma_{PnL}}{\sqrt{N}}$$

## Implementation Considerations

### 16. Numerical Stability

To avoid division by zero and numerical instability:
- Use $M_{i,t} = \max(M_{i,t}, \epsilon)$ where $\epsilon = 10^{-8}$
- Clip extreme deviations: $\delta_{i,t} = \text{clip}(\delta_{i,t}, -0.1, 0.1)$
- Use robust statistics for threshold estimation

### 17. Real-Time Calculation Optimization

**Incremental Updates**:
$$M_{i,t} = M_{i,t-1} + \frac{1}{2}[(B_{i,t} - B_{i,t-1}) + (A_{i,t} - A_{i,t-1})]$$

**Vectorized Operations** (for multiple exchanges):
$$\mathbf{O}_t^{entry} = \boldsymbol{\delta}_t^{ask} + \boldsymbol{\delta}_t^{bid}$$

Where bold notation represents vectors across all exchange pairs.

---

**Next**: See [Implementation Guide](AMIA_implementation_guide.md) for practical coding implementation and [Risk Management Framework](AMIA_risk_management.md) for comprehensive risk analysis.