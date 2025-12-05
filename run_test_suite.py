"""
Test Runner for Trading Bot
Feeds dummy messages from test_messages.json into the bot for comprehensive testing
WITHOUT connecting to Telegram.
"""

import sqlite3
import json
from datetime import datetime, timezone
from trader import (
    AISignalExtractor, 
    BinanceTrader, 
    MessageDatabase,
    BINANCE_CONFIG,
    DEEPSEEK_CONFIG
)
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestRunner:
    def __init__(self):
        self.db = MessageDatabase()
        self.trader = BinanceTrader(
            BINANCE_CONFIG['api_key'],
            BINANCE_CONFIG['api_secret'],
            testnet=BINANCE_CONFIG.get('testnet', False)
        )
        self.ai = AISignalExtractor(
            DEEPSEEK_CONFIG['api_key'],
            DEEPSEEK_CONFIG['base_url'],
            DEEPSEEK_CONFIG['model']
        )
        
    def load_test_messages(self):
        """Load test messages from JSON file"""
        with open('test_messages.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def inject_message(self, msg):
        """Inject a test message into the database"""
        msg_id = 9000 + msg['id']  # Use high IDs to avoid conflicts
        msg_text = msg['message_text']
        msg_date = datetime.fromisoformat(msg['message_date'].replace('Z', '+00:00'))
        
        # Save to database
        self.db.save_message(msg_id, msg_text, msg_date)
        return msg_id
    
    async def process_test_message(self, msg):
        """Process a single test message"""
        logger.info("=" * 100)
        logger.info(f"📨 TEST MESSAGE #{msg['id']}: {msg['description']}")
        logger.info(f"📝 Expected Action: {msg['expected_action']}")
        logger.info("=" * 100)
        logger.info(f"Message: {msg['message_text'][:150]}...")
        
        # Inject into database
        msg_id = self.inject_message(msg)
        
        # Analyze with AI
        logger.info("\n🤖 Analyzing with AI...")
        analysis = self.ai.analyze_message(msg['message_text'])
        
        logger.info(f"✅ AI Analysis Complete:")
        logger.info(f"   Type: {analysis.get('type')}")
        
        if analysis['type'] == 'NEW_POSITION':
            signal = analysis.get('signal', {})
            logger.info(f"   Symbol: {signal.get('symbol')}")
            logger.info(f"   Side: {signal.get('side')}")
            logger.info(f"   Entry: {signal.get('entry_price')}")
            logger.info(f"   SL: {signal.get('stop_loss')}")
            logger.info(f"   TP: {signal.get('take_profit')}")
            
        elif analysis['type'] == 'POSITION_UPDATE':
            update = analysis.get('update', {})
            logger.info(f"   Symbol: {update.get('symbol')}")
            logger.info(f"   Action: {update.get('action')}")
            
            if update.get('action') == 'CLOSE_PARTIAL':
                logger.info(f"   Percentage: {update.get('partial_close_percentage')}%")
            elif update.get('action') == 'MODIFY_SL':
                logger.info(f"   New SL: {update.get('new_stop_loss')}")
        
        # Mark as processed
        self.db.mark_message_processed(msg_id, analysis['type'], json.dumps(analysis))
        
        # Save to message_actions for tracking
        try:
            self.db.save_message_action(
                message_id=msg_id,
                message_text=msg['message_text'],
                message_date=msg['message_date'],
                action_taken=analysis['type'],
                action_details=json.dumps(analysis),
                symbol=analysis.get('signal', {}).get('symbol') or analysis.get('update', {}).get('symbol'),
                success=True
            )
        except Exception as e:
            logger.warning(f"Could not save to message_actions: {e}")
        
        # Validation
        expected = msg['expected_action']
        actual = analysis['type']
        
        if expected.upper() in actual.upper() or actual.upper() in expected.upper():
            logger.info(f"\n✅ VALIDATION PASSED: Expected '{expected}', Got '{actual}'")
        else:
            logger.warning(f"\n⚠️  VALIDATION WARNING: Expected '{expected}', Got '{actual}'")
        
        # Check percentage for partial closes
        if 'expected_percentage' in msg and analysis['type'] == 'POSITION_UPDATE':
            update = analysis.get('update', {})
            if update.get('action') == 'CLOSE_PARTIAL':
                expected_pct = msg['expected_percentage']
                actual_pct = update.get('partial_close_percentage')
                if abs(expected_pct - actual_pct) < 1:  # Allow 1% tolerance
                    logger.info(f"✅ PERCENTAGE MATCH: Expected {expected_pct}%, Got {actual_pct}%")
                else:
                    logger.warning(f"⚠️  PERCENTAGE MISMATCH: Expected {expected_pct}%, Got {actual_pct}%")
        
        logger.info("=" * 100)
        logger.info("")
    
    async def run_test_suite(self):
        """Run the complete test suite"""
        logger.info("\n" + "=" * 100)
        logger.info("🧪 STARTING COMPREHENSIVE BOT TEST")
        logger.info("=" * 100)
        logger.info("This will test all bot actions using dummy messages")
        logger.info("No actual trades will be placed on Binance")
        logger.info("=" * 100)
        
        # Load messages
        messages = self.load_test_messages()
        logger.info(f"\n📊 Loaded {len(messages)} test messages\n")
        
        # Process each message
        for i, msg in enumerate(messages, 1):
            logger.info(f"\n\n{'='*100}")
            logger.info(f"TEST {i}/{len(messages)}")
            logger.info(f"{'='*100}")
            
            await self.process_test_message(msg)
            
            # Small delay between messages
            await asyncio.sleep(0.5)
        
        # Final summary
        logger.info("\n\n" + "=" * 100)
        logger.info("🏁 TEST SUITE COMPLETE")
        logger.info("=" * 100)
        
        # Query database for results
        conn = sqlite3.connect('improved_trading_bot.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT message_type, COUNT(*) 
            FROM messages 
            WHERE message_id >= 9000 
            GROUP BY message_type
        """)
        
        logger.info("\n📊 TEST RESULTS SUMMARY:")
        for msg_type, count in cursor.fetchall():
            logger.info(f"   {msg_type}: {count}")
        
        conn.close()
        
        logger.info("\n✅ All test messages processed!")
        logger.info("💡 Check the logs above to verify each action was analyzed correctly")
        logger.info("\n" + "=" * 100)

def main():
    """Main entry point"""
    print("\n🧪 Trading Bot Test Suite")
    print("=" * 100)
    print("This will simulate processing trading messages WITHOUT connecting to Telegram")
    print("and WITHOUT placing real trades on Binance.")
    print("=" * 100)
    
    input("\nPress Enter to start the test suite...")
    
    runner = TestRunner()
    asyncio.run(runner.run_test_suite())

if __name__ == '__main__':
    main()
