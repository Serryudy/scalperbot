from telethon import TelegramClient, events
import re
import asyncio

# ========== TELEGRAM ==========
api_id = 23008284
api_hash = "9b753f6de26369ddff1f498ce4d21fb5"
session_name = "extract_session"  # Unique session for extractor
group_id = -1002039861131
topic_id = 40011

# ---------- Signal Extraction ----------
def extract_signal(text, time):
    signal = {
        "time": str(time),
        "symbol": None,
        "side": None,
        "entry": [],
        "is_close": False
    }

    # Check if this is a close signal
    if re.search(r'\bclose\b', text, re.IGNORECASE):
        signal["is_close"] = True
        # Extract symbol from close signal (e.g., "XLM + 21.4% profit" or "Close XLM")
        match_symbol = re.findall(r'\b([A-Z]{2,6})\b', text)
        if match_symbol:
            signal["symbol"] = match_symbol[0]
        return signal

    # SIDE
    if "LONG" in text.upper():
        signal["side"] = "LONG"
    elif "SHORT" in text.upper():
        signal["side"] = "SHORT"

    # SYMBOL
    match_symbol = re.findall(r"\$([A-Z]{2,6})", text)
    if match_symbol:
        signal["symbol"] = match_symbol[0]

    # ENTRIES - improved pattern and validation
    match_entries = re.findall(r"Entry(?:\s*limit)?[:\s]+([\d]+\.?[\d]*)", text, re.IGNORECASE)
    if match_entries:
        for x in match_entries:
            try:
                price = float(x)
                if price > 0:
                    signal["entry"].append(price)
            except (ValueError, TypeError):
                pass

    return signal

def format_signal_output(parsed, message_text):
    """Format signal output for display"""
    print(f"\n{'='*60}")
    print(f"📅 TIME: {parsed['time']}")
    print(f"📝 MESSAGE: {message_text[:100]}{'...' if len(message_text) > 100 else ''}")
    print(f"{'='*60}")
    
    if parsed["is_close"] and parsed["symbol"]:
        print("🔒 CLOSE SIGNAL DETECTED")
        print(f"   Symbol: {parsed['symbol']}")
        print("   Action: Close position")
    elif parsed["symbol"] and parsed["side"] and parsed["entry"]:
        print("📈 TRADING SIGNAL DETECTED")
        print(f"   Symbol: ${parsed['symbol']}")
        print(f"   Side: {parsed['side']}")
        print(f"   Entry: {parsed['entry']}")
        print("   Status: Valid signal - ready for trading")
    else:
        print("⏭️ MESSAGE IGNORED")
        print("   Reason: Does not match signal patterns")
        if not parsed["symbol"]:
            print("   Missing: Symbol (e.g., $BTC)")
        if not parsed["side"] and not parsed["is_close"]:
            print("   Missing: Side (LONG/SHORT) or close keyword")
        if not parsed["entry"] and not parsed["is_close"]:
            print("   Missing: Entry price")
    
    print(f"{'='*60}\n")

# ---------- Telegram Message Listener ----------
async def main():
    tg = None
    try:
        tg = TelegramClient(session_name, api_id, api_hash)
        await tg.start()
        entity = await tg.get_entity(group_id)

        print("🤖 Message Extractor Started")
        print("📡 Listening for ALL messages in the topic")
        print("🔍 Will show both valid signals and ignored messages")
        print(f"📍 Topic ID: {topic_id}")
        print(f"{'='*60}\n")

        # Listen for all new messages
        @tg.on(events.NewMessage(chats=entity))
        async def handler(event):
            # Check if message is in the correct topic
            if event.message.reply_to and event.message.reply_to.reply_to_msg_id == topic_id:
                message_text = event.message.text or ""
                parsed = extract_signal(message_text, event.message.date)
                
                # Format and display all messages (both signals and ignored)
                format_signal_output(parsed, message_text)
            else:
                # Message not in target topic
                print(f"💬 Message not in target topic (Topic ID: {event.message.reply_to.reply_to_msg_id if event.message.reply_to else 'None'})")

        print("👂 Listening for new messages...")
        print("Press Ctrl+C to stop\n")
        await tg.run_until_disconnected()
    
    except Exception as e:
        print(f"❌ Error in extract main: {e}")
    finally:
        if tg and tg.is_connected():
            print("🔌 Disconnecting Telegram client...")
            await tg.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Message extractor stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")