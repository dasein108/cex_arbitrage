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
    clientOrderId: str = ""
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
