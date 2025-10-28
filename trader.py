from telethon import TelegramClient
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
import logging
import json
from binance.client import Client
from binance.enums import *
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_CONFIG = {
    'api_id': 23008284,
    'api_hash': '9b753f6de26369ddff1f498ce4d21fb5',
    'phone': '+94781440205',
    'group_id': -1001573488012,
    #'topic_id': 40011
}

BINANCE_CONFIG = {
    'api_key': '9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ',
    'api_secret': 'mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl'
}

TRADING_CONFIG = {
    'leverage': 10,
    'risk_percentage': 10,
    'fetch_interval': 300,  # 5 minutes
    'lookback_hours': 24,
    'max_open_positions': 5,  # Maximum 5 positions at once
    'max_total_risk': 50,  # Maximum 50% of account at risk
    'trailing_stop_enabled': True,
    'trailing_stop_activation': 20,  # Activate at 20% profit
    'trailing_stop_distance': 10,  # Trail 10% below peak
    'breakeven_at_profit': 15,  # Move SL to breakeven at 15% profit
    'position_sync_interval': 60  # Sync with Binance every 60 seconds
}

DEEPSEEK_CONFIG = {
    'api_key': 'sk-abaae5d245c64f899a1302208cc671b1',
    'base_url': 'https://api.deepseek.com/v1',
    'model': 'deepseek-chat'
}

EMAIL_CONFIG = {
    'enabled': True,
    'to_email': 'somapalagalagedara@gmail.com',
    'from_email': 'somapalagalagedara@gmail.com',
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'password': 'gmsq cxug zkhv jtik'
}

class MessageDatabase:
    def __init__(self, db_name='improved_trading_bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER UNIQUE NOT NULL,
                message_text TEXT NOT NULL,
                message_date TIMESTAMP NOT NULL,
                fetched_at TIMESTAMP NOT NULL,
                processed BOOLEAN NOT NULL DEFAULT 0,
                message_type TEXT,
                ai_analysis TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                current_stop_loss REAL,
                highest_price REAL,
                quantity REAL,
                leverage INTEGER,
                opened_at TIMESTAMP,
                closed_at TIMESTAMP,
                status TEXT NOT NULL,
                profit_percentage REAL,
                close_reason TEXT,
                source_message_id INTEGER,
                binance_order_id TEXT,
                last_synced_at TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS position_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER NOT NULL,
                update_type TEXT NOT NULL,
                old_value REAL,
                new_value REAL,
                profit_percentage REAL,
                note TEXT,
                updated_at TIMESTAMP NOT NULL,
                FOREIGN KEY (position_id) REFERENCES positions (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trading_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                details TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                timestamp TIMESTAMP NOT NULL
            )
        ''')
        
        self.conn.commit()
    
    def save_message(self, message_id, text, message_date):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO messages 
                (message_id, message_text, message_date, fetched_at)
                VALUES (?, ?, ?, ?)
            ''', (message_id, text, message_date, datetime.now(timezone.utc)))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def mark_message_processed(self, message_id, message_type, ai_analysis):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE messages 
            SET processed = 1, message_type = ?, ai_analysis = ?
            WHERE message_id = ?
        ''', (message_type, ai_analysis, message_id))
        self.conn.commit()
    
    def get_unprocessed_messages(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT message_id, message_text, message_date
            FROM messages 
            WHERE processed = 0
            ORDER BY message_date ASC
        ''')
        return cursor.fetchall()
    
    def save_position(self, symbol, entry, sl, tp, qty, leverage, message_id, order_id=None):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO positions 
            (symbol, entry_price, stop_loss, take_profit, current_stop_loss, highest_price,
             quantity, leverage, opened_at, status, source_message_id, binance_order_id, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
        ''', (symbol, entry, sl, tp, sl, entry, qty, leverage,
              datetime.now(timezone.utc), message_id, order_id, datetime.now(timezone.utc)))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_open_position(self, symbol):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM positions 
            WHERE symbol = ? AND status = 'open'
            ORDER BY opened_at DESC LIMIT 1
        ''', (symbol,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    def get_all_open_positions(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM positions 
            WHERE status = 'open'
            ORDER BY opened_at DESC
        ''')
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def count_open_positions(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'")
        return cursor.fetchone()[0]
    
    def update_position_status(self, position_id, status, profit_pct=None, close_reason=None):
        cursor = self.conn.cursor()
        if profit_pct is not None:
            cursor.execute('''
                UPDATE positions 
                SET status = ?, profit_percentage = ?, closed_at = ?, close_reason = ?
                WHERE id = ?
            ''', (status, profit_pct, datetime.now(timezone.utc), close_reason, position_id))
        else:
            cursor.execute('''
                UPDATE positions 
                SET status = ?, close_reason = ?
                WHERE id = ?
            ''', (status, close_reason, position_id))
        self.conn.commit()
    
    def update_position_stop_loss(self, position_id, new_sl, reason):
        cursor = self.conn.cursor()
        # Get old SL
        cursor.execute('SELECT current_stop_loss FROM positions WHERE id = ?', (position_id,))
        old_sl = cursor.fetchone()[0]
        
        # Update SL
        cursor.execute('''
            UPDATE positions 
            SET current_stop_loss = ?
            WHERE id = ?
        ''', (new_sl, position_id))
        
        # Log update
        cursor.execute('''
            INSERT INTO position_updates 
            (position_id, update_type, old_value, new_value, note, updated_at)
            VALUES (?, 'STOP_LOSS_MODIFIED', ?, ?, ?, ?)
        ''', (position_id, old_sl, new_sl, reason, datetime.now(timezone.utc)))
        
        self.conn.commit()
    
    def update_position_highest_price(self, position_id, price):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE positions 
            SET highest_price = ?, last_synced_at = ?
            WHERE id = ?
        ''', (price, datetime.now(timezone.utc), position_id))
        self.conn.commit()
    
    def log_trading_action(self, action_type, symbol, details, success, error_msg=None):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO trading_actions 
            (action_type, symbol, details, success, error_message, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (action_type, symbol, details, success, error_msg, datetime.now(timezone.utc)))
        self.conn.commit()

class AISignalExtractor:
    def __init__(self, api_key, base_url, model):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    def analyze_message(self, message_text):
        system_prompt = """You are a cryptocurrency trading signal analyzer. Analyze Telegram messages and extract trading signals or position updates.

Output MUST be valid JSON with one of these structures:

For NEW POSITION signals:
{
    "type": "NEW_POSITION",
    "signal": {
        "symbol": "SYMBOL",
        "entry_price": float,
        "entry_limit": float or null,
        "stop_loss": float,
        "take_profit": float or null,
        "position_type": "LONG" or "SHORT"
    }
}

For POSITION UPDATE messages:
{
    "type": "POSITION_UPDATE",
    "update": {
        "symbol": "SYMBOL",
        "action": "CLOSE_FULL" or "CLOSE_PARTIAL" or "MODIFY_ENTRY" or "CANCELLED" or "INFO",
        "profit_percentage": float or null,
        "new_entry": float or null,
        "partial_close_pct": float or null,
        "note": "any relevant information"
    }
}

For NON-TRADING messages:
{
    "type": "IGNORE",
    "reason": "explanation"
}

Rules:
1. Symbols should be uppercase without $ sign, append USDT (e.g., "ZORAUSDT")
2. Extract profit percentages from "SYMBOL + 56.1% profit" patterns
3. Messages with "cancel", "cancelled", or "missed" are UPDATE with action "CANCELLED"
4. Just profit updates are UPDATE with action "INFO"
5. Only return NEW_POSITION if message contains entry, SL, or TP prices
6. Return valid JSON only, no markdown"""

        user_prompt = f"Analyze this trading message:\n\n{message_text}"
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()
                
                # Clean markdown
                if content.startswith('```json'):
                    content = content[7:]
                if content.startswith('```'):
                    content = content[3:]
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()
                
                return json.loads(content)
            else:
                logger.error(f"DeepSeek API error: {response.status_code}")
                return {"type": "ERROR", "reason": f"API error: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Error calling DeepSeek API: {e}")
            return {"type": "ERROR", "reason": str(e)}

class BinanceTrader:
    def __init__(self, api_key, api_secret):
        self.client = Client(api_key, api_secret)
    
    def get_account_balance(self):
        try:
            balance = self.client.futures_account_balance()
            for b in balance:
                if b['asset'] == 'USDT':
                    return float(b['availableBalance'])
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
        return 0
    
    def get_current_price(self, symbol):
        """Get current market price"""
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None
    
    def get_position_info(self, symbol):
        """Get current position information from Binance"""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for pos in positions:
                if pos['symbol'] == symbol:
                    return {
                        'symbol': symbol,
                        'position_amt': float(pos['positionAmt']),
                        'entry_price': float(pos['entryPrice']),
                        'unrealized_pnl': float(pos['unRealizedProfit']),
                        'leverage': int(pos['leverage']),
                        'is_open': float(pos['positionAmt']) != 0
                    }
        except Exception as e:
            logger.error(f"Error getting position info: {e}")
        return None
    
    def set_leverage(self, symbol, leverage):
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"Set {leverage}x leverage for {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return False
    
    def calculate_position_size(self, balance, risk_pct, entry, sl):
        risk_amount = balance * (risk_pct / 100)
        risk_per_unit = abs(entry - sl)
        if risk_per_unit == 0:
            return 0
        quantity = risk_amount / risk_per_unit
        return quantity
    
    def get_symbol_precision(self, symbol):
        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    qty_precision = 0
                    price_precision = 0
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            step_size = float(f['stepSize'])
                            qty_precision = len(str(step_size).rstrip('0').split('.')[-1])
                        if f['filterType'] == 'PRICE_FILTER':
                            tick_size = float(f['tickSize'])
                            price_precision = len(str(tick_size).rstrip('0').split('.')[-1])
                    return qty_precision, price_precision
        except Exception as e:
            logger.error(f"Error getting precision: {e}")
        return 3, 2
    
    def modify_stop_loss(self, symbol, new_sl):
        """Modify stop loss for existing position"""
        try:
            # Get current position
            position = self.get_position_info(symbol)
            if not position or not position['is_open']:
                logger.warning(f"No open position for {symbol}")
                return False
            
            qty = abs(position['position_amt'])
            qty_precision, price_precision = self.get_symbol_precision(symbol)
            
            # Cancel existing stop loss orders
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            
            # Set new stop loss
            sl_order = self.client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=round(new_sl, price_precision),
                quantity=round(qty, qty_precision),
                closePosition=True
            )
            
            logger.info(f"✅ Modified SL for {symbol} to {new_sl}")
            return True
            
        except Exception as e:
            logger.error(f"Error modifying SL: {e}")
            return False
    
    def open_long_position(self, signal, leverage, risk_pct):
        try:
            symbol = signal['symbol']
            entry = signal['entry_price']
            sl = signal['stop_loss']
            tp = signal.get('take_profit')
            
            if not self.set_leverage(symbol, leverage):
                return None
            
            balance = self.get_account_balance()
            logger.info(f"Account balance: {balance} USDT")
            
            qty = self.calculate_position_size(balance, risk_pct, entry, sl)
            qty_precision, price_precision = self.get_symbol_precision(symbol)
            qty = round(qty, qty_precision)
            
            if qty <= 0:
                logger.error(f"Invalid quantity: {qty}")
                return None
            
            logger.info(f"Opening LONG {symbol}: qty={qty}, entry={entry}, sl={sl}, tp={tp}")
            
            # Place market order
            order = self.client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=qty
            )
            
            logger.info(f"✅ Market order executed: {order['orderId']}")
            
            # Set stop loss
            try:
                sl_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    type=FUTURE_ORDER_TYPE_STOP_MARKET,
                    stopPrice=round(sl, price_precision),
                    quantity=qty,
                    closePosition=True
                )
                logger.info(f"✅ Stop loss set: {sl_order['orderId']}")
            except Exception as e:
                logger.error(f"⚠️ Failed to set SL: {e}")
            
            # Set take profit if provided
            if tp:
                try:
                    tp_order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                        stopPrice=round(tp, price_precision),
                        quantity=qty,
                        closePosition=True
                    )
                    logger.info(f"✅ Take profit set: {tp_order['orderId']}")
                except Exception as e:
                    logger.error(f"⚠️ Failed to set TP: {e}")
            
            return {
                'symbol': symbol,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'quantity': qty,
                'order_id': order['orderId']
            }
            
        except Exception as e:
            logger.error(f"❌ Error opening position: {e}")
            return None
    
    def close_position(self, symbol, partial_pct=None):
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            
            for pos in positions:
                if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                    total_qty = abs(float(pos['positionAmt']))
                    
                    if partial_pct:
                        qty = round(total_qty * (partial_pct / 100), 8)
                        logger.info(f"Closing {partial_pct}% of {symbol}: {qty} units")
                    else:
                        qty = total_qty
                        logger.info(f"Closing full position {symbol}: {qty} units")
                        self.client.futures_cancel_all_open_orders(symbol=symbol)
                    
                    order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=ORDER_TYPE_MARKET,
                        quantity=qty
                    )
                    
                    logger.info(f"✅ Position closed: {order['orderId']}")
                    return True
            
            logger.warning(f"No open position found for {symbol}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error closing position: {e}")
            return False

class ImprovedAITradingBot:
    def __init__(self):
        self.telegram_client = TelegramClient(
            'my_session.session',
            TELEGRAM_CONFIG['api_id'],
            TELEGRAM_CONFIG['api_hash']
        )
        self.db = MessageDatabase()
        self.trader = BinanceTrader(
            BINANCE_CONFIG['api_key'],
            BINANCE_CONFIG['api_secret']
        )
        self.ai = AISignalExtractor(
            DEEPSEEK_CONFIG['api_key'],
            DEEPSEEK_CONFIG['base_url'],
            DEEPSEEK_CONFIG['model']
        )
    
    def send_email_notification(self, subject, message):
        if not EMAIL_CONFIG['enabled']:
            return
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = EMAIL_CONFIG['from_email']
            msg['To'] = EMAIL_CONFIG['to_email']
            msg['Subject'] = subject
            
            text_message = message.replace('<b>', '').replace('</b>', '')
            text_part = MIMEText(text_message, 'plain')
            html_part = MIMEText(message.replace('\n', '<br>'), 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
                server.starttls()
                server.login(EMAIL_CONFIG['from_email'], EMAIL_CONFIG['password'])
                server.send_message(msg)
            
            logger.info(f"📧 Email sent: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    def can_open_new_position(self):
        """Check if we can open a new position based on risk limits"""
        open_count = self.db.count_open_positions()
        total_risk = open_count * TRADING_CONFIG['risk_percentage']
        
        if open_count >= TRADING_CONFIG['max_open_positions']:
            logger.warning(f"⚠️ Max positions reached: {open_count}/{TRADING_CONFIG['max_open_positions']}")
            return False
        
        if total_risk >= TRADING_CONFIG['max_total_risk']:
            logger.warning(f"⚠️ Max total risk reached: {total_risk}%/{TRADING_CONFIG['max_total_risk']}%")
            return False
        
        return True
    
    async def sync_positions_with_binance(self):
        """CRITICAL: Sync database positions with actual Binance positions"""
        open_positions = self.db.get_all_open_positions()
        
        for position in open_positions:
            try:
                symbol = position['symbol']
                
                # Get actual position from Binance
                binance_position = self.trader.get_position_info(symbol)
                
                if not binance_position:
                    continue
                
                # Check if position is actually closed on Binance
                if not binance_position['is_open']:
                    # Position closed on Binance but still open in DB
                    entry = position['entry_price']
                    final_price = binance_position['entry_price'] if binance_position['entry_price'] != 0 else entry
                    profit_pct = ((final_price - entry) / entry) * 100 if entry != 0 else 0
                    
                    self.db.update_position_status(
                        position['id'],
                        'closed',
                        profit_pct,
                        'Closed on Binance (SL/TP hit)'
                    )
                    
                    logger.info(f"🔄 Synced: {symbol} was closed on Binance (Profit: {profit_pct:.2f}%)")
                    
                    # Send notification
                    profit_emoji = "🟢" if profit_pct > 0 else "🔴"
                    notification = f"""
{profit_emoji} <b>POSITION AUTO-CLOSED (SL/TP)</b>

<b>Symbol:</b> {symbol}
<b>Profit:</b> {profit_pct:+.2f}%
<b>Reason:</b> Stop Loss or Take Profit hit on Binance

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                    self.send_email_notification(
                        f"{profit_emoji} Auto-Closed - {symbol}",
                        notification
                    )
                    
                    self.db.log_trading_action(
                        'POSITION_SYNC',
                        symbol,
                        f"Synced closed position: {profit_pct:.2f}%",
                        True
                    )
                
            except Exception as e:
                logger.error(f"Error syncing position {position['symbol']}: {e}")
    
    async def manage_trailing_stops(self):
        """Manage trailing stop losses for open positions"""
        if not TRADING_CONFIG['trailing_stop_enabled']:
            return
        
        open_positions = self.db.get_all_open_positions()
        
        for position in open_positions:
            try:
                symbol = position['symbol']
                entry = position['entry_price']
                current_sl = position['current_stop_loss']
                highest_price = position['highest_price']
                
                # Get current price
                current_price = self.trader.get_current_price(symbol)
                if not current_price:
                    continue
                
                # Update highest price if current is higher
                if current_price > highest_price:
                    self.db.update_position_highest_price(position['id'], current_price)
                    highest_price = current_price
                
                # Calculate profit percentage
                profit_pct = ((current_price - entry) / entry) * 100
                
                # Move SL to breakeven at configured profit level
                if (profit_pct >= TRADING_CONFIG['breakeven_at_profit'] and 
                    current_sl < entry):
                    
                    logger.info(f"📈 {symbol}: Moving SL to breakeven (Profit: {profit_pct:.2f}%)")
                    
                    if self.trader.modify_stop_loss(symbol, entry):
                        self.db.update_position_stop_loss(
                            position['id'],
                            entry,
                            f"Moved to breakeven at {profit_pct:.2f}% profit"
                        )
                        
                        notification = f"""
🛡️ <b>STOP LOSS MOVED TO BREAKEVEN</b>

<b>Symbol:</b> {symbol}
<b>Current Profit:</b> {profit_pct:+.2f}%
<b>New SL:</b> ${entry:.4f} (Breakeven)
<b>Risk Protected:</b> Position now risk-free!

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                        self.send_email_notification(
                            f"🛡️ SL→Breakeven - {symbol}",
                            notification
                        )
                
                # Activate trailing stop
                elif profit_pct >= TRADING_CONFIG['trailing_stop_activation']:
                    trail_distance = TRADING_CONFIG['trailing_stop_distance']
                    new_sl = highest_price * (1 - trail_distance / 100)
                    
                    # Only update if new SL is higher than current
                    if new_sl > current_sl:
                        logger.info(f"📈 {symbol}: Trailing SL from ${current_sl:.4f} to ${new_sl:.4f}")
                        
                        if self.trader.modify_stop_loss(symbol, new_sl):
                            self.db.update_position_stop_loss(
                                position['id'],
                                new_sl,
                                f"Trailing stop: {trail_distance}% from peak ${highest_price:.4f}"
                            )
                            
                            logger.info(f"✅ Trailing SL updated for {symbol}")
                
            except Exception as e:
                logger.error(f"Error managing trailing stop for {position['symbol']}: {e}")
    
    async def fetch_messages(self):
        messages = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=TRADING_CONFIG['lookback_hours'])
        
        async for message in self.telegram_client.iter_messages(
            TELEGRAM_CONFIG['group_id'],
            #reply_to=TELEGRAM_CONFIG['topic_id'],
            limit=None
        ):
            if message.date < cutoff_time:
                break
            
            if message.text:
                self.db.save_message(message.id, message.text, message.date)
                messages.append({
                    'id': message.id,
                    'text': message.text,
                    'date': message.date
                })
        
        return messages
    
    async def process_new_position(self, signal, message_id):
        symbol = signal['signal']['symbol']
        
        logger.info(f"🆕 NEW POSITION SIGNAL: {symbol}")
        logger.info(f"   Entry: {signal['signal']['entry_price']}")
        logger.info(f"   SL: {signal['signal']['stop_loss']}")
        logger.info(f"   TP: {signal['signal'].get('take_profit', 'N/A')}")
        
        # Check if position already exists
        existing_position = self.db.get_open_position(symbol)
        if existing_position:
            logger.warning(f"⚠️ Position already open for {symbol}, skipping")
            self.db.log_trading_action('SKIP', symbol, 'Position already open', False)
            return
        
        # Check risk limits
        if not self.can_open_new_position():
            logger.warning(f"⚠️ Cannot open {symbol}: Risk limits reached")
            self.db.log_trading_action('SKIP', symbol, 'Risk limits reached', False)
            return
        
        # Open position
        result = self.trader.open_long_position(
            signal['signal'],
            TRADING_CONFIG['leverage'],
            TRADING_CONFIG['risk_percentage']
        )
        
        if result:
            self.db.save_position(
                symbol=result['symbol'],
                entry=result['entry'],
                sl=result['sl'],
                tp=result['tp'],
                qty=result['quantity'],
                leverage=TRADING_CONFIG['leverage'],
                message_id=message_id,
                order_id=result['order_id']
            )
            
            self.db.log_trading_action(
                'OPEN_POSITION',
                symbol,
                json.dumps(result),
                True
            )
            
            notification = f"""
🟢 <b>POSITION OPENED BY AI</b>

<b>Symbol:</b> {symbol}
<b>Type:</b> LONG
<b>Leverage:</b> {TRADING_CONFIG['leverage']}x
<b>Entry Price:</b> ${result['entry']:.4f}
<b>Stop Loss:</b> ${result['sl']:.4f}
<b>Take Profit:</b> ${result.get('tp', 'N/A')}
<b>Quantity:</b> {result['quantity']:.4f}
<b>Order ID:</b> {result['order_id']}
<b>Risk:</b> {TRADING_CONFIG['risk_percentage']}%

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            self.send_email_notification(f"🟢 AI Opened Position - {symbol}", notification)
            logger.info(f"✅ Position opened successfully: {symbol}")
        else:
            self.db.log_trading_action(
                'OPEN_POSITION',
                symbol,
                'Failed to open position',
                False,
                'See logs for details'
            )
            logger.error(f"❌ Failed to open position: {symbol}")
    
    async def process_position_update(self, update_info, message_id):
        symbol = update_info['update']['symbol']
        action = update_info['update']['action']
        profit_pct = update_info['update'].get('profit_percentage')
        
        logger.info(f"📊 POSITION UPDATE: {symbol}")
        logger.info(f"   Action: {action}")
        logger.info(f"   Profit: {profit_pct}%" if profit_pct else "   Profit: N/A")
        
        position = self.db.get_open_position(symbol)
        
        if not position and action not in ['CANCELLED', 'INFO']:
            logger.warning(f"⚠️ No open position found for {symbol}")
            self.db.log_trading_action('UPDATE_POSITION', symbol, 'No position found', False)
            return
        
        if action == 'CLOSE_FULL':
            success = self.trader.close_position(symbol)
            if success and position:
                self.db.update_position_status(position['id'], 'closed', profit_pct, 'Closed by AI signal')
                self.db.log_trading_action('CLOSE_FULL', symbol, f"Profit: {profit_pct}%", True)
                
                profit_emoji = "🟢" if profit_pct > 0 else "🔴"
                status = 'WIN' if profit_pct > 0 else 'LOSS'
                notification = f"""
{profit_emoji} <b>POSITION CLOSED BY AI</b>

<b>Symbol:</b> {symbol}
<b>Profit:</b> {profit_pct:+.2f}%
<b>Status:</b> {'✅ WIN' if profit_pct > 0 else '❌ LOSS'}
<b>Action:</b> Full Close

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                self.send_email_notification(f"{profit_emoji} AI Closed Position - {symbol} ({status})", notification)
                logger.info(f"✅ Position closed: {symbol} with {profit_pct}% profit")
        
        elif action == 'CLOSE_PARTIAL':
            partial_pct = update_info['update'].get('partial_close_pct', 50)
            success = self.trader.close_position(symbol, partial_pct)
            if success and position:
                self.db.log_trading_action('CLOSE_PARTIAL', symbol, f"Closed {partial_pct}%", True)
                logger.info(f"✅ Partial close: {symbol} - {partial_pct}%")
        
        elif action == 'CANCELLED':
            if position:
                self.trader.close_position(symbol)
                self.db.update_position_status(position['id'], 'cancelled', 0, 'Cancelled by signal')
            self.db.log_trading_action('CANCEL', symbol, update_info['update'].get('note', ''), True)
            logger.info(f"🚫 Position cancelled: {symbol}")
        
        elif action == 'INFO':
            if position:
                logger.info(f"ℹ️ Info update: {symbol} - {update_info['update'].get('note', '')}")
    
    async def process_messages(self):
        logger.info("="*80)
        logger.info(f"🔄 Starting message processing at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info("="*80)
        
        await self.fetch_messages()
        unprocessed = self.db.get_unprocessed_messages()
        
        if not unprocessed:
            logger.info("✓ No new messages to process")
            return
        
        logger.info(f"📬 Found {len(unprocessed)} unprocessed messages")
        
        for msg_id, msg_text, msg_date in unprocessed:
            logger.info(f"\n{'='*80}")
            logger.info(f"🔍 Analyzing message {msg_id} from {msg_date}")
            logger.info(f"📝 Content: {msg_text[:100]}...")
            
            analysis = self.ai.analyze_message(msg_text)
            logger.info(f"🤖 AI Analysis: {analysis['type']}")
            
            if analysis['type'] == 'NEW_POSITION':
                await self.process_new_position(analysis, msg_id)
            elif analysis['type'] == 'POSITION_UPDATE':
                await self.process_position_update(analysis, msg_id)
            elif analysis['type'] == 'IGNORE':
                logger.info(f"⏭️ Ignored: {analysis.get('reason', 'Not a trading message')}")
            elif analysis['type'] == 'ERROR':
                logger.error(f"⚠️ AI Error: {analysis.get('reason', 'Unknown error')}")
            
            self.db.mark_message_processed(msg_id, analysis['type'], json.dumps(analysis))
            await asyncio.sleep(0.5)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ Processing complete - {len(unprocessed)} messages processed")
        logger.info("="*80)
    
    async def position_sync_loop(self):
        """Background task to sync positions"""
        while True:
            try:
                await self.sync_positions_with_binance()
                await self.manage_trailing_stops()
            except Exception as e:
                logger.error(f"Error in position sync loop: {e}")
            
            await asyncio.sleep(TRADING_CONFIG['position_sync_interval'])
    
    async def run(self):
        await self.telegram_client.start(phone=TELEGRAM_CONFIG['phone'])
        logger.info("🚀 Improved AI Trading Bot started successfully")
        
        print("\n" + "="*80)
        print("🤖 IMPROVED AI-POWERED TRADING BOT")
        print("="*80)
        print(f"📍 Group ID: {TELEGRAM_CONFIG['group_id']}")
        #print(f"📍 Topic ID: {TELEGRAM_CONFIG['topic_id']}")
        print(f"⏰ Message Check: Every {TRADING_CONFIG['fetch_interval']} seconds")
        print(f"🔄 Position Sync: Every {TRADING_CONFIG['position_sync_interval']} seconds")
        print(f"💰 Risk per trade: {TRADING_CONFIG['risk_percentage']}%")
        print(f"📊 Leverage: {TRADING_CONFIG['leverage']}x")
        print(f"🛡️ Max Positions: {TRADING_CONFIG['max_open_positions']}")
        print(f"📈 Trailing Stop: {'Enabled' if TRADING_CONFIG['trailing_stop_enabled'] else 'Disabled'}")
        print("="*80 + "\n")
        
        # Start position sync loop in background
        asyncio.create_task(self.position_sync_loop())
        
        iteration = 0
        while True:
            try:
                iteration += 1
                logger.info(f"\n{'#'*80}")
                logger.info(f"ITERATION #{iteration}")
                logger.info(f"{'#'*80}\n")
                
                await self.process_messages()
                
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
            
            logger.info(f"\n⏳ Sleeping for {TRADING_CONFIG['fetch_interval']} seconds...\n")
            await asyncio.sleep(TRADING_CONFIG['fetch_interval'])

async def main():
    bot = ImprovedAITradingBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("\n\n👋 Bot stopped by user")

if __name__ == '__main__':
    asyncio.run(main())