from telethon import TelegramClient
import asyncio
import re
from datetime import datetime, timedelta, timezone
import sqlite3
from binance.client import Client
from binance.enums import *
import logging

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

NOTIFICATION_CONFIG = {
    'enabled': True,
    'chat_id': 'me',  # 'me' for saved messages, or specific chat_id/username
    'send_logs': True,  # Send log messages
    'send_errors': True,  # Send error messages
    'send_debug': True,  # Send debug info
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

class SignalExtractor:
    @staticmethod
    def extract_long_signal(text):
        """Extract LONG signal details from message"""
        text_upper = text.upper()
        
        # Check if it's a LONG signal
        if 'LONG' not in text_upper:
            return None
        
        # Extract symbol (common patterns: LONG - $API3, LONG $API3, etc.)
        symbol_pattern = r'(?:LONG\s*-?\s*\$?)([A-Z0-9]{2,10})'
        symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            return None
        
        symbol = symbol_match.group(1)
        
        # Extract entry price
        entry_pattern = r'(?:ENTRY[:\s]*|ENTRYC[:\s]*)(\d+\.?\d*)'
        entry_match = re.search(entry_pattern, text_upper)
        if not entry_match:
            return None
        
        entry_price = float(entry_match.group(1))
        
        # Extract stop loss
        sl_pattern = r'(?:SL[:\s]*)(\d+\.?\d*)'
        sl_match = re.search(sl_pattern, text_upper)
        if not sl_match:
            return None
        
        stop_loss = float(sl_match.group(1))
        
        # Extract take profit
        tp_pattern = r'(?:TP[:\s]*)(\d+\.?\d*)'
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
        
        # Check if it contains "close" keyword
        if 'CLOSE' not in text_upper:
            return None
        
        # Extract symbol
        symbol_pattern = r'([A-Z0-9]{2,10})\s*\+'
        symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            # Try alternative pattern
            symbol_pattern = r'-\s*([A-Z0-9]{2,10})'
            symbol_match = re.search(symbol_pattern, text_upper)
        
        if not symbol_match:
            return None
        
        symbol = symbol_match.group(1)
        
        # Extract profit percentage
        profit_pattern = r'\+?\s*(\d+\.?\d*)\s*%'
        profit_match = re.search(profit_pattern, text)
        
        profit_pct = float(profit_match.group(1)) if profit_match else 0
        
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
    
    async def send_notification(self, message):
        """Send notification message to Telegram"""
        if not NOTIFICATION_CONFIG['enabled']:
            return
        
        try:
            await self.telegram_client.send_message(
                NOTIFICATION_CONFIG['chat_id'],
                message,
                parse_mode='markdown'
            )
            logger.info(f"Notification sent: {message[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    async def fetch_recent_messages(self):
        """Fetch messages from the last 5 minutes"""
        messages = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=TRADING_CONFIG['message_lookback'])
        
        async for message in self.telegram_client.iter_messages(
            TELEGRAM_CONFIG['group_id'],
            reply_to=TELEGRAM_CONFIG['topic_id'],
            limit=50
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
    
    async def process_messages(self):
        """Process messages and execute trades"""
        messages = await self.fetch_recent_messages()
        logger.info(f"Fetched {len(messages)} messages from last 5 minutes")
        
        for msg in reversed(messages):  # Process oldest first
            text = msg['text']
            msg_date = msg['date']
            
            # Try to extract LONG signal
            long_signal = self.extractor.extract_long_signal(text)
            if long_signal:
                signal_hash = self.generate_signal_hash(long_signal, msg_date)
                
                # Check if already processed
                if self.db.is_signal_processed(signal_hash):
                    logger.info(f"Signal already processed: {long_signal['symbol']}")
                    continue
                
                # Check if position already open
                if self.db.is_position_open(long_signal['symbol']):
                    logger.info(f"Position already open for {long_signal['symbol']}")
                    self.db.mark_signal_processed(signal_hash)
                    continue
                
                logger.info(f"New LONG signal detected: {long_signal}")
                
                # Execute trade
                result = self.trader.open_long_position(
                    long_signal,
                    TRADING_CONFIG['leverage'],
                    TRADING_CONFIG['risk_percentage']
                )
                
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
                    logger.info(f"Position opened and logged: {result['symbol']}")
                    
                    # Send notification
                    notification = f"""
🟢 **POSITION OPENED**

**Symbol:** {result['symbol']}
**Type:** LONG
**Leverage:** {TRADING_CONFIG['leverage']}x
**Entry Price:** ${result['entry']:.4f}
**Stop Loss:** ${result['sl']:.4f}
**Take Profit:** ${result['tp']:.4f}
**Quantity:** {result['quantity']:.4f}
**Risk:** {TRADING_CONFIG['risk_percentage']}%

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                    await self.send_notification(notification)
            
            # Try to extract CLOSE signal
            close_signal = self.extractor.extract_close_signal(text)
            if close_signal:
                signal_hash = self.generate_signal_hash(close_signal, msg_date)
                
                # Check if already processed
                if self.db.is_signal_processed(signal_hash):
                    logger.info(f"Close signal already processed: {close_signal['symbol']}")
                    continue
                
                logger.info(f"CLOSE signal detected: {close_signal}")
                
                # Check if position exists in database
                if self.db.is_position_open(close_signal['symbol']):
                    # Close position on Binance
                    if self.trader.close_position(close_signal['symbol']):
                        # Update database
                        self.db.close_position(
                            close_signal['symbol'],
                            close_signal['profit_percentage']
                        )
                        self.db.mark_signal_processed(signal_hash)
                        logger.info(f"Position closed: {close_signal['symbol']} with {close_signal['profit_percentage']}% profit")
                        
                        # Send notification
                        profit_emoji = "🟢" if close_signal['profit_percentage'] > 0 else "🔴"
                        notification = f"""
{profit_emoji} **POSITION CLOSED**

**Symbol:** {close_signal['symbol']}
**Profit:** {close_signal['profit_percentage']:+.2f}%
**Status:** {'✅ WIN' if close_signal['profit_percentage'] > 0 else '❌ LOSS'}

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                        await self.send_notification(notification)
                else:
                    logger.info(f"No open position found for {close_signal['symbol']}")
                    self.db.mark_signal_processed(signal_hash)
    
    async def run(self):
        """Main loop to run the bot"""
        await self.telegram_client.start(phone=TELEGRAM_CONFIG['phone'])
        logger.info("Bot started successfully")
        
        while True:
            try:
                await self.process_messages()
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
            
            # Wait for next iteration
            await asyncio.sleep(TRADING_CONFIG['fetch_interval'])

async def main():
    bot = TradingBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())