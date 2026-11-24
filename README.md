# webhook-relay

I made this to have a backend project I can show. It takes webhooks from other services, checks their signature, saves them in PostgreSQL and passes them on to another URL if you ask it to. I picked webhooks because signature checks and replay protection fit the security work I already do.

Stack is FastAPI, SQLAlchemy 2, Alembic and uv.

## How it works

You create a source with `POST /sources` and get a secret back, once. The sender signs `<timestamp>.<body>` with HMAC-SHA256 using that secret and sends the result in `X-Relay-Signature`, with the timestamp in `X-Relay-Timestamp`. If the signature is wrong, or the timestamp is more than 5 minutes off, the request gets a 401 and nothing is saved.

Valid events are stored. If the same `X-Event-Id` arrives twice, it is stored once. If the source has a `target_url`, the event is sent there with the same kind of signature. Network errors, 5xx, 408, 425 and 429 are retried, up to 3 attempts in total, waiting twice as long each time. Other 4xx are not retried. Every attempt is saved, and `POST /events/{id}/redeliver` sends an event again.

You can list a source's events with `GET /sources/{id}/events` and open one with `GET /events/{id}`. Those routes and source creation need an `X-API-Key` header. Swagger is at `/docs`.

## Run it

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Change both values in `.env` first. Then create a source and send a signed event.

```bash
KEY=<your ADMIN_API_KEY>
curl -s -X POST localhost:8000/sources -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"name": "demo"}'
# take the id and secret from the response
BODY='{"hello":"world"}'
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -s -X POST localhost:8000/hooks/$ID -H "Content-Type: application/json" \
  -H "X-Relay-Timestamp: $TS" -H "X-Relay-Signature: sha256=$SIG" -d "$BODY"
```

## Tests

```bash
docker compose run --rm tests
```

Without Docker you need a PostgreSQL to point at. The database name has to end in `_test`, because the suite creates it if it is missing and wipes it on every run.

```bash
uv sync
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/relay_test uv run pytest
```

## What I tested and what I didn't

The 44 tests pass on my machine against a real PostgreSQL. They apply the Alembic migration first and check it matches the models. To see that the signature tests mean something, I broke the check on purpose and 5 of them failed.

There is no Docker on my machine, so the Dockerfile and `docker compose` only ran in CI. The `compose` job there runs the tests inside Compose, starts the stack and calls `/health` and `POST /sources`. It passed on the first run, along with lint, the tests, gitleaks and CodeQL. I have not tried `docker compose up` by hand.

## Limits

- Retries happen inside the web process, with no queue. If it restarts, the waiting retries are lost. Those events stay `pending` and can be sent again by hand.
- Targets that resolve to private or loopback addresses are refused, and redirects are not followed. The check resolves DNS before sending, so DNS rebinding could still get around it.
- Source secrets are saved as plain text, because the HMAC needs them.
- One shared admin key, no users, no rate limiting.
