"""
Trading Bot REST API

Provides RESTful endpoints to query:
- Current open positions
- Position history
- PNL summaries
- Processed messages and actions
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta, timezone
from binance.client import Client
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Database connection
DB_NAME = 'improved_trading_bot.db'

# Binance client (for real-time price data)
BINANCE_API_KEY = '9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ'
BINANCE_API_SECRET = 'mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl'
binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def get_current_price(symbol):
    """Get current price from Binance"""
    try:
        ticker = binance_client.futures_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {e}")
        return None

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM messages")
        message_count = cursor.fetchone()[0]
        
        # Get last message processed time
        cursor.execute("SELECT MAX(fetched_at) FROM messages WHERE processed = 1")
        last_processed = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'total_messages': message_count,
            'last_processed_at': last_processed,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/api/positions', methods=['GET'])
def get_open_positions():
    """Get all currently open positions from Binance Futures"""
    try:
        # Fetch positions directly from Binance
        binance_positions = binance_client.futures_position_information()
        
        positions = []
        for pos in binance_positions:
            # Only include positions that are actually open (have quantity)
            position_amt = float(pos['positionAmt'])
            if abs(position_amt) > 0:
                symbol = pos['symbol']
                entry_price = float(pos['entryPrice'])
                current_price = float(pos['markPrice'])  # Mark price (more accurate than last price)
                unrealized_pnl = float(pos['unRealizedProfit'])
                
                # Calculate PNL percentage
                if entry_price > 0:
                    pnl_percentage = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_percentage = 0
                
                # Get additional info from database if available
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, opened_at, highest_price, binance_order_id, current_stop_loss, take_profit, leverage
                    FROM positions 
                    WHERE symbol = ? AND status = 'open'
                    ORDER BY opened_at DESC LIMIT 1
                """, (symbol,))
                db_row = cursor.fetchone()
                conn.close()
                
                # Get leverage from database or default to position's leverage value
                leverage = db_row['leverage'] if db_row and db_row['leverage'] else int(float(pos.get('leverage', 1)))
                
                positions.append({
                    'id': db_row['id'] if db_row else None,
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'stop_loss': db_row['current_stop_loss'] if db_row else None,
                    'take_profit': db_row['take_profit'] if db_row else None,
                    'quantity': abs(position_amt),
                    'leverage': leverage,
                    'pnl_usdt': unrealized_pnl,
                    'pnl_percentage': pnl_percentage,
                    'highest_price': db_row['highest_price'] if db_row else None,
                    'opened_at': db_row['opened_at'] if db_row else None,
                    'binance_order_id': db_row['binance_order_id'] if db_row else None,
                    'last_synced_at': datetime.now(timezone.utc).isoformat(),
                    'position_side': pos.get('positionSide', 'BOTH'),
                    'liquidation_price': float(pos.get('liquidationPrice', 0)),
                    'margin_type': pos.get('marginType', 'cross'),
                    'isolated_margin': float(pos.get('isolatedMargin', 0)) if pos.get('marginType') == 'isolated' else None
                })
        
        return jsonify({
            'count': len(positions),
            'positions': positions,
            'data_source': 'binance_futures_live'
        })
    except Exception as e:
        logger.error(f"Error getting open positions from Binance: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions/history', methods=['GET'])
def get_position_history():
    """Get closed positions (history)"""
    try:
        # Get query parameters
        symbol = request.args.get('symbol')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        status =  request.args.get('status')  # 'won' or 'lost'
        limit = request.args.get('limit', 100, type=int)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if exit_price column exists (for backward compatibility)
        cursor.execute("PRAGMA table_info(positions)")
        columns = [column[1] for column in cursor.fetchall()]
        has_exit_price = 'exit_price' in columns
        
        # Build query based on available columns
        if has_exit_price:
            query = """
                SELECT 
                    id, symbol, entry_price, exit_price, quantity, leverage,
                    opened_at, closed_at, profit_percentage, close_reason,
                    binance_order_id
                FROM positions 
                WHERE status = 'closed'
            """
        else:
            query = """
                SELECT 
                    id, symbol, entry_price, quantity, leverage,
                    opened_at, closed_at, profit_percentage, close_reason,
                    binance_order_id
                FROM positions 
                WHERE status = 'closed'
            """
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if start_date:
            query += " AND closed_at >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND closed_at < ?"
            params.append(end_date)
        
        if status == 'won':
            query += " AND profit_percentage > 0"
        elif status == 'lost':
            query += " AND profit_percentage <= 0"
        
        query += f" ORDER BY closed_at DESC LIMIT {limit}"
        
        cursor.execute(query, params)
        
        positions = []
        for row in cursor.fetchall():
            entry_price = row['entry_price']
            profit_pct = row['profit_percentage'] or 0
            quantity = row['quantity']
            
            # Use actual exit_price if available (new records), otherwise calculate (old records)
            exit_price = row.get('exit_price') if has_exit_price else None
            if not exit_price and profit_pct and entry_price:
                # Fallback calculation for old records without exit_price
                exit_price = entry_price * (1 + profit_pct / 100)
            
            # Calculate PNL in USDT
            if exit_price and entry_price and quantity:
                pnl_usdt = (exit_price - entry_price) * quantity
            else:
                pnl_usdt = None
            
            positions.append({
                'id': row['id'],
                'symbol': row['symbol'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'quantity': quantity,
                'leverage': row['leverage'],
                'pnl_usdt': pnl_usdt,
                'pnl_percentage': profit_pct,
                'opened_at': row['opened_at'],
                'closed_at': row['closed_at'],
                'close_reason': row['close_reason'],
                'binance_order_id': row['binance_order_id']
            })
        
        conn.close()
        
        return jsonify({
            'count': len(positions),
            'positions': positions
        })
    except Exception as e:
        logger.error(f"Error getting position history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions/<symbol>', methods=['GET'])
def get_symbol_positions(symbol):
    """Get all positions for a specific symbol"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current open position
        cursor.execute("""
            SELECT * FROM positions 
            WHERE symbol = ? AND status = 'open'
            ORDER BY opened_at DESC LIMIT 1
        """, (symbol,))
        
        open_position = cursor.fetchone()
        
        # Get historical positions
        cursor.execute("""
           SELECT * FROM positions 
            WHERE symbol = ? AND status = 'closed'
            ORDER BY closed_at DESC LIMIT 20
        """, (symbol,))
        
        history = [dict(row) for row in cursor.fetchall()]
        
        # Calculate win rate for this symbol
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN profit_percentage > 0 THEN 1 ELSE 0 END) as wins
            FROM positions
            WHERE symbol = ? AND status = 'closed'
        """, (symbol,))
        
        stats_row = cursor.fetchone()
        total_trades = stats_row['total'] or 0
        wins = stats_row['wins'] or 0
        win_rate = (wins / total_trades * 100) if total_trades >  0 else 0
        
        conn.close()
        
        result = {
            'symbol': symbol,
            'open_position': dict(open_position) if open_position else None,
            'history_count': len(history),
            'history': history,
            'stats': {
                'total_trades': total_trades,
                'wins': wins,
                'losses': total_trades - wins,
                'win_rate': round(win_rate, 2)
            }
        }
        
        # Add current price for open position
        if open_position:
            current_price = get_current_price(symbol)
            entry_price = open_position['entry_price']
            if current_price and entry_price:
                result['open_position']['current_price'] = current_price
                result['open_position']['current_pnl_%'] = ((current_price - entry_price) / entry_price) * 100
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting positions for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pnl/summary', methods=['GET'])
def get_pnl_summary():
    """Get overall PNL summary"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all closed positions
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_percentage > 0 THEN 1 ELSE 0 END) as wins,
                AVG(profit_percentage) as avg_profit_pct,
                SUM(profit_percentage * quantity * entry_price / 100) as total_pnl_usdt
            FROM positions
            WHERE status = 'closed'
        """)
        
        row = cursor.fetchone()
        total_trades = row['total_trades'] or 0
        wins = row['wins'] or 0
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        avg_profit_pct = row['avg_profit_pct'] or 0
        total_pnl = row['total_pnl_usdt'] or 0
        
        # Get best and worst trades
        cursor.execute("""
            SELECT symbol, profit_percentage, opened_at, closed_at
            FROM positions
            WHERE status = 'closed'
            ORDER BY profit_percentage DESC
            LIMIT 1
        """)
        best_trade = cursor.fetchone()
        
        cursor.execute("""
            SELECT symbol, profit_percentage, opened_at, closed_at
            FROM positions
            WHERE status = 'closed'
            ORDER BY profit_percentage ASC
            LIMIT 1
        """)
        worst_trade = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'avg_profit_percentage': round(avg_profit_pct, 2),
            'total_pnl_usdt': round(total_pnl, 2),
            'best_trade': dict(best_trade) if best_trade else None,
            'worst_trade': dict(worst_trade) if worst_trade else None
        })
    except Exception as e:
        logger.error(f"Error getting PNL summary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pnl/daily', methods=['GET'])
def get_daily_pnl():
    """Get daily PNL breakdown"""
    try:
        days = request.args.get('days', 30, type=int)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                DATE(closed_at) as date,
                COUNT(*) as trades,
                SUM(CASE WHEN profit_percentage > 0 THEN 1 ELSE 0 END) as wins,
                SUM(profit_percentage * quantity * entry_price / 100) as daily_pnl
            FROM positions
            WHERE status = 'closed' 
                AND closed_at >= datetime('now', '-' || ? || ' days')
            GROUP BY DATE(closed_at)
            ORDER BY date DESC
        """, (days,))
        
        daily_data = []
        for row in cursor.fetchall():
            trades = row['trades']
            daily_data.append({
                'date': row['date'],
                'trades': trades,
                'wins': row['wins'],
               'losses': trades - row['wins'],
                'pnl_usdt': round(row['daily_pnl'] or 0, 2)
            })
        
        conn.close()
        
        return jsonify({
            'period_days': days,
            'data': daily_data
        })
    except Exception as e:
        logger.error(f"Error getting daily PNL: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/messages', methods=['GET'])
def get_messages_and_actions():
    """Get processed messages and their actions"""
    try:
        # Get query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        action_type = request.args.get('action_type')
        symbol = request.args.get('symbol')
        limit = request.args.get('limit', 100, type=int)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if message_actions table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='message_actions'
        """)
        
        if cursor.fetchone():
            # New schema with message_actions table
            query = """
                SELECT 
                    message_id, message_text, message_date,
                    action_taken, action_details, symbol,
                    success, error_message, processed_at
                FROM message_actions
                WHERE 1=1
            """
            params = []
            
            if start_date:
                query += " AND message_date >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND message_date < ?"
                params.append(end_date)
            
            if action_type:
                query += " AND action_taken = ?"
                params.append(action_type)
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            query += f" ORDER BY processed_at DESC LIMIT {limit}"
            
            cursor.execute(query, params)
            messages = [dict(row) for row in cursor.fetchall()]
        else:
            # Fallback to old schema (messages + trading_actions)
            query = """
                SELECT 
                    m.message_id, m.message_text, m.message_date,
                    m.message_type as action_taken,
                    m.ai_analysis as action_details,
                    m.fetched_at as processed_at
                FROM messages m
                WHERE m.processed = 1
            """
            params = []
            
            if start_date:
                query += " AND m.message_date >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND m.message_date < ?"
                params.append(end_date)
            
            query += f" ORDER BY m.fetched_at DESC LIMIT {limit}"
            
            cursor.execute(query, params)
            messages = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            'count': len(messages),
            'messages': messages
        })
    except Exception as e:
        logger.error(f"Error getting messages:{human} {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 Starting Trading Bot API Server...")
    logger.info("API will be available at http://localhost:5000")
    logger.info("\nAvailable endpoints:")
    logger.info("  GET /api/health - Health check")
    logger.info("  GET /api/positions - Current open positions")
    logger.info("  GET /api/positions/history - Historical positions")
    logger.info("  GET /api/positions/<symbol> - Positions for specific symbol")
    logger.info("  GET /api/pnl/summary - Overall PNL summary")
    logger.info("  GET /api/pnl/daily - Daily PNL breakdown")
    logger.info("  GET /api/messages - Processed messages and actions")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
