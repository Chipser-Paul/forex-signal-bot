# Forex Signal Bot

Forex Signal Bot is a Python trading research and execution project for MetaTrader 5. It explores SMC-style market structure analysis, liquidity mapping, fair value gaps, risk controls, backtesting, and dashboard tooling for strategy evaluation.

Repository: https://github.com/Chipser-Paul/forex-signal-bot

## Hiring-Manager Snapshot

- Python system with modular analysis, execution, state, risk, and notification layers
- MetaTrader 5 integration for market data and broker connection workflows
- Backtesting utilities with generated trade summaries and equity curves
- Streamlit-style frontend modules for dashboard, settings, analytics, AI assistant, and session management
- AI-assisted analysis hooks through Groq/OpenAI-compatible chat APIs
- Tests for session-clock behavior and architecture notes in `ARCHITECTURE.md`

## Important Safety Note

This is a research and portfolio engineering project, not financial advice and not a guaranteed trading system. Live trading requires independent review, broker testing, risk controls, and responsible capital management.

## Features

- Market structure and structural-shift analysis
- Liquidity mapping and fair value gap detection
- Symbol-specific configuration profiles
- Risk engine and trade execution modules
- Shadow-mode backtesting and diagnostic scripts
- Telegram and Firebase notification hooks
- Frontend utilities for MT5 login, dashboard, analytics, settings, and AI assistance
- Optional Groq-powered AI analysis helpers

## Tech Stack

- Python
- MetaTrader5 package
- pandas and NumPy
- scikit-learn
- FastAPI / Uvicorn utilities
- Streamlit-style frontend modules
- Firebase Admin SDK
- Groq/OpenAI-compatible API calls

## Project Layout

```text
main.py                  Main bot runner
bot/                     Analysis, execution, state, and utility modules
config/                  Symbol profiles and shared configuration
strategies/smc_engine/   SMC-style strategy components
utils/                   MT5 connection, indicators, logging, notifications, risk helpers
frontend/                Dashboard, settings, analytics, AI assistant, and session utilities
backtests/               Backtest scripts and generated strategy research outputs
tests/                   Focused Python tests
docs/                    Supporting documentation
ARCHITECTURE.md          System architecture notes
```

## Local Setup

1. Create and activate a virtual environment.

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create your environment file:

```bash
copy .env.example .env
```

4. Configure MT5 credentials and optional notification/API keys.

5. Run a basic test:

```bash
python -m pytest tests
```

6. Start the main runner only after your MT5 terminal and credentials are configured:

```bash
python main.py
```

## Environment Variables

See `.env.example` for placeholders.

Key values:

- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`
- `BOT_ACTIVE_ENGINE`
- `BOT_CAPITAL`
- `GROQ_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `FIREBASE_SERVICE_ACCOUNT_PATH`
- `NEWS_EVENTS_PATH`

## Repository Hygiene

Generated runtime data, caches, diagnostic runs, and local process files should stay out of commits. The `.gitignore` includes patterns for runtime folders, Python bytecode, `.env` files, cached market data, and temporary patch files.

## Current Status

Active research project. Best presented to hiring managers as a Python systems, data workflow, and trading-platform integration project rather than as a production financial product.

## License

MIT
