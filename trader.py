from telethon import TelegramClient, events
from binance.client import Client
from binance.enums import *
import re
import asyncio
import logging
from datetime import datetime
import os
import time

# ========== TELEGRAM ==========
api_id = 23008284
api_hash = "9b753f6de26369ddff1f498ce4d21fb5"
session_name = "trader_session"  # Unique session for trader
group_id = -1002039861131
topic_id = 40011

# ========== BINANCE ==========
binance_api_key = "9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ"
binance_api_secret = "mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl"
client = Client(binance_api_key, binance_api_secret, testnet=False)

RISK_PER_TRADE = 0.2
LEVERAGE = 10
RR_RATIO = 1.0
EXPECTED_SIGNALS_PER_DAY = 6  # Reserve balance for this many signals

# ========== LOGGING SETUP ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('trader_messages.log', encoding='utf-8')  # File output
    ]
)
logger = logging.getLogger(__name__)

# ========== SESSION MANAGEMENT ==========
def cleanup_session_files():
    """Clean up session files if they exist and might be corrupted"""
    session_files = [f"{session_name}.session", f"{session_name}.session-journal"]
    for file_path in session_files:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"🧹 Cleaned up session file: {file_path}")
                logger.info(f"SESSION CLEANUP: Removed {file_path}")
            except Exception as e:
                print(f"⚠ Could not remove {file_path}: {e}")

def create_safe_telegram_client():
    """Create a Telegram client with better error handling"""
    try:
        # Add a small delay to ensure no conflicts
        time.sleep(1)
        
        client = TelegramClient(
            session_name, 
            api_id, 
            api_hash,
            # Add session parameters for better stability
            device_model="Trading Bot",
            system_version="1.0",
            app_version="1.0",
            lang_code="en",
            system_lang_code="en"
        )
        return client
    except Exception as e:
        print(f"❌ Error creating Telegram client: {e}")
        logger.error(f"CLIENT CREATION ERROR: {e}")
        return None

# ---------- Binance Position Tracking Functions ----------
def get_open_positions():
    """Get all open positions from Binance API"""
    try:
        positions = client.futures_position_information()
        open_pos = {}
        for pos in positions:
            if float(pos['positionAmt']) != 0:
                symbol_base = pos['symbol'].replace('USDT', '')
                open_pos[symbol_base] = {
                    'side': 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT',
                    'qty': abs(float(pos['positionAmt'])),
                    'entry_price': float(pos['entryPrice']),
                    'symbol': pos['symbol']
                }
        return open_pos
    except Exception as e:
        print(f"❌ Error getting positions: {e}")
        return {}

def get_open_orders_for_symbol(symbol):
    """Get all open orders for a specific symbol"""
    try:
        orders = client.futures_get_open_orders(symbol=symbol)
        return orders
    except Exception as e:
        print(f"❌ Error getting orders for {symbol}: {e}")
        return []

def log_message_and_signal(message_text, parsed_signal, event_time):
    """Log every message and its signal extraction result"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create a clean message preview (first 100 chars)
    message_preview = (message_text[:100] + '...') if len(message_text) > 100 else message_text
    message_preview = message_preview.replace('\n', ' ').replace('\r', ' ')  # Remove newlines
    
    # Determine signal type
    if parsed_signal["is_close"] and parsed_signal["symbol"]:
        signal_type = "CLOSE_SIGNAL"
        signal_details = f"Symbol: {parsed_signal['symbol']}"
    elif parsed_signal["symbol"] and parsed_signal["side"] and parsed_signal["entry"]:
        signal_type = "TRADING_SIGNAL"
        signal_details = f"Symbol: ${parsed_signal['symbol']}, Side: {parsed_signal['side']}, Entry: {parsed_signal['entry']}"
    else:
        signal_type = "NO_SIGNAL"
        signal_details = "No valid signal detected"
    
    # Log to file and console
    log_entry = f"[{timestamp}] MESSAGE: '{message_preview}' | SIGNAL: {signal_type} | DETAILS: {signal_details}"
    logger.info(log_entry)
    
    # Also print to console with formatting
    print(f"\n📨 MESSAGE LOGGED: {timestamp}")
    print(f"📝 Content: {message_preview}")
    print(f"🔍 Signal: {signal_type}")
    print(f"📊 Details: {signal_details}")
    print("-" * 60)

# ---------- Signal Extraction ----------
def extract_signal(text, time):
    """Extract trading signal from message text - EXACT COPY from working tester script"""
    signal = {
        "time": str(time),
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

    # Extract SYMBOL
    match_symbol = re.findall(r"\$([A-Z]{2,10})", text)
    if match_symbol:
        signal["symbol"] = match_symbol[0]
    else:
        # Try patterns without $ prefix
        symbol_patterns = [
            r'^([A-Z]{3,10})\s*$',
            r'^([A-Z]{3,10})\s*\n',
            r'\b([A-Z]{3,10})(?=\s*(?:LONG|SHORT))',
            r'(?:^|\s)([A-Z]{3,10})(?=\s*[-:])',
            r'\b([A-Z]{3,10})\b(?=.*Entry)',
        ]
        
        excluded = {'ENTRY', 'LONG', 'SHORT', 'STOP', 'TAKE', 'PROFIT', 'LOSS', 'SWING', 'ORDER', 'SMALL', 'VOL'}
        
        for pattern in symbol_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            if matches:
                for match in matches:
                    if match.upper() not in excluded and len(match) >= 3:
                        signal["symbol"] = match.upper()
                        break
                if signal["symbol"]:
                    break

    # Extract ENTRY prices
    entry_patterns = [
        r"(?:LONG|SHORT)\s*-\s*Entry[\s:]*([\d]+\.?[\d]*)",
        r"Entry[\s:]*([\d]+\.?[\d]*)",
        r"Entry[\s:]*limit[\s:]*([\d]+\.?[\d]*)",
        r"-\s*Entry[\s:]*([\d]+\.?[\d]*)",
        r"([\d]+\.?[\d]+)\s*(?:entry|ent)",
        r"@\s*([\d]+\.?[\d]+)",
    ]
    
    for pattern in entry_patterns:
        match_entries = re.findall(pattern, text, re.IGNORECASE)
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
    
    # Log what we extracted for debugging
    logger.info(f"EXTRACTED: Symbol={signal['symbol']}, Side={signal['side']}, Entry={signal['entry']}, Close={signal['is_close']}")
    
    return signal

# ---------- Close Position Function ----------
def close_position(signal):
    """Close an open position based on close signal"""
    symbol_base = signal['symbol']
    symbol = f"{symbol_base}USDT"
    
    # Get current positions from Binance
    open_positions = get_open_positions()
    
    if symbol_base not in open_positions:
        print(f"⚠ No open position found for {symbol_base}")
        return
    
    try:
        print(f"\n{'='*50}")
        print(f"🔒 CLOSE SIGNAL DETECTED for {symbol_base}")
        print(f"{'='*50}")
        
        position_data = open_positions[symbol_base]
        
        # Get current market price
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        
        # Calculate P&L
        if position_data['side'] == 'LONG':
            pnl = (current_price - position_data['entry_price']) * position_data['qty']
        else:  # SHORT
            pnl = (position_data['entry_price'] - current_price) * position_data['qty']
        
        print(f"Position: {position_data['side']}")
        print(f"Entry Price: {position_data['entry_price']}")
        print(f"Current Price: {current_price}")
        print(f"Quantity: {position_data['qty']}")
        print(f"Estimated P&L: {pnl:+.2f} USDT")
        
        # Cancel all open orders for this symbol
        try:
            client.futures_cancel_all_open_orders(symbol=symbol)
            print(f"✓ Cancelled all open orders for {symbol}")
        except Exception as e:
            print(f"⚠ Could not cancel orders: {e}")
        
        # Close position at market price
        close_side = "SELL" if position_data['side'] == 'LONG' else "BUY"
        
        order = client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type="MARKET",
            quantity=position_data['qty'],
            reduceOnly=True
        )
        
        print(f"✓ Position closed at market price")
        print(f"  Order ID: {order['orderId']}")
        print(f"{'='*50}\n")
        
        # Log successful position close
        logger.info(f"POSITION CLOSED: {position_data['side']} {symbol_base} at {current_price} | P&L: {pnl:+.2f} USDT | Order: {order['orderId']}")
        
    except Exception as e:
        print(f"❌ Error closing position for {symbol_base}: {e}")
        import traceback
        traceback.print_exc()

# ---------- Trading Functions ----------
def get_account_balance():
    info = client.futures_account()
    balance = float(info["totalWalletBalance"])
    return balance

def round_step_size(value, step_size):
    from decimal import Decimal, ROUND_DOWN
    return float((Decimal(str(value)) // Decimal(str(step_size))) * Decimal(str(step_size)))

def place_trade(signal):
    try:
        symbol_base = signal['symbol']
        symbol = f"{symbol_base}USDT"
        side = signal['side'].upper()
        entry_price = signal['entry'][0]
        
        # Check if we already have a position for this symbol
        open_positions = get_open_positions()
        if symbol_base in open_positions:
            print(f"⚠ Already have an open position for {symbol_base}")
            print(f"  Current: {open_positions[symbol_base]['side']}")
            print(f"  Skipping new {side} signal")
            return
        
        # ========== EARLY BALANCE CHECK ==========
        print(f"\n{'='*50}")
        print(f"📊 PRE-TRADE BALANCE CHECK for {symbol}")
        print(f"{'='*50}")
        
        try:
            account = client.futures_account_balance()
            usdt_balance = float(next(b for b in account if b['asset'] == 'USDT')['balance'])
            
            account_info = client.futures_account()
            available_balance = float(account_info['availableBalance'])
            
            print(f"Total Balance: {usdt_balance:.2f} USDT")
            print(f"Available Balance: {available_balance:.2f} USDT")
            print(f"Already in Positions: {len(open_positions)}")
            
            # Calculate if we have enough for remaining expected signals
            remaining_signals = EXPECTED_SIGNALS_PER_DAY - len(open_positions)
            if remaining_signals < 1:
                remaining_signals = 1  # At least keep buffer for 1 more
            
            # Reserve balance for future signals
            reserved_balance = available_balance / remaining_signals
            risk_amount = usdt_balance * RISK_PER_TRADE
            
            # Estimate required margin (approximate)
            estimated_position_value = (risk_amount / 0.01) * 1.1  # 1% SL, 10% buffer
            estimated_margin_needed = estimated_position_value / LEVERAGE
            
            print(f"Risk per trade: {risk_amount:.2f} USDT ({RISK_PER_TRADE*100}%)")
            print(f"Estimated margin needed: {estimated_margin_needed:.2f} USDT")
            print(f"Balance per signal (reserved): {reserved_balance:.2f} USDT")
            print(f"Remaining signals to account for: {remaining_signals}")
            
            # Check if we have enough margin
            if estimated_margin_needed > reserved_balance:
                print(f"\n❌ INSUFFICIENT BALANCE - TRADE REJECTED")
                print(f"   Reason: Not enough balance to maintain {EXPECTED_SIGNALS_PER_DAY} signals/day capacity")
                print(f"   Need: {estimated_margin_needed:.2f} USDT")
                print(f"   Have (per signal): {reserved_balance:.2f} USDT")
                print(f"   Consider: Reduce position sizes or close existing positions")
                print(f"{'='*50}\n")
                return
            
            if available_balance < estimated_margin_needed * 1.2:  # 20% safety margin
                print(f"\n⚠️  WARNING: Low available balance!")
                print(f"   Continuing with reduced position size")
                
        except Exception as e:
            print(f"❌ Error checking balance: {e}")
            print(f"   Aborting trade for safety")
            print(f"{'='*50}\n")
            return
        
        print(f"✓ Balance check passed - proceeding with trade")
        print(f"{'='*50}\n")
        
        # Convert LONG/SHORT to BUY/SELL for Binance API
        binance_side = "BUY" if side == "LONG" else "SELL"

        # --- Get symbol info from Binance ---
        info = client.futures_exchange_info()
        symbol_info = None
        for s in info['symbols']:
            if s['symbol'] == symbol:
                symbol_info = s
                price_filter = next(f for f in s['filters'] if f['filterType'] == 'PRICE_FILTER')
                lot_size = next(f for f in s['filters'] if f['filterType'] == 'LOT_SIZE')
                tick_size = float(price_filter['tickSize'])
                step_size = float(lot_size['stepSize'])
                break
        
        if not symbol_info:
            print(f"❌ Symbol {symbol} not found on Binance Futures")
            return

        # --- Set Leverage (silently) ---
        try:
            client.futures_change_leverage(symbol=symbol, leverage=LEVERAGE)
        except Exception as e:
            print(f"⚠ Could not set leverage: {e}")

        # --- Risk Management with Balance Reservation ---
        risk_per_trade = usdt_balance * RISK_PER_TRADE
        stop_loss_pct = 0.01
        
        # Calculate position size with buffer for multiple signals
        remaining_signals = EXPECTED_SIGNALS_PER_DAY - len(open_positions)
        if remaining_signals < 1:
            remaining_signals = 1
        
        # Limit position value to ensure we can take more trades
        max_position_value = (available_balance / remaining_signals) * LEVERAGE * 0.85  # 15% safety buffer
        calculated_position_value = (risk_per_trade / stop_loss_pct)
        
        # Use the smaller of the two
        position_value = min(calculated_position_value, max_position_value)
        qty = position_value / entry_price
            
        # --- Get current market price ---
        try:
            ticker = client.futures_symbol_ticker(symbol=symbol)
            current_price = float(ticker['price'])
            print(f"Current market price: {current_price}")
        except Exception as e:
            print(f"❌ Could not fetch current price: {e}")
            return
        
        # --- Determine order type based on market conditions ---
        use_market_order = False
        
        if side == "LONG":
            if current_price <= entry_price:
                use_market_order = True
                print(f"✓ Market price ({current_price}) is below entry ({entry_price})")
                print(f"  Placing MARKET order to enter immediately")
            else:
                print(f"ℹ Market price ({current_price}) is above entry ({entry_price})")
                print(f"  Placing LIMIT order and waiting for price to come down")
        else:  # SHORT
            if current_price >= entry_price:
                use_market_order = True
                print(f"✓ Market price ({current_price}) is above entry ({entry_price})")
                print(f"  Placing MARKET order to enter immediately")
            else:
                print(f"ℹ Market price ({current_price}) is below entry ({entry_price})")
                print(f"  Placing LIMIT order and waiting for price to come up")
        
        actual_entry = current_price if use_market_order else entry_price
        stop_loss = actual_entry * (1 - stop_loss_pct) if side == "LONG" else actual_entry * (1 + stop_loss_pct)
        take_profit = actual_entry + (actual_entry - stop_loss) * RR_RATIO if side == "LONG" else actual_entry - (stop_loss - actual_entry) * RR_RATIO

        # --- Round values according to Binance rules ---
        stop_loss = round_step_size(stop_loss, tick_size)
        take_profit = round_step_size(take_profit, tick_size)
        qty = round_step_size(qty, step_size)
        
        if not use_market_order:
            entry_price = round_step_size(entry_price, tick_size)
        
        position_value = qty * actual_entry
        required_margin = position_value / LEVERAGE
        
        # Final margin check (should pass since we pre-checked)
        if required_margin > available_balance * 0.80:  # Use max 80% per trade
            print(f"❌ Position size too large after calculations")
            print(f"   Required margin: {required_margin:.2f} USDT")
            print(f"   Available: {available_balance:.2f} USDT")
            return

        print(f"\n{'='*50}")
        print(f"Placing {side} {'MARKET' if use_market_order else 'LIMIT'} order on {symbol}")
        if use_market_order:
            print(f"Entry: MARKET (~{current_price}), Stop: {stop_loss}, TP: {take_profit}, Qty: {qty}")
        else:
            print(f"Entry: {entry_price}, Stop: {stop_loss}, TP: {take_profit}, Qty: {qty}")
        print(f"Position Value: {position_value:.2f} USDT")
        print(f"Required Margin: {required_margin:.2f} USDT")
        print(f"Risk Amount: {risk_per_trade:.2f} USDT ({RISK_PER_TRADE*100}%)")
        print(f"{'='*50}\n")

        # --- Place order (MARKET or LIMIT) ---
        try:
            if use_market_order:
                order = client.futures_create_order(
                    symbol=symbol,
                    side=binance_side,
                    type="MARKET",
                    quantity=qty
                )
                print(f"✓ MARKET order executed: {order['orderId']}")
            else:
                order = client.futures_create_order(
                    symbol=symbol,
                    side=binance_side,
                    type="LIMIT",
                    timeInForce="GTC",
                    quantity=qty,
                    price=entry_price
                )
                print(f"✓ LIMIT order placed: {order['orderId']}")
        except Exception as e:
            print(f"❌ Failed to place entry order: {e}")
            return
        
        sl_order_id = None
        tp_order_id = None
        
        # --- Place Stop Loss ---
        try:
            sl_side = "SELL" if side == "LONG" else "BUY"
            sl_order = client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type="STOP_MARKET",
                stopPrice=stop_loss,
                quantity=qty,
                closePosition=False
            )
            sl_order_id = sl_order['orderId']
            print(f"✓ Stop Loss set at {stop_loss} (Order ID: {sl_order_id})")
        except Exception as e:
            error_msg = str(e)
            print(f"⚠ Warning: Could not set stop loss - {e}")
            
            if "-2021" in error_msg or "immediately trigger" in error_msg:
                print(f"⚠ Stop loss price ({stop_loss}) would trigger immediately!")
                print(f"   Current market has likely moved past your stop loss.")
            
            print(f"⚠ Attempting to cancel entry order {order['orderId']}...")
            try:
                cancel_response = client.futures_cancel_order(
                    symbol=symbol, 
                    orderId=order['orderId']
                )
                print(f"✓ Entry order canceled successfully")
                return
            except Exception as cancel_error:
                cancel_error_msg = str(cancel_error)
                if "-2011" in cancel_error_msg or "Unknown order" in cancel_error_msg:
                    print(f"⚠ Entry order already filled or doesn't exist!")
                    print(f"⚠ WARNING: You may have an open position WITHOUT stop loss!")
                    print(f"⚠ Please manually set stop loss at {stop_loss} or close position!")
                else:
                    print(f"❌ Failed to cancel entry order: {cancel_error}")
                    print(f"⚠ URGENT: Manually cancel order {order['orderId']} on Binance!")
                return
        
        # --- Place Take Profit ---
        try:
            tp_side = "SELL" if side == "LONG" else "BUY"
            tp_order = client.futures_create_order(
                symbol=symbol,
                side=tp_side,
                type="TAKE_PROFIT_MARKET",
                stopPrice=take_profit,
                quantity=qty,
                closePosition=False
            )
            tp_order_id = tp_order['orderId']
            print(f"✓ Take Profit set at {take_profit} (Order ID: {tp_order_id})")
        except Exception as e:
            error_msg = str(e)
            print(f"⚠ Warning: Could not set take profit - {e}")
            
            if "-2021" in error_msg or "immediately trigger" in error_msg:
                print(f"⚠ Take profit price ({take_profit}) would trigger immediately!")
            
            print(f"ℹ Stop Loss is still active at {stop_loss}")
        
        print(f"✓ Trade executed for {symbol_base} - {side}")
        print(f"✓ Position will be tracked via Binance API")
        
        # Log successful trade execution
        logger.info(f"TRADE EXECUTED: {side} {symbol_base} at {actual_entry} | SL: {stop_loss} | TP: {take_profit} | Qty: {qty}")
            
    except Exception as e:
        print(f"❌ Error placing trade: {e}")
        import traceback
        traceback.print_exc()


# ---------- Telegram Integration ----------
async def main():
    tg = None
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Clean up any existing session files on first attempt
            if retry_count == 0:
                cleanup_session_files()
                time.sleep(2)  # Give some time for cleanup
            
            print(f"🔄 Attempt {retry_count + 1}/{max_retries} - Creating Telegram client...")
            
            tg = create_safe_telegram_client()
            if tg is None:
                raise Exception("Failed to create Telegram client")
            
            print("🔗 Starting Telegram client...")
            await tg.start()
            
            print("🔍 Getting entity...")
            entity = await tg.get_entity(group_id)
            
            print("🤖 Bot started - listening for NEW messages from ALL TOPICS")
            print("📝 All messages and signals will be logged to 'trader_messages.log'")
            print(f"🎯 Primary target topic: {topic_id} (but monitoring all topics for signals)")
            
            # Show current positions from Binance
            current_positions = get_open_positions()
            print(f"📊 Currently tracking {len(current_positions)} open positions from Binance:")
            for symbol, pos in current_positions.items():
                print(f"  {symbol}: {pos['side']} @ {pos['entry_price']} (Qty: {pos['qty']})")
            print()
            
            # Log startup
            logger.info(f"TRADER BOT STARTED - Monitoring {len(current_positions)} positions")
            
            # Listen for new signals only
            @tg.on(events.NewMessage(chats=entity))
            async def handler(event):
                # Process ALL messages with reply_to (any topic), not just specific topic
                if event.message.reply_to and event.message.reply_to.reply_to_msg_id:
                    topic_id_found = event.message.reply_to.reply_to_msg_id
                    
                    # Extract text from message - use same logic as working tester
                    message_text = ""
                    
                    # Simple, reliable extraction like in tester script
                    if hasattr(event.message, 'text') and event.message.text:
                        message_text = event.message.text
                    elif hasattr(event.message, 'caption') and event.message.caption:
                        message_text = event.message.caption
                    
                    # Skip processing if no text content
                    if not message_text:
                        logger.info(f"MESSAGE NO TEXT (Topic ID: {topic_id_found}): Empty message")
                        return
                    
                    # ALWAYS try to extract signal from ANY topic - let signal detection decide if it's valid
                    parsed = extract_signal(message_text, event.message.date)
                    
                    # Log every message and its signal extraction result
                    log_message_and_signal(message_text, parsed, event.message.date)
                    
                    # Handle close signals from ANY topic
                    if parsed["is_close"] and parsed["symbol"]:
                        print(f"\n🔒 NEW CLOSE SIGNAL DETECTED (Topic {topic_id_found}):", parsed)
                        close_position(parsed)
                    # Handle trading signals from ANY topic  
                    elif parsed["symbol"] and parsed["side"] and parsed["entry"]:
                        print(f"\n📈 NEW TRADING SIGNAL DETECTED (Topic {topic_id_found}):", parsed)
                        place_trade(parsed)
                    else:
                        # Only log detailed rejection for original target topic to reduce noise
                        if topic_id_found == topic_id:
                            reasons = []
                            if not parsed["symbol"]:
                                reasons.append("missing symbol")
                            if not parsed["side"] and not parsed["is_close"]:
                                reasons.append("missing side (LONG/SHORT)")
                            if not parsed["entry"] and not parsed["is_close"]:
                                reasons.append("missing entry price")
                            
                            logger.info(f"SIGNAL REJECTED (Topic {topic_id_found}): {', '.join(reasons)}")
                            print(f"⚠️ Signal rejected (Topic {topic_id_found}): {', '.join(reasons)}")
                        else:
                            # Just log as regular message for other topics
                            logger.info(f"MESSAGE NO SIGNAL (Topic ID: {topic_id_found}): '{message_text[:50]}...'")
                else:
                    # Log messages not in any topic (simple approach like tester)
                    message_text = "[No text]"
                    if hasattr(event.message, 'text') and event.message.text:
                        message_text = event.message.text
                    elif hasattr(event.message, 'caption') and event.message.caption:
                        message_text = event.message.caption
                    
                    logger.info(f"MESSAGE NOT IN ANY TOPIC: '{message_text[:50]}...'")
                    print(f"💬 Message not in any topic")
            
            print("👂 Listening for new messages...\n")
            await tg.run_until_disconnected()
            
            # If we reach here, connection was successful and then disconnected normally
            break
            
        except Exception as e:
            retry_count += 1
            error_msg = str(e)
            
            print(f"❌ Error in trader main (attempt {retry_count}/{max_retries}): {e}")
            logger.error(f"TRADER ERROR (attempt {retry_count}): {e}")
            
            # Clean up the current client
            if tg:
                try:
                    if tg.is_connected():
                        await tg.disconnect()
                except:
                    pass
                tg = None
            
            # If it's a database lock error, clean up session files
            if "database is locked" in error_msg.lower():
                print("🧹 Database lock detected - cleaning up session files...")
                cleanup_session_files()
                time.sleep(3)  # Wait longer for database lock to clear
            
            if retry_count < max_retries:
                wait_time = retry_count * 5  # Increasing wait time
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ Maximum retries reached. Exiting.")
                logger.error("TRADER FAILED: Maximum retries reached")
    
    # Final cleanup
    if tg and tg.is_connected():
        try:
            print("🔌 Disconnecting Telegram client...")
            logger.info("TRADER BOT STOPPED - Disconnecting...")
            await tg.disconnect()
        except Exception as e:
            print(f"⚠ Error during final disconnect: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Trading bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        print(f"❌ Fatal error: {e}")