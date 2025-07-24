from trader import BinanceFuturesBot
from binance.client import Client

if __name__ == "__main__":
    # --- IMPORTANT ---
    # Store your API keys securely. Using environment variables is a good practice.
    API_KEY = "your api key"
    API_SECRET = "your api secret"
    
    # Trading parameters
    SYMBOL = "DOGEUSDT"
    INTERVAL = Client.KLINE_INTERVAL_1HOUR
    LEVERAGE = 10
    
    bot = BinanceFuturesBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol=SYMBOL,
        interval=INTERVAL,
        leverage=LEVERAGE
    )
    
    bot.run(interval_seconds=60)
