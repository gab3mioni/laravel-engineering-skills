---
name: laravel-integrations
description: Laravel 12 patterns for reliable external HTTP APIs and webhooks, including timeouts, retries, authentication, HMAC signatures, replay protection, idempotency, contracts, queues, and Http::fake tests.
---

# Laravel Integrations

Use for boundaries between a Laravel application and another system. Keep contracts explicit, failures bounded, and side effects safe to repeat.

## When to use

- Laravel HTTP Client calls, authentication, timeouts, retries, and circuit breaking.
- Incoming or outgoing webhooks, HMAC verification, replay protection, and delivery state.
- Idempotency keys between systems, versioned contracts, and vendor error handling.
- Tests with `Http::fake` and queued delivery after database commits.

## When NOT to use

| Topic | Use instead |
|---|---|
| Queue connections, worker retry mechanics, Horizon | `laravel-queues` |
| Internal API Resources, pagination, and traditional API shape | `laravel-backend` |
| Threat model, secret handling, and dependency risk | `laravel-security` |
| Logs, metrics, tracing, and incident response | `laravel-observability` |

## Workflow

1. Write down the external contract: endpoint/version, auth, request/response schema, timeout, retryable status codes, rate limits, and ownership.
2. Build a small client around Laravel's HTTP Client. Set connect and total timeouts, bounded retries with jitter where appropriate, and safe error classification.
3. Never retry non-idempotent side effects without a provider-supported idempotency key or a durable local idempotency record.
4. For incoming webhooks, verify the raw body with `hash_equals`, validate timestamp/nonce/event ID, persist a deduplication record, and enqueue processing after commit.
5. For outgoing webhooks, persist delivery attempts and response metadata, sign the exact transmitted body, and use a queued job with an explicit retry policy.
6. Test success, timeout, 429, 5xx, malformed response, invalid signature, replay, duplicate event, and exhausted delivery. Use `Http::fake`, never real HTTP.
7. Instrument attempts and outcomes through `laravel-observability` without logging secrets or raw payloads.

## Decision rules

| Failure | Default |
|---|---|
| Connect/read timeout | bounded retry only when operation is safe to repeat |
| 429 | respect `Retry-After`, rate-limit locally, retry within a deadline |
| 5xx | exponential backoff with jitter and bounded attempts |
| 4xx contract/auth error | fail fast, alert or dead-letter; retry only if documented transient |
| Circuit open | fail fast with a typed operational error and observable metric |
| Duplicate request/event | return the prior result or no-op after durable deduplication |

## Rules and anti-patterns

| Smell | Detection |
|---|---|
| Unbounded external request | `rg -n "Http::|->timeout\(|->connectTimeout\(" app` |
| Raw user URL causing SSRF | `rg -n "Http::(get|post|send)\(.*request|input|query" app` |
| Signature over parsed JSON | inspect webhook code; sign and verify the raw body |
| `===` for HMAC | `rg -n "signature|hash_hmac|hash_equals" app routes` |
| Real HTTP in tests | `rg -n "Http::fake|Http::get|Http::post" tests` |
| Queue dispatch before commit | `rg -n "DB::transaction|dispatch\(" app` |

## Reference routing

| Trigger | Reference |
|---|---|
| HTTP client construction and failure policy | `references/http_clients.md` |
| Incoming/outgoing webhook verification and delivery | `references/webhooks.md` |
| Cross-system idempotency and retry interaction | `references/idempotency_and_retries.md` |
| `Http::fake` and contract tests | `references/external_service_testing.md` |

## Cross-references

Job mechanics and job-specific idempotency remain in `laravel-queues`. Internal API design remains in `laravel-backend`. Operational signals belong to `laravel-observability`.
