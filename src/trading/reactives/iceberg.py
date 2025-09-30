import reactivex as rx
from reactivex import operators as ops
from reactivex.subject import Subject, BehaviorSubject
from dataclasses import dataclass
from typing import Optional
import asyncio



class ReactiveIcebergOrder:
    """Reactive iceberg order handler using RxPy."""

    @dataclass
    class IcebergOrder:
        total_quantity: float
        peak_size: float
        filled_quantity: float = 0.0

        @property
        def remaining_quantity(self) -> float:
            return self.total_quantity - self.filled_quantity

        @property
        def current_peak(self) -> float:
            return min(self.peak_size, self.remaining_quantity)

    def __init__(self, total_quantity: float, peak_size: float):
        self.order = self.IcebergOrder(total_quantity=total_quantity, peak_size=peak_size)
        self._fill_subject = Subject()
        self._order_subject = BehaviorSubject(self.order)

        # Subscribe to fill events to update the order state
        self._fill_subject.pipe(
            ops.scan(lambda acc, fill: acc + fill, 0.0),
            ops.map(self._update_filled_quantity)
        ).subscribe(self._order_subject)

    def _update_filled_quantity(self, filled: float) -> 'ReactiveIcebergOrder.IcebergOrder':
        self.order.filled_quantity += filled
        return self.order

    def fill(self, quantity: float):
        """Simulate a fill event."""
        if quantity <= 0 or quantity > self.order.current_peak:
            raise ValueError("Fill quantity must be positive and less than or equal to current peak size.")
        self._fill_subject.on_next(quantity)

    def get_order_observable(self) -> rx.Observable:
        """Get an observable for the iceberg order state."""
        return self._order_subject

    def is_complete(self) -> bool:
        """Check if the iceberg order is completely filled."""
        return self.order.remaining_quantity <= 0.0