"""
Trading Bot Backtester
Simulates trading bot behavior on historical messages and price data
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from binance.client import Client
import json
from trader import AISignalExtractor, BINANCE_CONFIG, DEEPSEEK_CONFIG
import time

class TradingBacktester:
    def __init__(self):
        self.db_path = 'improved_trading_bot.db'
        self.client = Client(BINANCE_CONFIG['api_key'], BINANCE_CONFIG['api_secret'], testnet=BINANCE_CONFIG.get('testnet', False))
        self.ai = AISignalExtractor(
            DEEPSEEK_CONFIG['api_key'],
            DEEPSEEK_CONFIG['base_url'],
            DEEPSEEK_CONFIG['model']
        )
        
    def get_all_messages(self):
        """Fetch all processed messages from database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Try message_actions table first, fallback to messages
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_actions'")
        has_message_actions = cursor.fetchone() is not None
        
        if has_message_actions:
            cursor.execute("""
                SELECT * FROM message_actions 
                ORDER BY message_date ASC
            """)
        else:
            cursor.execute("""
                SELECT 
                    message_id, message_text, message_date,
                    message_type as action_taken, ai_analysis as action_details,
                    fetched_at
                FROM messages 
                WHERE processed = 1
                ORDER BY message_date ASC
            """)
        
        messages = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return messages
    
    def display_messages(self, messages):
        """Display messages for user selection"""
        print("\n" + "="*100)
        print("📊 AVAILABLE MESSAGES FOR BACKTESTING")
        print("="*100)
        
        for idx, msg in enumerate(messages, 1):
            action = msg.get('action_taken', 'UNKNOWN')
            symbol = msg.get('symbol', 'N/A')
            msg_date = msg.get('message_date', 'N/A')
            msg_preview = msg.get('message_text', '')[:80] + '...' if len(msg.get('message_text', '')) > 80 else msg.get('message_text',  '')
            
            print(f"\n{idx}. [{action}] {symbol} - {msg_date}")
            print(f"   {msg_preview}")
        
        print("\n" + "="*100)
    
    def select_message(self, messages):
        """Let user select a message"""
        while True:
            try:
                choice = input("\n👉 Select message number (or 'q' to quit): ").strip()
                if choice.lower() == 'q':
                    return None
                
                idx = int(choice) - 1
                if 0 <= idx < len(messages):
                    return messages[idx]
                else:
                    print(f"❌ Invalid choice. Please select 1-{len(messages)}")
            except ValueError:
                print("❌ Please enter a valid number")
    
    def fetch_candles(self, symbol, start_time, end_time, interval='1h'):
        """Fetch OHLCV candles from Binance"""
        print(f"📥 Fetching {interval} candles for {symbol} from {start_time} to {end_time}...")
        
        try:
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=1000
            )
            
            candles = []
            for k in klines:
                candles.append({
                    'timestamp': datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
                })
            
            print(f"✅ Fetched {len(candles)} candles")
            return candles
        
        except Exception as e:
            print(f"❌ Error fetching candles: {e}")
            return []
    
    def get_symbol_updates(self, symbol, start_time, end_time, all_messages):
        """Get all update messages for a symbol within timeframe"""
        updates = []
        for msg in all_messages:
            msg_symbol = msg.get('symbol', '')
            msg_date_str = msg.get('message_date', '')
            
            if msg_symbol == symbol:
                try:
                    msg_date = datetime.fromisoformat(msg_date_str.replace('Z', '+00:00'))
                    if start_time <= msg_date <= end_time:
                        updates.append(msg)
                except:
                    pass
        
        return updates
    
    def re_analyze_message(self, message_text):
        """Re-analyze message with AI to determine action"""
        print(f"🤖 Re-analyzing message with AI...")
        result = self.ai.analyze_message(message_text)
        return result
    
    def simulate_position(self, initial_signal, symbol, start_time, all_messages):
        """Simulate position from opening to close"""
        print("\n" + "="*100)
        print(f"🎯 STARTING BACKTEST SIMULATION")
        print("="*100)
        
        # Parse initial signal
        entry_price = initial_signal.get('entry_price')
        stop_loss = initial_signal.get('stop_loss')
        take_profit = initial_signal.get('take_profit')
        quantity = initial_signal.get('quantity', 1.0)
        leverage = initial_signal.get('leverage', 10)
        
        print(f"\n📍 Position Details:")
        print(f"   Symbol: {symbol}")
        print(f"   Entry: ${entry_price}")
        print(f"   Stop Loss: ${stop_loss}")
        print(f"   Take Profit: ${take_profit if take_profit else 'N/A'}")
        print(f"   Quantity: {quantity}")
        print(f"   Leverage: {leverage}x")
        
        # Position state
        position = {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'quantity': quantity,
            'leverage': leverage,
            'opened_at': start_time,
            'status': 'open'
        }
        
        # Fetch initial candles (1 hour timeframe)
        end_time = datetime.now(timezone.utc)
        candles_1h = self.fetch_candles(symbol, start_time, end_time, '1h')
        
        if not candles_1h:
            print("❌ No candle data available")
            return None
        
        # Get all update messages for this symbol
        updates = self.get_symbol_updates(symbol, start_time, end_time, all_messages)
        print(f"\n📨 Found {len(updates)} update messages for {symbol}")
        
        # Simulate through candles
        for i, candle in enumerate(candles_1h):
            candle_start = candle['timestamp']
            candle_end = candle_start + timedelta(hours=1)
            
            print(f"\n⏰ Candle {i+1}/{len(candles_1h)}: {candle_start.strftime('%Y-%m-%d %H:%M')} UTC")
            print(f"   O: ${candle['open']:.4f} H: ${candle['high']:.4f} L: ${candle['low']:.4f} C: ${candle['close']:.4f}")
            
            if position['status'] != 'open':
                break
            
            # Check for updates within this candle
            candle_updates = [u for u in updates if candle_start <= datetime.fromisoformat(u['message_date'].replace('Z', '+00:00')) < candle_end]
            
            # Check if SL or TP hit in this candle
            sl_hit = candle['low'] <= position['stop_loss']
            tp_hit = position['take_profit'] and candle['high'] >= position['take_profit']
            
            # If we have updates AND (SL or TP hit), drill down to lower timeframes
            if candle_updates and (sl_hit or tp_hit):
                print(f"\n🔍 Drilling down to lower timeframes (update message + SL/TP hit in same hour)")
                result = self.drill_down_timeframes(symbol, candle_start, candle_end, position, candle_updates)
                if result:
                    return result
            
            # Process updates in this candle
            for update in candle_updates:
                print(f"\n📩 Processing update at {update['message_date']}")
                print(f"   Message: {update['message_text'][:100]}...")
                
                # Re-analyze the message
                analysis = self.re_analyze_message(update['message_text'])
                
                if analysis.get('type') == 'POSITION_UPDATE':
                    update_info = analysis.get('update', {})
                    action = update_info.get('action')
                    
                    print(f"   ✅ AI Analysis: {action}")
                    
                    if action == 'MODIFY_SL':
                        new_sl = update_info.get('new_stop_loss')
                        if new_sl:
                            old_sl = position['stop_loss']
                            position['stop_loss'] = new_sl
                            print(f"   🔄 Stop Loss: ${old_sl} → ${new_sl}")
                    
                    elif action == 'MOVE_SL_TO_ENTRY':
                        old_sl = position['stop_loss']
                        position['stop_loss'] = position['entry_price']
                        print(f"   🔄 Moved SL to Entry: ${old_sl} → ${position['entry_price']}")
                    
                    elif action == 'CLOSE_PARTIAL':
                        partial_pct = update_info.get('partial_close_percentage', 50)
                        close_qty = position['quantity'] * (partial_pct / 100)
                        position['quantity'] -= close_qty
                        print(f"   📉 Partial Close: {partial_pct}% ({close_qty} units)")
                        print(f"   Remaining Quantity: {position['quantity']}")
                    
                    elif action == 'CLOSE_FULL':
                        exit_price = candle['close']
                        return self.close_position(position, exit_price, candle['timestamp'], 'Manual Close')
            
            # After processing updates, check SL/TP again with updated values
            if candle['low'] <= position['stop_loss']:
                print(f"\n🛑 STOP LOSS HIT at ${position['stop_loss']}")
                return self.close_position(position, position['stop_loss'], candle['timestamp'], 'Stop Loss')
            
            if position['take_profit'] and candle['high'] >= position['take_profit']:
                print(f"\n🎯 TAKE PROFIT HIT at ${position['take_profit']}")
                return self.close_position(position, position['take_profit'], candle['timestamp'], 'Take Profit')
        
        # Position still open at end
        if position['status'] == 'open':
            final_candle = candles_1h[-1]
            print(f"\n⏸️  Position still open at end of data")
            return self.close_position(position, final_candle['close'], final_candle['timestamp'], 'End of Data')
    
    def drill_down_timeframes(self, symbol, start_time, end_time, position, updates):
        """Drill down to lower timeframes when needed"""
        print(f"   🔎 Analyzing 15m candles...")
        candles_15m = self.fetch_candles(symbol, start_time, end_time, '15m')
        
        for candle in candles_15m:
            candle_time = candle['timestamp']
            
            # Check if any update happened before this candle
            for update in updates:
                update_time = datetime.fromisoformat(update['message_date'].replace('Z', '+00:00'))
                
                if update_time <= candle_time:
                    # Process update
                    analysis = self.re_analyze_message(update['message_text'])
                    if analysis.get('type') == 'POSITION_UPDATE':
                        update_info = analysis.get('update', {})
                        action = update_info.get('action')
                        
                        if action == 'MODIFY_SL':
                            position['stop_loss'] = update_info.get('new_stop_loss', position['stop_loss'])
                        elif action == 'MOVE_SL_TO_ENTRY':
                            position['stop_loss'] = position['entry_price']
            
            # Check SL/TP with updated position
            if candle['low'] <= position['stop_loss']:
                return self.close_position(position, position['stop_loss'], candle_time, 'Stop Loss (15m)')
            
            if position['take_profit'] and candle['high'] >= position['take_profit']:
                return self.close_position(position, position['take_profit'], candle_time, 'Take Profit (15m)')
        
        return None
    
    def close_position(self, position, exit_price, close_time, reason):
        """Calculate final PNL and return results"""
        entry_price = position['entry_price']
        quantity = position['quantity']
        leverage = position['leverage']
        
        # Calculate PNL
        price_diff = exit_price - entry_price
        pnl_usdt = price_diff * quantity
        pnl_percentage = (price_diff / entry_price) * 100
        
        # Calculate duration
        duration = close_time - position['opened_at']
        
        result = {
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': quantity,
            'leverage': leverage,
            'pnl_usdt': pnl_usdt,
            'pnl_percentage': pnl_percentage,
            'opened_at': position['opened_at'],
            'closed_at': close_time,
            'duration': duration,
            'close_reason': reason
        }
        
        position['status'] = 'closed'
        
        print("\n" + "="*100)
        print("🏁 POSITION CLOSED")
        print("="*100)
        print(f"Reason: {reason}")
        print(f"Entry Price: ${entry_price:.4f}")
        print(f"Exit Price: ${exit_price:.4f}")
        print(f"Quantity: {quantity}")
        print(f"Leverage: {leverage}x")
        print(f"\n💰 PNL: ${pnl_usdt:.2f} USDT ({pnl_percentage:+.2f}%)")
        print(f"⏱️  Duration: {duration}")
        print(f"📅 Opened: {position['opened_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"📅 Closed: {close_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("="*100)
        
        return result
    
    def run(self):
        """Main backtest flow"""
        print("\n🚀 TRADING BOT BACKTESTER")
        print("="*100)
        
        # Get all messages
        messages = self.get_all_messages()
        print(f"\n📊 Loaded {len(messages)} processed messages from database")
        
        if not messages:
            print("❌ No messages found in database")
            return
        
        # Display and let user select
        self.display_messages(messages)
        selected = self.select_message(messages)
        
        if not selected:
            print("\n👋 Backtest cancelled")
            return
        
        print(f"\n✅ Selected message:")
        print(f"   Date: {selected.get('message_date')}")
        print(f"   Action: {selected.get('action_taken')}")
        print(f"   Text: {selected.get('message_text')[:150]}...")
        
        # Re-analyze to get signal details
        print(f"\n🤖 Analyzing message with AI...")
        analysis = self.re_analyze_message(selected['message_text'])
        
        if analysis.get('type') != 'NEW_POSITION':
            print(f"\n❌ Selected message is not a NEW_POSITION signal")
            print(f"   Type: {analysis.get('type')}")
            print(f"   Cannot backtest. Please select a NEW_POSITION message.")
            return
        
        # Extract signal details
        signal = analysis.get('signal', {})
        symbol = signal.get('symbol')
        
        if not symbol:
            print("❌ Could not extract symbol from message")
            return
        
        start_time = datetime.fromisoformat(selected['message_date'].replace('Z', '+00:00'))
        
        # Run simulation
        result = self.simulate_position(signal, symbol, start_time, messages)
        
        if result:
            # Save result to file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'backtest_result_{symbol}_{timestamp}.json'
            
            with open(filename, 'w') as f:
                json.dump({
                    **result,
                    'opened_at': result['opened_at'].isoformat(),
                    'closed_at': result['closed_at'].isoformat(),
                    'duration': str(result['duration'])
                }, f, indent=2)
            
            print(f"\n💾 Results saved to: {filename}")

if __name__ == '__main__':
    backtester = TradingBacktester()
    backtester.run()
