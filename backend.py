from flask import Flask, jsonify, request
from flask_cors import CORS
from binance.client import Client
from binance.exceptions import BinanceAPIException
import sqlite3
import datetime
import json
import logging
from typing import Dict, List, Optional
 
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=['https://traderdashbord.onrender.com', 'http://localhost:3000'])  # Add localhost for development

# --- IMPORTANT ---
# Store your API keys securely. Using environment variables is a good practice.
API_KEY = "9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ"
API_SECRET = "mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl"

client = Client(API_KEY, API_SECRET)

def get_db_connection():
    """Creates a connection to the SQLite database."""
    conn = sqlite3.connect('trades.db')
    conn.row_factory = sqlite3.Row
    return conn

def safe_float(value, default=0.0):
    """Safely convert value to float."""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

@app.route('/api/balance', methods=['GET'])
def get_balance():
    """Endpoint to get the futures account balance."""
    try:
        account_info = client.futures_account_balance()
        usdt_balance = 0
        for asset in account_info:
            if asset['asset'] == 'USDT':
                usdt_balance = float(asset['balance'])
                break
        return jsonify({'balance': usdt_balance})
    except BinanceAPIException as e:
        logger.error(f"Binance API error in get_balance: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_balance: {e}")
        return jsonify({'error': f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/api/position', methods=['GET'])
def get_current_position():
    """Endpoint to get current position information."""
    try:
        symbol = request.args.get('symbol', 'BTCUSDT')
        positions = client.futures_position_information(symbol=symbol)
        
        current_position = None
        position_amt = 0
        entry_price = 0
        unrealized_pnl = 0
        
        for position in positions:
            if position['symbol'] == symbol:
                amt = float(position['positionAmt'])
                if amt > 0:
                    current_position = 'LONG'
                    position_amt = amt
                    entry_price = float(position['entryPrice'])
                    unrealized_pnl = float(position['unRealizedProfit'])
                elif amt < 0:
                    current_position = 'SHORT'
                    position_amt = abs(amt)
                    entry_price = float(position['entryPrice'])
                    unrealized_pnl = float(position['unRealizedProfit'])
                break
        
        return jsonify({
            'current_position': current_position,
            'position_amt': position_amt,
            'entry_price': entry_price,
            'unrealized_pnl': unrealized_pnl,
            'symbol': symbol
        })
    except BinanceAPIException as e:
        logger.error(f"Binance API error in get_current_position: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_current_position: {e}")
        return jsonify({'error': f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/api/bot-status', methods=['GET'])
def get_bot_status():
    """Endpoint to get bot status information."""
    try:
        # Get current position
        symbol = 'BTCUSDT'  # Default symbol
        positions = client.futures_position_information(symbol=symbol)
        
        current_position = None
        for position in positions:
            if position['symbol'] == symbol:
                amt = float(position['positionAmt'])
                if amt > 0:
                    current_position = 'LONG'
                elif amt < 0:
                    current_position = 'SHORT'
                break
        
        # Get account balance
        account_info = client.futures_account_balance()
        usdt_balance = 0
        for asset in account_info:
            if asset['asset'] == 'USDT':
                usdt_balance = float(asset['balance'])
                break
        
        # Get last trade to determine last signal
        conn = get_db_connection()
        try:
            last_trade = conn.execute(
                'SELECT side FROM trades ORDER BY timestamp DESC LIMIT 1'
            ).fetchone()
            last_signal = 'BUY' if last_trade and last_trade['side'] == 'LONG' else 'SELL'
        finally:
            conn.close()
        
        return jsonify({
            'isRunning': True,  # You can implement logic to check if bot is actually running
            'currentPosition': current_position,
            'currentSymbol': symbol,
            'leverage': 10,  # Default leverage from your bot
            'balance': usdt_balance,
            'lastSignal': last_signal,
            'lastUpdate': datetime.datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in get_bot_status: {e}")
        return jsonify({'error': f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/api/trades', methods=['GET'])
def get_trades():
    """Endpoint to get all trades from the database."""
    conn = get_db_connection()
    try:
        # Get query parameters
        limit = request.args.get('limit', type=int)
        days = request.args.get('days', type=int)
        
        query = 'SELECT * FROM trades'
        params = []
        
        if days:
            query += ' WHERE timestamp >= datetime("now", "-{} days")'.format(days)
        
        query += ' ORDER BY timestamp DESC'
        
        if limit:
            query += ' LIMIT ?'
            params.append(limit)
        
        trades = conn.execute(query, params).fetchall()
        
        trades_list = []
        for trade in trades:
            trades_list.append({
                'id': trade['id'],
                'symbol': trade['symbol'],
                'side': trade['side'],
                'quantity': safe_float(trade['quantity']),
                'entry_price': safe_float(trade['entry_price']),
                'exit_price': safe_float(trade['exit_price']),
                'profit': safe_float(trade['profit']),
                'timestamp': trade['timestamp']
            })
        
        return jsonify(trades_list)
    except sqlite3.Error as e:
        logger.error(f"Database error in get_trades: {e}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/performance-metrics', methods=['GET'])
def get_performance_metrics():
    """Endpoint to get comprehensive performance metrics."""
    conn = get_db_connection()
    try:
        # Get all trades
        trades = conn.execute('SELECT * FROM trades ORDER BY timestamp ASC').fetchall()
        
        if not trades:
            return jsonify({
                'totalProfit': 0,
                'totalTrades': 0,
                'winningTrades': 0,
                'losingTrades': 0,
                'winRate': 0,
                'avgWin': 0,
                'avgLoss': 0,
                'profitFactor': 0,
                'maxDrawdown': 0,
                'sharpeRatio': 0
            })
        
        # Calculate metrics
        total_profit = sum(safe_float(trade['profit']) for trade in trades)
        total_trades = len(trades)
        
        winning_trades = [trade for trade in trades if safe_float(trade['profit']) > 0]
        losing_trades = [trade for trade in trades if safe_float(trade['profit']) < 0]
        
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        
        win_rate = (winning_count / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = sum(safe_float(trade['profit']) for trade in winning_trades) / winning_count if winning_count > 0 else 0
        avg_loss = sum(safe_float(trade['profit']) for trade in losing_trades) / losing_count if losing_count > 0 else 0
        
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        # Calculate max drawdown
        max_drawdown = calculate_max_drawdown(trades)
        
        # Calculate Sharpe ratio
        sharpe_ratio = calculate_sharpe_ratio(trades)
        
        return jsonify({
            'totalProfit': round(total_profit, 2),
            'totalTrades': total_trades,
            'winningTrades': winning_count,
            'losingTrades': losing_count,
            'winRate': round(win_rate, 1),
            'avgWin': round(avg_win, 2),
            'avgLoss': round(avg_loss, 2),
            'profitFactor': round(profit_factor, 2),
            'maxDrawdown': round(max_drawdown, 2),
            'sharpeRatio': round(sharpe_ratio, 2) if sharpe_ratio != 'N/A' else 'N/A'
        })
    except sqlite3.Error as e:
        logger.error(f"Database error in get_performance_metrics: {e}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()

def calculate_max_drawdown(trades):
    """Calculate maximum drawdown from trades."""
    if not trades:
        return 0
    
    running_sum = 0
    peak = 0
    max_drawdown = 0
    
    for trade in trades:
        profit = safe_float(trade['profit'])
        running_sum += profit
        if running_sum > peak:
            peak = running_sum
        drawdown = peak - running_sum
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    return max_drawdown

def calculate_sharpe_ratio(trades):
    """Calculate Sharpe ratio from trades."""
    if len(trades) < 2:
        return 'N/A'
    
    returns = [safe_float(trade['profit']) for trade in trades]
    avg_return = sum(returns) / len(returns)
    
    variance = sum((ret - avg_return) ** 2 for ret in returns) / len(returns)
    std_dev = variance ** 0.5
    
    return avg_return / std_dev if std_dev != 0 else 'N/A'

@app.route('/api/chart-data', methods=['GET'])
def get_chart_data():
    """Endpoint to get data formatted for charts."""
    conn = get_db_connection()
    try:
        trades = conn.execute('SELECT * FROM trades ORDER BY timestamp ASC').fetchall()
        
        chart_data = []
        cumulative_profit = 0
        
        for i, trade in enumerate(trades):
            profit = safe_float(trade['profit'])
            cumulative_profit += profit
            
            chart_data.append({
                'trade': i + 1,
                'profit': profit,
                'cumulativeProfit': round(cumulative_profit, 2),
                'timestamp': trade['timestamp'],
                'side': trade['side'],
                'symbol': trade['symbol']
            })
        
        return jsonify(chart_data)
    except sqlite3.Error as e:
        logger.error(f"Database error in get_chart_data: {e}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/side-distribution', methods=['GET'])
def get_side_distribution():
    """Endpoint to get LONG vs SHORT distribution."""
    conn = get_db_connection()
    try:
        long_count = conn.execute('SELECT COUNT(*) as count FROM trades WHERE side = "LONG"').fetchone()['count']
        short_count = conn.execute('SELECT COUNT(*) as count FROM trades WHERE side = "SHORT"').fetchone()['count']
        
        return jsonify([
            {'name': 'LONG', 'value': long_count, 'color': '#10B981'},
            {'name': 'SHORT', 'value': short_count, 'color': '#EF4444'}
        ])
    except sqlite3.Error as e:
        logger.error(f"Database error in get_side_distribution: {e}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/profit', methods=['GET'])
def get_profit():
    """Endpoint to get total profit from the database."""
    conn = get_db_connection()
    try:
        profit_data = conn.execute('SELECT SUM(profit) as total_profit FROM trades').fetchone()
        total_profit = safe_float(profit_data['total_profit'])
        return jsonify({'total_profit': total_profit})
    except sqlite3.Error as e:
        logger.error(f"Database error in get_profit: {e}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/daily-stats', methods=['GET'])
def get_daily_stats():
    """Endpoint to get daily trading statistics."""
    conn = get_db_connection()
    try:
        daily_stats = conn.execute('''
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as trades_count,
                SUM(profit) as daily_profit,
                AVG(profit) as avg_profit
            FROM trades 
            WHERE timestamp >= datetime('now', '-30 days')
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        ''').fetchall()
        
        stats_list = []
        for stat in daily_stats:
            stats_list.append({
                'date': stat['date'],
                'trades_count': stat['trades_count'],
                'daily_profit': round(safe_float(stat['daily_profit']), 2),
                'avg_profit': round(safe_float(stat['avg_profit']), 2)
            })
        
        return jsonify(stats_list)
    except sqlite3.Error as e:
        logger.error(f"Database error in get_daily_stats: {e}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/current-price', methods=['GET'])
def get_current_price():
    """Endpoint to get current price for a symbol."""
    try:
        symbol = request.args.get('symbol', 'BTCUSDT')
        ticker = client.futures_symbol_ticker(symbol=symbol)
        return jsonify({
            'symbol': symbol,
            'price': float(ticker['price'])
        })
    except BinanceAPIException as e:
        logger.error(f"Binance API error in get_current_price: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_current_price: {e}")
        return jsonify({'error': f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.datetime.now().isoformat(),
        'version': '1.0.0'
    })

def init_db():
    """Initializes the database and creates the trades table if it doesn't exist."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                profit REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        logger.info("Database initialized.")
    except sqlite3.Error as e:
        logger.error(f"Database error on initialization: {e}")
    finally:
        conn.close()

def clear_trades_if_new_month():
    """Clears trades if a new month has started."""
    conn = get_db_connection()
    try:
        # Create a table to store the last cleared month if it doesn't exist
        conn.execute('''
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()

        # Get the last cleared month
        cur = conn.execute("SELECT value FROM meta WHERE key = 'last_cleared_month'")
        row = cur.fetchone()
        current_month = datetime.datetime.now().strftime('%Y-%m')
        last_cleared_month = row['value'] if row else None

        if last_cleared_month != current_month:
            # Clear trades table
            conn.execute('DELETE FROM trades')
            conn.commit()
            # Update last cleared month
            conn.execute("REPLACE INTO meta (key, value) VALUES (?, ?)", ('last_cleared_month', current_month))
            conn.commit()
            logger.info(f"Trades table cleared for new month: {current_month}")
    except Exception as e:
        logger.error(f"Error clearing trades for new month: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    clear_trades_if_new_month()
    # Note: For production, use a proper WSGI server like Gunicorn or Waitress
    app.run(host='0.0.0.0', port=5000, debug=True)