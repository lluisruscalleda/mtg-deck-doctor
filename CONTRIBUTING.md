# Contributing

Thanks for helping improve MTG Deck Doctor. This project analyzes Magic: The Gathering decks with deterministic metrics and recommendations grounded in real Scryfall cards.

## Before you start

- Python 3.12+
- Docker and Docker Compose, or local PostgreSQL 16 and RabbitMQ 3.13
- An OpenAI-compatible API key only if you want live LLM recommendations. The default test suite does not need one.

Setup, environment variables, and how to run the stack are in the [README](README.md).

Do not commit `.env`, API keys, or connection strings. Copy `.env.example` and keep secrets local.

## What to keep true

- Card names in recommendations must come from Scryfall (or the test fakes). Do not invent cards.
- Analysis progress is persisted and replayed over SSE. Do not switch that path to polling or an ad-hoc websocket.
- Jobs are published through the transactional outbox. Do not publish to RabbitMQ from the request that creates an analysis.
- The default test suite mocks Scryfall and uses a deterministic fake LLM. Production paths must not silently fall back to that fake model when `LLM_API_KEY` is missing.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

With Postgres and RabbitMQ running:

```bash
export DATABASE_URL=postgresql+asyncpg://mtg:mtg@localhost:5432/mtg_deck_doctor
alembic upgrade head
uvicorn app.main:app --reload --port 55700
```

The analysis worker and the outbox publisher are separate processes. See the README for `python -m app.workers.analysis_worker` and `python -m app.workers.outbox_publisher`, or use `docker compose up --build`.

Schema changes belong in a new Alembic revision under `migrations/versions/`.

## Tests and lint

```bash
pytest
ruff check app tests
```

Ruff is configured in `pyproject.toml` (line length 100, target Python 3.12). Match the surrounding module: API routes, repositories, services, workers, and the LangGraph agent stay in their existing packages.

## Pull requests

- Describe the behavior you changed and how you checked it.
- Keep the change focused. A metrics fix and a UI redesign should be separate requests.
- Update the README when setup, endpoints, or user-facing limitations change.

By contributing, you agree that your work is licensed under the [MIT License](LICENSE).
