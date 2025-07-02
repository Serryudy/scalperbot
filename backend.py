from flask import Flask, jsonify
from flask_cors import CORS
from binance.client import Client
from binance.exceptions import BinanceAPIException
import sqlite3

# --- IMPORTANT ---
# Store your API keys securely. Using environment variables is a good practice.
# For this example, I'm leaving them here, but you should change this.
API_KEY = "9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ"
API_SECRET = "mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl"

app = Flask(__name__)
CORS(app)  # This will allow the React frontend to make requests to the backend

client = Client(API_KEY, API_SECRET)

def get_db_connection():
    """Creates a connection to the SQLite database."""
    conn = sqlite3.connect('trades.db')
    conn.row_factory = sqlite3.Row
    return conn

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
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': f"An unexpected error occurred: {str(e)}"}), 500


@app.route('/api/profit', methods=['GET'])
def get_profit():
    """Endpoint to get total profit from the database."""
    conn = get_db_connection()
    try:
        profit_data = conn.execute('SELECT SUM(profit) as total_profit FROM trades').fetchone()
        total_profit = profit_data['total_profit'] if profit_data['total_profit'] else 0
        return jsonify({'total_profit': total_profit})
    except sqlite3.Error as e:
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/trades', methods=['GET'])
def get_trades():
    """Endpoint to get all trades from the database."""
    conn = get_db_connection()
    try:
        trades = conn.execute('SELECT * FROM trades ORDER BY timestamp DESC').fetchall()
        return jsonify([dict(ix) for ix in trades])
    except sqlite3.Error as e:
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        conn.close()


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
        print("Database initialized.")
    except sqlite3.Error as e:
        print(f"Database error on initialization: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()
    # Note: For production, use a proper WSGI server like Gunicorn or Waitress
    app.run(host='0.0.0.0', port=5000, debug=True)
