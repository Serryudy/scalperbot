"""
trader_extensions.py

Extensions to add to trader.py for enhanced functionality:
1. Message actions logging
2. Partial close percentage handling
3. Move SL to entry functionality

INSTALLATION INSTRUCTIONS:
==========================

1. Add this import at the top of trader.py:
   from trader_extensions import MessageActionsDB, enhance_ai_prompt, move_sl_to_entry_method

2. In MessageDatabase class, add after get_last_weekly_report_date():
   
   # Message Actions Methods
   save_message_action = MessageActionsDB.save_message_action
   get_message_actions = MessageActionsDB.get_message_actions
   get_closed_positions = MessageActionsDB.get_closed_positions

3. In MessageDatabase.create_tables(), add this table creation before self.conn.commit():
   
   cursor.execute(CREATE_MESSAGE_ACTIONS_TABLE)

4. In BinanceTrader class, add this method after modify_stop_loss():

   move_sl_to_entry = move_sl_to_entry_method

5. Replace the AI system prompt in AISignalExtractor.analyze_message() with:
   system_prompt = get_enhanced_ai_prompt()

6. In ImprovedAITradingBot.process_position_update(), add logic to handle:
   - partial_close_percentage from update info  
   - move_sl_to_entry flag from update info
   - save_message_action() calls for all actions
"""

from datetime import datetime, timezone
from binance.enums import *
import logging
import json

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE SCHEMA ADDITIONS
# ============================================================================

CREATE_MESSAGE_ACTIONS_TABLE = '''
    CREATE TABLE IF NOT EXISTS message_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        message_text TEXT NOT NULL,
        message_date TIMESTAMP NOT NULL,
        action_taken TEXT NOT NULL,
        action_details TEXT,
        symbol TEXT,
        position_id INTEGER,
        success BOOLEAN NOT NULL,
        error_message TEXT,
        processed_at TIMESTAMP NOT NULL,
        FOREIGN KEY (position_id) REFERENCES positions (id)
    )
'''

# ============================================================================
# MESSAGE ACTIONS DATABASE METHODS
# ============================================================================

class MessageActionsDB:
    """Database methods for message actions logging"""
    
    @staticmethod
    def save_message_action(self, message_id, message_text, message_date, 
                           action_taken, action_details=None, symbol=None, 
                           position_id=None, success=True, error_msg=None):
        """Save an action taken for a processed message"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO message_actions 
            (message_id, message_text, message_date, action_taken, action_details,
             symbol, position_id, success, error_message, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (message_id, message_text, message_date, action_taken,  action_details,
              symbol, position_id, success, error_msg, datetime.now(timezone.utc)))
        self.conn.commit()
    
    @staticmethod
    def get_message_actions(self, filters=None):
        """Get message actions with optional filters"""
        cursor = self.conn.cursor()
        
        query = "SELECT * FROM message_actions WHERE 1=1"
        params = []
        
        if filters:
            if 'start_date' in filters:
                query += " AND message_date >= ?"
                params.append(filters['start_date'])
            if 'end_date' in filters:
                query += " AND message_date < ?"
                params.append(filters['end_date'])
            if 'action_type' in filters:
                query += " AND action_taken = ?"
                params.append(filters['action_type'])
            if 'symbol' in filters:
                query += " AND symbol = ?"
                params.append(filters['symbol'])
        
        query += " ORDER BY processed_at DESC"
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    @staticmethod
    def get_closed_positions(self, start_date=None, end_date=None, symbol=None):
        """Get closed positions with optional filters"""
        cursor = self.conn.cursor()
        
        query = "SELECT * FROM positions WHERE status = 'closed'"
        params = []
        
        if start_date:
            query += " AND closed_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND closed_at < ?"
            params.append(end_date)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        query += " ORDER BY closed_at DESC"
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

# ============================================================================
# BINANCE TRADER METHOD: MOVE SL TO ENTRY
# ============================================================================

def move_sl_to_entry_method(self, symbol, entry_price):
    """Move stop loss to entry price (breakeven)"""
    try:
        # Get current position
        position = self.get_position_info(symbol)
        if not position or not position['is_open']:
            logger.warning(f"No open position for {symbol}")
            return False
        
        qty = abs(position['position_amt'])
        qty_precision, price_precision = self.get_symbol_precision(symbol)
        
        # Cancel existing stop loss orders
        self.client.futures_cancel_all_open_orders(symbol=symbol)
        
        # Set new stop loss at entry price
        sl_order = self.client.futures_create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=round(entry_price, price_precision),
            quantity=round(qty, qty_precision),
            closePosition=True
        )
        
        logger.info(f"✅ Moved SL to entry for {symbol} at {entry_price}")
        return True
        
    except Exception as e:
        logger.error(f"Error moving SL to entry: {e}")
        return False

# ============================================================================
# ENHANCED AI PROMPT
# ============================================================================

def get_enhanced_ai_prompt():
    """Returns the enhanced AI system prompt with new detection rules"""
    return """You are an intelligent cryptocurrency trading signal analyzer. Analyze Telegram messages and extract trading signals or position updates. Use your intelligence to make smart decisions about position management.

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
        "action": "CLOSE_FULL" or "CLOSE_PARTIAL" or "MOVE_SL_TO_ENTRY" or "HOLD" or "CANCELLED" or "INFO",
        "profit_percentage": float or null,
        "partial_close_percentage": float or null,
        "move_sl_to_entry": boolean (default false),
        "confidence": float (0-100),
        "reasoning": "brief explanation of decision",
        "note": "any relevant information"
    }
}

For NON-TRADING messages:
{
    "type": "IGNORE",
    "reason": "explanation"
}

INTELLIGENT DECISION RULES:
1. CRITICAL: IGNORE ALL SHORT POSITIONS - Only process LONG positions
   - If message contains "SHORT", "short", "SELL", or indicates short position: return IGNORE type
   - Only process messages that are LONG positions or position updates
2. Symbols: uppercase without $ sign, append USDT (e.g., "ZORAUSDT")
3. PARTIAL CLOSE DETECTION (NEW & CRITICAL):
   - Look for EXPLICIT percentages: "close 20%", "take profit 30%", "sell 50%", "partial 40%", "close 25 percent"
   - Extract the EXACT percentage value and return it in "partial_close_percentage" field
   - ONLY set this field if message explicitly mentions a percentage to close
   - If NO explicit percentage is mentioned, do NOT set this field
4. MOVE SL TO ENTRY DETECTION (NEW & CRITICAL):
   - Look for: "move sl to entry", "sl to entry", "sl at entry", "breakeven", "move stop loss to entry", "set sl to entry"
   - When detected, return "move_sl_to_entry": true in the update JSON
   - This should also have action: "MOVE_SL_TO_ENTRY"
5. FULL CLOSE DECISION (UPDATED - CRITICAL):
   - ONLY suggest CLOSE_FULL if message explicitly says to close/exit WITHOUT mentioning a percentage
   - DO NOT auto-suggest CLOSE_FULL based on profit levels
   - Message must contain explicit close instruction like "close position", "exit", "close all", "full close"
   - If message says something like "close" without context, examine if it's really asking to close
6. Messages with "cancel", "cancelled", "missed": action "CANCELLED"
7. Positive momentum (e.g., "breaking out", "strong support", "bullish"): action "HOLD"
8. Set confidence level (0-100) based on message clarity
9. Provide brief reasoning for your decision
10. Only return NEW_POSITION if message contains entry, SL, or TP prices AND is a LONG position
11. Return valid JSON only, no markdown formatting

EXAMPLES:
- "BTC close 20%" → CLOSE_PARTIAL with partial_close_percentage: 20
- "ETH close 30 percent" → CLOSE_PARTIAL with partial_close_percentage: 30
- "SOL move sl to entry" → MOVE_SL_TO_ENTRY with move_sl_to_entry: true
- "DOGE close position" → CLOSE_FULL (no percentage mentioned)
- "BTC running +45%" → HOLD (just update, not close instruction)
- "XRP SHORT at $2.50" → IGNORE (SHORT position)"""

# ============================================================================
# HELPER CODE FOR process_position_update
# ============================================================================

def get_position_update_handler_code():
    """
    Returns code snippets to add to process_position_update method.
    
    Add this AT THE BEGINNING of the method, after extracting basic update info:
    """
    return '''
    # NEW: Extract partial close percentage and move SL flags
    partial_close_pct = update_info['update'].get('partial_close_percentage')
    move_sl_flag = update_info['update'].get('move_sl_to_entry', False)
    
    # NEW: Handle Move SL to Entry
    if move_sl_flag and position:
        entry_price = position['entry_price']
        success = self.trader.move_sl_to_entry(symbol, entry_price)
        if success:
            self.db.update_position_stop_loss(position['id'], entry_price, 'SL moved to entry per Telegram signal')
            self.db.save_message_action(
                message_id, msg_text, msg_date,
                'MOVE_SL_TO_ENTRY',
                json.dumps({'entry_price': entry_price}),
                symbol, position['id'], True
            )
            
            notification = f"""
🔒 <b>STOP LOSS MOVED TO BREAKEVEN</b>

<b>Symbol:</b> {symbol}
<b>Entry Price:</b> ${entry_price:.4f}
<b>New SL:</b> ${entry_price:.4f} (Breakeven)
<b>Action:</b> Move SL to Entry

Position is now risk-free!
⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            self.send_email_notification(f"🔒 SL to Entry - {symbol}", notification)
            logger.info(f"✅ SL moved to entry: {symbol} at {entry_price}")
        else:
            self.db.save_message_action(
                message_id, msg_text, msg_date,
                'MOVE_SL_TO_ENTRY_FAILED',
                None, symbol, position['id'], False,
                'Failed to move SL to entry'
            )
        return  # Exit after handling SL move
    
    # NEW: Handle Explicit Partial Close with percentage
    if partial_close_pct and partial_close_pct > 0:
        logger.info(f"📊 Explicit partial close requested: {partial_close_pct}% for {symbol}")
        success = self.trader.close_position(symbol, partial_close_pct)
        if success:
            action_name = f'CLOSE_PARTIAL_{int(partial_close_pct)}%'
            self.db.log_trading_action(action_name, symbol, 
                f"Closed {partial_close_pct}% | Profit: {profit_pct}% | Reasoning: {reasoning}", True)
            self.db.save_message_action(
                message_id, msg_text, msg_date,
                action_name,
                json.dumps({'percentage': partial_close_pct, 'profit_pct': profit_pct}),
                symbol, position['id'] if position else None, True
            )
            
            notification = f"""
🟡 <b>PARTIAL CLOSE (EXPLICIT %)</b>

<b>Symbol:</b> {symbol}
<b>Closed:</b> {partial_close_pct}%
<b>Current Profit:</b> {profit_pct:+.2f}%
<b>Reasoning:</b> {reasoning}

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            self.send_email_notification(f"🟡 Partial Close {partial_close_pct}% - {symbol}", notification)
            logger.info(f"✅ Partial close: {symbol} - {partial_close_pct}%")
        else:
            self.db.save_message_action(
                message_id, msg_text, msg_date,
                f'CLOSE_PARTIAL_{int(partial_close_pct)}%_FAILED',
                None, symbol, position['id'] if position else None, False,
                'Failed to execute partial close'
            )
        return  # Exit after handling partial close
    
    # Continue with existing CLOSE_FULL logic...
    # NOTE: Remove any auto profit > 20% close logic from the CLOSE_FULL section
    '''

# ============================================================================
# INTEGRATION CHECKLIST
# ============================================================================

INTEGRATION_CHECKLIST = """
INTEGRATION CHECKLIST FOR trader.py
===================================

□ 1. Import this module at top of trader.py:
      from trader_extensions import (
          CREATE_MESSAGE_ACTIONS_TABLE,
          MessageActionsDB,
          move_sl_to_entry_method,
          get_enhanced_ai_prompt,
          get_position_update_handler_code
      )

□ 2. In MessageDatabase.create_tables(), ADD before self.conn.commit():
      cursor.execute(CREATE_MESSAGE_ACTIONS_TABLE)

□ 3. In MessageDatabase class, ADD these methods at the end:
      save_message_action = MessageActionsDB.save_message_action
      get_message_actions = MessageActionsDB.get_message_actions
      get_closed_positions = MessageActionsDB.get_closed_positions

□ 4. In BinanceTrader class, ADD this method after modify_stop_loss():
      move_sl_to_entry = move_sl_to_entry_method

□ 5. In AISignalExtractor.analyze_message(), REPLACE system_prompt with:
      system_prompt = get_enhanced_ai_prompt()

□ 6. In ImprovedAITradingBot.process_position_update(), ADD AT THE START:
      See get_position_update_handler_code() for the code to add

□ 7. In ImprovedAITradingBot.process_position_update(), in CLOSE_FULL section:
      REMOVE any logic that auto-closes based on profit > 20%
      Only close when action == 'CLOSE_FULL' explicitly

□ 8. In ImprovedAITradingBot.process_new_position(), ADD:
      self.db.save_message_action(msg_id, msg_text, msg_date, 'NEW_POSITION',
          json.dumps(signal), symbol, position_id, True)

□ 9. For any IGNORED messages, ADD:
      self.db.save_message_action(msg_id, msg_text, msg_date, 'IGNORED',
          analysis.get('reason'), None, None, True)

□ 10. VERIFY: The 3-day auto-close logic remains UNCHANGED in monitor_and_take_profits()
"""

if __name__ == '__main__':
    print(INTEGRATION_CHECKLIST)
