---
name: laravel-role-code-review
description: Shared read-only Laravel review role for diffs, branches, security, correctness, tests, performance, frontend, operations, and ownership boundaries.
---

# Laravel code review role

## Responsibility

Review the requested diff or scope without editing it. Route findings to canonical skills: `laravel-backend`, `laravel-auth`, `laravel-security`, `laravel-queues`, `laravel-integrations`, `laravel-observability`, `laravel-qa`, `laravel-a11y`, `laravel-static-analysis`, and `laravel-deploy`.

## Activation and limits

Activate for PR, branch, or unscoped Laravel reviews. Read-only ownership means no edits, commits, dependency changes, database changes, or production actions.

## Procedure

1. Establish scope and inspect the full diff plus nearby contracts.
2. Run relevant detection greps and canonical skill checklists.
3. Classify findings by severity and distinguish current-diff regressions from pre-existing issues.
4. Check tests, authorization, transactions/`afterCommit`, external calls, observability, accessibility, and deploy impact as applicable.

## Definition of Done and output

Report only actionable findings with `file:line`, impact, evidence, canonical section/skill, and concrete fix. State checks actually run and skipped checks. Do not pad the report with correct behavior.
