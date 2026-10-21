# MTG Deck Doctor

Analyze Magic: The Gathering decks with **deterministic statistics** and **grounded LLM recommendations**, with **Old School Swedish** as the primary format ([Swedish OS rules](https://ragingbullseries.com/index.php/swedish-os-rules/)). Submit a deck list, watch analysis progress over Server-Sent Events, and receive validated card suggestions backed by Scryfall data — never invented names.

> Card prices may be missing or stale. This application does **not** fully verify tournament legality; Old School Swedish candidate search uses the Swedish OS legal sets and filters banned cards, but B&R can change.

## Features

- Create and retrieve decks with Scryfall name resolution
- Deterministic metrics: card counts, mana curve, colors, types
- Async analysis jobs via transactional outbox + RabbitMQ
- LangGraph workflow with structured, candidate-grounded LLM output
- Real-time progress over SSE (persisted events, reconnect replay)
- Simple responsive web UI (no frontend build step)
- Docker Compose stack for local development

## Architecture

```mermaid
flowchart LR
  UI[Web UI] --> API[FastAPI]
  API --> PG[(PostgreSQL)]
  API --> Outbox[Outbox table]
  Pub[Outbox publisher] --> Outbox
  Pub --> RMQ[RabbitMQ]
  RMQ --> Worker[Analysis worker]
  Worker --> Scryfall[Scryfall API]
  Worker --> LLM[LangChain / LangGraph]
  Worker --> PG
  UI -->|SSE| API
```

**Why RabbitMQ?** Analysis can take tens of seconds (Scryfall + LLM). The API returns `202` immediately; workers process jobs asynchronously with durable queues and manual acks.

**Why SSE?** Progress is persisted as `analysis_events` rows. Clients stream those events (with `Last-Event-ID` replay) without polling a custom websocket stack.

**Transactional outbox:** Creating an analysis inserts the job and an outbox row in one DB transaction. A publisher process pushes unpublished messages to RabbitMQ and marks them published only after confirm. Consumers are idempotent so duplicate deliveries (crash after publish, before `published_at`) cannot complete the same job twice.

## Technology stack

| Layer | Choice |
| --- | --- |
| API | Python 3.12+, FastAPI, Uvicorn, Pydantic v2 |
| DB | PostgreSQL, SQLAlchemy 2, Alembic |
| Messaging | RabbitMQ, aio-pika |
| AI | LangChain, LangGraph, OpenAI-compatible chat model (`LLM_BASE_URL`) |
| HTTP | httpx (Scryfall) |
| Frontend | HTML / CSS / vanilla JS |
| Ops | Docker Compose, Ruff, pytest |

## Prerequisites

- Docker and Docker Compose **or**
- Python 3.12+, PostgreSQL 16, RabbitMQ 3.13
- An OpenAI-compatible API key for live LLM recommendations (tests use a fake model)

## Environment configuration

```bash
cp .env.example .env
# Set LLM_API_KEY for real recommendations
```

See `.env.example` for all variables. RabbitMQ defaults (`guest` / `guest`) are for **local development only**.

`LLM_PROVIDER` must stay `openai` (LangChain `ChatOpenAI`). Any OpenAI-compatible API works via optional `LLM_BASE_URL`. Example for DeepSeek:

```bash
LLM_PROVIDER=openai
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com
```

Leave `LLM_BASE_URL` empty to use the default OpenAI endpoint.

## Startup (Docker Compose)

```bash
cp .env.example .env
# Fill in LLM_API_KEY (and LLM_MODEL / LLM_BASE_URL if not using OpenAI)
```

Containers do not read `.env` on their own. In `docker-compose.yml`, `api`, `worker`, `outbox-publisher`, and `migrate` set `env_file` to `.env.example`, where `LLM_API_KEY` is empty. Once `.env` has your credentials, point those entries at it:

```yaml
    env_file:
      - .env
```

The analysis **worker** is the process that calls the LLM. Recreate it after the change (a running container keeps the old file):

```bash
docker compose up -d --force-recreate worker
```

First startup, or after the `env_file` edit:

```bash
docker compose up --build
```

Services:

| Service | Role |
| --- | --- |
| `api` | HTTP + UI on [http://localhost:55700](http://localhost:55700) |
| `worker` | Consumes analysis jobs |
| `outbox-publisher` | Publishes outbox → RabbitMQ |
| `postgres` | Database (port 5432 for local tooling) |
| `rabbitmq` | Broker + management UI on [http://localhost:15672](http://localhost:15672) |
| `migrate` | One-shot `alembic upgrade head` |

Migrations run automatically via the `migrate` service before API/worker start.

## Database migrations (manual)

```bash
export DATABASE_URL=postgresql+asyncpg://mtg:mtg@localhost:5432/mtg_deck_doctor
alembic upgrade head
```

## Local development (without Docker for the app)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# Start Postgres + RabbitMQ (e.g. docker compose up postgres rabbitmq -d)
alembic upgrade head
uvicorn app.main:app --reload --port 55700
python -m app.workers.outbox_publisher
python -m app.workers.analysis_worker
```

## Tests

Default suite mocks Scryfall and uses a deterministic fake LLM — **no API key required**:

```bash
pytest
ruff check app tests
```

## Example API requests

Create a deck:

```bash
curl -s -X POST http://localhost:55700/api/v1/decks \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Burn test",
    "format": "modern",
    "cards": [
      {"name": "Lightning Bolt", "quantity": 4},
      {"name": "Monastery Swiftspear", "quantity": 4},
      {"name": "Mountain", "quantity": 20}
    ]
  }'
```

Start an analysis:

```bash
curl -s -X POST http://localhost:55700/api/v1/decks/<deck_id>/analyses \
  -H 'Content-Type: application/json' \
  -d '{"budget_usd": 30, "recommendation_count": 3}'
```

Stream events:

```bash
curl -N http://localhost:55700/api/v1/analyses/<analysis_id>/events
```

## Example SSE events

```text
id: 1
event: queued
data: {"status":"queued"}

id: 2
event: progress
data: {"step":"fetch_cards","percent":20}

id: 5
event: completed
data: {"analysis_id":"...","status":"completed"}
```

## Screenshots

Open [http://localhost:55700](http://localhost:55700) after `docker compose up` to use the UI.

### Analyze a deck

![Analyze a deck form](docs/screenshots/analyze-deck.png)

### Analysis progress

![Live analysis progress over SSE](docs/screenshots/analysis-progress.png)

### Results

![Deck stats, mana curve, strengths, and weaknesses](docs/screenshots/results.png)

### Recommendations

![Grounded card recommendations and warnings](docs/screenshots/recommendations.png)

## Reliability decisions

- Durable RabbitMQ queue with dead-letter queue `mtg.analysis.dlq`
- Manual acknowledgements; permanent failures reject without requeue
- Idempotent worker: terminal jobs are skipped on redelivery
- Progress percentages are monotonic and capped at 100
- Secrets and connection strings are never returned in API/SSE payloads
- Missing `LLM_API_KEY` fails the job clearly (no silent fake LLM in production paths)

### Stuck `running` jobs (MVP limitation)

If a worker dies mid-job, an analysis may remain `running`. Safe recovery (SQL):

```sql
UPDATE analyses
SET status = 'failed',
    error_message = 'Worker interrupted; please retry',
    completed_at = NOW()
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '15 minutes';
```

Then retry from the UI or `POST .../analyses`.

## Limitations

- Format legality is not checked
- Prices come from Scryfall and may be missing/stale
- Candidate cards for recommendations are a bounded Scryfall search, not a full metagame model
- Single LLM provider path (`openai`) in the MVP
- No authentication or multi-user accounts

## Future improvements

- Stuck-job reclaim worker / lease timeouts
- Additional LLM providers
- Deck import from Moxfield / Archidekt
- Format legality via Scryfall / MTGJSON
- Richer candidate selection (archetype-aware)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
