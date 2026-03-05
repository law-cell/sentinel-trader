# SentinelTrader

A rule-based trading assistant that connects to Interactive Brokers, monitors real-time market data, and sends alerts based on user-defined trading rules.

## Features

- **IB Connection**: Real-time market data streaming via TWS API
- **Rule Engine**: Define custom trading rules (price alerts, technical indicators, position-based rules)
- **Notifications**: Telegram alerts when rules are triggered
- **Dashboard**: Web UI for managing rules and monitoring positions
- **AWS Deployment**: Dockerized application running on ECS with CI/CD via Jenkins

## Tech Stack

- **Language**: Python 3.11+
- **IB API**: ib_async (successor to ib_insync)
- **Web Framework**: FastAPI
- **Frontend**: React + Vite + TypeScript + Tailwind CSS
- **Database**: PostgreSQL (planned)
- **Cache**: Redis (planned)
- **Deployment**: Docker → AWS ECS
- **CI/CD**: Jenkins

## Prerequisites

1. **Interactive Brokers Account** with Paper Trading enabled
2. **TWS or IB Gateway** installed and running
3. **Python 3.11+** and **Node.js 18+**
4. **API Settings in TWS/Gateway**:
   - Enable API: Configure → API → Settings → Enable ActiveX and Socket Clients
   - Port: 7497 (TWS Paper) or 4002 (Gateway Paper)
   - Add 127.0.0.1 to Trusted IPs

## Quick Start

```bash
# Clone the repo
git clone <your-repo-url>
cd ib-trading-assistant

# Backend
python -m venv venv
source venv/Scripts/activate  # Windows
pip install -r requirements.txt
cp .env.example .env          # fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
python run_api.py             # http://localhost:8000/docs

# Frontend (separate terminal)
cd web
npm install
npm run dev                   # http://localhost:5173
```

## Project Structure

```
ib-trading-assistant/
├── src/
│   ├── api/            # FastAPI routes and schemas
│   ├── core/           # IB connection and account data
│   ├── data/           # Market data and options chain
│   ├── notifications/  # Telegram notifier
│   └── rules/          # Rule engine (conditions, actions, loader)
├── web/                # React frontend
├── tests/
├── rules.json          # Active trading rules
├── run_api.py          # API server launcher
└── requirements.txt
```
