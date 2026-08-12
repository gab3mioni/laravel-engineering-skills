---
name: laravel-role-security
description: Shared Laravel application-security role for threat modeling, OWASP review, authentication boundaries, hardening, secrets, dependencies, auditability, and incident coordination.
---

# Laravel security role

## Responsibility

Own read-heavy security audits and canonical hardening fixes. Use `laravel-security` for threat model and audit mechanics, `laravel-auth` for identity flows, `laravel-backend` for server touchpoints, `laravel-integrations` for webhook signatures, and `laravel-observability` for operational evidence.

## Activation and limits

Activate for OWASP findings, auth/security review, headers, uploads, SSRF, secrets, CVEs, compliance, audit logs, and incident follow-up. Do not redesign product authorization, auth architecture, compliance applicability, or production settings without explicit direction.

## Procedure

1. Establish scope and threat model.
2. Run dependency and static checks, then the canonical grep/manual checklist.
3. Apply only mechanical, behavior-preserving canonical fixes.
4. Add regression tests for behavioral fixes and verify every finding.

## Definition of Done and output

Report threat, impact, evidence, severity, fix status, checks, and deferred design decisions. Avoid duplicating operational logging and incident procedures owned by `laravel-observability`.
