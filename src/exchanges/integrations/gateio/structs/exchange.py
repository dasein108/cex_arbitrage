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
    label: str
    message: str


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


class GateioCurrencyResponse(msgspec.Struct):
    """Gate.io currency information response structure."""
    currency: str
    delisted: bool
    withdraw_disabled: bool
    withdraw_delayed: bool
    deposit_disabled: bool
    trade_disabled: bool


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