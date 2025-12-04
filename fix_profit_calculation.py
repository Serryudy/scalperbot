"""
Fix Script: Add exit_price parameter to update_position_status
"""

import re

def fix_update_position_status():
    """Update update_position_status method to handle exit_price"""
    
    with open('trader.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print("🔧 Fixing update_position_status method...")
    
    # Find the method and update it
    in_method = False
    method_start = None
    
    for i, line in enumerate(lines):
        # Find method definition
        if 'def update_position_status(self, position_id, status, profit_pct=None, close_reason=None):' in line:
            lines[i] = line.replace(
                'def update_position_status(self, position_id, status, profit_pct=None, close_reason=None):',
                'def update_position_status(self, position_id, status, profit_pct=None, close_reason=None, exit_price=None):'
            )
            print(f"✅ Updated method signature at line {i+1}")
            method_start = i
            in_method = True
        
        # Update the SQL query within the method
        if in_method and 'SET status = ?, profit_percentage = ?, closed_at = ?, close_reason = ?' in line:
            lines[i] = line.replace(
                'SET status = ?, profit_percentage = ?, closed_at = ?, close_reason = ?',
                'SET status = ?, profit_percentage = ?, exit_price = ?, closed_at = ?, close_reason = ?'
            )
            print(f"✅ Updated SQL query at line {i+1}")
        
        # Update the execute parameters
        if in_method and "''', (status, profit_pct, datetime.now(timezone.utc), close_reason, position_id))" in line:
            lines[i] = line.replace(
                "''', (status, profit_pct, datetime.now(timezone.utc), close_reason, position_id))",
                "''', (status, profit_pct, exit_price, datetime.now(timezone.utc), close_reason, position_id))"
            )
            print(f"✅ Updated execute parameters at line {i+1}")
            in_method = False
    
    # Save the updated file
    with open('trader.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("\n✅ trader.py updated successfully!")
    print("\n📝 Changes made:")
    print("   1. Added exit_price parameter to update_position_status()")
    print("   2. Updated SQL query to include exit_price column")
    print("   3. Updated execute() parameters to pass exit_price value")

if __name__ == '__main__':
    fix_update_position_status()
