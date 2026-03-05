# SentinelTrader - Project Context

## Project Overview
Trading assistant that connects to Interactive Brokers to execute custom trading rules, monitor signals, and manage positions.

## Tech Stack
- **Backend**: Python 3.11+, ib_async, FastAPI
- **Database**: PostgreSQL, Redis
- **Frontend**: React
- **IB API**: TWS API via ib_async (NOT Client Portal API)
- **Deployment**: Docker → AWS ECS, Jenkins CI/CD

## Development Environment
- **OS**: Windows, VS Code
- **IB Connection**: TWS Paper Account, port 7497
- **Virtual env**: `venv/` in project root

## Project Structure
标准分层结构：

```
src/
├── core/         # IB连接、账户、订单执行
│   ├── connection.py   IB connection management via ib_async
│   └── account.py      Account data (balances, positions, P&L)
├── data/         # 行情数据、期权链
│   ├── market_data.py  Real-time market data streaming
│   └── options.py      Options chain data
├── config/       # 配置
│   └── settings.py     Configuration and environment variables
├── rules/        # 规则引擎（下一阶段）
└── api/          # FastAPI接口（下一阶段）
tests/            # 测试
requirements.txt  # 根目录
.env              # 根目录
```

**运行方式**（从项目根目录）：
```bash
python -m src.core.connection
python -m src.core.account
python -m src.data.market_data
python -m src.data.options [SYMBOL]
```

## Current Status
**MVP Phase 1 complete:**
- IB connection via ib_async
- Account data retrieval
- Real-time market data
- Options chain

**Next phase:** Rules engine development

## Trading Instruments
US equities, options, ETFs

## Key Conventions
- Use `ib_async` for all IB API interactions — never the raw `ibapi` client directly
- Async/await throughout (ib_async is async-first)
- TWS must be running on port 7497 (paper) before connecting
- Do not use IB Client Portal REST API
