"""
Script to update Binance API credentials to use demo/testnet account
"""
import re

# Update trader.py
with open('trader.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the old API keys with new demo keys  
old_binance_config = """BINANCE_CONFIG = {
    'api_key': '9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ',
    'api_secret': 'mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl'
}"""

new_binance_config = """BINANCE_CONFIG = {
    # ⚠️ DEMO/TESTNET ACCOUNT - Temporary for testing
    'api_key': 'NPCpHKP3Qi5GyEWlfknmrbipXXg6NbBULsfseqaDzsZ5LYjigQmydblIP9ZgvHs7',
    'api_secret': 'dmZmE6NNzZcw6Dyx0blRlZYy1PziJccvUVUAjyPUsRyohc3cDttjdsbSNpyM5vXs',
    'testnet': True  # Using testnet/demo environment
}"""

content = content.replace(old_binance_config, new_binance_config)

# Update BinanceTrader __init__ method
old_trader_init = """class BinanceTrader:
    def __init__(self, api_key, api_secret):
        self.client = Client(api_key, api_secret)"""

new_trader_init = """class BinanceTrader:
    def __init__(self, api_key, api_secret, testnet=False):
        self.client = Client(api_key, api_secret, testnet=testnet)"""

content = content.replace(old_trader_init, new_trader_init)

# Update the BinanceTrader instantiation to pass testnet parameter
# Find the pattern where BinanceTrader is initialized with BINANCE_CONFIG
old_trader_call_pattern = r"BinanceTrader\(\s*BINANCE_CONFIG\['api_key'\],\s*BINANCE_CONFIG\['api_secret'\]\s*\)"
new_trader_call = "BinanceTrader(\n            BINANCE_CONFIG['api_key'],\n            BINANCE_CONFIG['api_secret'],\n            testnet=BINANCE_CONFIG.get('testnet', False)\n        )"

content = re.sub(old_trader_call_pattern, new_trader_call, content)

with open('trader.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Updated trader.py with demo credentials")

# Update api.py 
with open('api.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_api_key_line = "BINANCE_API_KEY = '9pkSF4J0rpXeVor9uDeqgAgMBTUdS0xqhomDxIOqYy0OMGAQMmj6d402yuLOJWQQ'"
new_api_key_line = "# ⚠️ DEMO/TESTNET ACCOUNT - Temporary for testing\nBINANCE_API_KEY = 'NPCpHKP3Qi5GyEWlfknmrbipXXg6NbBULsfseqaDzsZ5LYjigQmydblIP9ZgvHs7'"

old_secret_line = "BINANCE_API_SECRET = 'mIQHkxDQAOM58eRbrzTNqrCr0AQJGtmvEbZWXkiPgci8tfMV6bqLSCWCY3ymF8Xl'"
new_secret_line = "BINANCE_API_SECRET = 'dmZmE6NNzZcw6Dyx0blRlZYy1PziJccvUVUAjyPUsRyohc3cDttjdsbSNpyM5vXs'"

content = content.replace(old_api_key_line, new_api_key_line)
content = content.replace(old_secret_line, new_secret_line)

# Also update the client initialization to use testnet
old_client_line = "binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)"
new_client_line = "binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=True)  # Using testnet/demo"

content = content.replace(old_client_line, new_client_line)

with open('api.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Updated api.py with demo credentials")
print("\n⚠️  Remember: These are temporary testnet credentials. Revert when done testing!")
print("\nℹ️  The Binance testnet/demo environment is separate from production.")
print("   - Testnet data may differ from production")
print("   - Testnet USDT balance is for testing only")
print("   - Use https://testnet.binancefuture.com to fund your testnet account")
