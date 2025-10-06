import asyncio
from telethon import TelegramClient
from datetime import datetime, timezone, timedelta
import re

# Telegram API credentials
api_id = 29426913
api_hash = 'bcacac7acdc7ddcf2fb95e2a34ac4b97'
phone = '+94781440205'

client = TelegramClient('search_session', api_id, api_hash)

async def search_specific_signals():
    await client.start(phone)
    print("Connected to Telegram")
    
    # Get the group
    group = await client.get_entity(-1002039861131)
    
    # Today's date range (UTC)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    print(f"Searching for PYTH and XPL signals from {today} to {tomorrow}")
    
    async for message in client.iter_messages(group, offset_date=tomorrow, reverse=True):
        if message.date < today:
            break
            
        # Extract text from message using multiple methods
        message_text = ""
        try:
            if hasattr(message, 'text') and message.text:
                message_text = message.text
            elif hasattr(message, 'caption') and message.caption:
                message_text = message.caption
            elif hasattr(message, 'message') and message.message:
                message_text = message.message
            elif hasattr(message, 'media') and message.media and hasattr(message.media, 'caption'):
                message_text = message.media.caption or ""
        except:
            continue
            
        if message_text and ('PYTH' in message_text.upper() or 'XPL' in message_text.upper()):
            print(f"\n=== Found Signal ===")
            print(f"Time: {message.date}")
            print(f"Topic ID: {getattr(message, 'reply_to', {}).get('reply_to_top_id', 'N/A')}")
            print(f"Message: {message_text[:200]}...")
            
            # Check for trading signal pattern
            if 'LONG' in message_text or 'SHORT' in message_text:
                print("This appears to be a TRADING SIGNAL")
            else:
                print("This appears to be other content")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(search_specific_signals())