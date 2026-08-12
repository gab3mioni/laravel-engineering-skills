---
name: laravel-observability
description: Provider-neutral observability for Laravel 12 applications, covering structured logs, correlation, metrics, tracing, health checks, SLOs, alerts, incidents, deploy verification, jobs, and integrations.
---

# Laravel Observability

Use this skill when a change must be measurable in production or when diagnosing an incident. It is provider-neutral. Detect installed adapters before using Pulse, Telescope, OpenTelemetry, Sentry, or a hosted backend.

## When to use

- Designing structured request, job, database, or integration telemetry.
- Adding health/readiness checks, SLIs, SLOs, alerts, or deploy verification.
- Investigating latency, errors, queue backlogs, failed jobs, or external-service outages.
- Planning incident response and post-incident evidence.

## When NOT to use

| Topic | Use instead |
|---|---|
| OWASP logging threats, secrets, compliance | `laravel-security` |
| Queue mechanics, retries, Horizon configuration | `laravel-queues` |
| Docker, CI, runtime, and rollout mechanics | `laravel-deploy` |
| External HTTP, webhooks, and idempotency contracts | `laravel-integrations` |

## Detection

Run the repository stack detector, then detect optional packages. Native Laravel logging and `/up` remain valid without any provider. An adapter is an implementation detail, not a prerequisite for instrumentation design.

## Workflow

1. Define the user-visible failure and its SLI before adding telemetry.
2. Establish a correlation contract: request ID, trace ID, job ID, tenant-safe dimensions, and external attempt ID. Never use secrets or raw payloads as dimensions.
3. Emit structured events at request start/end, queue dispatch/finish/failure, database slow-query boundaries, and integration attempt/result boundaries.
4. Add health, readiness, and liveness checks that test dependencies appropriate to the process. Keep liveness cheap and readiness honest.
5. Define an SLO, alert threshold, owner, runbook link, and deploy verification query or smoke test.
6. Verify locally with logs, metrics stubs, health responses, and the nearest Pest tests. Verify the provider adapter only when detected.

## Decision rules

| Signal | Good default |
|---|---|
| Logs | JSON, stable event name, severity, correlation IDs, bounded fields |
| Metrics | Counters for outcomes, histograms for latency, low-cardinality labels |
| Traces | Propagate context across HTTP and jobs; sample deliberately |
| Health | Liveness checks process; readiness checks required dependencies |
| Alerts | Page on customer impact or error-budget burn, not every exception |
| Incident | Stabilize, communicate, preserve evidence, recover, then learn |

## Rules and anti-patterns

| Smell | Detection |
|---|---|
| Logging request payloads or secrets | `rg -n "request->all\(\)|password|token|secret|authorization" app config` |
| High-cardinality metric labels | `rg -n "label|tag|dimension" app config` and inspect user IDs, URLs, or exception text |
| Health endpoint exposing dependency details | `rg -n "health|readiness|liveness|/up" routes app` |
| Job/integration without correlation | `rg -n "ShouldQueue|Http::|withHeaders" app` |
| Alert without owner or runbook | inspect alert definitions and operational docs |

## Reference routing

| Trigger | Reference |
|---|---|
| Correlation, logs, metrics, tracing, provider adapters | `references/telemetry.md` |
| Health endpoints, SLIs, SLOs, alerts | `references/health_checks_and_slos.md` |
| Incident handling and deploy verification | `references/incident_response.md` |
| Queues, jobs, failed jobs, and worker telemetry | `references/queue_and_job_observability.md` |

## Cross-references

`laravel-role-devops` owns rollout mechanics. `laravel-role-security` owns threat modeling and sensitive-data policy. `laravel-integrations` owns external contract semantics. `laravel-queues` owns retry and worker mechanics.
