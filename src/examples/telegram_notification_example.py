"""
Example usage of Telegram notification utilities.

Demonstrates how to send various types of messages and alerts to Telegram
using the async aiohttp-based utility functions.
"""

import asyncio
import os
from core.transport.telegram import (
    configure_telegram,
    send_to_telegram,
    send_alert,
    send_warning_alert,
    send_info_alert,
    send_trade_alert,
    send_profit_alert,
    send_to_telegram_batch
)


async def main():
    """Example usage of Telegram utilities."""
    
    # Configure Telegram (normally done at app startup)
    # These would typically come from environment variables
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token_here")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "your_channel_id_here")
    
    if bot_token == "your_bot_token_here" or channel_id == "your_channel_id_here":
        print("⚠️ Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID environment variables")
        print("Example usage:")
        print("TELEGRAM_BOT_TOKEN=your_token TELEGRAM_CHANNEL_ID=@your_channel python examples/telegram_notification_example.py")
        return
    
    # Configure Telegram globally
    configure_telegram(
        bot_token=bot_token,
        channel_id=channel_id,
        bot_prefix="HFT_DEMO"
    )
    
    print("🚀 Testing Telegram notifications...")
    
    # Basic message
    success = await send_to_telegram("System startup completed successfully")
    print(f"Basic message: {'✅' if success else '❌'}")
    
    await asyncio.sleep(0.5)  # Rate limiting
    
    # Different alert types
    await send_info_alert("Market data connection established")
    await asyncio.sleep(0.5)
    
    await send_warning_alert("High volatility detected in BTC/USDT")
    await asyncio.sleep(0.5)
    
    await send_trade_alert("Arbitrage opportunity found: MEXC->Gate.io BTC/USDT 0.25%")
    await asyncio.sleep(0.5)
    
    await send_profit_alert("Trade executed successfully: +$125.50 profit")
    await asyncio.sleep(0.5)
    
    # Custom alert
    await send_alert("SYSTEM", "All exchanges connected and operational", urgent=False)
    await asyncio.sleep(0.5)
    
    # Batch messages
    batch_messages = [
        "Batch message 1: System health check",
        "Batch message 2: Performance metrics updated",
        "Batch message 3: Daily summary completed"
    ]
    
    sent_count = await send_to_telegram_batch(batch_messages, delay_between_messages=0.2)
    print(f"Batch messages: {sent_count}/{len(batch_messages)} sent")
    
    # Error alert (normally only sent on actual errors)
    # await send_error_alert("WebSocket connection lost - attempting reconnection")
    
    print("✅ Telegram notification test completed")


if __name__ == "__main__":
    asyncio.run(main())