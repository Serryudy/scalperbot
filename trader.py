from telethon import TelegramClient, events
from binance.client import Client
from binance.enums import *
import re
import asyncio

# ========== TELEGRAM ==========
api_id = 23008284            # your Telegram API ID
api_hash = "9b753f6de26369ddff1f498ce4d21fb5"  # your Telegram API Hash
session_name = "my_session"
group_id = -1002039861131  # replace with your group/channel ID
topic_id = 40011           # your topic/thread ID

# ========== BINANCE ==========
binance_api_key = "9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ"
binance_api_secret = "mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl"
client = Client(binance_api_key, binance_api_secret, testnet=False)  # set testnet=False for live trading

RISK_PER_TRADE = 0.05   # 5% risk
LEVERAGE = 10
RR_RATIO = 1.0          # risk:reward

# ---------- Signal Extraction ----------
def extract_signal(text, time):
    signal = {
        "time": str(time),
        "symbol": None,
        "side": None,
        "entry": [],
    }

    # SIDE
    if "LONG" in text.upper():
        signal["side"] = "LONG"
    elif "SHORT" in text.upper():
        signal["side"] = "SHORT"

    # SYMBOL
    match_symbol = re.findall(r"\$([A-Z]{2,6})", text)
    if match_symbol:
        signal["symbol"] = match_symbol[0]

    # ENTRIES
    match_entries = re.findall(r"Entry(?:\s*limit)?[:\s]*([\d.]+)", text, re.IGNORECASE)
    if match_entries:
        signal["entry"] = [float(x) for x in match_entries]

    return signal

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
        symbol = f"{signal['symbol']}USDT"
        side = signal['side'].upper()
        entry_price = signal['entry'][0]
        
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
        
        # Get account info to check available margin
        account_info = client.futures_account()
        available_balance = float(account_info['availableBalance'])
        
        if available_balance <= 0:
            print("Error: Insufficient available balance")
            return
        
        risk_per_trade = usdt_balance * RISK_PER_TRADE  # 5% risk
        stop_loss_pct = 0.01  # 1% stop loss
        
        # Calculate position size based on risk and leverage
        # Position value = (risk amount / stop loss %)
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
            # For LONG: if current price <= entry, market has moved in our favor
            if current_price <= entry_price:
                use_market_order = True
                print(f"✓ Market price ({current_price}) is below entry ({entry_price})")
                print(f"  Placing MARKET order to enter immediately")
            else:
                print(f"ℹ Market price ({current_price}) is above entry ({entry_price})")
                print(f"  Placing LIMIT order and waiting for price to come down")
        else:  # SHORT
            # For SHORT: if current price >= entry, market has moved in our favor
            if current_price >= entry_price:
                use_market_order = True
                print(f"✓ Market price ({current_price}) is above entry ({entry_price})")
                print(f"  Placing MARKET order to enter immediately")
            else:
                print(f"ℹ Market price ({current_price}) is below entry ({entry_price})")
                print(f"  Placing LIMIT order and waiting for price to come up")
        
        # Recalculate stop loss and take profit based on actual entry price
        actual_entry = current_price if use_market_order else entry_price
        stop_loss = actual_entry * (1 - stop_loss_pct) if side == "LONG" else actual_entry * (1 + stop_loss_pct)
        take_profit = actual_entry + (actual_entry - stop_loss) * RR_RATIO if side == "LONG" else actual_entry - (stop_loss - actual_entry) * RR_RATIO

        # --- Round values according to Binance rules ---
        stop_loss = round_step_size(stop_loss, tick_size)
        take_profit = round_step_size(take_profit, tick_size)
        qty = round_step_size(qty, step_size)
        
        if not use_market_order:
            entry_price = round_step_size(entry_price, tick_size)
        
        # Calculate required margin
        position_value = qty * entry_price
        required_margin = position_value / LEVERAGE
        
        # Check if we have enough available margin
        if required_margin > available_balance * 0.95:  # Leave 5% buffer
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
            
            # Check if it's the "would immediately trigger" error
            if "-2021" in error_msg or "immediately trigger" in error_msg:
                print(f"⚠ Stop loss price ({stop_loss}) would trigger immediately!")
                print(f"   Current market has likely moved past your stop loss.")
                print(f"   Consider adjusting your stop loss distance or skip this trade.")
            
            # Cancel entry order if SL fails
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
                # Check if order already filled
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
            if parsed["symbol"] and parsed["side"] and parsed["entry"]:
                print("Signal found:", parsed)
                place_trade(parsed)

    # Listen for new signals
    @tg.on(events.NewMessage(chats=entity))
    async def handler(event):
        if event.message.reply_to and event.message.reply_to.reply_to_msg_id == topic_id:
            parsed = extract_signal(event.message.text or "", event.message.date)
            if parsed["symbol"] and parsed["side"] and parsed["entry"]:
                print("NEW SIGNAL:", parsed)
                place_trade(parsed)

    print("Listening for new messages...\n")
    await tg.run_until_disconnected()

asyncio.run(main())