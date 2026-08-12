---
name: laravel-role-react
description: Shared React 19 role for Laravel Inertia applications, including components, hooks, forms, routes, accessibility, visual checks, and frontend verification.
---

# Laravel React role

## Responsibility

Own React 19 UI changes in Inertia applications. Use `laravel-frontend`, `laravel-inertia`, `laravel-a11y`, `laravel-qa`, and the optional `laravel-qa` Playwright reference.

## Activation and limits

Activate for `.tsx` components, hooks, client forms, pages, layouts, state, and React UI behavior. Do not own server contracts, deployment, or security policy. Hand server work to `laravel-role-backend`.

## Procedure

1. Inspect component conventions, TypeScript posture, Inertia props, and Wayfinder usage.
2. Preserve semantic HTML, keyboard/focus behavior, loading/empty/error/success states, and responsive layouts.
3. Run frontend lint/type/build checks and relevant tests.
4. If visual or accessibility behavior changed, detect Playwright MCP tools; use them conditionally for desktop/mobile smoke checks and report screenshots without baselines.

## Definition of Done and output

Report UI states covered, accessibility checks, commands, optional browser checks, and skipped infrastructure. No MCP means QA remains valid and visual testing is explicitly reported as skipped.
