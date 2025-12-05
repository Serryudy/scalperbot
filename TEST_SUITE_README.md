# 🧪 Trading Bot Test Suite

## Overview

This test suite allows you to **comprehensively test the trading bot** using dummy Telegram-style messages **WITHOUT**:
- ❌ Connecting to Telegram
- ❌ Placing real trades on Binance
- ❌ Requiring live market data

## Files

### 1. `test_messages.json`
Contains 15 realistic dummy messages covering all trading scenarios:

**Scenario Flow:**

#### **BNB Trade (LONG) - Complete Lifecycle:**
1. ✅ **NEW_POSITION** - Open LONG position
2. 💬 **HOLD** - Encouraging message (ignored)
3. 🔒 **MOVE_SL_TO_ENTRY** - Protect capital
4. 📉 **CLOSE_PARTIAL 25%** - Take first profit
5. 📉 **CLOSE_PARTIAL 30%** - Take second profit at resistance
6. 📉 **CLOSE_PARTIAL 40%** - Risk management
7. ✅ **CLOSE_FULL** - Take profit target hit

#### **ETH Trade (SHORT) - Failed Trade:**
8. ✅ **NEW_POSITION** - Open SHORT position
9. 📉 **CLOSE_PARTIAL 50%** - Bad performance, reduce risk
10. ❌ **CLOSE_FULL** - Cut losses

#### **General Messages:**
11. ⏭️ **IGNORE** - Market commentary
12. ⏭️ **IGNORE** - General advice

#### **SOL Trade (LONG) - Partial Profits:**
13. ✅ **NEW_POSITION** - Open LONG position
14. 🔧 **MODIFY_SL** - Adjust stop loss
15. 📉 **CLOSE_PARTIAL 34%** - Specific percentage close

### 2. `run_test_suite.py`
Test runner that:
- Loads dummy messages from JSON
- Injects them into the database
- Processes through AI analysis
- Validates expected vs actual results
- Provides detailed logging
- Generates summary report

## How to Run

### Step 1: Run the Test Suite

```bash
python run_test_suite.py
```

### Step 2: Review Output

The script will:
1. Display each test message
2. Show AI analysis results
3. Validate against expected actions
4. Report any discrepancies
5. Provide final summary

### Expected Output

```
🧪 STARTING COMPREHENSIVE BOT TEST
==========================================
Loaded 15 test messages

TEST 1/15
==========================================
📨 TEST MESSAGE #1: Open new LONG position
📝 Expected Action: NEW_POSITION
Message: 🚀 #BNBUSDT LONG Entry: 692.50...

🤖 Analyzing with AI...
✅ AI Analysis Complete:
   Type: NEW_POSITION
   Symbol: BNBUSDT
   Side: LONG
   Entry: 692.50
   SL: 680.00
   TP: 720.00

✅ VALIDATION PASSED: Expected 'NEW_POSITION', Got 'NEW_POSITION'
==========================================

...

📊 TEST RESULTS SUMMARY:
   NEW_POSITION: 3
   POSITION_UPDATE: 9
   IGNORE: 3

✅ All test messages processed!
```

## What Gets Tested

### ✅ Action Types:
- **NEW_POSITION** - Opening new trades (LONG & SHORT)
- **CLOSE_PARTIAL** - Partial closes (25%, 30%, 34%, 40%, 50%)
- **CLOSE_FULL** - Full position exits
- **MODIFY_SL** - Stop loss modifications
- **MOVE_SL_TO_ENTRY** - Move SL to breakeven
- **IGNORE** - Non-trading messages

### ✅ Edge Cases:
- Multiple partial closes on same position
- Risk management scenarios
- Failed trades (cut losses)
- Percentage accuracy
- Both LONG and SHORT positions

### ✅ Validation:
- Expected action vs actual action
- Percentage accuracy for partial closes
- Symbol extraction
- Entry/SL/TP parsing

## Customizing Tests

### Add Your Own Messages

Edit `test_messages.json`:

```json
{
  "id": 16,
  "message_text": "Your message here",
  "message_date": "2025-12-05T17:00:00Z",
  "expected_action": "CLOSE_PARTIAL",
  "expected_percentage": 75,
  "description": "Test description"
}
```

### Message Format Guidelines:

**For NEW_POSITION:**
- Include symbol (e.g., BTCUSDT)
- Specify LONG or SHORT
- Provide Entry, TP, SL
- Optional: Leverage, Risk%

**For CLOSE_PARTIAL:**
- Mention symbol
- Include percentage (e.g., "close 50%", "50% vol")
- Can use phrases like "close half" (interpreted as 50%)

**For MODIFY_SL:**
- Mention symbol
- Provide new SL price
- Can say "move SL to entry"

**For CLOSE_FULL:**
- Mention symbol
- Use phrases like "close full", "close all", "exit position"

## Database Impact

- Messages are stored with IDs starting at 9000 to avoid conflicts
- All messages are marked as processed
- Results are saved in `messages` and `message_actions` tables
- **Safe to run multiple times** - just generates more test records

## Cleanup (Optional)

To remove test messages from database:

```sql
DELETE FROM messages WHERE message_id >= 9000;
DELETE FROM message_actions WHERE message_id >= 9000;
```

Or in Python:
```python
import sqlite3
conn = sqlite3.connect('improved_trading_bot.db')
cursor = conn.cursor()
cursor.execute("DELETE FROM messages WHERE message_id >= 9000")
cursor.execute("DELETE FROM message_actions WHERE message_id >= 9000")
conn.commit()
conn.close()
```

## Next Steps After Testing

Once all tests pass:

1. ✅ **Restart main bot**: `python trader.py`
2. ✅ **Connect to real Telegram** messages
3. ✅ **Monitor live processing** with confidence

## Troubleshooting

### AI Analysis Fails
- Check DEEPSEEK_CONFIG credentials
- Verify internet connection
- Check API rate limits

### Validation Warnings
- Review AI prompt in `trader_extensions.py`
- Check message phrasing
- Adjust expected_action if needed

### Database Locked
- Ensure `trader.py` is not running
- Close any DB browser tools
- Wait a moment and retry

---

**Created:** 2025-12-05  
**Purpose:** Comprehensive testing without live connections  
**Status:** Ready to use 🚀
