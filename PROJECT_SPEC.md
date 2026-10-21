# PROJECT SPECIFICATION — MTG Deck Doctor

## 1. Role and mission

Act as a senior Python backend engineer and AI engineer.

Build a complete, runnable, portfolio-quality project called **MTG Deck Doctor**.

The application analyzes Magic: The Gathering decks, calculates objective deck statistics, and uses an LLM-powered workflow to produce grounded recommendations.

The application must demonstrate:

- Python and FastAPI
- PostgreSQL and SQLAlchemy 2
- RabbitMQ and asynchronous background processing
- LangChain and LangGraph
- Server-Sent Events (SSE)
- Docker Compose
- Automated tests
- Clean architecture, type safety, error handling, and documentation

Do not build a large production platform. Build a small but complete MVP suitable for a weekend project and a public GitHub portfolio.

**The most important requirement is that the entire application works end to end.**

Do not leave TODOs, fake implementations, placeholder API responses, or non-functional buttons in the final implementation.

When a feature cannot be implemented within scope, document the limitation explicitly rather than pretending it works.

---

## 2. Product definition

### User story

As a Magic: The Gathering player, I want to submit a deck and receive an AI-powered analysis containing:

- Total card count
- Average mana value
- Mana curve
- Land count
- Color distribution
- Potential deck weaknesses
- Three grounded card recommendations
- Explanations for each recommendation
- Progress updates while the analysis runs

The user must be able to interact with the application through a simple web interface.

### MVP scope

Implement:

1. Create a deck.
2. Validate and resolve card names.
3. Calculate deterministic deck statistics.
4. Create an asynchronous analysis job.
5. Process the job using RabbitMQ.
6. Run an analysis workflow using LangGraph and LangChain.
7. Persist the analysis and its events.
8. Stream progress to the browser using SSE.
9. Display the completed result in the frontend.
10. Run the application using Docker Compose.

Do not implement authentication, payments, user accounts, tournament management, deck importing from external platforms, or a vector database.

### Supported formats

Initially support:

- Old School Swedish (`old_school_swedish`) — primary format; Swedish OS legal sets and B&R from [Swedish OS Rules](https://ragingbullseries.com/index.php/swedish-os-rules/)
- Modern
- Commander
- Standard
- Pioneer
- Legacy
- Vintage
- Pauper
- Custom

Use normalized format identifiers internally.

Candidate card search should use a format-appropriate Scryfall filter (Swedish OS set pool for Old School Swedish). Full tournament legality verification remains out of scope for the first version. Never claim that a deck is legal in a format unless legality has actually been checked against a reliable data source.

---

## 3. Technology stack

Use the following stack:

- Python 3.12+
- FastAPI
- Uvicorn
- Pydantic v2
- SQLAlchemy 2.x
- PostgreSQL
- Alembic
- RabbitMQ
- aio-pika
- LangChain
- LangGraph
- A configurable chat model supported by LangChain
- httpx for asynchronous HTTP requests
- pytest
- pytest-asyncio
- Ruff
- HTML5
- CSS
- Vanilla JavaScript
- Docker
- Docker Compose

Use compatible stable dependency versions and pin or constrain them in `pyproject.toml`.

Do not introduce Celery, Redis, Kafka, Kubernetes, a vector database, or a large frontend framework.

Use a lockfile if the selected dependency manager supports it cleanly.

---

## 4. Architecture

Implement the following logical components.

### 4.1 Frontend

A small, responsive single-page interface served by FastAPI.

Responsibilities:

- Enter a deck name.
- Select a format.
- Enter card names and quantities.
- Submit the deck.
- Start an analysis.
- Display the analysis status.
- Subscribe to SSE progress events.
- Display statistics, recommendations, warnings, and errors.
- Allow the user to retry a failed analysis.

Use plain HTML, CSS, and JavaScript.

No frontend build system should be necessary.

### 4.2 FastAPI application

Responsibilities:

- Validate HTTP requests.
- Expose the REST API.
- Persist decks and analysis jobs.
- Publish jobs through a reliable messaging mechanism.
- Expose SSE streams.
- Return consistent HTTP errors.
- Expose health endpoints.

The API must never wait for the complete LLM analysis before returning the job identifier.

### 4.3 PostgreSQL

Store:

- Decks
- Analysis jobs
- Analysis events
- Outbox messages

Use SQLAlchemy 2.x with explicit models and Alembic migrations.

Do not create database tables automatically at application startup in production mode. Use migrations.

### 4.4 RabbitMQ

Use RabbitMQ to distribute analysis jobs to background workers.

Use durable queues, persistent messages, publisher confirms where supported, manual acknowledgements, and appropriate failure handling.

The worker must be able to recover from transient errors.

Design message processing to be idempotent.

A duplicate message must not generate duplicate completed analyses or corrupt the analysis status.

### 4.5 Background worker

Implement a separate worker process.

The worker must:

1. Consume an analysis job.
2. Validate the job identifier.
3. Load the analysis and associated deck.
4. Transition the job to `running`.
5. Persist progress events.
6. Retrieve card information from Scryfall.
7. Calculate deck metrics.
8. Run the LangGraph workflow.
9. Validate the LLM output.
10. Persist the final result.
11. Set the job status to `completed`.
12. Persist a terminal event.

On failure, persist a safe error message, set the status to `failed`, emit a terminal error event, and acknowledge or reject the RabbitMQ message according to the retry policy.

Do not expose API keys, database credentials, stack traces, or other secrets to the frontend.

---

## 5. Repository structure

Use this structure as the starting point:

```text
mtg-deck-doctor/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── health.py
│   │   ├── decks.py
│   │   └── analyses.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── exceptions.py
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models.py
│   ├── schemas/
│   │   ├── deck.py
│   │   └── analysis.py
│   ├── repositories/
│   │   ├── decks.py
│   │   ├── analyses.py
│   │   └── events.py
│   ├── services/
│   │   ├── scryfall.py
│   │   ├── deck_metrics.py
│   │   └── analysis_service.py
│   ├── messaging/
│   │   ├── rabbitmq.py
│   │   └── outbox.py
│   ├── agents/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   ├── workers/
│   │   ├── analysis_worker.py
│   │   └── outbox_publisher.py
│   └── frontend/
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── migrations/
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_decks.py
│   ├── test_deck_metrics.py
│   ├── test_analyses.py
│   ├── test_sse.py
│   ├── test_agent.py
│   └── test_worker.py
├── .env.example
├── .gitignore
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── PROJECT_SPEC.md
└── README.md
```

You may adjust this structure if a clear technical reason exists. Keep the code modular, but avoid unnecessary abstractions.

---

## 6. Environment configuration

Implement configuration with Pydantic Settings.

Provide `.env.example` containing all required variables:

```dotenv
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=55700
LOG_LEVEL=INFO

DATABASE_URL=postgresql+asyncpg://mtg:mtg@postgres:5432/mtg_deck_doctor

RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
RABBITMQ_QUEUE=mtg.analysis

LLM_PROVIDER=openai
LLM_MODEL=
LLM_API_KEY=
LLM_BASE_URL=

SCRYFALL_BASE_URL=https://api.scryfall.com
SCRYFALL_USER_AGENT=MTGDeckDoctor/1.0

MAX_CARDS_PER_DECK=100
MAX_CARD_NAME_LENGTH=120
MAX_RECOMMENDATIONS=3

SSE_HEARTBEAT_SECONDS=15
SSE_POLL_INTERVAL_SECONDS=1

OUTBOX_POLL_INTERVAL_SECONDS=1
OUTBOX_BATCH_SIZE=20

LLM_TIMEOUT_SECONDS=45
LLM_MAX_RETRIES=1
```

Use safe defaults where possible.

Never commit real API keys.

Do not silently fall back to a fake LLM response if credentials are missing.

Implement a clear startup or job-level error when the requested provider is not configured.

The application should still support local development and automated tests without a real LLM API key through dependency injection and a deterministic fake chat model in tests.

---

## 7. Database schema

Implement the following tables.

### 7.1 `decks`

Fields:

- `id`: UUID primary key
- `name`: VARCHAR(120), required
- `format`: VARCHAR(30), required
- `cards`: JSONB, required
- `created_at`: timezone-aware timestamp

Each card entry should contain:

```json
{
  "name": "Lightning Bolt",
  "quantity": 4
}
```

Preserve the original card name and quantity.

### 7.2 `analyses`

Fields:

- `id`: UUID primary key
- `deck_id`: foreign key to `decks.id`
- `status`: constrained to `queued`, `running`, `completed`, `failed`
- `options`: JSONB, required
- `metrics`: JSONB, nullable
- `result`: JSONB, nullable
- `error_message`: nullable text
- `created_at`: timezone-aware timestamp
- `started_at`: nullable timezone-aware timestamp
- `completed_at`: nullable timezone-aware timestamp

Store the analysis options, including budget and requested recommendation count.

### 7.3 `analysis_events`

Fields:

- `id`: incrementing BIGINT primary key
- `analysis_id`: foreign key to `analyses.id`
- `event_type`: VARCHAR(30)
- `payload`: JSONB
- `created_at`: timezone-aware timestamp

Add an index on `(analysis_id, id)`.

Event identifiers must be monotonically increasing within the event stream because they are used by SSE.

### 7.4 `outbox_messages`

Fields:

- `id`: UUID primary key
- `analysis_id`: foreign key to `analyses.id`
- `payload`: JSONB
- `created_at`: timezone-aware timestamp
- `published_at`: nullable timezone-aware timestamp
- `attempts`: integer, default 0

Use an index to efficiently retrieve unpublished messages.

### Transactional outbox

When creating an analysis:

1. Begin a database transaction.
2. Insert the analysis with status `queued`.
3. Insert the corresponding outbox message.
4. Commit the transaction.
5. Return the analysis identifier.

Implement an outbox publisher process that publishes pending messages to RabbitMQ.

Mark a message as published only after RabbitMQ confirms publication.

Handle concurrent publisher execution safely.

A crash after publication but before updating `published_at` may cause redelivery. Therefore, the consumer must be idempotent.

Keep the outbox implementation as small as possible while preserving these guarantees.

---

## 8. REST API contract

All API endpoints except health checks must use the `/api/v1` prefix.

### Health

`GET /health`

Return basic application health.

`GET /health/ready`

Check database and RabbitMQ connectivity.

Do not expose connection strings or credentials in health responses.

### Create deck

`POST /api/v1/decks`

Example request:

```json
{
  "name": "Burn test",
  "format": "modern",
  "cards": [
    {"name": "Lightning Bolt", "quantity": 4},
    {"name": "Monastery Swiftspear", "quantity": 4},
    {"name": "Mountain", "quantity": 20}
  ]
}
```

Requirements:

- Validate the name and format.
- Require at least one card.
- Require positive quantities.
- Reject duplicate card entries or normalize them consistently.
- Enforce a configurable maximum card count.
- Resolve card names against Scryfall.
- Return a `201 Created` response.
- Return clear validation errors.

Do not require a complete deck to be tournament legal.

### Retrieve deck

`GET /api/v1/decks/{deck_id}`

Return the deck and its card list.

Return `404` for unknown identifiers.

### Create analysis

`POST /api/v1/decks/{deck_id}/analyses`

Example request:

```json
{
  "budget_usd": 30,
  "recommendation_count": 3
}
```

Requirements:

- Validate the deck identifier.
- Validate the budget and recommendation count.
- Create the analysis and outbox message in one transaction.
- Return `202 Accepted`.
- Include the analysis ID, initial status, and event URL.
- Do not wait for the LLM.

### Retrieve analysis

`GET /api/v1/analyses/{analysis_id}`

Return:

- ID
- Status
- Deck ID
- Creation and completion timestamps
- Metrics, when available
- Final result, when available
- Safe error information, when failed

### Analysis events

`GET /api/v1/analyses/{analysis_id}/events`

Return an SSE stream.

Requirements:

- Set `Content-Type: text/event-stream`.
- Disable caching.
- Send event IDs.
- Support `Last-Event-ID`.
- Replay persisted events after reconnecting.
- Send periodic heartbeat comments.
- Stop after the terminal event has been delivered.
- Cleanly handle client disconnects.
- Return `404` for unknown analysis IDs.

Use FastAPI's `StreamingResponse`.

Do not implement SSE by storing all events in memory.

---

## 9. Scryfall integration

Implement an asynchronous Scryfall client using `httpx.AsyncClient`.

Responsibilities:

- Resolve card names.
- Retrieve card metadata.
- Retrieve mana costs and mana values.
- Retrieve colors and color identity.
- Retrieve card types and oracle text.
- Retrieve price data when available.
- Support cards with multiple faces.
- Handle missing prices.
- Handle unknown card names.
- Handle timeouts, rate limits, and transient HTTP errors.
- Reuse the HTTP client appropriately.
- Respect Scryfall API usage guidelines and rate limits.

Use exact-name lookup first where appropriate.

Use a reliable card identifier or normalized card name internally to deduplicate resolved cards.

Never fabricate missing card information.

If a card cannot be resolved, record a warning and handle the failure explicitly.

A deck with unresolved cards must not be presented as if all cards were verified.

Do not make excessive API requests. Cache resolved card data within the lifetime of a job, and consider a small in-process cache if it is straightforward.

Keep the integration isolated so tests can mock it.

---

## 10. Deck metrics

Implement deterministic metric calculations in `services/deck_metrics.py`.

Calculate:

- Total number of cards, counting quantities.
- Number of lands.
- Number of nonlands.
- Average mana value of nonland cards when meaningful.
- Mana curve grouped into mana-value buckets, including a bucket for 6+.
- Distribution by color.
- Counts by broad card type where reliable.

Do not assume every card has a numeric mana cost.

Lands and cards with unusual mana costs must be handled correctly.

Cards with multiple faces require a documented policy for mana-value calculations.

Do not count unknown cards as zero-cost cards.

Return both metrics and warnings when incomplete information affects the calculation.

Use pure functions where possible so the metric calculation can be tested without a database, RabbitMQ, or an LLM.

---

## 11. LangChain and LangGraph

Build a typed LangGraph workflow.

### Graph state

Define a typed state containing:

- `analysis_id`
- `deck_id`
- `format`
- `budget_usd`
- `recommendation_count`
- `card_data`
- `warnings`
- `metrics`
- `recommendations`
- `summary`
- `error`

Avoid passing database sessions or non-serializable runtime objects through the graph state.

### Nodes

Implement the following nodes:

1. `fetch_cards`
2. `calculate_metrics`
3. `generate_recommendations`
4. `validate_output`
5. `persist_result`

Use conditional edges for recoverable validation failures.

Limit LLM output retries to a configurable, small number.

### Grounded recommendations

The LLM must receive:

- Deck format
- Verified cards in the deck
- Calculated metrics
- Budget constraints
- A bounded set of verified candidate cards
- Relevant card text and metadata

Recommendations must reference actual candidates obtained from Scryfall.

Do not allow the model to invent card names, prices, mana values, or oracle text.

Validate each recommendation against the supplied candidate set.

If there are not enough valid candidates, return fewer recommendations and an explanatory warning rather than inventing cards.

Budget comparisons must use available, sufficiently current price data. If prices are missing or stale, disclose the limitation and do not claim that the recommendation fits the budget.

### Structured output

Define a Pydantic response model with fields similar to:

```json
{
  "summary": "A concise deck assessment.",
  "strengths": [
    "A verified observation about the deck."
  ],
  "weaknesses": [
    "A limitation supported by the deck data."
  ],
  "recommendations": [
    {
      "card_name": "A verified candidate",
      "reason": "Why this card may improve the deck.",
      "category": "consistency",
      "estimated_price_usd": null
    }
  ],
  "warnings": []
}
```

Use suitable enums or constrained fields where appropriate.

Validate the structured output before persistence.

The model must not claim format legality unless the application actually verifies it.

Do not use a vector database or RAG in the MVP.

### Model configuration

Create a provider abstraction so the LLM can be configured through environment variables.

Use the selected provider's supported LangChain integration.

Do not hardcode model names or API keys in source files.

Do not expose chain-of-thought. Return concise, user-facing justifications grounded in supplied facts.

### Testing

Use a deterministic fake chat model for automated tests.

The fake model must return schema-valid output referencing the supplied candidate set.

Do not require external LLM calls in the default test suite.

---

## 12. RabbitMQ worker reliability

Implement a separate worker entry point.

The worker must:

- Declare or verify a durable queue.
- Consume persistent messages.
- Validate incoming payloads.
- Use manual acknowledgements.
- Ignore or safely acknowledge already completed jobs.
- Handle duplicate deliveries.
- Record job status transitions.
- Apply bounded retry behavior.
- Distinguish transient infrastructure errors from permanent input errors.
- Avoid infinite retry loops.
- Ensure that failed jobs produce a terminal persisted event.
- Log useful contextual information without exposing secrets.

Use a dead-letter queue if practical and document how it works.

Ensure an exception cannot silently leave an analysis in `running` forever under normal failure conditions.

Implement a simple recovery strategy for jobs left in `running` after an unexpected worker termination, or explicitly document the MVP limitation and provide a safe recovery command or process.

---

## 13. SSE event protocol

Use the following event types:

- `queued`
- `progress`
- `completed`
- `failed`

Example:

```text
id: 1
event: queued
data: {"status":"queued"}

id: 2
event: progress
data: {"step":"fetch_cards","percent":20}

id: 3
event: progress
data: {"step":"calculate_metrics","percent":45}

id: 4
event: progress
data: {"step":"generate_recommendations","percent":75}

id: 5
event: completed
data: {"analysis_id":"...","status":"completed"}
```

Use JSON serialization for event payloads.

Do not concatenate arbitrary unescaped user input into SSE frames.

Progress percentages must be monotonic and must not exceed 100.

Persist the event and associated state transition transactionally when appropriate.

If a job is already terminal when a client connects, replay the existing events and close the stream after the terminal event.

---

## 14. Frontend requirements

Implement a simple, responsive interface with no frontend framework.

The page should contain:

### Header

- Product name: MTG Deck Doctor
- Short description
- A link to the API documentation

### Deck form

- Deck name
- Format selector
- Multiline card list
- Budget in USD
- Recommendation count

Accept card-list lines such as:

```text
4 Lightning Bolt
4 Monastery Swiftspear
20 Mountain
```

Parse the format on the frontend and validate it on the backend as well.

Show helpful validation errors.

### Analysis progress

When the user starts an analysis:

1. Create the deck if necessary.
2. Start the analysis.
3. Open the SSE connection.
4. Display progress updates.
5. Handle successful completion.
6. Handle failure.
7. Close the SSE connection appropriately.

Do not simulate progress using arbitrary JavaScript timers.

Progress must come from actual backend events.

### Result view

Display:

- Summary
- Metrics
- Mana curve
- Strengths
- Weaknesses
- Recommendations
- Available price estimates
- Warnings about incomplete or stale data

Render user-provided and model-generated content safely. Do not inject untrusted strings through `innerHTML` without appropriate escaping.

Provide loading, empty, error, and completed states.

The interface must remain usable on mobile and desktop.

---

## 15. Docker Compose

Provide a working `docker-compose.yml` with:

- `api`
- `worker`
- `outbox-publisher`
- `postgres`
- `rabbitmq`

The API, worker, and outbox publisher should use the same application image but different commands where appropriate.

Use health checks and sensible startup dependencies.

Persist PostgreSQL data using a named volume.

Persist RabbitMQ data if appropriate.

Expose:

- API on port 55700
- RabbitMQ management UI on port 15672 for local development

Do not expose PostgreSQL publicly unless necessary for local development.

Use a non-root user in the application image where practical.

Run database migrations as an explicit documented step or a controlled one-off service.

Do not rely solely on `depends_on` for service readiness.

Document the local RabbitMQ development credentials and make it clear that they are not suitable for production.

The project should start using a small number of documented commands.

---

## 16. Testing strategy

Implement meaningful tests for:

### Unit tests

- Deck input parsing.
- Quantity validation.
- Metric calculation.
- Missing mana values.
- Unknown cards.
- Structured recommendation validation.
- Candidate-card grounding.
- Budget handling when prices are missing.

### API tests

- Health endpoints.
- Create deck.
- Retrieve deck.
- Invalid request payload.
- Unknown deck identifier.
- Create analysis.
- Retrieve analysis.
- Unknown analysis identifier.

### Messaging and worker tests

- Publish an analysis job.
- Consume a job.
- Handle duplicate delivery.
- Handle a transient failure.
- Handle a permanent failure.
- Persist the final result.

### SSE tests

- Correct content type.
- Event identifiers.
- Replay from `Last-Event-ID`.
- Progress events.
- Terminal events.
- Unknown analysis identifier.

### Test infrastructure

- Use dependency injection.
- Mock Scryfall responses.
- Use a fake LLM.
- Avoid real external network requests in unit tests.
- Ensure tests can run with no LLM API key.
- Use an isolated test database or transaction-based test fixtures.
- Mark tests requiring actual Docker services separately if needed.

Provide a documented command to run the default test suite.

Do not claim that an integration test passed unless it was actually executed.

---

## 17. Code quality and engineering conventions

Follow these rules:

- Use type hints throughout.
- Use async database and HTTP operations where appropriate.
- Use Pydantic models at API and external-data boundaries.
- Separate API routes, business logic, persistence, messaging, and AI workflows.
- Use dependency injection for database sessions and external services.
- Use structured logging.
- Avoid global mutable state.
- Avoid broad exception handling that hides failures.
- Never log API keys or full secret-bearing environment configuration.
- Avoid circular imports.
- Avoid unnecessary generic abstractions.
- Keep functions small and focused.
- Add comments only where they clarify non-obvious decisions.
- Use UTC-aware timestamps.
- Use consistent HTTP status codes.
- Use database transactions around related writes.
- Configure Ruff for linting and formatting.
- Use `pytest` for automated tests.
- Use Alembic migrations for schema changes.

Do not create extra layers simply to make the architecture look sophisticated.

---

## 18. README requirements

Write a professional English README suitable for a public GitHub portfolio.

Include:

1. Project overview.
2. Main features.
3. Architecture diagram using Mermaid.
4. Technology stack.
5. Prerequisites.
6. Environment configuration.
7. Startup instructions.
8. Database migration instructions.
9. How to run the tests.
10. Example API requests.
11. Example SSE events.
12. Example screenshots section.
13. Error handling and reliability decisions.
14. Limitations.
15. Future improvements.

Explain why RabbitMQ is used for background processing and why SSE is used for progress updates.

Explain the transactional outbox and idempotent consumer if implemented.

Include a clear disclaimer that card prices may be missing or stale and that the application does not guarantee tournament legality.

Do not claim benchmarks, coverage percentages, or test results that have not been measured.

---

## 19. Implementation workflow for Cursor

Work incrementally.

### Phase 1 — Repository inspection and plan

Inspect the existing repository before changing files.

If the repository is empty, initialize the project structure.

Create a concise implementation checklist and identify any dependency or compatibility issues.

Do not overwrite existing user work without a clear reason.

### Phase 2 — Infrastructure and persistence

Implement:

- Project configuration.
- Docker Compose.
- SQLAlchemy models.
- Alembic migrations.
- Database session management.
- Health endpoints.

Run the relevant checks.

### Phase 3 — Deck management and Scryfall

Implement:

- Deck schemas.
- Deck endpoints.
- Scryfall client.
- Deck persistence.
- Deterministic metric calculations.
- Unit tests.

### Phase 4 — Asynchronous processing

Implement:

- Analysis creation.
- Transactional outbox.
- Outbox publisher.
- RabbitMQ worker.
- Job status transitions.
- Event persistence.
- Failure handling and idempotency.

Test the asynchronous flow.

### Phase 5 — LangGraph and LangChain

Implement:

- Typed graph state.
- Workflow nodes.
- LLM configuration.
- Structured output.
- Candidate grounding.
- Retry logic.
- Fake model tests.

### Phase 6 — SSE

Implement:

- Persisted event stream.
- Replay using `Last-Event-ID`.
- Heartbeats.
- Terminal-event handling.
- Disconnect handling.
- SSE tests.

### Phase 7 — Frontend

Implement the actual HTML/CSS/JavaScript interface.

Connect it to the real endpoints and SSE stream.

Do not create a disconnected mockup.

### Phase 8 — Final verification

Run:

- Ruff checks.
- Automated tests.
- Alembic migration checks.
- Docker Compose configuration validation.
- A real end-to-end local smoke test if Docker and required services are available.

Fix errors rather than merely listing them.

If a check cannot be executed because of missing infrastructure or credentials, state that explicitly.

### Phase 9 — Documentation and delivery

Complete the README and `.env.example`.

Summarize:

- What was implemented.
- Which commands were executed.
- Which tests passed.
- Any checks that could not be executed.
- Any known limitations.
- How to start the project locally.

---

## 20. Definition of Done

The project is complete only when:

- The repository contains all required source files.
- The API starts successfully.
- PostgreSQL migrations work.
- Deck creation and retrieval work.
- Scryfall integration handles real responses and failures.
- Metric calculations are deterministic.
- An analysis is published through the outbox and RabbitMQ.
- The worker processes the job.
- LangGraph generates validated, grounded recommendations when an LLM is configured.
- The result and events persist in PostgreSQL.
- SSE streams real persisted events.
- The frontend displays the actual result.
- Failure states are visible and do not silently disappear.
- Tests run without a real LLM API key.
- Docker Compose and startup instructions are documented.
- The README accurately describes what works.

**Do not declare completion just because the source files have been generated. Verify the implementation as far as the available environment permits.**

---

## 21. Final instruction

Start by inspecting the repository and presenting a concise plan.

Then implement the project phase by phase.

Prioritize a working, tested, end-to-end MVP over unnecessary features or excessive abstraction.

Make reasonable implementation decisions without asking for approval on every file.

Ask a question only if a decision is genuinely blocking.

Do not replace real integrations with mock implementations in the application itself. Mocks are for tests only.

Keep the code readable, maintainable, and suitable for discussion in a backend engineering interview.

The final result must be a real, runnable GitHub project — not merely an architecture proposal.

