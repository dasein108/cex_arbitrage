"""
WebSocket Authentication Mixin

Authentication behavior override system for exchanges requiring WebSocket authentication.
Provides base authentication patterns and exchange-specific implementations for secure
private WebSocket connections.

Key Features:
- Base authentication interface for WebSocket connections
- Exchange-specific authentication message creation
- Signature generation and validation
- Authentication timeout handling
- Support for exchanges requiring auth vs public-only endpoints

HFT COMPLIANCE: <5s authentication completion, <1ms message creation.
"""

import asyncio
import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from config.structs import ExchangeConfig
from infrastructure.logging import get_logger
from infrastructure.exceptions.exchange import ExchangeRestError


class AuthMixin(ABC):
    """
    Base mixin for exchanges requiring WebSocket authentication.
    
    Provides abstract interface for authentication workflows that can be
    composed with connection and message handling mixins. Exchanges not
    requiring authentication should use NoAuthMixin.
    """
    
    def __init__(self, config: ExchangeConfig, *args, **kwargs):
        # Only call super() if there are other classes in the MRO that need initialization
        if hasattr(super(), '__init__'):
            try:
                super().__init__(*args, **kwargs)
            except TypeError:
                # If super().__init__ doesn't accept kwargs, call without them
                pass
        
        self.config = config
        
        # Logger setup
        if not hasattr(self, 'logger') or self.logger is None:
            self.logger = get_logger(f'auth.{self.__class__.__name__}')
        
        # Authentication state
        self._is_authenticated = False
        self._auth_timeout = 10.0  # Default auth timeout
        
        self.logger.info(f"AuthMixin initialized for {config.name}",
                        exchange=config.name,
                        requires_auth=self.requires_authentication(),
                        has_credentials=config.has_credentials())
    
    @abstractmethod
    async def create_auth_message(self) -> Dict[str, Any]:
        """
        Create authentication message format for the exchange.
        
        Returns:
            Dictionary containing exchange-specific authentication message
            
        Raises:
            ExchangeRestError: If credentials are missing or invalid
        """
        pass
    
    @abstractmethod
    def requires_authentication(self) -> bool:
        """
        Check if this mixin requires authentication.
        
        Returns:
            True if authentication is required for this exchange/endpoint
        """
        pass
    
    async def authenticate(self) -> bool:
        """
        Perform authentication workflow.
        
        Sends authentication message and waits for confirmation.
        Default implementation handles common authentication patterns.
        
        Returns:
            True if authentication successful or not required
            
        Raises:
            RuntimeError: If no WebSocket connection available
            ExchangeRestError: If authentication fails
        """
        if not self.requires_authentication():
            self._is_authenticated = True
            return True
        
        if not hasattr(self, '_websocket') or not self._websocket:
            raise RuntimeError("No WebSocket connection available for authentication")
        
        if not self.config.has_credentials():
            raise ExchangeRestError(401, "Authentication required but no credentials provided")
        
        try:
            # Create and send authentication message
            auth_message = await self.create_auth_message()
            
            self.logger.info("Sending authentication message",
                           message_id=auth_message.get('id'),
                           method=auth_message.get('method'))
            
            # Send auth message through WebSocket
            await self._send_auth_message(auth_message)
            
            # Wait for authentication confirmation
            auth_success = await self._wait_for_auth_confirmation()
            
            if auth_success:
                self._is_authenticated = True
                self.logger.info("WebSocket authentication successful")
            else:
                self.logger.error("WebSocket authentication failed")
                raise ExchangeRestError(401, "Authentication failed")
            
            return auth_success
            
        except Exception as e:
            self.logger.error("Authentication error",
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
    
    async def _send_auth_message(self, auth_message: Dict[str, Any]) -> None:
        """Send authentication message through WebSocket."""
        if hasattr(self, 'send_message'):
            # Use the WebSocket send_message method if available
            await self.send_message(auth_message)
        elif hasattr(self, '_websocket') and self._websocket:
            # Direct WebSocket sending if no send_message method
            import msgspec
            msg_str = msgspec.json.encode(auth_message).decode("utf-8")
            await self._websocket.send(msg_str)
        else:
            raise RuntimeError("No method available to send authentication message")
    
    async def _wait_for_auth_confirmation(self) -> bool:
        """
        Wait for authentication confirmation from the exchange.
        
        Default implementation waits for a short period assuming success.
        Override for exchanges with explicit auth confirmation messages.
        
        Returns:
            True if authentication confirmed
        """
        # Default: wait briefly and assume success if no error received
        # Exchange-specific implementations should override for proper confirmation
        await asyncio.sleep(1.0)
        return True
    
    def is_authenticated(self) -> bool:
        """
        Check if currently authenticated.
        
        Returns:
            True if authenticated or authentication not required
        """
        if not self.requires_authentication():
            return True
        return self._is_authenticated
    
    def _create_signature(self, timestamp: int, method: str = "GET", path: str = "", body: str = "") -> str:
        """
        Create HMAC signature for authentication.
        
        Default implementation for common HMAC-SHA256 pattern.
        Override for exchange-specific signature algorithms.
        
        Args:
            timestamp: Unix timestamp
            method: HTTP method (for REST-style auth)
            path: Request path (for REST-style auth)
            body: Request body (for REST-style auth)
            
        Returns:
            Hex-encoded HMAC signature
        """
        if not self.config.api_secret:
            raise ExchangeRestError(401, "API secret required for signature generation")
        
        # Common signature pattern: timestamp + method + path + body
        message = f"{timestamp}{method}{path}{body}"
        
        signature = hmac.new(
            self.config.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature


class NoAuthMixin(AuthMixin):
    """
    No-authentication mixin for public endpoints.
    
    Used for exchanges or endpoints that don't require authentication.
    Provides default implementations that indicate no auth required.
    """
    
    def requires_authentication(self) -> bool:
        """Public endpoints don't require authentication."""
        return False
    
    async def create_auth_message(self) -> Dict[str, Any]:
        """No auth message needed for public endpoints."""
        return {}
    
    async def authenticate(self) -> bool:
        """Always return True for public endpoints."""
        self._is_authenticated = True
        return True


class GateioAuthMixin(AuthMixin):
    """
    Gate.io specific authentication implementation.
    
    Implements Gate.io WebSocket authentication using API key and signature.
    Supports both spot and futures authentication patterns.
    """
    
    def requires_authentication(self) -> bool:
        """Gate.io private endpoints require authentication."""
        return True
    
    async def create_auth_message(self) -> Dict[str, Any]:
        """
        Create Gate.io authentication message.
        
        Gate.io uses a server.sign method with API key, signature, and timestamp.
        
        Returns:
            Gate.io formatted authentication message
        """
        if not self.config.has_credentials():
            raise ExchangeRestError(401, "Gate.io authentication requires API key and secret")
        
        timestamp = int(time.time())
        
        # Gate.io signature format: timestamp for WebSocket auth
        signature = self._create_gateio_signature(timestamp)
        
        return {
            "id": timestamp,
            "method": "server.sign",
            "params": [
                self.config.api_key,
                signature,
                timestamp
            ]
        }
    
    def _create_gateio_signature(self, timestamp: int) -> str:
        """
        Create Gate.io specific signature for WebSocket authentication.
        
        Gate.io WebSocket auth signature is HMAC-SHA512 of timestamp.
        
        Args:
            timestamp: Unix timestamp
            
        Returns:
            Hex-encoded HMAC-SHA512 signature
        """
        if not self.config.api_secret:
            raise ExchangeRestError(401, "API secret required for Gate.io signature")
        
        message = str(timestamp)
        
        signature = hmac.new(
            self.config.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        return signature
    
    async def _wait_for_auth_confirmation(self) -> bool:
        """
        Wait for Gate.io authentication confirmation.
        
        Gate.io sends a response to the server.sign method.
        This is a simplified implementation that waits for success.
        A full implementation would listen for the auth response message.
        
        Returns:
            True if authentication appears successful
        """
        # Wait for auth response (simplified - real implementation should parse response)
        await asyncio.sleep(2.0)
        
        # In a full implementation, we would:
        # 1. Listen for response with matching ID
        # 2. Parse response for success/failure
        # 3. Return based on actual response
        
        # For now, assume success if no exception thrown
        return True


class BinanceAuthMixin(AuthMixin):
    """
    Binance specific authentication implementation.
    
    Implements Binance WebSocket authentication for future use.
    Binance uses listenKey for private streams rather than WebSocket auth.
    """
    
    def requires_authentication(self) -> bool:
        """Binance uses listenKey instead of WebSocket auth."""
        return False  # Binance private streams use listenKey, not WebSocket auth
    
    async def create_auth_message(self) -> Dict[str, Any]:
        """Binance doesn't use WebSocket auth messages."""
        return {}
    
    async def authenticate(self) -> bool:
        """Binance doesn't require WebSocket authentication."""
        self._is_authenticated = True
        return True


class KucoinAuthMixin(AuthMixin):
    """
    KuCoin specific authentication implementation.
    
    Implements KuCoin WebSocket authentication for future use.
    """
    
    def requires_authentication(self) -> bool:
        """KuCoin private endpoints require authentication."""
        return True
    
    async def create_auth_message(self) -> Dict[str, Any]:
        """
        Create KuCoin authentication message.
        
        KuCoin uses a different auth pattern - placeholder for future implementation.
        
        Returns:
            KuCoin formatted authentication message
        """
        # Placeholder - implement when KuCoin integration is needed
        raise NotImplementedError("KuCoin authentication not yet implemented")
    
    def _create_kucoin_signature(self, timestamp: int, passphrase: str) -> str:
        """Create KuCoin specific signature."""
        # Placeholder - implement when KuCoin integration is needed
        raise NotImplementedError("KuCoin signature generation not yet implemented")