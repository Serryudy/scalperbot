# Trading Dashboard - Files Overview

## 🚀 Core Application Files (Required to Run)

### Main Bot
- **trader.py** - Main trading bot with AI signal processing
- **trader_extensions.py** - Extension module with new features
- **api.py** - REST API backend for querying positions and PNL

### Configuration
All credentials and settings are in the Python files (TELEGRAM_CONFIG, BINANCE_CONFIG, etc.)

---

## 📁 Data Files

### Databases (SQLite)
- **improved_trading_bot.db** - Main production database (KEEP THIS!)
- **ai_trading_bot.db** - Old database (can be deleted if not needed)
- **trading_bot.db** - Old database (can be deleted if not needed)

### Telegram Session Files
- **my_session.session** - Active Telegram session (KEEP THIS!)
- **improved_ai_trading_session.session** - Alternative session
- **session_name.session** - Alternative session
- **trading_bot_session.session** - Alternative session

*Note: Keep at least one .session file. Delete others if not needed.*

---

## 📋 Documentation
- **TIMING_FIX_SUMMARY.md** - Documentation about timestamp fixes
- **trading_bot.log** - Log file (will be recreated)
- **.gitignore** - Git configuration

---

## 🗂️ Project Structure
- **venv/** - Virtual environment
- **.git/** - Git repository

---

## 🗑️ Recently Cleaned Up

The following development files have been removed:
- ❌ apply_changes.py
- ❌ final_integration.py
- ❌ update_trader.py
- ❌ trader_backup_before_integration.py
- ❌ trader_backup_original.py
- ❌ trader_modified.py
- ❌ test.db
- ❌ test_new.db
- ❌ apply_profit_transfer.py
- ❌ extract.py
- ❌ __pycache__/

---

## 🎯 Minimal Setup to Run

### Required Files:
```
trading_dashboard/
├── trader.py                           # Main bot
├── trader_extensions.py                # Extensions module
├── api.py                              # REST API
├── improved_trading_bot.db             # Database
├── my_session.session                  # Telegram session
└── venv/                               # Python packages
```

### Optional (can delete if not needed):
- ai_trading_bot.db
- trading_bot.db
- Other .session files (keep only one)
- TIMING_FIX_SUMMARY.md
- trading_bot.log

---

## ▶️ How to Run

### Start the Trading Bot:
```bash
python trader.py
```

### Start the API (separate terminal):
```bash
python api.py
```

---

## 📦 Dependencies

Required Python packages (in venv):
- telethon
- python-binance
- requests
- flask
- flask-cors

Install with:
```bash
pip install telethon python-binance requests flask flask-cors
```

---

## 💡 Quick Commands

### Clean old database files (optional):
```powershell
# Review first, then delete if not needed:
Remove-Item ai_trading_bot.db, trading_bot.db
```

### Clean extra session files (optional):
```powershell
# Keep my_session.session, delete others:
Remove-Item improved_ai_trading_session.session, session_name.session, trading_bot_session.session
```

### View current directory size:
```powershell
Get-ChildItem -Recurse | Measure-Object -Property Length -Sum
```

---

## ✨ Current Directory Status

**Clean and production-ready!**

All development and backup files have been removed.
Only essential runtime files remain.
