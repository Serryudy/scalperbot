import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime
import time
import logging
import sqlite3
import json

# --- Database Setup ---
def setup_database():
    """Create database and tables if they don't exist"""
    conn = sqlite3.connect('trades.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            side TEXT,
            quantity REAL,
            entry_price REAL,
            exit_price REAL,
            profit REAL,
            return_pct REAL
        )
    ''')
    conn.commit()
    conn.close()

def log_trade_to_db(symbol, side, quantity, entry_price, exit_price, profit):
    """Logs a completed trade to the SQLite database."""
    return_pct = ((exit_price - entry_price) / entry_price * 100) if side == 'LONG' else ((entry_price - exit_price) / entry_price * 100)
    
    conn = None
    try:
        conn = sqlite3.connect('trades.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (symbol, side, quantity, entry_price, exit_price, profit, return_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, side, quantity, entry_price, exit_price, profit, return_pct))
        conn.commit()
        logging.info(f"Logged trade to database: {side} {quantity} {symbol} with profit ${profit:.2f} ({return_pct:+.2f}%)")
    except sqlite3.Error as e:
        logging.error(f"Database error while logging trade: {e}")
    finally:
        if conn:
            conn.close()

# --- Signal Generation ---
def total_signal(df, current_candle):
    """Signal generation logic"""
    current_pos = df.index.get_loc(current_candle)
    if current_pos < 3:
        return 0
    
    # Buy signal conditions
    c1 = df['High'].iloc[current_pos] > df['High'].iloc[current_pos-1]
    c2 = df['High'].iloc[current_pos-1] > df['Low'].iloc[current_pos]
    c3 = df['Low'].iloc[current_pos] > df['High'].iloc[current_pos-2]
    c4 = df['High'].iloc[current_pos-2] > df['Low'].iloc[current_pos-1]
    c5 = df['Low'].iloc[current_pos-1] > df['High'].iloc[current_pos-3]
    c6 = df['High'].iloc[current_pos-3] > df['Low'].iloc[current_pos-2]
    c7 = df['Low'].iloc[current_pos-2] > df['Low'].iloc[current_pos-3]
    
    if c1 and c2 and c3 and c4 and c5 and c6 and c7:
        return 2  # Buy
    
    # Sell signal conditions
    c1 = df['Low'].iloc[current_pos] < df['Low'].iloc[current_pos-1]
    c2 = df['Low'].iloc[current_pos-1] < df['High'].iloc[current_pos]
    c3 = df['High'].iloc[current_pos] < df['Low'].iloc[current_pos-2]
    c4 = df['Low'].iloc[current_pos-2] < df['High'].iloc[current_pos-1]
    c5 = df['High'].iloc[current_pos-1] < df['Low'].iloc[current_pos-3]
    c6 = df['Low'].iloc[current_pos-3] < df['High'].iloc[current_pos-2]
    c7 = df['High'].iloc[current_pos-2] < df['High'].iloc[current_pos-3]
    
    if c1 and c2 and c3 and c4 and c5 and c6 and c7:
        return 1  # Sell
    
    return 0

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger()

class OptimizedBinanceFuturesBot:
    def __init__(self, api_key, api_secret, symbol, interval, 
                 stop_loss_pct=2.0, take_profit_pct=3.0, 
                 leverage=10, risk_per_trade=0.20,
                 trading_session='all'):
        """
        Initialize trading bot with optimized parameters
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            symbol: Trading pair (e.g., 'DOGEUSDT')
            interval: Candle interval (e.g., Client.KLINE_INTERVAL_1HOUR)
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            leverage: Leverage multiplier
            risk_per_trade: Risk per trade (0.20 = 20%)
            trading_session: 'all', 'london', 'newyork', 'london_newyork', 'asian'
        """
        self.symbol = symbol
        self.interval = interval
        self.leverage = leverage
        self.risk_per_trade = risk_per_trade
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trading_session = trading_session
        
        self.client = Client(api_key, api_secret)
        self.current_position = None
        self.entry_price = 0
        self.position_size = 0
        
        # Trading sessions (UTC time)
        self.sessions = {
            'all': {'start': 0, 'end': 24},
            'london': {'start': 7, 'end': 16},
            'newyork': {'start': 12, 'end': 21},
            'london_newyork': {'start': 12, 'end': 16},
            'asian': {'start': 23, 'end': 8}
        }
        
        # Setup database
        setup_database()

    def is_trading_session(self):
        """Check if current time is within trading session"""
        if self.trading_session == 'all':
            return True
        
        current_hour = datetime.utcnow().hour
        session = self.sessions[self.trading_session]
        
        if session['start'] < session['end']:
            return session['start'] <= current_hour < session['end']
        else:  # Session wraps around midnight
            return current_hour >= session['start'] or current_hour < session['end']

    def setup_futures_account(self):
        """Set up the futures account with the specified leverage"""
        try:
            self.client.futures_change_margin_type(symbol=self.symbol, marginType='ISOLATED')
        except BinanceAPIException as e:
            if "Already" not in str(e):
                logger.error(f"Error setting margin type: {e}")
        
        try:
            self.client.futures_change_leverage(symbol=self.symbol, leverage=self.leverage)
            logger.info(f"Leverage set to {self.leverage}x for {self.symbol}")
        except BinanceAPIException as e:
            logger.error(f"Error setting leverage: {e}")

    def get_current_position(self):
        """Get the current position information"""
        try:
            positions = self.client.futures_position_information(symbol=self.symbol)
            for position in positions:
                if position['symbol'] == self.symbol:
                    amt = float(position['positionAmt'])
                    if amt > 0:
                        self.current_position = 'LONG'
                        self.entry_price = float(position['entryPrice'])
                        self.position_size = amt
                    elif amt < 0:
                        self.current_position = 'SHORT'
                        self.entry_price = float(position['entryPrice'])
                        self.position_size = abs(amt)
                    else:
                        self.current_position = None
                        self.entry_price = 0
                        self.position_size = 0
                    return self.current_position, amt
        except BinanceAPIException as e:
            logger.error(f"Error getting position: {e}")
        return None, 0

    def fetch_account_balance(self):
        """Fetch USDT balance in futures account"""
        try:
            account_info = self.client.futures_account_balance()
            for asset in account_info:
                if asset['asset'] == 'USDT':
                    return float(asset['balance'])
        except BinanceAPIException as e:
            logger.error(f"Error fetching balance: {e}")
        return 0.0

    def get_symbol_info(self):
        """Get symbol information including precision"""
        try:
            exchange_info = self.client.futures_exchange_info()
            for symbol_info in exchange_info['symbols']:
                if symbol_info['symbol'] == self.symbol:
                    return symbol_info
        except BinanceAPIException as e:
            logger.error(f"Error getting symbol info: {e}")
        return None

    def get_price_precision(self, symbol_info=None):
        """Get price precision for the symbol"""
        if not symbol_info:
            symbol_info = self.get_symbol_info()
        
        price_precision = 2
        if symbol_info:
            for filter in symbol_info['filters']:
                if filter['filterType'] == 'PRICE_FILTER':
                    tick_size = filter['tickSize']
                    if '.' in tick_size:
                        price_precision = len(tick_size.rstrip('0').split('.')[1])
                    break
        return price_precision

    def get_quantity_precision(self, symbol_info=None):
        """Get quantity precision for the symbol"""
        if not symbol_info:
            symbol_info = self.get_symbol_info()
        
        qty_precision = 0
        if symbol_info:
            for filter in symbol_info['filters']:
                if filter['filterType'] == 'LOT_SIZE':
                    step_size = filter['stepSize']
                    if '.' in step_size:
                        qty_precision = len(step_size.rstrip('0').split('.')[1])
                    break
        return qty_precision

    def round_price(self, price):
        """Round price to appropriate precision"""
        precision = self.get_price_precision()
        return round(price, precision)

    def round_quantity(self, quantity):
        """Round quantity to appropriate precision"""
        precision = self.get_quantity_precision()
        return round(quantity, precision)

    def calculate_position_size_with_risk(self, entry_price):
        """
        Calculate position size based on 20% risk per trade
        This ensures we only risk 20% of capital on each trade
        """
        balance = self.fetch_account_balance()
        
        # Amount we're willing to risk (20% of capital)
        risk_amount = balance * self.risk_per_trade
        
        # Distance to stop loss in price
        stop_distance = entry_price * (self.stop_loss_pct / 100)
        
        # Position size needed to risk exactly risk_amount
        # If we lose stop_distance per coin, we want total loss = risk_amount
        position_size_coins = risk_amount / stop_distance
        
        # With leverage, we can control a larger position
        # But our RISK is still capped at risk_amount
        leveraged_position = position_size_coins * self.leverage
        
        # Ensure we don't exceed capital limits
        max_position_by_capital = (balance * self.leverage) / entry_price
        
        # Use the smaller value
        final_position = min(leveraged_position, max_position_by_capital)
        
        # Round to correct precision
        final_position = self.round_quantity(final_position)
        
        # Ensure minimum position size
        symbol_info = self.get_symbol_info()
        if symbol_info:
            for filter in symbol_info['filters']:
                if filter['filterType'] == 'LOT_SIZE':
                    min_qty = float(filter['minQty'])
                    if final_position < min_qty:
                        final_position = min_qty
                        logger.warning(f"Position size adjusted to minimum: {min_qty}")
                    break
        
        logger.info(f"Account Balance: ${balance:.2f}")
        logger.info(f"Risk Amount (20%): ${risk_amount:.2f}")
        logger.info(f"Entry Price: ${entry_price:.4f}")
        logger.info(f"Stop Loss Distance: ${stop_distance:.4f}")
        logger.info(f"Position Size: {final_position} coins")
        logger.info(f"Position Value: ${final_position * entry_price:.2f}")
        logger.info(f"Max Loss if SL Hit: ${risk_amount:.2f}")
        
        return final_position

    def fetch_latest_candles(self, num_candles=4):
        """Fetch the latest candles needed for signal generation"""
        try:
            klines = self.client.futures_klines(
                symbol=self.symbol,
                interval=self.interval,
                limit=num_candles
            )
            
            df = pd.DataFrame(klines, columns=[
                'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume',
                'CloseTime', 'QuoteAssetVolume', 'NumberOfTrades',
                'TakerBuyBaseAssetVolume', 'TakerBuyQuoteAssetVolume', 'Ignore'
            ])
            
            df['OpenTime'] = pd.to_datetime(df['OpenTime'], unit='ms')
            
            for col in ['Open', 'High', 'Low', 'Close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df.set_index('OpenTime', inplace=True)
            
            return df
        except BinanceAPIException as e:
            logger.error(f"Error fetching candles: {e}")
            return None

    def get_signal(self):
        """Get the current trading signal"""
        # Check if we're in trading session
        if not self.is_trading_session():
            logger.debug(f"Outside trading session: {self.trading_session}")
            return 0
        
        df = self.fetch_latest_candles(num_candles=4)
        if df is None or len(df) < 4:
            logger.error("Not enough candles to generate signal")
            return 0
        
        current_candle = df.index[-1]
        signal = total_signal(df, current_candle)
        
        if signal == 2:
            logger.info("BUY signal detected")
        elif signal == 1:
            logger.info("SELL signal detected")
        
        return signal

    def get_current_price(self):
        """Get current market price for the symbol"""
        try:
            ticker = self.client.futures_symbol_ticker(symbol=self.symbol)
            return float(ticker['price'])
        except BinanceAPIException as e:
            logger.error(f"Error getting current price: {e}")
            return None

    def execute_trade(self, signal):
        """Execute a trade based on the signal"""
        current_position, position_amt = self.get_current_position()
        
        current_price = self.get_current_price()
        if current_price is None:
            logger.error("Failed to get current price. Aborting trade execution.")
            return
        
        if signal == 2:  # Buy signal
            if current_position == 'SHORT':
                logger.info("Closing SHORT position before opening LONG")
                self.close_position()
                time.sleep(2)
            
            if current_position != 'LONG':
                self.open_long_position(current_price)
        
        elif signal == 1:  # Sell signal
            if current_position == 'LONG':
                logger.info("Closing LONG position before opening SHORT")
                self.close_position()
                time.sleep(2)
            
            if current_position != 'SHORT':
                self.open_short_position(current_price)

    def check_price_filter(self, price):
        """Check if price meets the PRICE_FILTER requirements"""
        symbol_info = self.get_symbol_info()
        if symbol_info:
            for filter in symbol_info['filters']:
                if filter['filterType'] == 'PRICE_FILTER':
                    min_price = float(filter['minPrice'])
                    max_price = float(filter['maxPrice'])
                    
                    if price < min_price:
                        logger.warning(f"Price {price} below minimum {min_price}. Adjusting.")
                        return min_price
                    
                    if price > max_price:
                        logger.warning(f"Price {price} above maximum {max_price}. Adjusting.")
                        return max_price
        
        return price

    def open_long_position(self, current_price):
        """Open a long position with 20% risk management"""
        try:
            latest_price = self.get_current_price()
            if latest_price is None:
                logger.error("Failed to get latest price. Aborting long position.")
                return
            
            # Calculate position size with risk management
            position_size = self.calculate_position_size_with_risk(latest_price)
            
            if position_size <= 0:
                logger.error("Invalid position size calculated. Aborting.")
                return
            
            # Calculate SL/TP
            stop_loss = latest_price * (1 - self.stop_loss_pct/100)
            take_profit = latest_price * (1 + self.take_profit_pct/100)
            
            stop_loss = self.round_price(stop_loss)
            take_profit = self.round_price(take_profit)
            
            stop_loss = self.check_price_filter(stop_loss)
            take_profit = self.check_price_filter(take_profit)
            
            logger.info(f"Opening LONG position at {latest_price}")
            logger.info(f"Stop Loss: {stop_loss} (-{self.stop_loss_pct}%)")
            logger.info(f"Take Profit: {take_profit} (+{self.take_profit_pct}%)")
            logger.info(f"Risk/Reward Ratio: 1:{self.take_profit_pct/self.stop_loss_pct:.2f}")
            
            # Cancel all existing orders
            try:
                self.client.futures_cancel_all_open_orders(symbol=self.symbol)
            except BinanceAPIException as e:
                logger.warning(f"Error canceling existing orders: {e}")
            
            # Open position
            order = self.client.futures_create_order(
                symbol=self.symbol,
                side='BUY',
                type='MARKET',
                quantity=position_size
            )
            
            time.sleep(2)
            
            # Verify position
            current_position, position_amt = self.get_current_position()
            if current_position != 'LONG' or position_amt <= 0:
                logger.warning("Long position order may not have executed properly.")
                return
            
            # Set stop loss
            try:
                sl_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='SELL',
                    type='STOP_MARKET',
                    stopPrice=stop_loss,
                    closePosition='true'
                )
                logger.info(f"Stop loss set: {sl_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting stop loss: {e}")
            
            # Set take profit
            try:
                tp_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='SELL',
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=take_profit,
                    closePosition='true'
                )
                logger.info(f"Take profit set: {tp_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting take profit: {e}")
            
            logger.info(f"✅ LONG position opened: {order['orderId']}")
            self.current_position = 'LONG'
            
        except BinanceAPIException as e:
            logger.error(f"Error opening long position: {e}")
        except Exception as e:
            logger.error(f"Unexpected error opening long position: {e}")

    def open_short_position(self, current_price):
        """Open a short position with 20% risk management"""
        try:
            latest_price = self.get_current_price()
            if latest_price is None:
                logger.error("Failed to get latest price. Aborting short position.")
                return
            
            # Calculate position size with risk management
            position_size = self.calculate_position_size_with_risk(latest_price)
            
            if position_size <= 0:
                logger.error("Invalid position size calculated. Aborting.")
                return
            
            # Calculate SL/TP
            stop_loss = latest_price * (1 + self.stop_loss_pct/100)
            take_profit = latest_price * (1 - self.take_profit_pct/100)
            
            stop_loss = self.round_price(stop_loss)
            take_profit = self.round_price(take_profit)
            
            stop_loss = self.check_price_filter(stop_loss)
            take_profit = self.check_price_filter(take_profit)
            
            logger.info(f"Opening SHORT position at {latest_price}")
            logger.info(f"Stop Loss: {stop_loss} (+{self.stop_loss_pct}%)")
            logger.info(f"Take Profit: {take_profit} (-{self.take_profit_pct}%)")
            logger.info(f"Risk/Reward Ratio: 1:{self.take_profit_pct/self.stop_loss_pct:.2f}")
            
            # Cancel all existing orders
            try:
                self.client.futures_cancel_all_open_orders(symbol=self.symbol)
            except BinanceAPIException as e:
                logger.warning(f"Error canceling existing orders: {e}")
            
            # Open position
            order = self.client.futures_create_order(
                symbol=self.symbol,
                side='SELL',
                type='MARKET',
                quantity=position_size
            )
            
            time.sleep(2)
            
            # Verify position
            current_position, position_amt = self.get_current_position()
            if current_position != 'SHORT' or position_amt >= 0:
                logger.warning("Short position order may not have executed properly.")
                return
            
            # Set stop loss
            try:
                sl_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='BUY',
                    type='STOP_MARKET',
                    stopPrice=stop_loss,
                    closePosition='true'
                )
                logger.info(f"Stop loss set: {sl_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting stop loss: {e}")
            
            # Set take profit
            try:
                tp_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='BUY',
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=take_profit,
                    closePosition='true'
                )
                logger.info(f"Take profit set: {tp_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting take profit: {e}")
            
            logger.info(f"✅ SHORT position opened: {order['orderId']}")
            self.current_position = 'SHORT'
            
        except BinanceAPIException as e:
            logger.error(f"Error opening short position: {e}")
        except Exception as e:
            logger.error(f"Unexpected error opening short position: {e}")

    def close_position(self):
        """Close the current position and log the trade"""
        try:
            current_position, position_amt = self.get_current_position()
            if current_position is None or position_amt == 0:
                logger.info("No position to close")
                return

            self.client.futures_cancel_all_open_orders(symbol=self.symbol)
            
            side = 'SELL' if current_position == 'LONG' else 'BUY'
            quantity = abs(position_amt)
            
            exit_price = self.get_current_price()

            order = self.client.futures_create_order(
                symbol=self.symbol,
                side=side,
                type='MARKET',
                quantity=self.round_quantity(quantity)
            )

            # Calculate profit
            profit = 0
            if self.entry_price > 0 and exit_price > 0:
                if current_position == 'LONG':
                    profit = (exit_price - self.entry_price) * quantity
                else:
                    profit = (self.entry_price - exit_price) * quantity
            
            # Log to database
            log_trade_to_db(self.symbol, current_position, quantity, 
                          self.entry_price, exit_price, profit)

            logger.info(f"✅ Closed {current_position} position: {order['orderId']}")
            logger.info(f"PnL: ${profit:+.2f}")
            
            self.current_position = None
            self.entry_price = 0
            self.position_size = 0

        except BinanceAPIException as e:
            logger.error(f"Error closing position: {e}")
        except Exception as e:
            logger.error(f"Unexpected error closing position: {e}")

    def run(self, check_interval_seconds=60):
        """Run the trading bot"""
        logger.info(f"{'='*60}")
        logger.info(f"Starting Optimized Trading Bot")
        logger.info(f"{'='*60}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Interval: {self.interval}")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info(f"Risk Per Trade: {self.risk_per_trade*100}%")
        logger.info(f"Stop Loss: {self.stop_loss_pct}%")
        logger.info(f"Take Profit: {self.take_profit_pct}%")
        logger.info(f"Risk/Reward: 1:{self.take_profit_pct/self.stop_loss_pct:.2f}")
        logger.info(f"Trading Session: {self.trading_session}")
        logger.info(f"{'='*60}\n")
        
        self.setup_futures_account()
        
        try:
            while True:
                try:
                    signal = self.get_signal()
                    if signal > 0:
                        logger.info(f"🔔 Signal detected: {'BUY' if signal == 2 else 'SELL'}")
                        self.execute_trade(signal)
                    else:
                        logger.debug("No trading signal")
                    
                    time.sleep(check_interval_seconds)
                    
                except BinanceAPIException as e:
                    logger.error(f"Binance API error: {e}")
                    time.sleep(30)
                except Exception as e:
                    logger.error(f"Error in bot loop: {e}")
                    time.sleep(30)
                    
        except KeyboardInterrupt:
            logger.info("\n⚠️  Bot stopped by user")
        finally:
            logger.info("Closing any open positions...")
            self.close_position()
            logger.info("Bot shutdown complete")





def run_default():
    """Run bot with conservative default settings"""
    API_KEY = "9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ"
    API_SECRET = "mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl"
    
    bot = OptimizedBinanceFuturesBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol='DOGEUSDT',
        interval=Client.KLINE_INTERVAL_15MINUTE,
        stop_loss_pct=1.0,
        take_profit_pct=1.5,
        leverage=10,
        risk_per_trade=0.10,
        trading_session='all'
    )
    
    bot.run(check_interval_seconds=60)


if __name__ == "__main__":
    run_default()