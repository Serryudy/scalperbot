import sys
import os
import asyncio
from telethon import TelegramClient

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trader import TELEGRAM_CONFIG

async def test_telegram_connection():
    print("Testing Telegram Connection...")
    
    # Using the most likely session file based on 'improved_trading_bot.db' existing
    session_name = 'improved_ai_trading_session'
    session_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), session_name)
    
    print(f"Session File: {session_name}")
    print(f"API ID: {TELEGRAM_CONFIG['api_id']}")
    
    client = TelegramClient(
        session_path,
        TELEGRAM_CONFIG['api_id'],
        TELEGRAM_CONFIG['api_hash']
    )
    
    try:
        print("Connecting...")
        await client.connect()
        
        if not await client.is_user_authorized():
            print("❌ User is NOT authorized.")
            print("   You may need to run the main bot to login interactively first,")
            print("   or the session file is invalid/expired.")
            return
            
        print("✅ User is authorized")
        
        me = await client.get_me()
        if me:
            print(f"Logged in as: {me.first_name} (@{me.username})")
            print(f"ID: {me.id}")
            
            print("\nChecking dialogs (access to groups)...")
            count = 0
            async for dialog in client.iter_dialogs(limit=5):
                print(f"- {dialog.name} (ID: {dialog.id})")
                count += 1
            if count == 0:
                print("   No dialogs found (or permission issue).")
            
            print("\n✅ Telegram Connection Successful")
        else:
            print("❌ Start failed: Could not get 'me'")
        
    except Exception as e:
        print(f"\n❌ Exception: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_telegram_connection())
