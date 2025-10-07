from typing import Optional, List

import msgspec

# Gate.io REST API structures

class GateioSymbolResponse(msgspec.Struct):
    """Gate.io exchange info symbol response structure."""
    id: str
    base: str
    quote: str
    fee: str
    min_base_amount: str
    min_quote_amount: str
    amount_precision: int
    precision: int
    trade_status: str
    sell_start: int
    buy_start: int


class GateioExchangeInfoResponse(msgspec.Struct):
    """Gate.io exchange info API response."""
    symbols: List[GateioSymbolResponse]


class GateioOrderBookResponse(msgspec.Struct):
    """Gate.io order book API response structure."""
    id: int
    current: int
    update: int
    asks: List[List[str]]  # [price, amount]
    bids: List[List[str]]  # [price, amount]


class GateioTradeResponse(msgspec.Struct):
    """Gate.io recent trades API response structure."""
    id: str
    create_time: str
    create_time_ms: str
    side: str  # "buy" or "sell"
    amount: str
    price: str
    range: str


class GateioBalanceResponse(msgspec.Struct):
    """Gate.io balance entry structure."""
    currency: str
    available: str
    locked: str


class GateioAccountResponse(msgspec.Struct):
    """Gate.io account info API response structure."""
    user_id: int
    locked: bool
    balances: List[GateioBalanceResponse]


class GateioOrderResponse(msgspec.Struct):
    """Gate.io order API response structure."""
    id: str
    text: str
    create_time: str
    update_time: str
    create_time_ms: str
    update_time_ms: str
    status: str
    currency_pair: str
    type: str  # "limit" or "market"
    account: str
    side: str  # "buy" or "sell"
    amount: str
    price: str
    time_in_force: str
    iceberg: str
    auto_borrow: bool
    auto_repay: bool
    left: str
    filled_total: str
    filled_amount: str
    avg_deal_price: str
    fee: str
    fee_currency: str
    point_fee: str
    gt_fee: str
    gt_discount: bool
    rebated_fee: str
    rebated_fee_currency: str


class GateioErrorResponse(msgspec.Struct):
    """Gate.io error response structure."""
    label: Optional[str] = None
    message: Optional[str] = None


# WebSocket-specific structures for HFT orderbook processing

class GateioWSOrderbookResult(msgspec.Struct):
    """Gate.io WebSocket orderbook result structure."""
    t: int  # Event time
    e: str  # Event type: "depthUpdate"
    E: int  # Event time
    s: str  # Symbol: "BTC_USDT"
    U: int  # First update ID
    u: int  # Final update ID
    b: List[List[str]]  # Bids: [[price, size], ...]
    a: List[List[str]]  # Asks: [[price, size], ...]


class GateioWSOrderbookMessage(msgspec.Struct):
    """Gate.io WebSocket orderbook message structure."""
    time: int
    channel: str  # "spot.order_book_update"
    event: str  # "update"
    result: GateioWSOrderbookResult


class GateioWSTradeResult(msgspec.Struct):
    """Gate.io WebSocket trade result structure."""
    id: int
    create_time: str
    create_time_ms: str
    side: str  # "buy" or "sell"
    currency_pair: str
    amount: str
    price: str
    range: str


class GateioWSTradeMessage(msgspec.Struct):
    """Gate.io WebSocket trade message structure."""
    time: int
    channel: str  # "spot.trades"
    event: str  # "update"
    result: List[GateioWSTradeResult]


class GateioWSSubscriptionMessage(msgspec.Struct):
    """Gate.io WebSocket subscription message structure."""
    time: int
    channel: str
    event: str  # "subscribe" or "unsubscribe"
    payload: List[str]
    auth: Optional[dict] = None

class GateioCurrencyChain(msgspec.Struct):
    """Gate.io currency chain details from /spot/currencies endpoint."""
    name: str  # Chain name like "ETH", "BSC", etc.
    addr: Optional[str] = None  # Contract address
    withdraw_disabled: Optional[bool] = None
    withdraw_delayed: Optional[bool] = None
    deposit_disabled: Optional[bool] = None


class GateioCurrencyResponse(msgspec.Struct):
    """Gate.io currency information response structure from /spot/currencies."""
    currency: str
    delisted: bool
    withdraw_disabled: bool
    withdraw_delayed: bool
    deposit_disabled: bool
    trade_disabled: bool
    chains: Optional[List['GateioCurrencyChain']] = None


class GateioWithdrawStatusResponse(msgspec.Struct):
    """Gate.io withdrawal status response structure from /wallet/withdraw_status."""
    currency: str
    name: str
    name_cn: str
    deposit: str
    withdraw_percent: str
    withdraw_fix: str
    withdraw_day_limit: str
    withdraw_day_limit_remain: str
    withdraw_amount_mini: str
    withdraw_eachtime_limit: str
    withdraw_fix_on_chains: Optional[dict] = None  # Chain name -> fee amount
    withdraw_percent_on_chains: Optional[dict] = None  # Chain name -> percentage


class GateioChainResponse(msgspec.Struct):
    """Gate.io currency chain information response structure."""
    chain: str
    name_cn: str
    name_en: str
    is_deposit_enabled: bool
    is_withdraw_enabled: bool
    withdraw_fee: str
    withdraw_min: str
    withdraw_max: str
    deposit_min: Optional[str] = None
    confirmations: Optional[int] = None


# Gate.io Futures API structures



class GateioFuturesContractResponse(msgspec.Struct):
    """Gate.io futures contract information response."""
    name: str
    type: str
    quanto_multiplier: str
    leverage_min: str
    leverage_max: str
    maintenance_rate: str
    mark_type: str
    mark_price: str
    index_price: str
    last_price: str
    maker_fee_rate: str
    taker_fee_rate: str
    order_price_round: str
    mark_price_round: str
    funding_rate: str
    funding_interval: int
    order_size_min: int
    order_size_max: int
    order_price_deviate: str
    ref_discount_rate: str
    ref_rebate_rate: str
    orderbook_id: int
    trade_id: int
    trade_size: str
    position_size: str
    config_change_time: Optional[int] = None
    in_delisting: bool = False


class GateioFuturesAccountResponse(msgspec.Struct):
    """Gate.io futures account response structure."""
    total: str
    unrealised_pnl: str
    position_margin: str
    order_margin: str
    available: str
    point: str
    currency: str
    in_dual_mode: bool = False
    enable_credit: bool = True
    position_initial_margin: Optional[str] = None
    maintenance_margin: Optional[str] = None
    bonus: Optional[str] = None
    enable_bonus: Optional[bool] = None
    cross_order_margin: Optional[str] = None
    cross_initial_margin: Optional[str] = None
    cross_maintenance_margin: Optional[str] = None
    cross_unrealised_pnl: Optional[str] = None
    cross_available: Optional[str] = None


# Futures WebSocket channel structures

class GateioFuturesOrderbookResult(msgspec.Struct):
    """Gate.io futures WebSocket orderbook result structure."""
    t: int  # Event time
    e: str  # Event type: "depthUpdate"
    E: int  # Event time
    s: str  # Contract: "BTC_USDT"
    U: int  # First update ID
    u: int  # Final update ID
    b: List[List[str]]  # Bids: [[price, size], ...]
    a: List[List[str]]  # Asks: [[price, size], ...]


class GateioFuturesOrderbookMessage(msgspec.Struct):
    """Gate.io futures WebSocket orderbook message structure."""
    time: int
    time_ms: int
    channel: str  # "futures.order_book_update"
    event: str  # "update"
    result: GateioFuturesOrderbookResult


class GateioFuturesTradeResult(msgspec.Struct):
    """Gate.io futures WebSocket trade result structure."""
    id: int
    create_time: str
    create_time_ms: str
    contract: str
    size: str  # Can be negative for sell orders
    price: str


class GateioFuturesTradeMessage(msgspec.Struct):
    """Gate.io futures WebSocket trade message structure."""
    time: int
    time_ms: int
    channel: str  # "futures.trades"
    event: str  # "update"
    result: List[GateioFuturesTradeResult]