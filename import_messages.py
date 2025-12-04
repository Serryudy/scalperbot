#!/usr/bin/env python3
"""
Import Messages from CSV for Backtesting
Imports CSV file into local database for backtesting
"""

import sqlite3
import csv

DB_PATH = 'improved_trading_bot.db'
INPUT_FILE = 'messages_export.csv'

def import_messages_from_csv():
    """Import messages from CSV to local database"""
    
    print("📥 Importing messages from CSV...")
    print(f"Input: {INPUT_FILE}")
    print(f"Database: {DB_PATH}")
    
    # Read CSV
    with open(INPUT_FILE, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)
    
    print(f"📊 Found {len(rows)} records in CSV")
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create message_actions table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            message_text TEXT,
            message_date TIMESTAMP,
            action_taken TEXT,
            action_details TEXT,
            symbol TEXT,
            success INTEGER,
            error_message TEXT,
            processed_at TIMESTAMP
        )
    """)
    
    # Clear existing data (optional - comment out if you want to keep existing data)
    print("🗑️  Clearing existing data...")
    cursor.execute("DELETE FROM message_actions")
    
    # Insert data
    print("💾 Inserting records...")
    for row in rows:
        cursor.execute("""
            INSERT INTO message_actions 
            (message_id, message_text, message_date, action_taken, action_details,
             symbol, success, error_message, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get('message_id'),
            row.get('message_text'),
            row.get('message_date'),
            row.get('action_taken'),
            row.get('action_details'),
            row.get('symbol'),
            row.get('success', 1),
            row.get('error_message', ''),
            row.get('processed_at')
        ))
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Import complete!")
    print(f"📊 Imported {len(rows)} records")
    print(f"\n🎯 Ready for backtesting! Run: python backtest.py")

if __name__ == '__main__':
    import_messages_from_csv()
