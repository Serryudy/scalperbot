#!/usr/bin/env python3

from telethon import TelegramClient
from datetime import datetime, timedelta, timezone
import re
import asyncio

# ========== TELEGRAM CREDENTIALS ==========
api_id = 23008284
api_hash = "9b753f6de26369ddff1f498ce4d21fb5"
session_name = "signal_test_session"

# ========== TARGET GROUP/TOPIC ==========
group_id = -1002039861131
target_topic_id = 40011  # Main trading signals topic

# ========== ENHANCED SIGNAL EXTRACTION ==========
def extract_signal_enhanced(text, message_time):
    """Enhanced signal extraction for image captions and all message types"""
    signal = {
        "time": message_time.strftime('%Y-%m-%d %H:%M:%S'),
        "symbol": None,
        "side": None,
        "entry": [],
        "is_close": False
    }

    if not text or len(text.strip()) == 0:
        return signal

    # Check for close signal
    if re.search(r'\bclose\b', text, re.IGNORECASE):
        signal["is_close"] = True
        match_symbol = re.findall(r'\b([A-Z]{2,6})\b', text)
        if match_symbol:
            signal["symbol"] = match_symbol[0]
        return signal

    # Extract SIDE (LONG/SHORT)
    if re.search(r'\bLONG\b', text, re.IGNORECASE):
        signal["side"] = "LONG"
    elif re.search(r'\bSHORT\b', text, re.IGNORECASE):
        signal["side"] = "SHORT"

    # Extract SYMBOL - Enhanced patterns for image-based signals
    match_symbol = re.findall(r"\$([A-Z]{2,10})", text)
    if match_symbol:
        signal["symbol"] = match_symbol[0]
    else:
        # Try patterns without $ prefix - enhanced for image captions
        symbol_patterns = [
            r'^([A-Z]{3,10})\s*$',                          # MILK (standalone)
            r'^([A-Z]{3,10})\s*\n',                         # MILK (with newline)
            r'\b([A-Z]{3,10})(?=\s*(?:LONG|SHORT))',        # MILK LONG
            r'(?:^|\s)([A-Z]{3,10})(?=\s*[-:])',            # MILK -
            r'\b([A-Z]{3,10})\b(?=.*Entry)',                # MILK ... Entry
            r'(?:LONG|SHORT)\s*-\s*([A-Z]{3,10})',          # LONG - MILK
            r'^-\s*([A-Z]{3,10})',                          # - MILK (at start)
            r'([A-Z]{3,10})\s*\n.*?LONG',                   # MILK\nLONG pattern
        ]
        
        excluded = {'ENTRY', 'LONG', 'SHORT', 'STOP', 'TAKE', 'PROFIT', 'LOSS', 'SWING', 'ORDER', 'SMALL', 'VOL', 'LIMIT'}
        
        for pattern in symbol_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if matches:
                for match in matches:
                    if match.upper() not in excluded and len(match) >= 3:
                        signal["symbol"] = match.upper()
                        break
                if signal["symbol"]:
                    break

    # Extract ENTRY prices - Enhanced patterns for image-based signals
    entry_patterns = [
        r"(?:LONG|SHORT)\s*-\s*Entry[\s:]*([\d]+\.?[\d]*)",     # LONG - Entry: 0.04287
        r"Entry[\s:]*([\d]+\.?[\d]*)",                          # Entry: 0.04287
        r"Entry[\s:]*Limit[\s:]*([\d]+\.?[\d]*)",               # Entry Limit: 0.04278
        r"-\s*Entry[\s:]*([\d]+\.?[\d]*)",                      # - Entry: 0.04287
        r"([\d]+\.?[\d]+)\s*(?:entry|ent)",                     # 0.04287 entry
        r"@\s*([\d]+\.?[\d]+)",                                 # @ 0.04287
        r"([\d]+\.?[\d]+)\s*\(\d+%\s*VOL\)",                    # 0.04287 (30% VOL)
        r"Entry[\s:]*([0-9]*\.?[0-9]+).*?\(",                   # Entry: 0.04287 (
    ]
    
    for pattern in entry_patterns:
        match_entries = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match_entries:
            for x in match_entries:
                try:
                    price = float(x)
                    if price > 0:
                        signal["entry"].append(price)
                except (ValueError, TypeError):
                    continue
            if signal["entry"]:
                break
    
    return signal

def extract_message_text_enhanced(message):
    """Enhanced text extraction for ALL message types including media with captions"""
    message_text = ""
    
    try:
        # Method 1: Direct text attribute
        if hasattr(message, 'text') and message.text:
            message_text = message.text
        
        # Method 2: Caption attribute (for images/media)
        elif hasattr(message, 'caption') and message.caption:
            message_text = message.caption
        
        # Method 3: Alternative caption access
        elif hasattr(message, 'message') and message.message:
            message_text = message.message
        
        # Method 4: Try to get caption via getattr (safest)
        elif getattr(message, 'caption', None):
            message_text = getattr(message, 'caption', '')
        
        # Method 5: Check for media with text
        elif hasattr(message, 'media') and message.media:
            # For photos with captions
            if hasattr(message.media, 'caption'):
                message_text = message.media.caption or ""
            # Try alternative media text extraction
            elif hasattr(message, 'raw_text'):
                message_text = message.raw_text or ""
        
        # Method 6: Last resort - try raw_text
        elif hasattr(message, 'raw_text'):
            message_text = message.raw_text or ""
        
        # Try one more method for stubborn media messages
        if not message_text and message.media:
            try:
                if hasattr(message, 'text'):
                    message_text = str(message.text or "")
                elif message.media:
                    # Sometimes the text is embedded differently in media
                    message_text = str(getattr(message, 'message', ''))
            except:
                pass
        
    except Exception as extraction_error:
        print(f"❌ TEXT EXTRACTION ERROR: {extraction_error}")
        message_text = ""
    
    return message_text.strip() if message_text else ""

def format_signal_output(signal, message_text, topic_id):
    """Format signal for display with enhanced debugging"""
    print(f"\n{'='*80}")
    print(f"⏰ TIME: {signal['time']}")
    print(f"📌 TOPIC ID: {topic_id}")
    
    if signal["is_close"]:
        print(f"🔒 SIGNAL TYPE: CLOSE")
        print(f"🪙 SYMBOL: {signal['symbol'] or 'N/A'}")
        if signal['symbol']:
            print(f"✅ RESULT: Would close {signal['symbol']} position")
        else:
            print(f"❌ RESULT: Invalid close signal (no symbol detected)")
    elif signal["symbol"] and signal["side"] and signal["entry"]:
        print(f"📈 SIGNAL TYPE: TRADING")
        print(f"🪙 SYMBOL: ${signal['symbol']}")
        print(f"📊 SIDE: {signal['side']}")
        print(f"💰 ENTRY: {', '.join(map(str, signal['entry']))}")
        print(f"✅ RESULT: Would open {signal['side']} {signal['symbol']} at {signal['entry'][0]}")
    else:
        print(f"❌ SIGNAL TYPE: INVALID/INCOMPLETE")
        reasons = []
        if not signal["symbol"]:
            reasons.append("No symbol")
        if not signal["side"] and not signal["is_close"]:
            reasons.append("No side")
        if not signal["entry"] and not signal["is_close"]:
            reasons.append("No entry")
        print(f"⚠️  MISSING: {', '.join(reasons)}")
        print(f"❌ RESULT: No action would be taken")
    
    # Show message preview with better formatting
    preview = message_text[:200].replace('\n', ' ↵ ').replace('\r', ' ')
    if len(message_text) > 200:
        preview += "..."
    print(f"📝 MESSAGE: {preview}")
    print(f"📏 MESSAGE LENGTH: {len(message_text)} characters")
    print(f"{'='*80}")

async def fetch_todays_signals():
    """Fetch and analyze today's messages for signals"""
    
    print(f"🚀 Testing Enhanced Signal Detection for Today's Messages")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"🎯 Target Topic: {target_topic_id}")
    print("=" * 80)
    
    client = TelegramClient(session_name, api_id, api_hash)
    
    try:
        await client.start()
        print("✅ Connected to Telegram\n")
        
        # Get the group entity
        entity = await client.get_entity(group_id)
        print(f"📁 Group: {entity.title if hasattr(entity, 'title') else 'Unknown'}")
        print(f"🆔 Group ID: {group_id}")
        print(f"📌 Target Topic ID: {target_topic_id}\n")
        
        # Calculate today's date range (timezone-aware)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        print(f"📆 Fetching messages from: {today.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"📆 To: {tomorrow.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
        
        # Counters
        total_messages = 0
        target_topic_messages = 0
        other_topic_messages = 0
        empty_messages = 0
        valid_signals = []
        close_signals = []
        invalid_signals = []
        
        print("⏳ Fetching today's messages...")
        print("🔍 Analyzing ALL topics for signals...\n")
        
        # Fetch messages from today
        async for message in client.iter_messages(
            entity,
            offset_date=tomorrow,  # Start from tomorrow and go backwards
            limit=1000  # Limit to prevent too many messages
        ):
            total_messages += 1
            
            # Stop if we've gone past today
            if message.date < today:
                break
            
            # Only process messages with reply_to (in topics)
            if message.reply_to and message.reply_to.reply_to_msg_id:
                topic_id = message.reply_to.reply_to_msg_id
                
                # Extract text using enhanced method
                message_text = extract_message_text_enhanced(message)
                
                # Count messages by topic
                if topic_id == target_topic_id:
                    target_topic_messages += 1
                else:
                    other_topic_messages += 1
                
                # Track empty messages
                if not message_text:
                    empty_messages += 1
                    print(f"⚠️  EMPTY MESSAGE (Topic {topic_id}) at {message.date.strftime('%H:%M:%S')}")
                    
                    # Debug media information for empty messages
                    if hasattr(message, 'media') and message.media:
                        media_type = type(message.media).__name__
                        print(f"   📷 Media Type: {media_type}")
                        print(f"   📝 Has Caption: {hasattr(message, 'caption')}")
                        if hasattr(message, 'caption'):
                            print(f"   📄 Caption Content: {repr(getattr(message, 'caption', None))}")
                    continue
                
                # Extract signal using enhanced method
                signal = extract_signal_enhanced(message_text, message.date)
                
                # Categorize signals
                if signal["is_close"] and signal["symbol"]:
                    close_signals.append((signal, message_text, topic_id))
                    format_signal_output(signal, message_text, topic_id)
                elif signal["symbol"] and signal["side"] and signal["entry"]:
                    valid_signals.append((signal, message_text, topic_id))
                    format_signal_output(signal, message_text, topic_id)
                else:
                    invalid_signals.append((signal, message_text, topic_id))
                    # Only show invalid signals from target topic or if they have partial detection
                    if topic_id == target_topic_id or signal["symbol"] or signal["side"]:
                        format_signal_output(signal, message_text, topic_id)
        
        # Print comprehensive summary
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE ANALYSIS SUMMARY")
        print("="*80)
        print(f"📨 Total Messages Analyzed: {total_messages}")
        print(f"🎯 Target Topic ({target_topic_id}) Messages: {target_topic_messages}")
        print(f"📍 Other Topics Messages: {other_topic_messages}")
        print(f"📭 Empty Messages (Failed Extraction): {empty_messages}")
        print(f"✅ Valid Trading Signals: {len(valid_signals)}")
        print(f"🔒 Close Signals: {len(close_signals)}")
        print(f"❌ Invalid/Incomplete Signals: {len(invalid_signals)}")
        print("="*80)
        
        # Show valid signals summary
        if valid_signals:
            print("\n📈 VALID TRADING SIGNALS DETECTED:")
            for signal, _, topic_id in valid_signals:
                print(f"  🎯 {signal['time']} | Topic {topic_id} | ${signal['symbol']} {signal['side']} @ {signal['entry'][0]}")
        
        # Show close signals summary
        if close_signals:
            print("\n🔒 CLOSE SIGNALS DETECTED:")
            for signal, _, topic_id in close_signals:
                print(f"  🔒 {signal['time']} | Topic {topic_id} | Close {signal['symbol']}")
        
        # Show empty message analysis
        if empty_messages > 0:
            print(f"\n⚠️  EMPTY MESSAGE ANALYSIS:")
            print(f"   📊 {empty_messages} messages had no extractable text")
            print(f"   📷 These were likely images/media with caption extraction issues")
            print(f"   🎯 {target_topic_messages - len([s for s, _, t in valid_signals + close_signals + invalid_signals if t == target_topic_id])} from target topic {target_topic_id}")
        
        # Performance analysis
        extraction_success_rate = ((total_messages - empty_messages) / total_messages * 100) if total_messages > 0 else 0
        signal_detection_rate = ((len(valid_signals) + len(close_signals)) / (total_messages - empty_messages) * 100) if (total_messages - empty_messages) > 0 else 0
        
        print(f"\n📈 PERFORMANCE METRICS:")
        print(f"   🔍 Text Extraction Success: {extraction_success_rate:.1f}%")
        print(f"   🎯 Signal Detection Rate: {signal_detection_rate:.1f}%")
        
        if empty_messages > 0:
            print(f"\n💡 RECOMMENDATIONS:")
            print(f"   🔧 Need to fix image caption extraction for {empty_messages} messages")
            print(f"   📱 Consider alternative Telegram API methods for media messages")
        
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.disconnect()
        print("👋 Disconnected from Telegram")

if __name__ == "__main__":
    try:
        asyncio.run(fetch_todays_signals())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")