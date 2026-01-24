import sys
import os
import logging
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env before importing trader to ensure config is set
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)

from trader import handle_critical_error, EMAIL_CONFIG

def test_email_alert():
    print("🧪 Testing Critical Error Alert System...")
    print(f"📧 Email Enabled: {EMAIL_CONFIG['enabled']}")
    print(f"📧 To: {EMAIL_CONFIG['to_email']}")
    
    if not EMAIL_CONFIG['enabled']:
        print("⚠️ Email alerts are disabled in config. Skipping test.")
        return

    try:
        # Simulate a critical error
        print("\n💥 Simulating a critical division-by-zero error...")
        x = 1 / 0
    except Exception as e:
        print("⚡ Catching exception and triggering alert...")
        handle_critical_error("TEST_SCRIPT_VERIFICATION", e)
        print("\n✅ Alert trigger called. Check your inbox for an email with subject '🚨 CRITICAL: Trading Bot Error in TEST_SCRIPT_VERIFICATION'")

if __name__ == "__main__":
    test_email_alert()
