"""Test signal extraction with actual Telegram messages"""

import re

class SignalExtractor:
    @staticmethod
    def extract_long_signal(text):
        """Extract LONG signal details from message"""
        text_upper = text.upper()
        
        # Check if it's a LONG signal
        if 'LONG' not in text_upper:
            return None
        
        # Extract symbol (patterns: LONG - $API3, LONG - **$API3, **LONG - **$API3, etc.)
        symbol_pattern = r'LONG\s*-\s*\*{0,2}\s*\$([A-Z0-9]{2,15})'
        symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            # Try alternative pattern without dash
            symbol_pattern = r'LONG\s*\*{0,2}\s*\$([A-Z0-9]{2,15})'
            symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            return None
        
        symbol = symbol_match.group(1)
        
        # Extract entry price (handle multiple formats)
        # Format: - Entry: 0.8571 or - Entry: 1.836 (30% VOL) or - Entry: 5.749 ( 30% VOL)
        entry_pattern = r'-\s*ENTRY(?:\s*LIMIT)?[:\s]*(\d+(?:\.\d+)?)'
        entry_match = re.search(entry_pattern, text_upper)
        if not entry_match:
            return None
        
        entry_price = float(entry_match.group(1))
        
        # Extract stop loss
        # Format: - SL: 0.8030
        sl_pattern = r'-\s*SL[:\s]*(\d+(?:\.\d+)?)'
        sl_match = re.search(sl_pattern, text_upper)
        if not sl_match:
            return None
        
        stop_loss = float(sl_match.group(1))
        
        # Extract take profit
        # Format: 🎯 TP: 1.5278
        tp_pattern = r'(?:🎯|TARGET)?\s*TP[:\s]*(\d+(?:\.\d+)?)'
        tp_match = re.search(tp_pattern, text_upper)
        if not tp_match:
            return None
        
        take_profit = float(tp_match.group(1))
        
        return {
            'type': 'LONG',
            'symbol': symbol + 'USDT',
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    @staticmethod
    def extract_close_signal(text):
        """Extract CLOSE signal details from message"""
        text_upper = text.upper()
        
        # Only treat as CLOSE signal if it explicitly mentions "close" in the message
        if 'CLOSE' not in text_upper:
            return None
        
        # Extract symbol - pattern: SYMBOL + percentage% profit OR just SYMBOL before "close"
        # First try: SYMBOL + percentage% profit
        symbol_pattern = r'([A-Z0-9]{2,15})\s*(?:\+|\s+EVERYONE\s+CAN\s+CLOSE)'
        symbol_match = re.search(symbol_pattern, text_upper)
        if not symbol_match:
            return None
        
        symbol = symbol_match.group(1)
        
        # Extract profit percentage if present
        profit_pattern = r'(\d+(?:\.\d+)?)\s*%\s*PROFIT'
        profit_match = re.search(profit_pattern, text_upper)
        
        profit_pct = float(profit_match.group(1)) if profit_match else 0
        
        return {
            'type': 'CLOSE',
            'symbol': symbol + 'USDT',
            'profit_percentage': profit_pct
        }

# Test messages from your actual Telegram
test_messages = [
    """🟢 SWING ORDER - SMALL VOL

LONG - $AVAX
- Entry: 28.24
- SL: 27.26
🎯 TP: 30.06

Reason behind this call:

AVAX is running in an ascending triangle pattern, the price is still creating a solid base and waiting for a pump break.

⚠️ Disclaimer
This is not financial advice. Trade at your own risk. Our team will continue to provide timely updates on trade actions and performance in real-time.S""",
    
    """🟢 SWING ORDER - SMALL VOL

LONG - $TAKE
- Entry: 0.22383
- SL: 0.19818
🎯 TP: 0.32645

Reason behind this call:

TAKE is running in an ascending triangle pattern, the price is still creating a solid base and waiting for a pump break.

⚠️ Disclaimer
This is not financial advice. Trade at your own risk. Our team will continue to provide timely updates on trade actions and performance in real-time.S""",
    
    """TAKE everyone can close 50% profit then hold to target or close to cover order before that""",
    
    """🟢 SWING ORDER - SMALL VOL

LONG - $MYX
- Entry: 5.749 ( 30% VOL)
- Entry Limit: 4.443 ( 70% VOL)
- SL: 3.682
🎯 TP: 16.343

Reason behind this call:

MYX is running in an ascending triangle pattern, the price is still creating a solid base and waiting for a pump break.

⚠️ Disclaimer
This is not financial advice. Trade at your own risk. Our team will continue to provide timely updates on trade actions and performance in real-time.S"""
]

print("="*80)
print("TESTING SIGNAL EXTRACTION")
print("="*80)

extractor = SignalExtractor()

for i, msg in enumerate(test_messages, 1):
    print(f"\n\n{'='*80}")
    print(f"TEST MESSAGE #{i}")
    print(f"{'='*80}")
    print(f"Message:\n{msg}")
    print(f"\n{'-'*80}")
    
    # Try LONG signal
    long_signal = extractor.extract_long_signal(msg)
    if long_signal:
        print("✅ LONG SIGNAL DETECTED:")
        print(f"   Symbol: {long_signal['symbol']}")
        print(f"   Entry: ${long_signal['entry_price']:.5f}")
        print(f"   Stop Loss: ${long_signal['stop_loss']:.5f}")
        print(f"   Take Profit: ${long_signal['take_profit']:.5f}")
    
    # Try CLOSE signal
    close_signal = extractor.extract_close_signal(msg)
    if close_signal:
        print("✅ CLOSE SIGNAL DETECTED:")
        print(f"   Symbol: {close_signal['symbol']}")
        print(f"   Profit: {close_signal['profit_percentage']:+.2f}%")
    
    if not long_signal and not close_signal:
        print("❌ NO SIGNAL DETECTED")

print(f"\n\n{'='*80}")
print("SUMMARY")
print("="*80)
print("Expected results:")
print("  Message #1: AVAX LONG signal")
print("  Message #2: TAKE LONG signal")
print("  Message #3: TAKE CLOSE signal")
print("  Message #4: MYX LONG signal")
print("="*80)
