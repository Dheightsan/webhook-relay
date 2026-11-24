# webhook-relay

Receives signed webhooks, stores them in PostgreSQL and forwards them to another URL with retries. FastAPI, SQLAlchemy 2, Alembic, uv and pytest.

## How it works

1. You create a source with `POST /sources`. The response has a secret, shown only once.
2. The sender signs each request with HMAC-SHA256 over `<timestamp>.<body>` and sends it in the `X-Relay-Timestamp` and `X-Relay-Signature` headers. A wrong signature, or a timestamp more than 5 minutes off, gets a 401 and nothing is stored.
3. Valid events are saved. Sending the same `X-Event-Id` twice stores it once.
4. If the source has a `target_url`, the event is forwarded with the same kind of signature. Network errors, 5xx, 408, 425 and 429 are retried up to 3 times with a doubling wait. Other 4xx are not. Every attempt is saved.
5. `GET /sources/{id}/events` lists events, with a `delivery_status` filter and pagination. `GET /events/{id}` shows one with its attempts. `POST /events/{id}/redeliver` sends it again.

The admin routes need an `X-API-Key` header. Docs are at `/docs` once it is running.

## Run it

```bash
cp .env.example .env     # change both values
docker compose up -d --build --wait
```

Create a source and send a signed event:

```bash
KEY=<your ADMIN_API_KEY>
curl -s -X POST localhost:8000/sources -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"name": "demo"}'
# use the id and secret from the response
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

You can also run them without Docker, against any PostgreSQL you can reach. The database name must end in `_test`. It is created if missing and wiped on every run.

```bash
uv sync
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/relay_test uv run pytest
```

The suite runs the Alembic migration first and checks it matches the models. CI runs lint, the tests, a Compose job, gitleaks and CodeQL.

## Limits

- Retries run inside the web process, with no queue. A restart loses the ones waiting. Those events stay `pending` and can be sent again with `redeliver`.
- Targets that resolve to private or loopback addresses are refused, and redirects are not followed. The check resolves DNS before sending, so a DNS rebinding trick could still get past it.
- Source secrets are stored in plain text because the HMAC needs them.
- One shared admin key, no users, no rate limiting.
