# IB Trading Assistant

A rule-based trading assistant that connects to Interactive Brokers, monitors real-time market data, and sends alerts based on user-defined trading rules.

## Features (Planned)

- **IB Connection**: Real-time market data streaming via TWS API
- **Rule Engine**: Define custom trading rules (price alerts, technical indicators, position-based rules)
- **Notifications**: Telegram/Email alerts when rules are triggered
- **Dashboard**: Web UI for managing rules and monitoring positions
- **AWS Deployment**: Dockerized application running on ECS with CI/CD via Jenkins

## Tech Stack

- **Language**: Python 3.11+
- **IB API**: ib_async (successor to ib_insync)
- **Web Framework**: FastAPI
- **Database**: PostgreSQL (SQLite for local dev)
- **Cache**: Redis
- **Deployment**: Docker → AWS ECS
- **CI/CD**: Jenkins

## Prerequisites

1. **Interactive Brokers Account** with Paper Trading enabled
2. **TWS or IB Gateway** installed and running
3. **Python 3.11+**
4. **API Settings in TWS/Gateway**:
   - Enable API: Configure → API → Settings → Enable ActiveX and Socket Clients
   - Port: 7497 (TWS Paper) or 4002 (Gateway Paper)
   - Add 127.0.0.1 to Trusted IPs
   - Check "Download open orders on connection"

## Quick Start

```bash
# Clone the repo
git clone <your-repo-url>
cd ib-trading-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Make sure TWS/IB Gateway is running with Paper Account

# Test connection
python src/core/connection.py

# Get account info
python src/data/account.py

# Stream real-time quotes
python src/data/market_data.py

# Get options chain
python src/data/options.py
```

## Project Structure

```
ib-trading-assistant/
├── src/
│   ├── core/           # IB connection management
│   ├── data/           # Market data, account info, options
│   ├── rules/          # Rule engine (coming soon)
│   └── notifications/  # Alert system (coming soon)
├── tests/
├── config/
├── docs/
├── requirements.txt
├── Dockerfile          (Phase 2)
├── Jenkinsfile         (Phase 3)
└── README.md
```
