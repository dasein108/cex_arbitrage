from abc import ABC, abstractmethod
from typing import Any, Optional, List, Generic
from typing import TypeVar, Generic, Callable, Dict, Literal
import reactivex as rx
from reactivex.subject import BehaviorSubject
from exchanges.structs.common import Order, Position, BookTicker, Trade, AssetBalance, Ticker

PublicObservableName = Literal['trades', 'book_tickers', 'tickers']
PrivateObservableName = Literal['balances', 'orders', 'positions']

T = TypeVar('T', PublicObservableName, PrivateObservableName)


class ObservableStreamsInterface(Generic[T]):
    _streams: Dict[T, BehaviorSubject]

    def publish(self, name: T, value: Any = None) -> None:
        if name not in self._streams:
            raise ValueError(f"Unsupported public observable name: {name}")
        self._streams[name].on_next(value)

    def dispose(self) -> None:
        for subject in self._streams.values():
            subject.on_completed()
            subject.dispose()

class PublicObservableStreams(ObservableStreamsInterface[PublicObservableName]):
    def __init__(self):
        self._streams: Dict[PublicObservableName, BehaviorSubject] = {
            'trades': BehaviorSubject[Order](None),  # Initial value None
            'book_tickers': BehaviorSubject[BookTicker](None),  # Initial value None
            'tickers': BehaviorSubject[Ticker](None),  # Initial value None
        }

    @property
    def trades_stream(self) -> rx.Observable[Order]:
        return self._streams['trades']

    @property
    def book_tickers_stream(self) -> rx.Observable[BookTicker]:
        return self._streams['book_tickers']

class PrivateObservableStreams(ObservableStreamsInterface[PrivateObservableName]):
    def __init__(self):
        self._streams: Dict[PrivateObservableName, BehaviorSubject] = {
            'balances': BehaviorSubject[AssetBalance](None),  # Initial value None
            'orders': BehaviorSubject[Order](None),  # Initial value None
            'positions': BehaviorSubject[Position](None),  # Initial value None
        }

    def publish(self, name: PrivateObservableName, value: Any = None) -> None:
        if name not in self._streams:
            raise ValueError(f"Unsupported private observable name: {name}")
        self._streams[name].on_next(value)

    @property
    def balances_stream(self) -> rx.Observable[AssetBalance]:
        return self._streams['balances']

    @property
    def orders_stream(self) -> rx.Observable[Order]:
        return self._streams['orders']

    @property
    def positions_stream(self) -> rx.Observable[Position]:
        return self._streams['positions']

