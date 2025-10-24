from telethon import TelegramClient
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
import logging
import json
from binance.client import Client
from binance.enums import *
import requests

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
    'fetch_interval': 300,  # 5 minutes
    'lookback_hours': 24
}

# DeepSeek API Configuration (Free tier available)
# Alternative: Use local Ollama or Hugging Face models
DEEPSEEK_CONFIG = {
    'api_key': 'sk-abaae5d245c64f899a1302208cc671b1',  # Get from https://platform.deepseek.com
    'base_url': 'https://api.deepseek.com/v1',
    'model': 'deepseek-chat'
}

# Email notifications
EMAIL_CONFIG = {
    'enabled': True,
    'to_email': 'somapalagalagedara@gmail.com',
    'from_email': 'somapalagalagedara@gmail.com',
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'password': 'gmsq cxug zkhv jtik'
}

class MessageDatabase:
    def __init__(self, db_name='ai_trading_bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Messages table
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
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL,
                entry_limit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                quantity REAL,
                leverage INTEGER,
                opened_at TIMESTAMP,
                closed_at TIMESTAMP,
                status TEXT NOT NULL,
                profit_percentage REAL,
                source_message_id INTEGER,
                binance_order_id TEXT,
                position_details TEXT
            )
        ''')
        
        # Position updates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS position_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                update_type TEXT NOT NULL,
                update_details TEXT NOT NULL,
                profit_percentage REAL,
                action_taken TEXT,
                updated_at TIMESTAMP NOT NULL,
                FOREIGN KEY (position_id) REFERENCES positions (id)
            )
        ''')
        
        # Trading actions log
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
        """Save a message to database"""
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
        """Mark message as processed with AI analysis"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE messages 
            SET processed = 1, message_type = ?, ai_analysis = ?
            WHERE message_id = ?
        ''', (message_type, ai_analysis, message_id))
        self.conn.commit()
    
    def get_unprocessed_messages(self):
        """Get all unprocessed messages"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT message_id, message_text, message_date
            FROM messages 
            WHERE processed = 0
            ORDER BY message_date ASC
        ''')
        return cursor.fetchall()
    
    def save_position(self, symbol, entry, entry_limit, sl, tp, qty, leverage, message_id, order_id=None):
        """Save a new position"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO positions 
            (symbol, entry_price, entry_limit_price, stop_loss, take_profit, 
             quantity, leverage, opened_at, status, source_message_id, binance_order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
        ''', (symbol, entry, entry_limit, sl, tp, qty, leverage, 
              datetime.now(timezone.utc), message_id, order_id))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_open_position(self, symbol):
        """Get open position for a symbol"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM positions 
            WHERE symbol = ? AND status = 'open'
            ORDER BY opened_at DESC LIMIT 1
        ''', (symbol,))
        return cursor.fetchone()
    
    def update_position_status(self, position_id, status, profit_pct=None):
        """Update position status"""
        cursor = self.conn.cursor()
        if profit_pct is not None:
            cursor.execute('''
                UPDATE positions 
                SET status = ?, profit_percentage = ?, closed_at = ?
                WHERE id = ?
            ''', (status, profit_pct, datetime.now(timezone.utc), position_id))
        else:
            cursor.execute('''
                UPDATE positions 
                SET status = ?
                WHERE id = ?
            ''', (status, position_id))
        self.conn.commit()
    
    def save_position_update(self, position_id, message_id, update_type, details, profit_pct, action_taken):
        """Save a position update"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO position_updates 
            (position_id, message_id, update_type, update_details, 
             profit_percentage, action_taken, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (position_id, message_id, update_type, details, 
              profit_pct, action_taken, datetime.now(timezone.utc)))
        self.conn.commit()
    
    def log_trading_action(self, action_type, symbol, details, success, error_msg=None):
        """Log a trading action"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO trading_actions 
            (action_type, symbol, details, success, error_message, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (action_type, symbol, details, success, error_msg, datetime.now(timezone.utc)))
        self.conn.commit()

class AISignalExtractor:
    """Uses DeepSeek AI to extract and analyze trading signals"""
    
    def __init__(self, api_key, base_url, model):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    def analyze_message(self, message_text):
        """Analyze message using AI to extract trading signals"""
        
        system_prompt = """You are a cryptocurrency trading signal analyzer. Your job is to analyze Telegram messages and extract trading signals or position updates.

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
1. Symbols should be uppercase without $ sign (e.g., "ZORA" not "$ZORA")
2. Always append "USDT" to symbols (e.g., "ZORAUSDT")
3. Extract profit percentages from messages like "SYMBOL + 56.1% profit"
4. Messages mentioning "cancel", "cancelled", or "missed" are UPDATE type with action "CANCELLED"
5. Messages with just profit updates are UPDATE type with action "INFO"
6. Only return NEW_POSITION if message contains entry, SL, or TP prices
7. Return valid JSON only, no markdown or extra text"""

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
                content = result['choices'][0]['message']['content']
                
                # Clean up response (remove markdown if present)
                content = content.strip()
                if content.startswith('```json'):
                    content = content[7:]
                if content.startswith('```'):
                    content = content[3:]
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()
                
                # Parse JSON
                analysis = json.loads(content)
                return analysis
            else:
                logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
                return {"type": "ERROR", "reason": f"API error: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Error calling DeepSeek API: {e}")
            return {"type": "ERROR", "reason": str(e)}

class BinanceTrader:
    def __init__(self, api_key, api_secret):
        self.client = Client(api_key, api_secret)
    
    def get_account_balance(self):
        """Get USDT balance for futures account"""
        try:
            balance = self.client.futures_account_balance()
            for b in balance:
                if b['asset'] == 'USDT':
                    return float(b['availableBalance'])
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
        return 0
    
    def set_leverage(self, symbol, leverage):
        """Set leverage for symbol"""
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"Set {leverage}x leverage for {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return False
    
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
        return 3, 2
    
    def open_long_position(self, signal, leverage, risk_pct):
        """Open a LONG position"""
        try:
            symbol = signal['symbol']
            entry = signal['entry_price']
            sl = signal['stop_loss']
            tp = signal.get('take_profit')
            
            # Set leverage
            if not self.set_leverage(symbol, leverage):
                return None
            
            # Get balance
            balance = self.get_account_balance()
            logger.info(f"Account balance: {balance} USDT")
            
            # Calculate position size
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
        """Close a position (full or partial)"""
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
                        # Cancel all open orders
                        self.client.futures_cancel_all_open_orders(symbol=symbol)
                    
                    # Close with market order
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
    
    def modify_position_entry(self, symbol, new_entry):
        """Modify position entry (note: can't modify filled orders, this is informational)"""
        logger.info(f"ℹ️ Entry modification noted for {symbol}: {new_entry}")
        # In real trading, you would need to close and reopen at new price
        # For now, just log it
        return True

class AITradingBot:
    def __init__(self):
        self.telegram_client = TelegramClient(
            'my_session',
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
    
    async def fetch_messages(self):
        """Fetch messages from the last 24 hours"""
        messages = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=TRADING_CONFIG['lookback_hours'])
        
        async for message in self.telegram_client.iter_messages(
            TELEGRAM_CONFIG['group_id'],
            reply_to=TELEGRAM_CONFIG['topic_id'],
            limit=None
        ):
            if message.date < cutoff_time:
                break
            
            if message.text:
                # Save to database if new
                self.db.save_message(message.id, message.text, message.date)
                messages.append({
                    'id': message.id,
                    'text': message.text,
                    'date': message.date
                })
        
        return messages
    
    async def process_new_position(self, signal, message_id):
        """Process a new position signal"""
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
        
        # Open position on Binance
        result = self.trader.open_long_position(
            signal['signal'],
            TRADING_CONFIG['leverage'],
            TRADING_CONFIG['risk_percentage']
        )
        
        if result:
            # Save to database
            self.db.save_position(
                symbol=result['symbol'],
                entry=result['entry'],
                entry_limit=signal['signal'].get('entry_limit'),
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
        """Process a position update"""
        symbol = update_info['update']['symbol']
        action = update_info['update']['action']
        profit_pct = update_info['update'].get('profit_percentage')
        
        logger.info(f"📊 POSITION UPDATE: {symbol}")
        logger.info(f"   Action: {action}")
        logger.info(f"   Profit: {profit_pct}%" if profit_pct else "   Profit: N/A")
        
        # Get position from database
        position = self.db.get_open_position(symbol)
        
        if not position and action not in ['CANCELLED', 'INFO']:
            logger.warning(f"⚠️ No open position found for {symbol}")
            self.db.log_trading_action('UPDATE_POSITION', symbol, 'No position found', False)
            return
        
        # Handle different actions
        if action == 'CLOSE_FULL':
            success = self.trader.close_position(symbol)
            if success and position:
                self.db.update_position_status(position[0], 'closed', profit_pct)
                self.db.save_position_update(
                    position[0], message_id, 'CLOSE_FULL',
                    json.dumps(update_info['update']), profit_pct, 'Position closed'
                )
                self.db.log_trading_action('CLOSE_FULL', symbol, f"Profit: {profit_pct}%", True)
                logger.info(f"✅ Position closed: {symbol} with {profit_pct}% profit")
        
        elif action == 'CLOSE_PARTIAL':
            partial_pct = update_info['update'].get('partial_close_pct', 50)
            success = self.trader.close_position(symbol, partial_pct)
            if success and position:
                self.db.save_position_update(
                    position[0], message_id, 'CLOSE_PARTIAL',
                    json.dumps(update_info['update']), profit_pct, f'Closed {partial_pct}%'
                )
                self.db.log_trading_action('CLOSE_PARTIAL', symbol, f"Closed {partial_pct}%", True)
                logger.info(f"✅ Partial close: {symbol} - {partial_pct}%")
        
        elif action == 'MODIFY_ENTRY':
            new_entry = update_info['update'].get('new_entry')
            if new_entry and position:
                self.db.save_position_update(
                    position[0], message_id, 'MODIFY_ENTRY',
                    json.dumps(update_info['update']), None, f'Entry modified to {new_entry}'
                )
                self.db.log_trading_action('MODIFY_ENTRY', symbol, f"New entry: {new_entry}", True)
                logger.info(f"ℹ️ Entry modified for {symbol}: {new_entry}")
        
        elif action == 'CANCELLED':
            if position:
                # Close any open position
                self.trader.close_position(symbol)
                self.db.update_position_status(position[0], 'cancelled', 0)
                self.db.save_position_update(
                    position[0], message_id, 'CANCELLED',
                    json.dumps(update_info['update']), None, 'Position cancelled'
                )
            self.db.log_trading_action('CANCEL', symbol, update_info['update'].get('note', ''), True)
            logger.info(f"🚫 Position cancelled: {symbol}")
        
        elif action == 'INFO':
            if position:
                self.db.save_position_update(
                    position[0], message_id, 'INFO',
                    json.dumps(update_info['update']), profit_pct, 'Profit update'
                )
            logger.info(f"ℹ️ Info update: {symbol} - {update_info['update'].get('note', '')}")
    
    async def process_messages(self):
        """Main message processing loop"""
        logger.info("="*80)
        logger.info(f"🔄 Starting message processing at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info("="*80)
        
        # Fetch all messages
        await self.fetch_messages()
        
        # Get unprocessed messages
        unprocessed = self.db.get_unprocessed_messages()
        
        if not unprocessed:
            logger.info("✓ No new messages to process")
            return
        
        logger.info(f"📬 Found {len(unprocessed)} unprocessed messages")
        
        for msg_id, msg_text, msg_date in unprocessed:
            logger.info(f"\n{'='*80}")
            logger.info(f"🔍 Analyzing message {msg_id} from {msg_date}")
            logger.info(f"📝 Content: {msg_text[:100]}...")
            
            # Use AI to analyze message
            analysis = self.ai.analyze_message(msg_text)
            
            logger.info(f"🤖 AI Analysis: {analysis['type']}")
            
            # Process based on message type
            if analysis['type'] == 'NEW_POSITION':
                await self.process_new_position(analysis, msg_id)
            
            elif analysis['type'] == 'POSITION_UPDATE':
                await self.process_position_update(analysis, msg_id)
            
            elif analysis['type'] == 'IGNORE':
                logger.info(f"⏭️ Ignored: {analysis.get('reason', 'Not a trading message')}")
            
            elif analysis['type'] == 'ERROR':
                logger.error(f"⚠️ AI Error: {analysis.get('reason', 'Unknown error')}")
            
            # Mark as processed
            self.db.mark_message_processed(msg_id, analysis['type'], json.dumps(analysis))
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ Processing complete - {len(unprocessed)} messages processed")
        logger.info("="*80)
    
    async def run(self):
        """Main bot loop"""
        await self.telegram_client.start(phone=TELEGRAM_CONFIG['phone'])
        logger.info("🚀 AI Trading Bot started successfully")
        
        print("\n" + "="*80)
        print("🤖 AI-POWERED TRADING BOT")
        print("="*80)
        print(f"📍 Group ID: {TELEGRAM_CONFIG['group_id']}")
        print(f"📍 Topic ID: {TELEGRAM_CONFIG['topic_id']}")
        print(f"⏰ Check Interval: {TRADING_CONFIG['fetch_interval']} seconds")
        print(f"💰 Risk per trade: {TRADING_CONFIG['risk_percentage']}%")
        print(f"📊 Leverage: {TRADING_CONFIG['leverage']}x")
        print("="*80 + "\n")
        
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
    bot = AITradingBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("\n\n👋 Bot stopped by user")

if __name__ == '__main__':
    asyncio.run(main())