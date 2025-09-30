from telethon import TelegramClient, events
from binance.client import Client
from binance.enums import *
import re
import asyncio

# ========== TELEGRAM ==========
api_id = 23008284
api_hash = "9b753f6de26369ddff1f498ce4d21fb5"
session_name = "my_session"
group_id = -1002039861131
topic_id = 40011

# ========== BINANCE ==========
binance_api_key = "9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ"
binance_api_secret = "mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl"
client = Client(binance_api_key, binance_api_secret, testnet=False)

RISK_PER_TRADE = 0.05
LEVERAGE = 10
RR_RATIO = 1.0

# Track open positions with their order IDs
open_positions = {}  # {symbol: {'side': 'LONG', 'sl_order_id': 123, 'tp_order_id': 456, 'qty': 0.5}}

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

# ---------- Close Position Function ----------
def close_position(signal):
    """Close an open position based on close signal"""
    symbol_base = signal['symbol']
    symbol = f"{symbol_base}USDT"
    
    if symbol_base not in open_positions:
        print(f"⚠ No tracked position found for {symbol_base}")
        print(f"  Checking Binance for any open positions...")
        
        # Check if there's actually an open position on Binance
        try:
            positions = client.futures_position_information(symbol=symbol)
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    print(f"  Found open position on Binance!")
                    # We'll close it anyway even if not tracked
                    break
            else:
                print(f"  No open position found on Binance either.")
                return
        except Exception as e:
            print(f"❌ Error checking position: {e}")
            return
    
    try:
        print(f"\n{'='*50}")
        print(f"🔒 CLOSE SIGNAL DETECTED for {symbol_base}")
        print(f"{'='*50}")
        
        # Get current position info from Binance
        positions = client.futures_position_information(symbol=symbol)
        position = None
        for pos in positions:
            if float(pos['positionAmt']) != 0:
                position = pos
                break
        
        if not position:
            print(f"⚠ No open position found on Binance for {symbol}")
            # Clean up tracking
            if symbol_base in open_positions:
                del open_positions[symbol_base]
            return
        
        position_amt = float(position['positionAmt'])
        entry_price = float(position['entryPrice'])
        
        # Get current market price
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        
        # Calculate P&L
        if position_amt > 0:  # LONG position
            pnl = (current_price - entry_price) * abs(position_amt)
            side_text = "LONG"
        else:  # SHORT position
            pnl = (entry_price - current_price) * abs(position_amt)
            side_text = "SHORT"
        
        print(f"Position: {side_text}")
        print(f"Entry Price: {entry_price}")
        print(f"Current Price: {current_price}")
        print(f"Quantity: {abs(position_amt)}")
        print(f"Estimated P&L: {pnl:+.2f} USDT")
        
        # Cancel all open orders for this symbol (SL and TP)
        if symbol_base in open_positions:
            pos_data = open_positions[symbol_base]
            
            # Cancel Stop Loss
            if pos_data.get('sl_order_id'):
                try:
                    client.futures_cancel_order(symbol=symbol, orderId=pos_data['sl_order_id'])
                    print(f"✓ Cancelled Stop Loss order {pos_data['sl_order_id']}")
                except Exception as e:
                    if "-2011" not in str(e):  # Ignore "Unknown order" error
                        print(f"⚠ Could not cancel SL: {e}")
            
            # Cancel Take Profit
            if pos_data.get('tp_order_id'):
                try:
                    client.futures_cancel_order(symbol=symbol, orderId=pos_data['tp_order_id'])
                    print(f"✓ Cancelled Take Profit order {pos_data['tp_order_id']}")
                except Exception as e:
                    if "-2011" not in str(e):
                        print(f"⚠ Could not cancel TP: {e}")
        else:
            # Try to cancel all open orders for this symbol
            try:
                client.futures_cancel_all_open_orders(symbol=symbol)
                print(f"✓ Cancelled all open orders for {symbol}")
            except Exception as e:
                print(f"⚠ Could not cancel orders: {e}")
        
        # Close position at market price
        close_side = "SELL" if position_amt > 0 else "BUY"
        
        order = client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type="MARKET",
            quantity=abs(position_amt),
            reduceOnly=True
        )
        
        print(f"✓ Position closed at market price")
        print(f"  Order ID: {order['orderId']}")
        print(f"{'='*50}\n")
        
        # Remove from tracking
        if symbol_base in open_positions:
            del open_positions[symbol_base]
            print(f"✓ Removed {symbol_base} from position tracking")
        
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
        if symbol_base in open_positions:
            print(f"⚠ Already have an open position for {symbol_base}")
            print(f"  Skipping new {side} signal")
            return
        
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
            print(f"Error: Symbol {symbol} not found on Binance Futures")
            return

        # --- Set Leverage ---
        try:
            client.futures_change_leverage(symbol=symbol, leverage=LEVERAGE)
            print(f"Leverage set to {LEVERAGE}x for {symbol}")
        except Exception as e:
            print(f"Warning: Could not set leverage - {e}")

        # --- Risk Management ---
        account = client.futures_account_balance()
        usdt_balance = float(next(b for b in account if b['asset'] == 'USDT')['balance'])
        
        account_info = client.futures_account()
        available_balance = float(account_info['availableBalance'])
        
        if available_balance <= 0:
            print("Error: Insufficient available balance")
            return
        
        risk_per_trade = usdt_balance * RISK_PER_TRADE
        stop_loss_pct = 0.01
        
        position_value = (risk_per_trade / stop_loss_pct)
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
        
        position_value = qty * entry_price
        required_margin = position_value / LEVERAGE
        
        if required_margin > available_balance * 0.95:
            print(f"❌ Insufficient available margin.")
            print(f"   Required: {required_margin:.2f} USDT")
            print(f"   Available: {available_balance:.2f} USDT")
            print(f"   Total Balance: {usdt_balance:.2f} USDT")
            print(f"   (Margin already used in other positions)")
            return

        print(f"\n{'='*50}")
        print(f"Placing {side} {'MARKET' if use_market_order else 'LIMIT'} order on {symbol}")
        if use_market_order:
            print(f"Entry: MARKET (~{current_price}), Stop: {stop_loss}, TP: {take_profit}, Qty: {qty}")
        else:
            print(f"Entry: {entry_price}, Stop: {stop_loss}, TP: {take_profit}, Qty: {qty}")
        print(f"Total Balance: {usdt_balance:.2f} USDT")
        print(f"Available Balance: {available_balance:.2f} USDT")
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
        
        # Track this position
        open_positions[symbol_base] = {
            'side': side,
            'sl_order_id': sl_order_id,
            'tp_order_id': tp_order_id,
            'qty': qty,
            'entry_price': actual_entry
        }
        print(f"✓ Position tracked for {symbol_base}")
            
    except Exception as e:
        print(f"❌ Error placing trade: {e}")
        import traceback
        traceback.print_exc()


# ---------- Telegram Integration ----------
async def main():
    tg = TelegramClient(session_name, api_id, api_hash)
    await tg.start()
    entity = await tg.get_entity(group_id)

    print("Fetching past signals...\n")
    async for msg in tg.iter_messages(entity, reply_to=topic_id, limit=10):
        if msg.text:
            parsed = extract_signal(msg.text, msg.date)
            
            # Handle close signals
            if parsed["is_close"] and parsed["symbol"]:
                print("Close signal found:", parsed)
                close_position(parsed)
            # Handle trading signals
            elif parsed["symbol"] and parsed["side"] and parsed["entry"]:
                print("Trading signal found:", parsed)
                place_trade(parsed)

    # Listen for new signals
    @tg.on(events.NewMessage(chats=entity))
    async def handler(event):
        if event.message.reply_to and event.message.reply_to.reply_to_msg_id == topic_id:
            parsed = extract_signal(event.message.text or "", event.message.date)
            
            # Handle close signals
            if parsed["is_close"] and parsed["symbol"]:
                print("NEW CLOSE SIGNAL:", parsed)
                close_position(parsed)
            # Handle trading signals
            elif parsed["symbol"] and parsed["side"] and parsed["entry"]:
                print("NEW TRADING SIGNAL:", parsed)
                place_trade(parsed)

    print("Listening for new messages...\n")
    print(f"Currently tracking {len(open_positions)} open positions")
    await tg.run_until_disconnected()

asyncio.run(main())