"""
Balance Sync Mixin for Private Composite Exchanges

Provides integration between private composite exchanges and balance synchronization
task for automatic balance tracking and storage.
"""

from typing import Optional, TYPE_CHECKING, Protocol
from exchanges.structs import ExchangeEnum

if TYPE_CHECKING:
    from trading.tasks.balance_sync_task import BalanceSyncTask


class LoggerProtocol(Protocol):
    """Protocol for logger interface required by this mixin."""
    def info(self, msg: str, **kwargs) -> None: ...
    def warning(self, msg: str, **kwargs) -> None: ...


class BalanceSyncTaskMixin:
    """Mixin for private composite exchanges to integrate with balance sync task.
    
    Provides methods to register/unregister with a global balance sync task
    for automatic periodic balance collection and storage.
    
    Required attributes from the using class:
    - logger: LoggerProtocol - For logging sync events
    """
    
    # Type hints for IDE - these should be provided by the using class
    if TYPE_CHECKING:
        logger: LoggerProtocol
    
    def __init__(self, *args, **kwargs):
        """Initialize balance sync mixin."""
        super().__init__(*args, **kwargs)
        
        # Balance sync integration
        self._balance_sync_task: Optional['BalanceSyncTask'] = None
        self._is_registered_for_sync: bool = False
    
    def register_balance_sync(self, 
                            balance_sync_task: 'BalanceSyncTask', 
                            exchange_enum: ExchangeEnum):
        """Register this exchange with a balance sync task.
        
        Args:
            balance_sync_task: Balance sync task instance
            exchange_enum: Exchange identifier for this instance
        """
        if self._is_registered_for_sync:
            if hasattr(self, 'logger'):
                self.logger.warning(f"Exchange {exchange_enum.name} already registered for balance sync")
            return
        
        self._balance_sync_task = balance_sync_task
        balance_sync_task.add_private_exchange(exchange_enum, self)
        self._is_registered_for_sync = True
        
        if hasattr(self, 'logger'):
            self.logger.info(f"Registered {exchange_enum.name} for balance sync")
    
    def unregister_balance_sync(self, exchange_enum: ExchangeEnum):
        """Unregister this exchange from balance sync.
        
        Args:
            exchange_enum: Exchange identifier for this instance
        """
        if not self._is_registered_for_sync or self._balance_sync_task is None:
            return
        
        self._balance_sync_task.remove_private_exchange(exchange_enum)
        self._balance_sync_task = None
        self._is_registered_for_sync = False
        
        if hasattr(self, 'logger'):
            self.logger.info(f"Unregistered {exchange_enum.name} from balance sync")
    
    @property
    def is_balance_sync_enabled(self) -> bool:
        """Check if balance sync is enabled for this exchange.
        
        Returns:
            True if registered for balance sync, False otherwise
        """
        return self._is_registered_for_sync
    
    @property
    def balance_sync_task(self) -> Optional['BalanceSyncTask']:
        """Get the associated balance sync task.
        
        Returns:
            Balance sync task instance if registered, None otherwise
        """
        return self._balance_sync_task