"""
Script to add profit transfer functionality to trader.py
This script surgically adds the transfer_to_spot_wallet method and modifies close_position
"""

import re

# Read the original file
with open('trader.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new transfer_to_spot_wallet method
transfer_method = '''    
    def transfer_to_spot_wallet(self, amount):
        """Transfer USDT from futures wallet to spot wallet"""
        try:
            if amount <= 0:
                logger.warning(f"Transfer amount must be positive: {amount}")
                return False
            
            # Round to 2 decimal places for USDT
            amount = round(amount, 2)
            
            logger.info(f"💸 Transferring ${amount:.2f} USDT from Futures to Spot wallet...")
            
            # Transfer from UMFUTURE (USD-M Futures) to MAIN (Spot)
            result = self.client.futures_account_transfer(
                asset='USDT',
                amount=amount,
                type=2  # 1 = MAIN to UMFUTURE, 2 = UMFUTURE to MAIN
            )
            
            logger.info(f"✅ Successfully transferred ${amount:.2f} to Spot wallet. Transaction ID: {result.get('tranId', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error transferring to spot wallet: {e}")
            return False
    
'''

# Insert transfer_to_spot_wallet method before close_position
# Find the close_position method signature
close_pos_pattern = r'(\s+)(def close_position\(self, symbol, partial_pct=None\):)'
content = re.sub(close_pos_pattern, transfer_method + r'\1\2', content, count=1)

# Now modify the close_position method to add profit calculation and transfer
# Find the entire close_position method
old_close_method = r'''    def close_position\(self, symbol, partial_pct=None\):
        try:
            positions = self\.client\.futures_position_information\(symbol=symbol\)
            
            for pos in positions:
                if pos\['symbol'\] == symbol and float\(pos\['positionAmt'\]\) != 0:
                    total_qty = abs\(float\(pos\['positionAmt'\]\)\)
                    
                    if partial_pct:
                        qty = round\(total_qty \* \(partial_pct / 100\), 8\)
                        logger\.info\(f"Closing {partial_pct}% of {symbol}: {qty} units"\)
                    else:
                        qty = total_qty
                        logger\.info\(f"Closing full position {symbol}: {qty} units"\)
                        self\.client\.futures_cancel_all_open_orders\(symbol=symbol\)
                    
                    order = self\.client\.futures_create_order\(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=ORDER_TYPE_MARKET,
                        quantity=qty
                    \)
                    
                    logger\.info\(f"✅ Position closed: {order\['orderId'\]}"\)
                    return True
            
            logger\.warning\(f"No open position found for {symbol}"\)
            return False
            
        except Exception as e:
            logger\.error\(f"❌ Error closing position: {e}"\)
            return False'''

new_close_method = '''    def close_position(self, symbol, partial_pct=None):
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            
            for pos in positions:
                if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                    total_qty = abs(float(pos['positionAmt']))
                    entry_price = float(pos['entryPrice'])
                    
                    # Get current price before closing
                    current_price = self.get_current_price(symbol)
                    if not current_price:
                        logger.error(f"Could not get current price for {symbol}")
                        return False
                    
                    if partial_pct:
                        qty = round(total_qty * (partial_pct / 100), 8)
                        logger.info(f"Closing {partial_pct}% of {symbol}: {qty} units")
                    else:
                        qty = total_qty
                        logger.info(f"Closing full position {symbol}: {qty} units")
                        self.client.futures_cancel_all_open_orders(symbol=symbol)
                    
                    order = self.client.futures_create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=ORDER_TYPE_MARKET,
                        quantity=qty
                    )
                    
                    logger.info(f"✅ Position closed: {order['orderId']}")
                    
                    # Calculate profit in USDT (only for full close)
                    if not partial_pct:
                        # Profit = (Exit Price - Entry Price) * Quantity
                        profit_usdt = (current_price - entry_price) * total_qty
                        profit_pct = ((current_price - entry_price) / entry_price) * 100
                        
                        logger.info(f"💰 Position closed with profit: ${profit_usdt:.2f} USDT ({profit_pct:+.2f}%)")
                        
                        # Transfer 50% of profit to spot wallet if profitable
                        if profit_usdt > 0:
                            transfer_amount = profit_usdt * 0.5
                            logger.info(f"📤 Transferring 50% of profit (${transfer_amount:.2f}) to Spot wallet...")
                            transfer_success = self.transfer_to_spot_wallet(transfer_amount)
                            
                            return {
                                'success': True,
                                'order_id': order['orderId'],
                                'profit_usdt': profit_usdt,
                                'profit_pct': profit_pct,
                                'transferred_to_spot': transfer_amount if transfer_success else 0,
                                'transfer_success': transfer_success
                            }
                        else:
                            logger.info(f"🔴 Position closed with loss: ${profit_usdt:.2f} USDT - no transfer")
                            return {
                                'success': True,
                                'order_id': order['orderId'],
                                'profit_usdt': profit_usdt,
                                'profit_pct': profit_pct,
                                'transferred_to_spot': 0,
                                'transfer_success': False
                            }
                    
                    return True
            
            logger.warning(f"No open position found for {symbol}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error closing position: {e}")
            return False'''

content = re.sub(old_close_method, new_close_method, content, count=1, flags=re.DOTALL)

# Write the modified content back
with open('trader.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Successfully modified trader.py")
print("Added transfer_to_spot_wallet method")
print("Modified close_position to calculate profit and transfer 50% to spot wallet")
