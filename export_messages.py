#!/usr/bin/env python3
"""
Export Messages to CSV for Backtesting
Exports message_actions table to CSV for offline analysis
"""

import sqlite3
import csv
from datetime import datetime

DB_PATH = 'improved_trading_bot.db'
OUTPUT_FILE = 'messages_export.csv'

def export_messages_to_csv():
    """Export all messages and actions to CSV"""
    
    print("📊 Exporting messages to CSV...")
    print(f"Database: {DB_PATH}")
    print(f"Output: {OUTPUT_FILE}")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check which table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_actions'")
    has_message_actions = cursor.fetchone() is not None
    
    if has_message_actions:
        print("\n✅ Using 'message_actions' table")
        cursor.execute("""
            SELECT 
                message_id, message_text, message_date,
                action_taken, action_details, symbol,
                success, error_message, processed_at
            FROM message_actions 
            ORDER BY message_date ASC
        """)
    else:
        print("\n✅ Using 'messages' table")
        cursor.execute("""
            SELECT 
                message_id, message_text, message_date,
                message_type as action_taken, 
                ai_analysis as action_details,
                '' as symbol,
                1 as success,
                '' as error_message,
                fetched_at as processed_at
            FROM messages 
            WHERE processed = 1
            ORDER BY message_date ASC
        """)
    
    rows = cursor.fetchall()
    
    if not rows:
        print("❌ No data found!")
        conn.close()
        return
    
    # Write to CSV
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        # Get column names
        column_names = rows[0].keys()
        writer = csv.DictWriter(csvfile, fieldnames=column_names)
        
        # Write header
        writer.writeheader()
        
        # Write rows
        for row in rows:
            writer.writerow(dict(row))
    
    conn.close()
    
    print(f"\n✅ Export complete!")
    print(f"📁 File: {OUTPUT_FILE}")
    print(f"📊 Records: {len(rows)}")
    print(f"📅 Date range: {rows[0]['message_date']} to {rows[-1]['message_date']}")
    print(f"\n💾 Download this file from your VM to use with backtest.py")
    print(f"\nTo download from VM:")
    print(f"   scp your-username@104.214.186.42:~/trading_dashboard/{OUTPUT_FILE} .")

if __name__ == '__main__':
    export_messages_to_csv()
