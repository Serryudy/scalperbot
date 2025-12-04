"""
Database Migration Script: Add exit_price column to positions table

This migration adds the exit_price column to store the actual exit price
from Binance when positions are closed, allowing for accurate PNL display.
"""

import sqlite3
from datetime import datetime

DB_PATH = 'improved_trading_bot.db'

def migrate():
    """Add exit_price column to positions table"""
    print("🔄 Starting database migration...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(positions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'exit_price' in columns:
            print("✅ Column 'exit_price' already exists, skipping migration")
            return
        
        # Add exit_price column
        print("📝 Adding 'exit_price' column to positions table...")
        cursor.execute('''
            ALTER TABLE positions 
            ADD COLUMN exit_price REAL
        ''')
        
        conn.commit()
        print("✅ Migration completed successfully!")
        print(f"   - Added 'exit_price' column to positions table")
        print(f"   - Timestamp: {datetime.now()}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
