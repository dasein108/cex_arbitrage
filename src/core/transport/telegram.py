"""
Telegram notification utilities using aiohttp for async operations.

Provides async functions for sending messages to Telegram channels/chats
with proper error handling and timeout management for HFT environments.
"""

import logging
import asyncio
from typing import Optional
from urllib.parse import quote

import aiohttp


# Configuration constants - should be set via environment variables
TELEGRAM_BOT_TOKEN: Optional[str] = '1065120410:AAFVNDOl1OeNAOo2iBrRZZPSnfa35kjHRYc'
TELEGRAM_CHANNEL_ID: Optional[str] = '-869981089'
TG_BOT_PREFIX: str = "HFT_ARBITRAGE"

# Telegram API endpoints
TELEGRAM_API_BASE_URL = "https://api.telegram.org/bot{token}"
TELEGRAM_API_SEND_MESSAGE_URL = TELEGRAM_API_BASE_URL + "/sendMessage"


logger = logging.getLogger(__name__)


def configure_telegram(bot_token: str, channel_id: str, bot_prefix: str = "HFT_ARBITRAGE"):
    """
    Configure Telegram settings globally.
    
    Args:
        bot_token: Telegram bot token
        channel_id: Default channel/chat ID to send messages to
        bot_prefix: Prefix for all messages
    """
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TG_BOT_PREFIX
    TELEGRAM_BOT_TOKEN = bot_token
    TELEGRAM_CHANNEL_ID = channel_id
    TG_BOT_PREFIX = bot_prefix


async def send_to_telegram(
    message: str, 
    channel_id: Optional[str] = None,
    parse_mode: str = "html",
    timeout: float = 3.0,
    session: Optional[aiohttp.ClientSession] = None
) -> bool:
    """
    Send message to Telegram channel using aiohttp.
    
    Args:
        message: Message text to send
        channel_id: Target channel/chat ID (uses default if None)
        parse_mode: Message parsing mode ('html', 'markdown', or None)
        timeout: Request timeout in seconds
        session: Optional existing aiohttp session to reuse
        
    Returns:
        True if message was sent successfully, False otherwise
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram bot token not configured")
        return False
    
    target_channel = channel_id or TELEGRAM_CHANNEL_ID
    if not target_channel:
        logger.warning("No Telegram channel ID provided")
        return False
    
    try:
        # Format message with prefix
        formatted_message = f"#{TG_BOT_PREFIX} - {message}"
        
        # Prepare request data
        url = TELEGRAM_API_SEND_MESSAGE_URL.format(token=TELEGRAM_BOT_TOKEN)
        data = {
            'chat_id': quote(target_channel),
            'text': formatted_message,
        }
        
        if parse_mode:
            data['parse_mode'] = parse_mode
        
        # Create session if not provided
        close_session = session is None
        if session is None:
            timeout_config = aiohttp.ClientTimeout(total=timeout)
            session = aiohttp.ClientSession(timeout=timeout_config)
        
        try:
            # Send message
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    logger.debug(f"Telegram message sent successfully to {target_channel}")
                    return True
                else:
                    logger.warning(f"Telegram API returned status {response.status}: {await response.text()}")
                    return False
                    
        finally:
            if close_session:
                await session.close()
                
    except asyncio.TimeoutError:
        logger.warning(f"Telegram request timeout after {timeout}s")
        return False
    except aiohttp.ClientError as e:
        logger.warning(f"Telegram client error: {e}")
        return False
    except Exception as e:
        logger.debug(f"Telegram error: {e}")
        return False


async def send_to_telegram_batch(
    messages: list[str],
    channel_id: Optional[str] = None,
    parse_mode: str = "html",
    timeout: float = 3.0,
    delay_between_messages: float = 0.1
) -> int:
    """
    Send multiple messages to Telegram with rate limiting.
    
    Args:
        messages: List of message texts to send
        channel_id: Target channel/chat ID (uses default if None)
        parse_mode: Message parsing mode
        timeout: Request timeout per message
        delay_between_messages: Delay between messages to avoid rate limits
        
    Returns:
        Number of messages sent successfully
    """
    if not messages:
        return 0
    
    successful_sends = 0
    timeout_config = aiohttp.ClientTimeout(total=timeout)
    
    async with aiohttp.ClientSession(timeout=timeout_config) as session:
        for i, message in enumerate(messages):
            if i > 0:
                await asyncio.sleep(delay_between_messages)
            
            success = await send_to_telegram(
                message=message,
                channel_id=channel_id,
                parse_mode=parse_mode,
                timeout=timeout,
                session=session
            )
            
            if success:
                successful_sends += 1
            else:
                logger.warning(f"Failed to send message {i+1}/{len(messages)}")
    
    logger.info(f"Sent {successful_sends}/{len(messages)} messages to Telegram")
    return successful_sends


async def send_alert(
    alert_type: str,
    message: str,
    channel_id: Optional[str] = None,
    urgent: bool = False
) -> bool:
    """
    Send formatted alert message to Telegram.
    
    Args:
        alert_type: Type of alert (e.g., 'ERROR', 'WARNING', 'INFO')
        message: Alert message content
        channel_id: Target channel/chat ID
        urgent: If True, use bold formatting for urgent alerts
        
    Returns:
        True if alert was sent successfully
    """
    if urgent:
        formatted_message = f"🚨 <b>{alert_type.upper()}</b>: {message}"
    else:
        alert_emoji = {
            'ERROR': '❌',
            'WARNING': '⚠️',
            'INFO': 'ℹ️',
            'SUCCESS': '✅',
            'PROFIT': '💰',
            'TRADE': '📈'
        }.get(alert_type.upper(), '📢')
        
        formatted_message = f"{alert_emoji} <b>{alert_type.upper()}</b>: {message}"
    
    return await send_to_telegram(
        message=formatted_message,
        channel_id=channel_id,
        parse_mode="html"
    )


# Convenience functions for common alert types
async def send_error_alert(message: str, urgent: bool = True) -> bool:
    """Send error alert to Telegram."""
    return await send_alert("ERROR", message, urgent=urgent)


async def send_warning_alert(message: str) -> bool:
    """Send warning alert to Telegram."""
    return await send_alert("WARNING", message)


async def send_info_alert(message: str) -> bool:
    """Send info alert to Telegram."""
    return await send_alert("INFO", message)


async def send_trade_alert(message: str) -> bool:
    """Send trading alert to Telegram."""
    return await send_alert("TRADE", message)


async def send_profit_alert(message: str) -> bool:
    """Send profit alert to Telegram."""
    return await send_alert("PROFIT", message, urgent=True)