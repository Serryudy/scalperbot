import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime
import time
import logging
import sqlite3

# --- Database Function ---
def log_trade_to_db(symbol, side, quantity, entry_price, exit_price, profit):
    """Logs a completed trade to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect('trades.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (symbol, side, quantity, entry_price, exit_price, profit)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (symbol, side, quantity, entry_price, exit_price, profit))
        conn.commit()
        logging.info(f"Logged trade to database: {side} {quantity} {symbol} with profit {profit}")
    except sqlite3.Error as e:
        logging.error(f"Database error while logging trade: {e}")
    finally:
        if conn:
            conn.close()

# --- EXACT SIGNAL GENERATION LOGIC FROM FILE 1 ---
def total_signal(df, current_candle):
    """
    Exact copy of signal generation logic from File 1 (Analysis Script)
    """
    current_pos = df.index.get_loc(current_candle)
    if current_pos < 3:
        return 0
    
    # Buy signal conditions (exactly as in File 1)
    c1 = df['High'].iloc[current_pos] > df['High'].iloc[current_pos-1]
    c2 = df['High'].iloc[current_pos-1] > df['Low'].iloc[current_pos]
    c3 = df['Low'].iloc[current_pos] > df['High'].iloc[current_pos-2]
    c4 = df['High'].iloc[current_pos-2] > df['Low'].iloc[current_pos-1]
    c5 = df['Low'].iloc[current_pos-1] > df['High'].iloc[current_pos-3]
    c6 = df['High'].iloc[current_pos-3] > df['Low'].iloc[current_pos-2]
    c7 = df['Low'].iloc[current_pos-2] > df['Low'].iloc[current_pos-3]
    
    if c1 and c2 and c3 and c4 and c5 and c6 and c7:
        return 2
    
    # Sell signal conditions (exactly as in File 1)
    c1 = df['Low'].iloc[current_pos] < df['Low'].iloc[current_pos-1]
    c2 = df['Low'].iloc[current_pos-1] < df['High'].iloc[current_pos]
    c3 = df['High'].iloc[current_pos] < df['Low'].iloc[current_pos-2]
    c4 = df['Low'].iloc[current_pos-2] < df['High'].iloc[current_pos-1]
    c5 = df['High'].iloc[current_pos-1] < df['Low'].iloc[current_pos-3]
    c6 = df['Low'].iloc[current_pos-3] < df['High'].iloc[current_pos-2]
    c7 = df['High'].iloc[current_pos-2] < df['High'].iloc[current_pos-3]
    
    if c1 and c2 and c3 and c4 and c5 and c6 and c7:
        return 1
    
    return 0

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger()

class BinanceFuturesBot:
    def __init__(self, api_key, api_secret, symbol, interval, leverage=10):
        self.symbol = symbol
        self.interval = interval
        self.leverage = leverage
        self.client = Client(api_key, api_secret)
        self.current_position = None
        self.entry_price = 0

    def setup_futures_account(self):
        """Set up the futures account with the specified leverage"""
        try:
            # Set margin type to ISOLATED
            self.client.futures_change_margin_type(symbol=self.symbol, marginType='ISOLATED')
        except BinanceAPIException as e:
            if "Already" not in str(e):
                logger.error(f"Error setting margin type: {e}")
        
        try:
            # Set leverage
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
                    elif amt < 0:
                        self.current_position = 'SHORT'
                        self.entry_price = float(position['entryPrice'])
                    else:
                        self.current_position = None
                        self.entry_price = 0
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
        
        price_precision = 2  # Default precision
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
        
        qty_precision = 0  # Default precision
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

    def calculate_position_size_full_capital(self):
        """Calculate position size using full available capital with leverage"""
        balance = self.fetch_account_balance()
        
        # Use 95% of available balance (leave 5% as buffer for fees and margin requirements)
        usable_capital = balance * (95.0 / 100)
        
        # Get current price
        ticker = self.client.futures_symbol_ticker(symbol=self.symbol)
        current_price = float(ticker['price'])
        
        # Calculate position size using leverage
        # With leverage, we can control a position worth: usable_capital * leverage
        position_value_usd = usable_capital * self.leverage
        position_size_coins = position_value_usd / current_price
        
        # Round position size to correct precision
        position_size_coins = self.round_quantity(position_size_coins)
        
        # Ensure minimum position size
        symbol_info = self.get_symbol_info()
        if symbol_info:
            for filter in symbol_info['filters']:
                if filter['filterType'] == 'LOT_SIZE':
                    min_qty = float(filter['minQty'])
                    if position_size_coins < min_qty:
                        position_size_coins = min_qty
                        logger.warning(f"Position size adjusted to minimum: {min_qty}")
                    break
        
        logger.info(f"Available balance: ${balance:.2f}")
        logger.info(f"Usable capital (95%): ${usable_capital:.2f}")
        logger.info(f"Position value with {self.leverage}x leverage: ${position_value_usd:.2f}")
        logger.info(f"Position size: {position_size_coins} coins")
        
        return position_size_coins

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
            
            # Convert types
            df['OpenTime'] = pd.to_datetime(df['OpenTime'], unit='ms')
            
            for col in ['Open', 'High', 'Low', 'Close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Set index to OpenTime
            df.set_index('OpenTime', inplace=True)
            
            return df
        except BinanceAPIException as e:
            logger.error(f"Error fetching candles: {e}")
            return None

    def get_signal(self):
        """
        Get the current trading signal using EXACT same logic as File 1
        """
        df = self.fetch_latest_candles(num_candles=4)
        if df is None or len(df) < 4:
            logger.error("Not enough candles to generate signal")
            return 0
        
        # Current candle is the last one in the dataframe
        current_candle = df.index[-1]
        
        # Use the exact same total_signal function from File 1
        signal = total_signal(df, current_candle)
        
        # Log signal details for debugging
        if signal == 2:
            logger.info("BUY signal detected using File 1 logic")
        elif signal == 1:
            logger.info("SELL signal detected using File 1 logic")
        else:
            logger.debug("No signal detected")
        
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
        
        # Get current price
        current_price = self.get_current_price()
        if current_price is None:
            logger.error("Failed to get current price. Aborting trade execution.")
            return
        
        # Handle buy signal
        if signal == 2:  # Buy signal
            if current_position == 'SHORT':
                logger.info("Closing SHORT position before opening LONG")
                self.close_position()
                time.sleep(2)  # Give time for position to close
            
            if current_position != 'LONG':
                self.open_long_position(current_price)
        
        # Handle sell signal
        elif signal == 1:  # Sell signal
            if current_position == 'LONG':
                logger.info("Closing LONG position before opening SHORT")
                self.close_position()
                time.sleep(2)  # Give time for position to close
            
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
        """Open a long position using full capital"""
        try:
            # Get fresh market price to ensure accuracy
            latest_price = self.get_current_price()
            if latest_price is None:
                logger.error("Failed to get latest price. Aborting long position.")
                return
            
            # Calculate position size using full capital
            position_size = self.calculate_position_size_full_capital()
            
            if position_size <= 0:
                logger.error("Invalid position size calculated. Aborting.")
                return
            
            # Calculate stop loss and take profit prices
            stop_loss = latest_price * (1 - 2.0/100)
            take_profit = latest_price * (1 + 3.0/100)
            
            # Round prices to appropriate precision
            stop_loss = self.round_price(stop_loss)
            take_profit = self.round_price(take_profit)
            
            # Validate against price filters
            stop_loss = self.check_price_filter(stop_loss)
            take_profit = self.check_price_filter(take_profit)
            
            logger.info(f"Opening LONG position at {latest_price}")
            logger.info(f"Position size: {position_size} {self.symbol.replace('USDT', '')}")
            logger.info(f"Stop loss: {stop_loss}, Take profit: {take_profit}")
            logger.info(f"WARNING: Using full capital with {self.leverage}x leverage - HIGH RISK!")
            
            # Open position with market order
            order = self.client.futures_create_order(
                symbol=self.symbol,
                side='BUY',
                type='MARKET',
                quantity=position_size
            )
            
            # Wait for order to be processed
            time.sleep(2)
            
            # Get current position details to confirm order execution
            current_position, position_amt = self.get_current_position()
            if current_position != 'LONG' or position_amt <= 0:
                logger.warning("Long position order may not have executed properly.")
                return
            
            try:
                # Set stop loss order
                sl_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='SELL',
                    type='STOP_MARKET',
                    stopPrice=stop_loss,
                    closePosition='true'
                )
                logger.info(f"Stop loss set at {stop_loss}: {sl_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting stop loss: {e}")
                if "would trigger immediately" in str(e):
                    logger.warning("Adjusting stop loss further to prevent immediate trigger.")
                    stop_loss = latest_price * (1 - (2.0 * 1.5)/100)
                    stop_loss = self.round_price(stop_loss)
                    try:
                        sl_order = self.client.futures_create_order(
                            symbol=self.symbol,
                            side='SELL',
                            type='STOP_MARKET',
                            stopPrice=stop_loss,
                            closePosition='true'
                        )
                        logger.info(f"Adjusted stop loss set at {stop_loss}: {sl_order['orderId']}")
                    except BinanceAPIException as e2:
                        logger.error(f"Failed to set adjusted stop loss: {e2}")
            
            try:
                # Set take profit order
                tp_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='SELL',
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=take_profit,
                    closePosition='true'
                )
                logger.info(f"Take profit set at {take_profit}: {tp_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting take profit: {e}")
                if "would trigger immediately" in str(e):
                    logger.warning("Adjusting take profit further to prevent immediate trigger.")
                    take_profit = latest_price * (1 + (3.0 * 1.5)/100)
                    take_profit = self.round_price(take_profit)
                    try:
                        tp_order = self.client.futures_create_order(
                            symbol=self.symbol,
                            side='SELL',
                            type='TAKE_PROFIT_MARKET',
                            stopPrice=take_profit,
                            closePosition='true'
                        )
                        logger.info(f"Adjusted take profit set at {take_profit}: {tp_order['orderId']}")
                    except BinanceAPIException as e2:
                        logger.error(f"Failed to set adjusted take profit: {e2}")
            
            logger.info(f"LONG position opened with order: {order['orderId']}")
            self.current_position = 'LONG'
            
        except BinanceAPIException as e:
            logger.error(f"Error opening long position: {e}")
        except Exception as e:
            logger.error(f"Unexpected error opening long position: {e}")

    def open_short_position(self, current_price):
        """Open a short position using full capital"""
        try:
            # Get fresh market price to ensure accuracy
            latest_price = self.get_current_price()
            if latest_price is None:
                logger.error("Failed to get latest price. Aborting short position.")
                return
            
            # Calculate position size using full capital
            position_size = self.calculate_position_size_full_capital()
            
            if position_size <= 0:
                logger.error("Invalid position size calculated. Aborting.")
                return
            
            # Calculate stop loss and take profit prices
            stop_loss = latest_price * (1 + 2.0/100)
            take_profit = latest_price * (1 - 3.0/100)
            
            # Round prices to appropriate precision
            stop_loss = self.round_price(stop_loss)
            take_profit = self.round_price(take_profit)
            
            # Validate against price filters
            stop_loss = self.check_price_filter(stop_loss)
            take_profit = self.check_price_filter(take_profit)
            
            logger.info(f"Opening SHORT position at {latest_price}")
            logger.info(f"Position size: {position_size} {self.symbol.replace('USDT', '')}")
            logger.info(f"Stop loss: {stop_loss}, Take profit: {take_profit}")
            logger.info(f"WARNING: Using full capital with {self.leverage}x leverage - HIGH RISK!")
            
            # Open position with market order
            order = self.client.futures_create_order(
                symbol=self.symbol,
                side='SELL',
                type='MARKET',
                quantity=position_size
            )
            
            # Wait for order to be processed
            time.sleep(2)
            
            # Get current position details to confirm order execution
            current_position, position_amt = self.get_current_position()
            if current_position != 'SHORT' or position_amt >= 0:
                logger.warning("Short position order may not have executed properly.")
                return
            
            try:
                # Set stop loss order
                sl_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='BUY',
                    type='STOP_MARKET',
                    stopPrice=stop_loss,
                    closePosition='true'
                )
                logger.info(f"Stop loss set at {stop_loss}: {sl_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting stop loss: {e}")
                if "would trigger immediately" in str(e):
                    logger.warning("Adjusting stop loss further to prevent immediate trigger.")
                    stop_loss = latest_price * (1 + (2.0 * 1.5)/100)
                    stop_loss = self.round_price(stop_loss)
                    try:
                        sl_order = self.client.futures_create_order(
                            symbol=self.symbol,
                            side='BUY',
                            type='STOP_MARKET',
                            stopPrice=stop_loss,
                            closePosition='true'
                        )
                        logger.info(f"Adjusted stop loss set at {stop_loss}: {sl_order['orderId']}")
                    except BinanceAPIException as e2:
                        logger.error(f"Failed to set adjusted stop loss: {e2}")
            
            try:
                # Set take profit order
                tp_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side='BUY',
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=take_profit,
                    closePosition='true'
                )
                logger.info(f"Take profit set at {take_profit}: {tp_order['orderId']}")
            except BinanceAPIException as e:
                logger.error(f"Error setting take profit: {e}")
                if "would trigger immediately" in str(e):
                    logger.warning("Adjusting take profit further to prevent immediate trigger.")
                    take_profit = latest_price * (1 - (3.0 * 1.5)/100)
                    take_profit = self.round_price(take_profit)
                    try:
                        tp_order = self.client.futures_create_order(
                            symbol=self.symbol,
                            side='BUY',
                            type='TAKE_PROFIT_MARKET',
                            stopPrice=take_profit,
                            closePosition='true'
                        )
                        logger.info(f"Adjusted take profit set at {take_profit}: {tp_order['orderId']}")
                    except BinanceAPIException as e2:
                        logger.error(f"Failed to set adjusted take profit: {e2}")
            
            logger.info(f"SHORT position opened with order: {order['orderId']}")
            self.current_position = 'SHORT'
            
        except BinanceAPIException as e:
            logger.error(f"Error opening short position: {e}")
        except Exception as e:
            logger.error(f"Unexpected error opening short position: {e}")

    def close_position(self):
        """Close the current position and log the trade."""
        try:
            current_position, position_amt = self.get_current_position()
            if current_position is None or position_amt == 0:
                logger.info("No position to close")
                return

            self.client.futures_cancel_all_open_orders(symbol=self.symbol)
            logger.info("Cancelled all open orders")

            side = 'SELL' if current_position == 'LONG' else 'BUY'
            quantity = abs(position_amt)
            
            # Get the exit price *before* closing
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
                else: # SHORT
                    profit = (self.entry_price - exit_price) * quantity
            
            # Log to database
            log_trade_to_db(self.symbol, current_position, quantity, self.entry_price, exit_price, profit)

            logger.info(f"Closed {current_position} position: {order['orderId']} with PnL: {profit}")
            self.current_position = None
            self.entry_price = 0

        except BinanceAPIException as e:
            logger.error(f"Error closing position: {e}")
        except Exception as e:
            logger.error(f"Unexpected error closing position: {e}")

    def run(self, interval_seconds=60):
        """Run the trading bot"""
        logger.info(f"Starting trading bot for {self.symbol} with {self.leverage}x leverage")
        logger.info("Signal generation logic now matches File 1 exactly!")
        self.setup_futures_account()
        
        try:
            while True:
                try:
                    signal = self.get_signal()
                    if signal > 0:
                        logger.info(f"Signal detected: {'BUY' if signal == 2 else 'SELL'}")
                        self.execute_trade(signal)
                    else:
                        logger.info("No trading signal")
                    
                    time.sleep(interval_seconds)
                except BinanceAPIException as e:
                    logger.error(f"Binance API error: {e}")
                    time.sleep(30)
                except Exception as e:
                    logger.error(f"Error in bot loop: {e}")
                    time.sleep(30)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            self.close_position()

# Example usage
if __name__ == "__main__":
    # Replace with your actual API credentials
    API_KEY = "your api key"
    API_SECRET = "your api secret"
    
    # Initialize the bot
    bot = BinanceFuturesBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol='DOGEUSDT',
        interval=Client.KLINE_INTERVAL_1HOUR,
        leverage=10
    )
    
    # Run the bot
    bot.run(interval_seconds=60)