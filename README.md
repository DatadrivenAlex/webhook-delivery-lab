# Webhook Delivery Lab

A newly created portfolio demonstration of Python backend design: a FastAPI service with a SQLite outbox, idempotency keys, retry/backoff and HMAC signature helpers. Delivery is simulated locally; this is not a past client project or a production delivery system.

## Run locally

Requires Python 3.10 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[dev]'
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API. In another terminal:

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: order-123' \
  -d '{"payload":{"order_id":"demo-123","status":"paid"}}'
curl -X POST http://127.0.0.1:8000/events/1/simulate \
  -H 'Content-Type: application/json' -d '{"succeeds":true}'
curl http://127.0.0.1:8000/events/1
```

Reusing a key with an equivalent JSON payload returns the existing event; changing its payload returns 409. A simulated failure schedules an exponential retry after 20, 40, then 80 seconds; the fourth failed attempt is terminal. Retry is triggered manually through the simulation endpoint, not by a background worker. `WEBHOOK_DB` sets the SQLite file path; default is `webhooks.sqlite3`.

## Tests

```bash
pytest -q
```

The tests exercise idempotency, concurrent writes, retry timing, terminal states, signature tampering and API behavior. GitHub Actions runs them for Python 3.10 and 3.12.

## Scope and safety

This is an educational demo prepared for this portfolio in 2026. No outbound HTTP is performed and no external service or real customer data is required. Signature functions are examples and are not wired into the API. The API has no authentication or rate limiting, so run it locally only. Production use would need authenticated endpoints, encrypted secret storage, real delivery with SSRF protection, durable scheduling/workers, signature timestamps and replay protection, observability, and deployment review.
