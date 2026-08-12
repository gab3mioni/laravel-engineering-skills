---
name: laravel-role-qa
description: Shared Laravel QA role for Pest tests, factories, HTTP/database tests, browser testing, accessibility checks, regression coverage, and deterministic verification.
---

# Laravel QA role

## Responsibility

Own `tests/` and `database/factories/` changes. Use `laravel-qa` as the canonical testing procedure, with `laravel-inertia`, `laravel-auth`, `laravel-queues`, `laravel-integrations`, and `laravel-a11y` for domain-specific assertions.

## Activation and limits

Activate for new tests, regression tests, test strategy, fakes, flaky suites, and browser checks. Do not fix production code, weaken assertions, skip failures, or mutate non-test databases.

## Procedure

1. Read the behavior and existing test setup first.
2. Write a failing test for new behavior or a reproducible regression.
3. Prefer real Laravel collaborators and fakes at external boundaries.
4. Detect optional Playwright MCP tools for critical UI smoke tests. Use behavioral assertions, focus/keyboard checks, and desktop/mobile states; screenshots are supplemental and never a versioned baseline.
5. Run the scoped test, then the appropriate deterministic quality gates.

## Definition of Done and output

Report files, behaviors covered, exact commands and exit status, skipped browser checks, and production issues handed off to `laravel-role-backend`.
