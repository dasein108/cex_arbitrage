from typing import Optional

import msgspec


class MexcSymbolResponse(msgspec.Struct):
    """MEXC exchange info symbol response structure."""
    symbol: str
    status: str
    baseAsset: str
    baseAssetPrecision: int
    baseCommissionPrecision: int
    baseSizePrecision: str
    contractAddress: str
    filters: list[dict]
    fullName: str
    isMarginTradingAllowed: bool
    isSpotTradingAllowed: bool
    makerCommission: str
    maxQuoteAmount: str
    maxQuoteAmountMarket: str
    orderTypes: list[str]
    permissions: list[str]
    quoteAmountPrecision: str
    quoteAmountPrecisionMarket: str
    quoteAsset: str
    quoteAssetPrecision: int
    quoteCommissionPrecision: int
    quotePrecision: int
    st: bool
    takerCommission: str
    tradeSideType: int


class MexcExchangeInfoResponse(msgspec.Struct):
    """MEXC exchange info API response."""
    timezone: str
    serverTime: int
    symbols: list[MexcSymbolResponse]


class MexcOrderBookResponse(msgspec.Struct):
    """MEXC order book API response structure."""
    lastUpdateId: int
    bids: list[list[str]]  # [price, quantity]
    asks: list[list[str]]  # [price, quantity]


class MexcTradeResponse(msgspec.Struct):
    """MEXC recent trades API response structure."""
    id: Optional[int]  # Can be None
    isBestMatch: bool
    isBuyerMaker: bool
    price: str
    qty: str
    quoteQty: str
    time: int
    tradeType: str  # "ASK" or "BID"


class MexcServerTimeResponse(msgspec.Struct):
    """MEXC server time API response."""
    serverTime: int


class MexcBalanceResponse(msgspec.Struct):
    """MEXC balance entry structure."""
    asset: str
    available: str
    free: str
    locked: str


class MexcAccountResponse(msgspec.Struct, kw_only=True):
    """MEXC account info API response structure."""
    makerCommission: Optional[int] = None
    takerCommission: Optional[int] = None
    buyerCommission: Optional[int] = None
    sellerCommission: Optional[int] = None
    canTrade: bool = True
    canWithdraw: bool = True
    canDeposit: bool = True
    updateTime: Optional[int] = None
    accountType: str = "SPOT"
    balances: list[MexcBalanceResponse] = []
    permissions: Optional[list[str]] = None


class MexcOrderResponse(msgspec.Struct):
    """MEXC order API response structure."""
    symbol: str
    orderId: str
    orderListId: int = -1
    clientOrderId: Optional[str] = ""
    transactTime: int = 0
    price: str = "0"
    origQty: str = "0"
    executedQty: str = "0"
    cummulativeQuoteQty: str = "0"
    status: str = "NEW"
    timeInForce: Optional[str] = "GTC"
    type: str = "LIMIT"
    side: str = "BUY"
    fills: Optional[list[dict]] = None


class MexcErrorResponse(msgspec.Struct):
    """MEXC error response structure."""
    code: int
    msg: str


# WebSocket-specific structures for HFT orderbook processing

class MexcWSDepthEntry(msgspec.Struct):
    """MEXC WebSocket depth entry for HFT processing."""
    price: str  # MEXC sends as string
    quantity: str  # MEXC sends as string


class MexcWSOrderbookData(msgspec.Struct):
    """MEXC WebSocket orderbook data structure."""
    bids: list[list[str]]  # [[price, size], ...]
    asks: list[list[str]]  # [[price, size], ...]
    version: Optional[str] = None  # Sequence number for ordering


class MexcWSOrderbookMessage(msgspec.Struct):
    """MEXC WebSocket orderbook message structure."""
    c: str  # Channel: spot@public.limit.depth.v3.api@BTCUSDT@20
    d: MexcWSOrderbookData  # Data
    s: str  # Symbol
    t: int  # Timestamp in milliseconds


class MexcWSTradeEntry(msgspec.Struct):
    """MEXC WebSocket trade entry structure."""
    p: str  # Price
    q: str  # Quantity
    t: int  # Trade type (1=buy, 2=sell)
    T: int  # Timestamp


class MexcWSTradeData(msgspec.Struct):
    """MEXC WebSocket trade data structure."""
    deals: list[MexcWSTradeEntry]


class MexcWSTradeMessage(msgspec.Struct):
    """MEXC WebSocket trade message structure."""
    c: str  # Channel
    d: MexcWSTradeData  # Data
    s: str  # Symbol
    t: int  # Timestamp


# Private WebSocket message structures

class MexcWSPrivateOrderData(msgspec.Struct):
    """MEXC private WebSocket order data structure."""
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL" 
    status: int  # Order status code
    orderType: int  # Order type code
    price: str
    quantity: str
    filled_qty: str = "0"
    updateTime: int = 0


class MexcWSPrivateOrderMessage(msgspec.Struct):
    """MEXC private WebSocket order message structure."""
    c: str  # Channel: spot@private.orders.v3.api.pb
    d: MexcWSPrivateOrderData  # Order data
    t: int  # Timestamp


class MexcWSPrivateBalanceData(msgspec.Struct):
    """MEXC private WebSocket balance data structure."""
    asset: str
    free: str
    locked: str
    total: str = "0"


class MexcWSPrivateBalanceMessage(msgspec.Struct):
    """MEXC private WebSocket balance message structure."""
    c: str  # Channel: spot@private.account.v3.api.pb
    d: MexcWSPrivateBalanceData  # Balance data
    t: int  # Timestamp


class MexcWSPrivateTradeData(msgspec.Struct):
    """MEXC private WebSocket trade data structure."""
    symbol: str
    side: str  # "BUY" or "SELL"
    price: str
    quantity: str
    timestamp: int
    is_maker: bool = False


class MexcWSPrivateTradeMessage(msgspec.Struct):
    """MEXC private WebSocket trade message structure."""
    c: str  # Channel: spot@private.deals.v3.api.pb
    d: MexcWSPrivateTradeData  # Trade data
    t: int  # Timestamp


class MexcNetworkConfigResponse(msgspec.Struct):
    """MEXC network configuration structure."""
    coin: str
    depositEnable: bool
    withdrawEnable: bool
    network: str
    withdrawFee: str
    withdrawMin: str
    withdrawMax: Optional[str] = None
    minConfirm: Optional[int] = None
    depositTips: Optional[str] = None
    withdrawTips: Optional[str] = None
    contract: Optional[str] = None


class MexcCurrencyInfoResponse(msgspec.Struct):
    """MEXC currency information API response structure."""
    coin: str
    name: str
    networkList: list[MexcNetworkConfigResponse]
