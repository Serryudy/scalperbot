import sys
import os
import json
import logging
import requests

# Add parent directory to path so we can import trader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trader import DEEPSEEK_CONFIG

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestDeepSeek")

def test_deepseek_connection():
    print("Testing DeepSeek Connection...")
    print(f"URL: {DEEPSEEK_CONFIG['base_url']}")
    print(f"Model: {DEEPSEEK_CONFIG['model']}")
    
    # Test message
    test_msg = "Hello! Please confirm you are working."
    print(f"\nSending test message: '{test_msg}'")
    
    try:
        response = requests.post(
            f"{DEEPSEEK_CONFIG['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_CONFIG['api_key']}",
                "Content-Type": "application/json"
            },
            json={
                "model": DEEPSEEK_CONFIG['model'],
                "messages": [
                    {"role": "user", "content": test_msg}
                ],
                "max_tokens": 50
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("Response:", json.dumps(result, indent=2))
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f"\nContent: {content}")
            print("\n✅ DeepSeek Connection Successful")
        else:
            print("Error Response:", response.text)
            print("\n❌ DeepSeek Connection Failed")

    except Exception as e:
        print(f"\n❌ Exception: {e}")

if __name__ == "__main__":
    test_deepseek_connection()
