# General Application Security

Framework-agnostic security principles. Loaded when reasoning about security architecture, threat modeling, or principles that apply regardless of stack.

## 1. OWASP Top 10 — overview

The Top 10 is the industry's working catalog of high-impact web app vulnerabilities. Current ordering (2021):

| ID | Category | Essence |
|---|---|---|
| A01 | Broken Access Control | User accesses resources they shouldn't |
| A02 | Cryptographic Failures | Sensitive data exposed via weak crypto or no crypto |
| A03 | Injection | Untrusted input interpreted as code/query |
| A04 | Insecure Design | Architectural — missing controls in the design itself |
| A05 | Security Misconfiguration | Default creds, debug enabled, weak headers |
| A06 | Vulnerable Components | Unpatched libraries with known CVEs |
| A07 | Auth Failures | Weak passwords, brute force, session fixation |
| A08 | Software/Data Integrity | Unsigned packages, deserialization, supply chain |
| A09 | Logging/Monitoring Failures | Can't detect or investigate breaches |
| A10 | SSRF | Server makes requests to attacker-controlled URLs |

For Laravel-specific application of each, see `laravel_php_security.md` in this skill.

## 2. Defense in depth

A single control is one bypass away from compromise. Layered controls create resilience.

| Layer | Examples |
|---|---|
| Network | TLS, WAF, DDoS protection, rate limit upstream |
| Identity | MFA, strong password policy, session timeout |
| Application | CSRF, CSP, auth, authorization (Policy + Gate) |
| Data | Encryption at rest, scoped queries, row-level security |
| Operational | Audit log, anomaly detection, dependency scanning, backups |

Design assuming each layer may fail. Do not rely on a single control as your primary defense.

## 3. Principle of least privilege

Every component (user, service, role, token, process) operates with the minimum permissions needed for its function — and nothing more.

Applications:

- **DB user** — separate accounts for migrations (DDL) vs. app runtime (DML only)
- **Service accounts** — one per service, scoped to its needs
- **API tokens** — abilities/scopes per token (e.g., `posts:read` vs. `posts:write`)
- **Files** — uploads stored on private disk, served via controller that re-checks
- **Logs** — different retention/access for app log vs. audit log
- **CI secrets** — repo-scoped, environment-scoped where possible

Periodic review: every quarter, audit who has access to what. Remove drift.

## 4. Threat modeling — STRIDE

Lightweight model from Microsoft. For each component or data flow, ask:

| Threat | Question |
|---|---|
| **S**poofing | Can an attacker impersonate this entity? |
| **T**ampering | Can data in transit or at rest be modified? |
| **R**epudiation | Can an actor deny they did the action? (countered by audit log) |
| **I**nformation disclosure | Can sensitive data leak (logs, errors, headers, URLs)? |
| **D**enial of service | Can a single user exhaust resources? |
| **E**levation of privilege | Can a low-privilege user become high-privilege? |

Run STRIDE during design review of any feature touching auth, payments, PII, or external integrations.

## 5. AuthN, AuthZ, Audit

Three orthogonal concerns; conflating them creates security holes.

| Concern | Question | Examples |
|---|---|---|
| **AuthN** (Authentication) | Who is the actor? | Login, MFA, token verification |
| **AuthZ** (Authorization) | What is this actor allowed to do? | Policy, Gate, role/permission check |
| **Audit** | What did the actor do? | Activity log, immutable event store |

Each layer needs its own controls. A user authenticated via MFA may still be unauthorized for an action; an action that's authorized still needs to be logged.

## 6. Input validation vs. output encoding

Two different, complementary mitigations.

### Input validation
At the trust boundary (HTTP request → app), validate:
- **Type** (string, int, email)
- **Format** (regex, length, range)
- **Domain** (must be in allowed set)

Rejected input never enters the system. In Laravel: FormRequest.

### Output encoding
At the boundary the data leaves the system through, encode for the destination context:
- **HTML** — `htmlspecialchars` (Blade `{{ }}` does this)
- **JS** — `json_encode` with appropriate flags
- **URL** — `urlencode` / `rawurlencode`
- **SQL** — bindings (parameterized queries)
- **Shell** — escapeshellarg
- **HTTP header** — strip CRLF

Validation alone is not enough — defenders must encode at every output path because:
- Validation can be bypassed by upstream changes
- Some "valid" data is unsafe in some contexts (a name with `<` is valid but XSS-unsafe in HTML)

## 7. Session management

Three properties of a secure session:

| Property | Mechanism |
|---|---|
| Confidentiality | HTTPS only; `Secure` cookie attribute |
| Integrity | Server-side state or signed/encrypted cookie |
| Freshness | Reasonable lifetime; regenerate on login; invalidate on logout |

Common failures:
- Session ID in URL — leaked via referrer headers, browser history, logs
- No regeneration on privilege change (login, role change) — fixation
- Indefinite lifetime — stolen cookie remains valid forever
- `HttpOnly=false` — JS can read; XSS escalates to session theft
- `SameSite=None` without `Secure=true` — invalid; browsers reject anyway

## 8. Secret management

Principles:

- **Never in source code** — even in dev environments. Rotate immediately if leaked.
- **Never in logs** — scrub before logging
- **Different per environment** — dev / staging / prod use different secrets
- **Rotated regularly** — 90 days for high-value, immediately on suspected leak
- **Tied to identity** — each developer / service has their own; revocable individually

Storage tiers:
- Local dev: `.env` (gitignored)
- CI: encrypted secrets store (GitHub Actions secrets, GitLab CI variables)
- Production: dedicated secret manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault)

## 9. Logging hygiene

Two failure modes — log too little vs. log too much.

### Too little
- No audit trail when investigating an incident
- Can't reproduce attacker behavior
- Compliance gap

### Too much
- Sensitive data in logs (PII, credentials, tokens)
- Log volume explodes; noise drowns signal
- Storage cost; retention difficulty

Right balance:
- Log all auth events (login, logout, MFA, password change)
- Log all permission changes
- Log access to sensitive data categories (not every read)
- Log all admin actions
- **Scrub** request bodies before logging — explicit allowlist of fields, not blocklist
- Centralize logs — never *only* local files in production

## 10. Incident response basics

A breach is when, not if. Have a plan before it happens.

### 10.1 Detect
- Monitoring on auth failures, anomalous traffic, error spikes
- Audit log review (manual or automated)
- External signal — researcher disclosure, customer report, abuse@ inbox

### 10.2 Contain
- Rotate suspected credentials immediately
- Revoke tokens / sessions for affected accounts
- Isolate affected systems if needed (read-only mode, take feature offline)

### 10.3 Eradicate
- Patch the vulnerability
- Remove attacker access (close backdoors, reset compromised accounts)

### 10.4 Recover
- Restore from clean backups if needed
- Re-enable systems progressively
- Monitor for residual activity

### 10.5 Post-incident
- Write a postmortem (what happened, timeline, what we did, what we'd do differently)
- File regulatory notifications if required (LGPD: 72h to authority for high-risk breaches; GDPR: 72h)
- Notify affected users when required

Document the runbook. Practice with tabletop exercises annually.

## 11. Security review process

Integrate security reviews into normal engineering flow:

| Trigger | Review |
|---|---|
| New feature touching auth, payments, PII | Threat model (STRIDE) |
| New external integration | Authentication, signature verification, rate limit |
| New endpoint accepting input | Validation, authorization, rate limit |
| New dependency | License + CVE check |
| Pre-release | Full audit of changed code |
| Quarterly | Permission audit, secret rotation, dep upgrade |
| Annually | Full pen test (external) |

## 12. Anti-patterns — generic

| Smell | Why |
|---|---|
| Single point of failure for security (one control) | One bypass = full compromise |
| Implicit trust between internal services | Lateral movement after one compromise |
| Security by obscurity (hidden URLs, custom crypto) | Eventual disclosure invalidates the entire model |
| Manual security review only at release | Issues compound; fix becomes expensive |
| No threat model for new feature | Design-time issues become runtime CVEs |
| Audit log mutable | Attacker can erase tracks |
| Same credentials across environments | Dev leak compromises prod |
| "We'll add security later" | Security retrofits are 10× the cost of designing it in |
| No incident response plan | First breach is also the first practice |
