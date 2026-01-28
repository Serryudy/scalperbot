import sys
import os
import logging
from dotenv import load_dotenv

# Add parent directory to path to allow importing trader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env before importing trader to ensure config is set
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_email_capability():
    print("🧪 Testing Email Capability...")
    
    try:
        from trader import send_email_alert, EMAIL_CONFIG
    except ImportError as e:
        print(f"❌ Failed to import trader module: {e}")
        return

    print(f"📧 Configuration Status:")
    print(f"   Enabled: {EMAIL_CONFIG.get('enabled')}")
    print(f"   From: {EMAIL_CONFIG.get('from_email')}")
    print(f"   To: {EMAIL_CONFIG.get('to_email')}")
    print(f"   SMTP Server: {EMAIL_CONFIG.get('smtp_server')}:{EMAIL_CONFIG.get('smtp_port')}")
    
    if not EMAIL_CONFIG.get('enabled'):
        print("\n⚠️ Email is DISABLED in configuration.")
        print("To enable, set EMAIL_ENABLED=True in your .env file.")
        return

    subject = "Test Email Capability Verification"
    body = (
        "This is a test email sent from the 'tests/test_email_capability.py' script.\n\n"
        "If you received this, the email sending capability in trader.py is working correctly.\n"
        f"Time: {os.popen('date /t').read().strip() if os.name == 'nt' else os.popen('date').read().strip()}"
    )
    
    print(f"\nki📨 Sending test email...")
    print(f"Subject: {subject}")
    
    try:
        # Call the function from trader.py
        send_email_alert(subject, body)
        print("\n✅ send_email_alert function execution completed.")
        print("Please check the logs above. If successful, you should see '📧 Alert email sent'.")
        print("Don't forget to check your inbox (and spam folder)!")
    except Exception as e:
        print(f"\n❌ Exception occurred while sending email: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_email_capability()
