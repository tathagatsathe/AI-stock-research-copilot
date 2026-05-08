# AI Stock Analysis Backend (FastAPI)

Production-ready starter backend for an AI stock analysis platform using FastAPI with a modular, LangGraph-ready architecture.

## Features

- FastAPI backend with versioned API routing
- Modular folder structure (`api`, `services`, `agents`, `core`)
- Environment-based configuration via `.env`
- Health check endpoint
- Service and agent abstraction layer for AI workflows
- LangGraph dependency included and orchestrator scaffolded
- Docker and Docker Compose support

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
│   │   └── stock_analysis_service.py
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

- `GET /api/v1/health` - health check
- `GET /api/v1/stocks/analysis?ticker=AAPL` - baseline stock analysis via service + agent layers

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
