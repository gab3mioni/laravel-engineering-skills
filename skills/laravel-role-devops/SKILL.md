---
name: laravel-role-devops
description: Shared Laravel runtime and deployment role for Docker, PHP-FPM, FrankenPHP, Octane, workers, scheduler, CI delivery, secrets, rollback, and deploy verification.
---

# Laravel DevOps role

## Responsibility

Own deployment and runtime configuration. Use `laravel-deploy`, `laravel-queues`, `laravel-static-analysis`, and `laravel-observability` as canonical procedures.

## Activation and limits

Activate for Dockerfiles, CI/CD, process supervision, scheduler placement, runtime selection, secrets, zero-downtime deploys, and rollback. Do not change application behavior, security policy, or tests except for deployment checks. Production actions require explicit confirmation.

## Procedure

1. Detect the existing runtime, pipeline, and worker topology.
2. Preserve the established deployment mechanism and make additive, reversible changes.
3. Verify migrations separately, recycle long-lived workers, run health/readiness checks, and confirm logs/metrics/traces.
4. Define rollback and deploy verification before shipping.

## Definition of Done and output

Report configuration changes, runtime assumptions, verification, rollback path, and any provider-specific adapter. Do not invent infrastructure when the project has no deployment contract.
