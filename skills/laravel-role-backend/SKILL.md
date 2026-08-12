---
name: laravel-role-backend
description: Shared backend role for Laravel 12 server-side implementation, including models, controllers, validation, APIs, migrations, actions, jobs, and policies.
---

# Laravel backend role

## Responsibility

Owns server-side implementation in `app/`, `routes/`, `database/migrations/`, and related production configuration. Use `laravel-backend` as the canonical implementation procedure, plus `laravel-auth`, `laravel-queues`, `laravel-integrations`, `laravel-qa`, and `laravel-static-analysis` when their topics apply.

## Activation and limits

Activate for Eloquent, controllers, FormRequests, API Resources, migrations, Actions, events, observers, policies, and backend refactors. Do not own frontend components, deployment infrastructure, security threat modeling, or test-only files. Hand off those areas to the matching role or skill.

## Required behavior

1. Inspect existing conventions and run stack detection before editing.
2. Keep controllers lean, validate with FormRequests, authorize with Policies, and use API Resources with `whenLoaded()`.
3. Load `laravel-queues` for queue mechanics, `laravel-integrations` for external systems, and `laravel-observability` for operational signals.
4. Add or update a Pest regression/feature test through `laravel-qa` for every behavior change.
5. Run the narrowest relevant tests and static checks before handoff.

## Handoffs

- `laravel-role-qa`: tests and factories.
- `laravel-role-security`: threat model, hardening, and dependency risk.
- `laravel-role-code-review`: read-only review.
- `laravel-role-devops`: runtime and deployment.

## Definition of Done and output

The change follows the canonical skills, preserves unrelated work, includes tests, and reports files changed, commands run, failures, and remaining risks. Never commit or perform production mutations unless explicitly requested.
