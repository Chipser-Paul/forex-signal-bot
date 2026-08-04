# forex-signal-bot

Algorithmic Trading Bot for XAUUSDm/BTCUSDm — modular 9-engine 
signal architecture (market structure, liquidity, fair-value-gap, 
confluence scoring, risk, and news/session filters).

A modular Forex trading / signal generation project. It contains components for strategy research, backtesting, a bot/engine to generate and execute signals, and a mobile/front-end wrapped in a Flutter app.

This README is customized from the repository contents. Please review and update configuration placeholders (API keys, broker credentials) before running.

## Project layout (high level)

- main.py — entry point for the bot/streamlit dashboard or orchestration.
- bot/ — core bot logic and integrations with messaging/broker(s).
- strategies/ — trading strategies and signal generation code.
- backtests/ — backtesting scripts and historical analysis.
- frontend/ — web frontend (if present).
- mobile_app/ — Flutter mobile application (mobile client).
- requirements.txt — Python dependencies.

## Features

- Strategy-based Forex signal generation
- Backtesting utilities for strategy evaluation
- Mobile and web front-ends to view signals and trades
- Trade execution helpers and utilities

## Requirements

- Python 3.9+ (3.10 recommended)
- pip
- Flutter SDK (only if you intend to build/run mobile_app)

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
.\.venv\Scripts\activate  # Windows
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

This project requires external credentials (API keys, broker credentials, chat tokens). Create a `.env` file or export environment variables before running. Example variables (replace with your provider names and keys):

- BROKER_API_KEY
- BROKER_SECRET
- TELEGRAM_BOT_TOKEN (if the bot uses Telegram for alerts)
- STREAMLIT_SERVER_PORT (if running the Streamlit dashboard)

Example .env (do NOT commit your secrets):

```
BROKER_API_KEY=your_api_key_here
BROKER_SECRET=your_secret_here
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
```

## Running

- To run the main bot/dashboard (replace with the actual command your repo uses):

```bash
python main.py
# or if there is a Streamlit dashboard
streamlit run main.py
```

- To run backtests (example):

```bash
python backtests/run_backtest.py --strategy strategies/your_strategy.py --from 2020-01-01 --to 2024-12-31
```

- To build/run the mobile app (in mobile_app/): follow the Flutter README in mobile_app/ (mobile_app/README.md).

## Development notes

- Add or update strategies in the strategies/ directory.
- Keep backtests isolated from production data; use saved historical datasets in backtests/data/ or similar.

## Contributing

Contributions are welcome. Please open an issue to discuss major changes first.

## License

License: MIT — see LICENSE file for details.
