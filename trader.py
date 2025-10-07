from telethon import TelegramClient
import asyncio
import re
from datetime import datetime, timedelta, timezone
import sqlite3
from binance.client import Client
from binance.enums import *
import logging
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
    'group_id': -1002039861131,
    'topic_id': 40011
}

BINANCE_CONFIG = {
    'api_key': '9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ',
    'api_secret': 'mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl'
}

TRADING_CONFIG = {
    'leverage': 10,
    'risk_percentage': 10,  # 10% of account
    'fetch_interval': 60,  # 1 minute
    'message_lookback': 5  # 5 minutes
}

EMAIL_CONFIG = {
    'enabled': True,
    'to_email': 'somapalagalagedara@gmail.com',
    'from_email': 'somapalagalagedara@gmail.com',  # Gmail account to send from
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'password': 'gmsq cxug zkhv jtik',  # Add your Gmail app password here (not regular password)
    'send_signals': True  # Send signal detection notifications
}

class TradingDatabase:
    def __init__(self, db_name='trading_bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                quantity REAL NOT NULL,
                leverage INTEGER NOT NULL,
                opened_at TIMESTAMP NOT NULL,
                closed_at TIMESTAMP,
                profit_percentage REAL,
                status TEXT NOT NULL,
                signal_time TIMESTAMP NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_hash TEXT UNIQUE NOT NULL,
                processed_at TIMESTAMP NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detected_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_hash TEXT UNIQUE NOT NULL,
                signal_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                profit_percentage REAL,
                detected_at TIMESTAMP NOT NULL,
                message_text TEXT NOT NULL,
                status TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        ''')
        self.conn.commit()
    
    def is_position_open(self, symbol):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM positions 
            WHERE symbol = ? AND status = 'open'
        ''', (symbol,))
        return cursor.fetchone()[0] > 0
    
    def add_position(self, symbol, entry, sl, tp, qty, leverage, signal_time):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO positions 
            (symbol, entry_price, stop_loss, take_profit, quantity, leverage, 
             opened_at, status, signal_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
        ''', (symbol, entry, sl, tp, qty, leverage, datetime.now(timezone.utc), signal_time))
        self.conn.commit()
        return cursor.lastrowid
    
    def close_position(self, symbol, profit_pct):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE positions 
            SET status = 'closed', closed_at = ?, profit_percentage = ?
            WHERE symbol = ? AND status = 'open'
        ''', (datetime.now(timezone.utc), profit_pct, symbol))
        self.conn.commit()
    
    def is_signal_processed(self, signal_hash):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM processed_signals 
            WHERE signal_hash = ?
        ''', (signal_hash,))
        return cursor.fetchone()[0] > 0
    
    def mark_signal_processed(self, signal_hash):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO processed_signals (signal_hash, processed_at)
            VALUES (?, ?)
        ''', (signal_hash, datetime.now(timezone.utc)))
        self.conn.commit()
    
    def save_detected_signal(self, signal, signal_hash, message_text, status='pending'):
        """Save a detected signal to the database"""
        cursor = self.conn.cursor()
        if signal['type'] == 'LONG':
            cursor.execute('''
                INSERT OR IGNORE INTO detected_signals 
                (signal_hash, signal_type, symbol, entry_price, stop_loss, take_profit, 
                 detected_at, message_text, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (signal_hash, signal['type'], signal['symbol'], signal['entry_price'],
                  signal['stop_loss'], signal['take_profit'], datetime.now(timezone.utc),
                  message_text, status))
        else:  # CLOSE
            cursor.execute('''
                INSERT OR IGNORE INTO detected_signals 
                (signal_hash, signal_type, symbol, profit_percentage, 
                 detected_at, message_text, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (signal_hash, signal['type'], signal['symbol'], 
                  signal.get('profit_percentage', 0), datetime.now(timezone.utc),
                  message_text, status))
        self.conn.commit()
    
    def is_signal_detected(self, signal_hash):
        """Check if signal was already detected"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM detected_signals 
            WHERE signal_hash = ?
        ''', (signal_hash,))
        return cursor.fetchone()[0] > 0
    
    def update_signal_status(self, signal_hash, status):
        """Update status of a detected signal"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE detected_signals 
            SET status = ?
            WHERE signal_hash = ?
        ''', (status, signal_hash))
        self.conn.commit()
    
    def get_setting(self, key, default=None):
        """Get a setting value"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        return result[0] if result else default
    
    def set_setting(self, key, value):
        """Set a setting value"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now(timezone.utc)))
        self.conn.commit()
    
    def is_first_run_today(self):
        """Check if this is the first run of the current day"""
        last_run = self.get_setting('last_run_date')
        today = datetime.now(timezone.utc).date().isoformat()
        return last_run != today
    
    def mark_run_completed(self):
        """Mark that a run has been completed for today"""
        today = datetime.now(timezone.utc).date().isoformat()
        self.set_setting('last_run_date', today)
        self.set_setting('initial_setup_done', 'true')

class SignalExtractor:
    @staticmethod
    def extract_long_signal(text):
        """Extract LONG signal details from message"""
        text_upper = text.upper()
        
        # Check if it's a LONG signal
        if 'LONG' not in text_upper:
            return None
        
        # Extract symbol (patterns: LONG - $API3, LONG - **$API3, **LONG - **$API3, etc.)
        symbol_pattern = r'LONG\s*-\s*\*{0,2}\s*\$([A-Z0-9]{2,15})'
        symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            # Try alternative pattern without dash
            symbol_pattern = r'LONG\s*\*{0,2}\s*\$([A-Z0-9]{2,15})'
            symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            return None
        
        symbol = symbol_match.group(1)
        
        # Extract entry price (handle multiple formats)
        # Format: - Entry: 0.8571 or - Entry: 1.836 (30% VOL)
        entry_pattern = r'-\s*ENTRY(?:\s*LIMIT)?[:\s]*(\d+\.?\d*)'
        entry_match = re.search(entry_pattern, text_upper)
        if not entry_match:
            return None
        
        entry_price = float(entry_match.group(1))
        
        # Extract stop loss
        # Format: - SL: 0.8030
        sl_pattern = r'-\s*SL[:\s]*(\d+\.?\d*)'
        sl_match = re.search(sl_pattern, text_upper)
        if not sl_match:
            return None
        
        stop_loss = float(sl_match.group(1))
        
        # Extract take profit
        # Format: 🎯 TP: 1.5278
        tp_pattern = r'(?:🎯|TARGET)?\s*TP[:\s]*(\d+\.?\d*)'
        tp_match = re.search(tp_pattern, text_upper)
        if not tp_match:
            return None
        
        take_profit = float(tp_match.group(1))
        
        return {
            'type': 'LONG',
            'symbol': symbol + 'USDT',  # Convert to Binance format
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    @staticmethod
    def extract_close_signal(text):
        """Extract CLOSE signal details from message"""
        text_upper = text.upper()
        
        # Check if it contains profit update keywords
        # Patterns: "API3 + 27.1% profit", "MUBARAK + 357% profit, close"
        if not ('+' in text and '%' in text and 'PROFIT' in text_upper):
            return None
        
        # Extract symbol - pattern: SYMBOL + percentage% profit
        # Look for word before the + sign
        symbol_pattern = r'([A-Z0-9]{2,15})\s*\+'
        symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            return None
        
        symbol = symbol_match.group(1)
        
        # Extract profit percentage
        profit_pattern = r'\+\s*(\d+\.?\d*)\s*%'
        profit_match = re.search(profit_pattern, text)
        
        profit_pct = float(profit_match.group(1)) if profit_match else 0
        
        # Only treat as CLOSE signal if it explicitly mentions "close" in the message
        if 'CLOSE' not in text_upper:
            # This is just a profit update, not a close signal
            return None
        
        return {
            'type': 'CLOSE',
            'symbol': symbol + 'USDT',
            'profit_percentage': profit_pct
        }

class BinanceTrader:
    def __init__(self, api_key, api_secret):
        self.client = Client(api_key, api_secret)
        
    def get_account_balance(self):
        """Get USDT balance for futures account"""
        balance = self.client.futures_account_balance()
        for b in balance:
            if b['asset'] == 'USDT':
                return float(b['availableBalance'])
        return 0
    
    def set_leverage(self, symbol, leverage):
        """Set leverage for symbol"""
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"Set {leverage}x leverage for {symbol}")
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
    
    def calculate_position_size(self, balance, risk_pct, entry, sl):
        """Calculate position size based on risk"""
        risk_amount = balance * (risk_pct / 100)
        risk_per_unit = abs(entry - sl)
        if risk_per_unit == 0:
            return 0
        quantity = risk_amount / risk_per_unit
        return quantity
    
    def get_symbol_precision(self, symbol):
        """Get quantity and price precision for symbol"""
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
        return 3, 2  # Default precision
    
    def open_long_position(self, signal, leverage, risk_pct):
        """Open a LONG position on Binance"""
        try:
            symbol = signal['symbol']
            entry = signal['entry_price']
            sl = signal['stop_loss']
            tp = signal['take_profit']
            
            # Set leverage
            self.set_leverage(symbol, leverage)
            
            # Get account balance
            balance = self.get_account_balance()
            logger.info(f"Account balance: {balance} USDT")
            
            # Calculate position size
            qty = self.calculate_position_size(balance, risk_pct, entry, sl)
            
            # Get precision
            qty_precision, price_precision = self.get_symbol_precision(symbol)
            qty = round(qty, qty_precision)
            
            if qty <= 0:
                logger.error(f"Invalid quantity calculated: {qty}")
                return None
            
            logger.info(f"Opening LONG {symbol}: qty={qty}, entry={entry}, sl={sl}, tp={tp}")
            
            # Place market order
            order = self.client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=qty
            )
            
            logger.info(f"Market order executed: {order}")
            
            # Try to set stop loss
            try:
                sl_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    type=FUTURE_ORDER_TYPE_STOP_MARKET,
                    stopPrice=round(sl, price_precision),
                    quantity=qty,
                    closePosition=True
                )
                logger.info(f"Stop loss set: {sl_order}")
            except Exception as e:
                logger.error(f"Failed to set SL from signal, calculating 1:1 RR: {e}")
                # Calculate 1:1 RR stop loss
                risk = abs(entry - sl)
                new_sl = entry - risk
                try:
                    sl_order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=FUTURE_ORDER_TYPE_STOP_MARKET,
                        stopPrice=round(new_sl, price_precision),
                        quantity=qty,
                        closePosition=True
                    )
                    sl = new_sl
                    logger.info(f"Stop loss set with 1:1 RR: {sl_order}")
                except Exception as e2:
                    logger.error(f"Failed to set SL even with 1:1 RR: {e2}")
            
            # Try to set take profit
            try:
                tp_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                    stopPrice=round(tp, price_precision),
                    quantity=qty,
                    closePosition=True
                )
                logger.info(f"Take profit set: {tp_order}")
            except Exception as e:
                logger.error(f"Failed to set TP from signal, calculating 1:1 RR: {e}")
                # Calculate 1:1 RR take profit
                risk = abs(entry - sl)
                new_tp = entry + risk
                try:
                    tp_order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                        stopPrice=round(new_tp, price_precision),
                        quantity=qty,
                        closePosition=True
                    )
                    tp = new_tp
                    logger.info(f"Take profit set with 1:1 RR: {tp_order}")
                except Exception as e2:
                    logger.error(f"Failed to set TP even with 1:1 RR: {e2}")
            
            return {
                'symbol': symbol,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'quantity': qty
            }
            
        except Exception as e:
            logger.error(f"Error opening position: {e}")
            return None
    
    def close_position(self, symbol):
        """Close a position on Binance"""
        try:
            # Get current position
            positions = self.client.futures_position_information(symbol=symbol)
            
            for pos in positions:
                if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                    qty = abs(float(pos['positionAmt']))
                    
                    # Cancel all open orders for this symbol
                    self.client.futures_cancel_all_open_orders(symbol=symbol)
                    
                    # Close position with market order
                    order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=ORDER_TYPE_MARKET,
                        quantity=qty
                    )
                    
                    logger.info(f"Position closed: {order}")
                    return True
            
            logger.info(f"No open position found for {symbol}")
            return False
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False

class TradingBot:
    def __init__(self):
        self.telegram_client = TelegramClient(
            'trading_bot_session',
            TELEGRAM_CONFIG['api_id'],
            TELEGRAM_CONFIG['api_hash']
        )
        self.db = TradingDatabase()
        self.trader = BinanceTrader(
            BINANCE_CONFIG['api_key'],
            BINANCE_CONFIG['api_secret']
        )
        self.extractor = SignalExtractor()
    
    def send_email_notification(self, subject, message):
        """Send notification via email"""
        if not EMAIL_CONFIG['enabled']:
            return
        
        if not EMAIL_CONFIG['password']:
            logger.warning("Email password not configured. Skipping email notification.")
            return
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = EMAIL_CONFIG['from_email']
            msg['To'] = EMAIL_CONFIG['to_email']
            msg['Subject'] = subject
            
            # Convert HTML-like formatting to plain text
            text_message = message.replace('<b>', '').replace('</b>', '')
            
            # Create both plain text and HTML versions
            text_part = MIMEText(text_message, 'plain')
            html_part = MIMEText(message.replace('\n', '<br>'), 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Connect to Gmail SMTP server
            with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
                server.starttls()
                server.login(EMAIL_CONFIG['from_email'], EMAIL_CONFIG['password'])
                server.send_message(msg)
            
            logger.info(f"Email notification sent: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
    async def fetch_recent_messages(self):
        """Fetch all messages from the start of current day"""
        messages = []
        
        # Always fetch all messages from start of current day
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_time = today_start
        logger.info(f"Fetching all messages from {cutoff_time} (start of today)")
        
        async for message in self.telegram_client.iter_messages(
            TELEGRAM_CONFIG['group_id'],
            reply_to=TELEGRAM_CONFIG['topic_id'],
            limit=None
        ):
            if message.date < cutoff_time:
                break
            if message.text:
                messages.append({
                    'text': message.text,
                    'date': message.date
                })
        
        return messages
    
    def generate_signal_hash(self, signal, message_date):
        """Generate unique hash for signal to prevent reprocessing"""
        signal_str = f"{signal['type']}_{signal['symbol']}_{message_date}"
        return hash(signal_str)
    
    async def review_signal_interactive(self, signal, message_text, signal_hash):
        """Interactive review for first run - ask user to skip or process"""
        print("\n" + "="*60)
        print(f"📊 NEW SIGNAL DETECTED")
        print("="*60)
        print(f"Type: {signal['type']}")
        print(f"Symbol: {signal['symbol']}")
        
        if signal['type'] == 'LONG':
            print(f"Entry: ${signal['entry_price']:.4f}")
            print(f"Stop Loss: ${signal['stop_loss']:.4f}")
            print(f"Take Profit: ${signal['take_profit']:.4f}")
        else:
            print(f"Profit: {signal.get('profit_percentage', 0):+.2f}%")
        
        print(f"\nOriginal Message:\n{message_text}")
        print("="*60)
        
        while True:
            response = input("\nDo you want to process this signal? (y/n/q to quit): ").lower().strip()
            if response in ['y', 'n', 'q']:
                return response
            print("Invalid input. Please enter 'y' for yes, 'n' for no, or 'q' to quit.")
    
    async def process_messages(self, is_first_run=False):
        """Process messages and execute trades"""
        messages = await self.fetch_recent_messages()
        logger.info(f"Fetched {len(messages)} messages from today")
        
        if is_first_run:
            print(f"\n🔍 INITIAL SETUP MODE - Found {len(messages)} messages from today")
            print("You will be asked to review each signal individually.\n")
        
        for msg in reversed(messages):  # Process oldest first
            text = msg['text']
            msg_date = msg['date']
            
            # Try to extract LONG signal
            long_signal = self.extractor.extract_long_signal(text)
            if long_signal:
                signal_hash = self.generate_signal_hash(long_signal, msg_date)
                
                # Save detected signal to database
                if not self.db.is_signal_detected(signal_hash):
                    self.db.save_detected_signal(long_signal, signal_hash, text, 'detected')
                
                # Check if already processed
                if self.db.is_signal_processed(signal_hash):
                    logger.info(f"Signal already processed: {long_signal['symbol']}")
                    continue
                
                # Check if position already open
                if self.db.is_position_open(long_signal['symbol']):
                    logger.info(f"Position already open for {long_signal['symbol']}")
                    self.db.mark_signal_processed(signal_hash)
                    self.db.update_signal_status(signal_hash, 'skipped-position-open')
                    continue
                
                # If first run, ask user to review
                if is_first_run:
                    response = await self.review_signal_interactive(long_signal, text, signal_hash)
                    
                    if response == 'q':
                        print("\n⚠️  Exiting initial setup. Run the bot again to continue.")
                        return False  # Signal to stop
                    
                    if response == 'n':
                        logger.info(f"User skipped signal: {long_signal['symbol']}")
                        self.db.mark_signal_processed(signal_hash)
                        self.db.update_signal_status(signal_hash, 'skipped-by-user')
                        continue
                    
                    print(f"\n✅ Processing signal for {long_signal['symbol']}...")
                
                logger.info(f"New LONG signal detected: {long_signal}")
                
                # Execute trade
                try:
                    result = self.trader.open_long_position(
                        long_signal,
                        TRADING_CONFIG['leverage'],
                        TRADING_CONFIG['risk_percentage']
                    )
                except Exception as trade_error:
                    error_msg = f"""
🔴 <b>ERROR OPENING POSITION</b>

<b>Symbol:</b> {long_signal['symbol']}
<b>Error:</b> {str(trade_error)}
<b>Signal Details:</b>
- Entry: ${long_signal['entry_price']:.4f}
- Stop Loss: ${long_signal['stop_loss']:.4f}
- Take Profit: ${long_signal['take_profit']:.4f}

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                    self.send_email_notification(f"🔴 Error Opening Position - {long_signal['symbol']}", error_msg)
                    logger.error(f"Error opening position for {long_signal['symbol']}: {trade_error}")
                    self.db.update_signal_status(signal_hash, 'error')
                    result = None
                
                if result:
                    # Save to database
                    self.db.add_position(
                        result['symbol'],
                        result['entry'],
                        result['sl'],
                        result['tp'],
                        result['quantity'],
                        TRADING_CONFIG['leverage'],
                        msg_date
                    )
                    self.db.mark_signal_processed(signal_hash)
                    self.db.update_signal_status(signal_hash, 'executed')
                    logger.info(f"Position opened and logged: {result['symbol']}")
                    
                    # Send notification
                    notification = f"""
🟢 <b>POSITION OPENED</b>

<b>Symbol:</b> {result['symbol']}
<b>Type:</b> LONG
<b>Leverage:</b> {TRADING_CONFIG['leverage']}x
<b>Entry Price:</b> ${result['entry']:.4f}
<b>Stop Loss:</b> ${result['sl']:.4f}
<b>Take Profit:</b> ${result['tp']:.4f}
<b>Quantity:</b> {result['quantity']:.4f}
<b>Risk:</b> {TRADING_CONFIG['risk_percentage']}%

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                    self.send_email_notification(f"🟢 Position Opened - {result['symbol']}", notification)
            
            # Try to extract CLOSE signal
            close_signal = self.extractor.extract_close_signal(text)
            if close_signal:
                signal_hash = self.generate_signal_hash(close_signal, msg_date)
                
                # Save detected signal to database
                if not self.db.is_signal_detected(signal_hash):
                    self.db.save_detected_signal(close_signal, signal_hash, text, 'detected')
                
                # Check if already processed
                if self.db.is_signal_processed(signal_hash):
                    logger.info(f"Close signal already processed: {close_signal['symbol']}")
                    continue
                
                # If first run, automatically process CLOSE signals without asking
                if is_first_run:
                    logger.info(f"First run: Auto-processing CLOSE signal for {close_signal['symbol']}")
                
                logger.info(f"CLOSE signal detected: {close_signal}")
                
                # Check if position exists in database
                if self.db.is_position_open(close_signal['symbol']):
                    # Close position on Binance
                    try:
                        close_success = self.trader.close_position(close_signal['symbol'])
                    except Exception as close_error:
                        error_msg = f"""
🔴 <b>ERROR CLOSING POSITION</b>

<b>Symbol:</b> {close_signal['symbol']}
<b>Error:</b> {str(close_error)}
<b>Expected Profit:</b> {close_signal['profit_percentage']:+.2f}%

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                        self.send_email_notification(f"🔴 Error Closing Position - {close_signal['symbol']}", error_msg)
                        logger.error(f"Error closing position for {close_signal['symbol']}: {close_error}")
                        self.db.update_signal_status(signal_hash, 'error')
                        close_success = False
                    
                    if close_success:
                        # Update database
                        self.db.close_position(
                            close_signal['symbol'],
                            close_signal['profit_percentage']
                        )
                        self.db.mark_signal_processed(signal_hash)
                        self.db.update_signal_status(signal_hash, 'executed')
                        logger.info(f"Position closed: {close_signal['symbol']} with {close_signal['profit_percentage']}% profit")
                        
                        # Send notification
                        profit_emoji = "🟢" if close_signal['profit_percentage'] > 0 else "🔴"
                        status = 'WIN' if close_signal['profit_percentage'] > 0 else 'LOSS'
                        notification = f"""
{profit_emoji} <b>POSITION CLOSED</b>

<b>Symbol:</b> {close_signal['symbol']}
<b>Profit:</b> {close_signal['profit_percentage']:+.2f}%
<b>Status:</b> {'✅ WIN' if close_signal['profit_percentage'] > 0 else '❌ LOSS'}

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                        self.send_email_notification(f"{profit_emoji} Position Closed - {close_signal['symbol']} ({status})", notification)
                else:
                    logger.info(f"No open position found for {close_signal['symbol']}")
                    self.db.mark_signal_processed(signal_hash)
                    self.db.update_signal_status(signal_hash, 'no-position')
        
        return True  # Continue running
    
    async def run(self):
        """Main loop to run the bot"""
        await self.telegram_client.start(phone=TELEGRAM_CONFIG['phone'])
        logger.info("Bot started successfully")
        
        # Check if this is the first run of the day
        is_first_run = self.db.is_first_run_today()
        
        if is_first_run:
            print("\n" + "="*60)
            print("🚀 FIRST RUN OF THE DAY - INITIAL SETUP MODE")
            print("="*60)
            print("\nThe bot will fetch ALL messages from today and let you")
            print("review each signal individually.")
            print("\nFor each signal, you can:")
            print("  - Press 'y' to process and open the position")
            print("  - Press 'n' to skip (if you already opened it manually)")
            print("  - Press 'q' to quit and resume later")
            print("\n" + "="*60 + "\n")
            
            # Process all today's messages with interactive review
            continue_running = await self.process_messages(is_first_run=True)
            
            if not continue_running:
                logger.info("Initial setup interrupted by user. Exiting.")
                return
            
            # Mark first run as completed
            self.db.mark_run_completed()
            
            print("\n" + "="*60)
            print("✅ INITIAL SETUP COMPLETED")
            print("="*60)
            print("\nThe bot will now run in continuous mode.")
            print("Every 5 minutes, it will:")
            print("  - Fetch ALL messages from today")
            print("  - Process only NEW signals automatically")
            print("  - Skip signals already in database")
            print("\nPress Ctrl+C to stop the bot.")
            print("="*60 + "\n")
        
        # Continuous mode - check every 5 minutes
        while True:
            try:
                # Check if it's a new day - if so, enter first run mode again
                if self.db.is_first_run_today():
                    logger.info("New day detected - entering first run mode")
                    print("\n" + "="*60)
                    print("📅 NEW DAY DETECTED - ENTERING INITIAL SETUP MODE")
                    print("="*60 + "\n")
                    
                    continue_running = await self.process_messages(is_first_run=True)
                    
                    if not continue_running:
                        logger.info("Initial setup interrupted by user. Exiting.")
                        return
                    
                    self.db.mark_run_completed()
                    print("\n✅ Initial setup for new day completed. Continuing in automatic mode.\n")
                else:
                    # Normal processing - automatic mode (fetches all today's messages every 5min)
                    await self.process_messages(is_first_run=False)
            except Exception as e:
                error_msg = f"""
🔴 <b>CRITICAL ERROR IN BOT</b>

<b>Error Type:</b> {type(e).__name__}
<b>Error Message:</b> {str(e)}

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

The bot will continue running and retry in the next cycle.
"""
                self.send_email_notification("🔴 Critical Error in Trading Bot", error_msg)
                logger.error(f"Error in main loop: {e}")
            
            # Wait for next iteration (5 minutes)
            await asyncio.sleep(TRADING_CONFIG['fetch_interval'])

async def main():
    bot = TradingBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())