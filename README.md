# FinScope TW — Taiwan Stock Research Agent

A grounded Taiwan-stock research assistant that decides when to retrieve live
market data, revenue history, and current web sources before answering. It is a
research tool—not a price predictor or trading-signal generator.

## What it demonstrates

- Agentic tool selection with a bounded multi-step loop
- Gemini Interactions API function calling
- Google Search grounding with structured citations
- Python/FastAPI calling a separate Java/Spring Boot data service
- Observable tool traces, failure handling, rate limiting, tests, and eval cases
- Cost-aware deployment where the hosted model stays outside the app container

## Architecture

```text
Browser
   │
   ▼
FastAPI research service ───────► Gemini Interactions API
   │                                └─ Google Search grounding
   │
   └── X-Agent-Key ─────────────► TaiwanStockTracker (Spring Boot)
                                      ├─ TWSE MIS
                                      ├─ FinMind
                                      └─ Neon PostgreSQL
```

Gemini receives function declarations but never receives database credentials.
The Python service executes approved read-only tools and sends only their JSON
results back to the model.

## Agent workflow

1. The model reads the user's Taiwan-stock research question.
2. It chooses zero or more tools:
   - `get_stock_snapshot`
   - `get_revenue_history`
   - managed `google_search`
3. FastAPI executes custom tools against the Java service.
4. Tool results return to the same Gemini interaction.
5. The model produces a Traditional Chinese brief with explicit limitations.
6. The UI displays the answer, tool trace, citations, and disclaimer.

The custom-tool loop is capped at three rounds. Invalid responses, timeouts,
unknown stock codes, and repeated tool calls fail closed instead of inventing
data.

## Project structure

```text
app/
├── agent/          # bounded orchestration loop and research policy
├── api/            # FastAPI endpoints
├── clients/        # Gemini and StockTracker provider adapters
├── middleware/     # portfolio-demo request limiter
├── schemas/        # validated API contracts
├── static/         # responsive research interface
└── tools/          # function declarations and execution
evals/cases.json    # fixed behavioral evaluation set
tests/              # orchestration, configuration, and HTTP adapter tests
```

## Requirements

- Python 3.12
- A running TaiwanStockTracker service with the Agent Data API
- Gemini API key with access to a Gemini 3 model

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Set the environment variables in your shell or load them with your preferred
local environment manager:

```text
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.6-flash
STOCKTRACKER_BASE_URL=http://localhost:8080
STOCKTRACKER_API_KEY=...
MAX_AGENT_STEPS=3
REQUEST_TIMEOUT_SECONDS=10
```

The application automatically loads a local `.env` file through
`python-dotenv`. The file is excluded from Git.

`STOCKTRACKER_API_KEY` must match `AGENT_API_KEY` on the Java service.

Run the app:

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000` or view the API contract at
`http://localhost:8000/docs`.

## API

### `POST /api/research`

```json
{
  "question": "台積電今天股價如何？近期有哪些重要事件？"
}
```

The response includes:

- the final research answer;
- every custom and managed search tool trace;
- structured source URLs returned by Gemini grounding;
- the active model ID and financial-information disclaimer.

### `GET /health`

Used by Render to wake and monitor the service.

## Verification

```bash
pytest
python -m compileall -q app
node --check app/static/app.js
```

The initial evaluation set in `evals/cases.json` covers quote lookup, company-name
resolution, OTC stocks, revenue, current news, citations, invalid codes,
weekends, upstream timeouts, direct investment advice, prediction requests,
causality overclaims, unrelated questions, and prompt injection.

With both services running, execute the deterministic tool-use checks:

```bash
python evals/run_evals.py --base-url http://localhost:8000
```

The runner scores required tool selection, important tool arguments, unnecessary
tool calls, and citation presence. Qualitative answer claims remain a manual
review item for the MVP.

## Deployment

The included `Dockerfile` and `render.yaml` deploy one lightweight FastAPI web
service to Render. Configure all secrets in Render—not in GitHub.

The Java service is deployed separately. Its public URL becomes
`STOCKTRACKER_BASE_URL`; the shared random service key is configured as
`AGENT_API_KEY` on Java and `STOCKTRACKER_API_KEY` on Python.

The model runs on Google's infrastructure, so no model weights or GPU runtime
are stored in the Render container.

## Responsible-use boundary

FinScope TW summarizes public information and identifies possible context. It
does not predict prices, guarantee causal explanations, personalize investment
recommendations, or execute trades. Users should verify primary sources before
making financial decisions.
