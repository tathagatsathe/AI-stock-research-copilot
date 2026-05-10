# AI Stock Analysis Backend (FastAPI)

Production-ready starter backend for an AI stock analysis platform using FastAPI with a modular, LangGraph-ready architecture.

## Features

- FastAPI backend with versioned API routing
- Modular folder structure (`api`, `services`, `agents`, `core`)
- Environment-based configuration via `.env`
- Health check endpoint
- Stock technicals (price, 50-day SMA, RSI, optional 20-trading-day return) via Yahoo Finance
- Headline sentiment / keyword risk scan via Google News RSS (keyword heuristic; not deep NLP)
- Fundamentals snapshot from Yahoo Finance (`info` plus latest reported statements when available)
- Macro backdrop via CBOE VIX (^VIX): spot level, short drift, and a 1–10 “risk climate” score
- Deterministic 1–10 scores for preset strategies: Value, Growth, Momentum, Dividend, Quality (research-assistance only)
- Service and agent abstraction layer for AI workflows
- LangGraph dependency included and orchestrator scaffolded
- Docker and Docker Compose support

### Limitations

- Data is sourced from **free/public Yahoo endpoints** and RSS feeds; coverage gaps, delays, and occasional malformed quotes happen—API responses include `coverage` / `warnings` fields where relevant.
- Strategy scores and the decision brief are **rule-based heuristics**, not investment advice, forecasts, or suitability judgments (see `disclaimer` on full analysis responses).

## Project Structure

```text
.
├── app
│   ├── agents
│   │   ├── base.py
│   │   ├── stock_analysis_agent.py
│   │   └── workflow.py
│   ├── api
│   │   ├── routes
│   │   │   ├── health.py
│   │   │   └── stocks.py
│   │   └── router.py
│   ├── core
│   │   └── config.py
│   ├── services
│   │   ├── stock_analysis_service.py
│   │   ├── news_analysis_service.py
│   │   ├── decision_brief_service.py
│   │   ├── fundamentals_service.py
│   │   ├── macro_instability_service.py
│   │   ├── strategy_ratings_service.py
│   │   └── stock_universe_service.py
│   └── main.py
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Local Setup

### 1) Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment variables

```bash
cp .env.example .env
```

Update `.env` if needed.

### 4) Run the app

```bash
uvicorn app.main:app --reload
```

API will be available at:

- `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Endpoints

- `GET /api/v1/health` — health check

- `GET /api/v1/stocks/universe` — ~50 curated US large-cap rows for list/grid UIs (`name`, `ticker`, `price`, prior-session `change_pct`, `market_cap`, `volume`, `currency`, `exchange`). Delayed per Yahoo; fixed symbol set (not live index membership). Pair with detailed analysis below.

- `GET /api/v1/stocks/analysis?ticker=AAPL` — technical snapshot only (Yahoo Finance)

Example response:

```json
{
  "ticker": "AAPL",
  "current_price": 197.12,
  "sma_50": 190.73,
  "rsi": 58.42,
  "return_20d_pct": 3.21
}
```

- `GET /api/v1/stocks/analyze/{ticker}` — full payload: technicals, Google News RSS signals, fundamentals snapshot, VIX-based macro context, preset strategy scores (1–10), and a short rule-based decision brief.

The full response always includes a top-level `disclaimer` string. Other notable sections:

- `fundamentals` — `coverage` (`high` / `partial` / `low`), `warnings`, and normalized numeric `fields`
- `macro` — `vix_level`, `vix_change_5d_pct`, `volatility_regime`, `instability_score_1_10`
- `strategy_ratings` — entries for `value`, `growth`, `momentum`, `dividend`, and `quality`, each with `score_1_10`, `confidence`, `drivers`, `headwinds`, and `score_label`

## Docker

### Build and run with Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

App will run at `http://127.0.0.1:8000`.

## LangGraph-Ready Notes

`app/agents/workflow.py` contains the orchestration abstraction (`WorkflowOrchestrator`).
Replace the placeholder logic with a compiled LangGraph workflow and node graph execution when implementing production agent flows.
