"""
Standalone Test Script: Close 50% of XVGUSDT Position on Binance Demo Account

This script tests the partial close functionality independently.
Run this to verify partial closing works on testnet.
"""

from binance.client import Client
from binance.enums import *
import time

# Binance Demo/Testnet API Credentials
API_KEY = 'NPCpHKP3Qi5GyEWlfknmrbipXXg6NbBULsfseqaDzsZ5LYjigQmydblIP9ZgvHs7'
API_SECRET = 'dmZmE6NNzZcw6Dyx0blRlZYy1PziJccvUVUAjyPUsRyohc3cDttjdsbSNpyM5vXs'
SYMBOL = 'XVGUSDT'
PARTIAL_PERCENTAGE = 50  # Close 50%

def main():
    print("=" * 80)
    print("🧪 PARTIAL CLOSE TEST - BINANCE TESTNET")
    print("=" * 80)
    
    # Initialize client with testnet=True
    client = Client(API_KEY, API_SECRET, testnet=True)
    
    # Sync time with Binance
    try:
        server_time = client.get_server_time()
        local_time = int(time.time() * 1000)
        client.timestamp_offset = server_time['serverTime'] - local_time
        print(f"✅ Time synced with Binance (offset: {client.timestamp_offset}ms)\n")
    except Exception as e:
        print(f"⚠️ Warning: Could not sync time: {e}\n")
    
    # Step 1: Get current position
    print(f"📊 Checking current {SYMBOL} position on testnet...\n")
    
    try:
        positions = client.futures_position_information(symbol=SYMBOL)
        
        position_found = False
        for pos in positions:
            if pos['symbol'] == SYMBOL:
                position_amt = float(pos['positionAmt'])
                
                if position_amt != 0:
                    position_found = True
                    entry_price = float(pos['entryPrice'])
                    mark_price = float(pos['markPrice'])
                    unrealized_pnl = float(pos['unRealizedProfit'])
                    
                    print(f"✅ OPEN POSITION FOUND:")
                    print(f"   Symbol: {SYMBOL}")
                    print(f"   Position Amount: {position_amt}")
                    print(f"   Entry Price: ${entry_price}")
                    print(f"   Mark Price: ${mark_price}")
                    print(f"   Unrealized PNL: ${unrealized_pnl}")
                    print(f"   Side: {'LONG' if position_amt > 0 else 'SHORT'}")
                    
                    # Calculate close quantity (50%)
                    total_qty = abs(position_amt)
                    close_qty = total_qty * (PARTIAL_PERCENTAGE / 100)
                    remaining_qty = total_qty - close_qty
                    
                    print(f"\n📉 PARTIAL CLOSE PLAN:")
                    print(f"   Total Quantity: {total_qty}")
                    print(f"   Close Quantity ({PARTIAL_PERCENTAGE}%): {close_qty}")
                    print(f"   Remaining Quantity: {remaining_qty}")
                    
                    # Ask for confirmation
                    print("\n⚠️  This will execute a REAL partial close on testnet!")
                    confirm = input("   Type 'yes' to proceed: ").strip().lower()
                    
                    if confirm != 'yes':
                        print("\n❌ Cancelled by user")
                        return
                    
                    # Step 2: Execute partial close
                    print(f"\n🔄 Executing partial close...")
                    
                    # Get symbol precision
                    info = client.futures_exchange_info()
                    qty_precision = 0
                    for s in info['symbols']:
                        if s['symbol'] == SYMBOL:
                            for f in s['filters']:
                                if f['filterType'] == 'LOT_SIZE':
                                    step_size = float(f['stepSize'])
                                    qty_precision = len(str(step_size).rstrip('0').split('.')[-1])
                                    break
                            break
                    
                    # Round quantity to proper precision
                    close_qty = round(close_qty, qty_precision)
                    
                    print(f"   Rounded quantity: {close_qty}")
                    
                    # Determine order side (opposite of position)
                    order_side = SIDE_SELL if position_amt > 0 else SIDE_BUY
                    
                    # Place market order to close partial position
                    order = client.futures_create_order(
                        symbol=SYMBOL,
                        side=order_side,
                        type=ORDER_TYPE_MARKET,
                        quantity=close_qty
                    )
                    
                    print(f"\n✅ PARTIAL CLOSE EXECUTED!")
                    print(f"   Order ID: {order['orderId']}")
                    print(f"   Status: {order['status']}")
                    print(f"   Executed Quantity: {order.get('executedQty', close_qty)}")
                    
                    # Step 3: Verify remaining position
                    print(f"\n🔍 Verifying remaining position...")
                    time.sleep(1)  # Wait for order to settle
                    
                    positions = client.futures_position_information(symbol=SYMBOL)
                    for pos in positions:
                        if pos['symbol'] == SYMBOL:
                            new_position_amt = float(pos['positionAmt'])
                            print(f"\n📊 UPDATED POSITION:")
                            print(f"   Position Amount: {new_position_amt}")
                            print(f"   Entry Price: ${pos['entryPrice']}")
                            print(f"   Mark Price: ${pos['markPrice']}")
                            print(f"   Unrealized PNL: ${pos['unRealizedProfit']}")
                            
                            if abs(new_position_amt) > 0:
                                print(f"\n✅ SUCCESS! Position partially closed.")
                                print(f"   Closed: {PARTIAL_PERCENTAGE}%")
                                print(f"   Remaining: {abs(new_position_amt)} units")
                            else:
                                print(f"\n⚠️  Note: Entire position was closed (quantity may have been too small to leave remainder)")
                    
                    break
        
        if not position_found:
            print(f"❌ NO OPEN {SYMBOL} POSITION FOUND ON TESTNET")
            print(f"\nTo test this script, you need to:")
            print(f"1. Go to https://testnet.binancefuture.com")
            print(f"2. Open a {SYMBOL} position")
            print(f"3. Run this script again")
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("🏁 Test Complete")
    print("=" * 80)

if __name__ == '__main__':
    main()
