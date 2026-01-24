import sys
import os
import traceback

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trader import BINANCE_CONFIG, BinanceTrader

def test_binance_connection():
    print("Testing Binance Connection...")
    print(f"Testnet: {BINANCE_CONFIG['testnet']}")
    
    try:
        # Initialize Trader (which initializes Client and syncs time)
        trader = BinanceTrader(
            api_key=BINANCE_CONFIG['api_key'],
            api_secret=BINANCE_CONFIG['api_secret'],
            testnet=BINANCE_CONFIG['testnet']
        )
        
        print("\n1. Testing Server Time Sync...")
        server_time = trader.client.get_server_time()
        print(f"Server Time: {server_time['serverTime']}")
        
        print("\n2. Testing Account Balance...")
        balance = trader.get_account_balance()
        print(f"USDT Balance: {balance}")
        
        print("\n3. Testing Symbol Ticker (BTCUSDT)...")
        price = trader.get_current_price('BTCUSDT')
        print(f"BTCUSDT Price: {price}")
        
        print("\n✅ Binance Connection Successful")
        
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_binance_connection()
