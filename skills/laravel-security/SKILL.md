---
name: laravel-security
description: 'Application security posture for Laravel 12 / PHP 8.3+ — OWASP Top 10:2025 applied (mass assignment, SQL injection, XSS, CSRF, SSRF, IDOR, auth failures, supply chain), security headers (CSP, HSTS, X-Frame-Options), rate limiting, cookies and sessions, timing attacks, file upload safety, dependency CVEs (composer audit, npm audit), secret management, audit logging, PHP-specific gotchas (deserialization, type juggling), and compliance (LGPD, GDPR, SOC 2, PCI, HIPAA). Use when: pre-production hardening, PR security review, CVE triage, "is this safe?" questions, incident follow-up. Used by shared security and review roles.'
---

# Laravel Security — Application posture

Application-wide security for Laravel 12 / PHP 8.3+. Operates above the per-feature backend touchpoints — focuses on **defense in depth, hardening, dependency hygiene, compliance**.

## When to use this skill

- Auditing the security posture of an app (full review or PR-level)
- Hardening before going to production
- Investigating a vulnerability disclosure or CVE
- Designing security headers, rate limits, file-upload policies
- Implementing compliance requirements (LGPD/GDPR/SOC 2)
- Triaging dependency CVEs (`composer audit`, `npm audit`)

## When NOT to use

| Topic | Use instead |
|---|---|
| Auth flow implementation (Sanctum, Fortify, login/MFA) | `laravel-auth` skill |
| Backend security touchpoints (mass assignment, FormRequest, raw queries) | `laravel-backend` skill (`security` reference) |
| Policy / Gate authoring patterns | `laravel-backend` skill §13 + `laravel-auth` skill (`authorization_patterns` reference) |
| Test scenarios for security regressions | `laravel-qa` skill |
| WCAG / a11y audits | `laravel-a11y` skill |
| Frontend component fixes (React/Vue) after an XSS finding | `laravel-role-react` / `laravel-role-vue` |
| Infra hardening (TLS termination, WAF, container images, CI secrets) | `laravel-role-devops` |

## Stack assumptions

- Laravel 12, PHP 8.3+
- HTTPS in production (TLS 1.2+, prefer 1.3)
- Composer 2 + npm/pnpm for dependency management
- Detection-based: agent runs `composer audit`, `npm audit`, `composer show <pkg>` to adapt

---

## Workflows

### Security audit runbook

Run in order. Every step feeds the report (step 5).

**1. Dependency scan** — record package versions and CVE IDs:

```bash
composer audit
npm audit                          # or pnpm audit
composer outdated --direct
```

**2. Config check** — run the §6 hardening table as commands:

```bash
php artisan config:show app.debug          # must be false
php artisan config:show app.env            # must be "production"
php artisan config:show session.secure     # must be true
php artisan config:show session.http_only  # must be true
php artisan config:show session.same_site  # lax or strict
ls -la .env                                # 600, owned by web user
php artisan route:list | grep -iE 'telescope|pulse|debugbar|horizon'
```

**3. Grep battery** — run every detection command in the §18 table. Record `file:line` for each hit; false positives get dismissed in step 4, not skipped here.

**4. Manual review** — priority order:

1. `routes/web.php` + `routes/api.php` — every mutating route behind `auth` / `auth:sanctum`; `throttle` coverage on login, register, password reset
2. Controllers whose mutating actions take `Request` instead of a FormRequest
3. Each `{!! !!}` hit from step 3 — is the value user input or trusted markup?
4. Upload endpoints — validation rules, storage disk, how files are served back
5. Webhook endpoints — signature verification (HMAC/JWT) present before any processing
6. `config/session.php`, `config/cors.php`, `config/sanctum.php` — cookie flags, allowed origins, stateful domains

**5. Report** — one entry per finding:

> finding → OWASP 2025 category → severity (critical / high / medium / low) → fix → detection command that catches regressions

### Canonical fix protocol

**Apply without asking** (mechanical, behavior-preserving):

- Missing `@csrf` in a Blade form
- `{!! !!}` → `{{ }}` when the value is user input
- Add `throttle` middleware to a login route
- `composer update <pkg>` for a patch-level CVE fix
- Missing FormRequest on a mutating endpoint

**Report only** (needs product judgment):

- CSP design — per-app allowlists break inline scripts and third-party embeds
- Session architecture — lifetime, driver, cookie domain changes
- Auth flow redesign — guards, MFA, SSO
- Anything that changes user-visible behavior or requires a data migration

After every applied fix: re-run the relevant §18 grep (must come back clean) and the nearest test (`php artisan test --filter=<Feature>`).

---

## Decision tables

### 1. OWASP Top 10 — quick map

OWASP Top 10:2025 codes. SSRF (formerly A10:2021) is now part of A01.

| OWASP | Laravel touchpoint | Where in skills |
|---|---|---|
| A01 Broken Access Control | IDOR, missing Policy, route-model binding without authorize | `laravel-backend` §13 + `laravel-auth` (`authorization_patterns`) |
| A01 — SSRF (folded in) | outbound HTTP with user-controlled URL, no allowlist | `references/laravel_php_security.md` §1 |
| A02 Security Misconfiguration | `APP_DEBUG=true` prod, weak CSP, exposed `.env` | §6 (this skill) |
| A03 Software Supply Chain Failures | unpatched deps, lockfile integrity, CI dependencies | §13 (this skill) |
| A04 Cryptographic Failures | weak hashing, hardcoded keys, missing TLS | §11 (this skill) |
| A05 Injection | SQL (raw + interpolation), command, LDAP, header | `laravel-backend` (`security` reference §4) + §3 (this skill) |
| A06 Insecure Design | architectural — covered in design review | `references/laravel_php_security.md` §6 |
| A07 Authentication Failures | weak passwords, brute force, session fixation | `laravel-auth` + §9, §11 here |
| A08 Software or Data Integrity Failures | unsigned packages, deserialization | §16.2 (this skill) |
| A09 Security Logging & Alerting Failures | missing audit trail, no alerting | §15 (this skill) |
| A10 Mishandling of Exceptional Conditions | `APP_DEBUG` leaks, fail-open catch blocks, exception detail in APIs | `references/laravel_php_security.md` §10 |

### Defense in depth

A single control is one bypass away from compromise. Layered controls create resilience:

| Layer | Example |
|---|---|
| Network | TLS, WAF, rate limit upstream |
| Application | CSP, CSRF, auth, Policies |
| Data | Encryption at rest, scoped queries, RLS |
| Operational | Audit log, monitoring, dependency scanning |

## 2. Mass assignment & input validation

The single highest-leverage server-side issue. Quick recap (full coverage in `laravel-backend`):

- Always declare `$fillable` or `$guarded = []`, never both, never neither
- Never `$request->all()` reaching `create()`/`update()`/`fill()`
- Always `$request->validated()` from a FormRequest

⚠️ Audit grep:

```bash
grep -rn '\$request->all()' app/Http/Controllers
grep -rn 'extends Model' app/Models | xargs -I {} grep -L 'fillable\|guarded' {}
```

## 3. SQL injection

Eloquent and Query Builder are safe by default — bindings are parameterized. The risk lives only in raw queries with concatenation:

```php
DB::raw("title = '{$user_input}'")              // BAD — interpolated
DB::select("SELECT * FROM x WHERE id = {$id}")  // BAD
->whereRaw("name = '{$name}'")                  // BAD
->orderByRaw("col_{$direction}")                // BAD — column-name injection
```

Safe forms — always pass bindings:

```php
DB::raw('? as label')                                                       // with binding
DB::select('SELECT * FROM x WHERE id = ?', [$id])
->whereRaw('name = ?', [$name])
```

⚠️ Column names are not bindable. For sortable columns from user input, use an allowlist (load `laravel-backend`, `api_design_patterns` reference §6).

```bash
grep -rnE 'DB::raw\(.*\$|whereRaw\(.*\$|orderByRaw\(.*\$|selectRaw\(.*\$' app/
```

## 4. XSS — Blade escape rules

```blade
{{ $userInput }}        {{-- escaped via htmlspecialchars — safe --}}
{!! $userInput !!}      {{-- raw, unescaped — DANGEROUS --}}
{!! Purifier::clean($html) !!}  {{-- raw acceptable when sanitized via mews/purifier --}}
```

`{!! !!}` is the only XSS surface in Blade. Audit:

```bash
grep -rn '{!!' resources/views/
```

For each match: confirm the value is either trusted (constant, controller-generated markup) or sanitized via HTML Purifier or DOMPurify equivalent.

In Inertia (React/Vue), the framework-level raw-HTML escape hatches (the React prop ending in `InnerHTML`, and the Vue `v-html` directive) carry the same risk. Audit `resources/js/`:

```bash
grep -rnE 'InnerHTML|v-html' resources/js/
```

## 5. CSRF

Laravel's `web` middleware group ships `VerifyCsrfToken`. Every Blade `<form method="POST">` needs `@csrf` inside it. For Inertia, the token is auto-injected (no `@csrf` needed in the SPA). For pure API endpoints under `auth:sanctum`, CSRF doesn't apply (token replaces it).

### 5.1 Webhook exceptions

Inbound webhooks (Stripe, GitHub) can't include the CSRF token. Exclude their routes:

```php
// bootstrap/app.php (Laravel 11+)
->withMiddleware(function (Middleware $m) {
    $m->validateCsrfTokens(except: ['stripe/*', 'webhooks/github']);
})
```

⚠️ When excluding from CSRF, **always** verify request authenticity via the provider's signature (HMAC, JWT). Load `laravel-backend` (`api_design_patterns` reference §9).

## 6. Security misconfiguration

Production hardening checklist — the audit runbook step 2 runs these as `php artisan config:show` commands:

| Setting | Required |
|---|---|
| `APP_ENV=production` | yes |
| `APP_DEBUG=false` | yes — otherwise stack traces leak file paths and DB names |
| `APP_KEY` set (32 random bytes) | yes |
| `php artisan config:cache` | recommended (faster, locks env reads) |
| `php artisan route:cache` | recommended |
| `php artisan view:cache` | recommended |
| `.env` permissions: 600, owned by web user | yes |
| `storage/logs/` permissions: not world-readable | yes |
| Telescope / Debugbar / Pulse disabled or auth-gated in prod | yes |

⚠️ Anti-pattern: shipping `APP_DEBUG=true` to production. Detect:

```bash
php artisan config:show app.debug
```

## 7. Security headers

Apply via middleware. Recommended baseline:

| Header | Value | Effect |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` | Force HTTPS |
| `X-Frame-Options` | `DENY` (or `SAMEORIGIN` if you embed) | Clickjacking |
| `X-Content-Type-Options` | `nosniff` | MIME sniffing |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer leak |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=()` | Feature opt-out |
| `Content-Security-Policy` | per-app — see below | XSS containment |

### 7.1 CSP

CSP is the strongest XSS containment but requires per-app tuning. Detect `spatie/laravel-csp` (`composer show spatie/laravel-csp`); if present, use it. Otherwise, a custom middleware:

```php
class SecureHeaders
{
    public function handle(Request $request, Closure $next): Response
    {
        $response = $next($request);

        $response->headers->set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
        $response->headers->set('X-Frame-Options', 'DENY');
        $response->headers->set('X-Content-Type-Options', 'nosniff');
        $response->headers->set('Referrer-Policy', 'strict-origin-when-cross-origin');
        $response->headers->set('Content-Security-Policy', $this->csp());

        return $response;
    }

    private function csp(): string
    {
        return implode('; ', [
            "default-src 'self'",
            "script-src 'self' https://cdn.example.com",
            "style-src 'self' 'unsafe-inline'",                  // tighten if possible
            "img-src 'self' data: https:",
            "connect-src 'self' https://api.example.com",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "base-uri 'self'",
        ]);
    }
}
```

⚠️ CSP rollout is a "report only" change in the fix protocol — deploy with `Content-Security-Policy-Report-Only` first.

For full CSP recipes per stack (Inertia SPA, server-rendered, mixed), see `references/laravel_php_security.md` §2.

## 8. Rate limiting

```php
// AppServiceProvider::boot()
RateLimiter::for('api', function (Request $r) {
    return Limit::perMinute(60)->by($r->user()?->id ?: $r->ip());
});

RateLimiter::for('login', function (Request $r) {
    return [
        Limit::perMinute(5)->by($r->ip()),
        Limit::perMinute(3)->by($r->input('email')),
    ];
});

RateLimiter::for('webhook', function (Request $r) {
    return Limit::perMinute(120)->by($r->ip());
});
```

Apply via middleware:

```php
Route::middleware('throttle:api')->group(/* ... */);
Route::post('/login', /* ... */)->middleware('throttle:login');
```

**Strategy:**
- Public endpoints: throttle by IP
- Authenticated endpoints: throttle by user ID
- Login: throttle by IP **and** by email/username (covers brute-force on a single account)
- Password reset / 2FA: tighter (3 / minute)

## 9. Cookies & sessions

```php
// config/session.php
'secure'        => env('SESSION_SECURE_COOKIE', true),     // HTTPS only
'http_only'     => true,                                   // not readable by JS
'same_site'     => 'lax',                                  // 'strict' for stricter; 'none' only with secure=true
'expire_on_close' => false,
'lifetime'      => 120,                                    // minutes
```

### 9.1 Session fixation

If the session ID survives login, an attacker who planted that ID (link, subdomain cookie) inherits the authenticated session. The mitigation is regenerating the ID on login and invalidating on logout — Fortify/Breeze do both automatically. The login/logout flow is owned by the `laravel-auth` skill; here, only verify custom login handlers call `session()->regenerate()`.

### 9.2 Sensitive ops — session timeout

For sensitive routes (account settings, password change), use Laravel's `password.confirm` middleware to require password re-entry within a short window:

```php
Route::middleware(['auth', 'password.confirm'])->group(function () {
    Route::get('/settings/security', /* ... */);
});
```

## 10. File upload safety

Quick recap (full coverage in `laravel-backend`, `security` reference §9):

```php
// FormRequest
'file' => [
    'required',
    File::types(['pdf', 'jpg', 'png'])->max(10 * 1024),   // KB; checks MIME + extension
    Rule::dimensions()->maxWidth(2000)->maxHeight(2000), // for images
],

// Controller
$path = $request->file('file')->store('uploads', 'private');   // never 'public'
```

⚠️ **Anti-pattern:** storing user uploads on the `public` disk and serving directly. Polyglot files (XSS in SVG, executable masquerading as image) become exploitable.

Serve via a controller that re-checks authorization:

```php
public function show(Upload $upload): StreamedResponse
{
    $this->authorize('view', $upload);
    return Storage::disk('private')->download($upload->path);
}
```

For S3 with signed URLs, content-type sniffing prevention, and AV scanning, load `laravel-backend` (`security` reference §9).

## 11. Password hashing

Fast digests (`md5`, `sha1`, `crypt`) fall to offline brute force in hours once a DB dump leaks — passwords need a slow, salted KDF (bcrypt or argon2id via the `Hash` facade). Hashing config, rehash-on-login, and the full flow are owned by the `laravel-auth` skill. In an audit, only detect violations:

```bash
grep -rnE 'md5\(|sha1\(|crypt\(|password_hash\(' app/
```

## 12. Timing attacks

Comparing secrets with `===` leaks timing. Use constant-time:

```php
// BAD
if ($signature === $expected) { /* ... */ }

// GOOD
if (hash_equals($expected, $signature)) { /* ... */ }

// Laravel helpers (constant-time internally)
Hash::check($input, $hashed);
```

Audit:

```bash
grep -rnE 'hash_equals|===' app/ | grep -i 'signature\|token\|secret'
```

## 13. Dependency security

### 13.1 Composer

```bash
composer audit                           # check for known CVEs
composer audit --format=json
composer outdated --direct               # what's old in your direct deps
composer why-not <pkg> <version>         # explain blocking constraints
```

Block merge on critical/high vulns; triage medium/low based on exploitability. CI wiring for these gates is owned by the `laravel-static-analysis` skill.

### 13.2 npm / pnpm

`npm audit` (or `pnpm audit`) for CVEs; `npm audit fix` auto-fixes non-breaking; `--force` may break — review the diff.

### 13.3 Dependabot / Renovate

Enable in `.github/dependabot.yml` or `renovate.json`. Cadence: weekly for non-security, daily for security advisories.

⚠️ Anti-pattern: auto-merging dependency updates without CI gates. Always run full test suite + security scan on the PR.

## 14. Secret management

```php
// .env (NEVER commit) holds the raw values
// config/services.php — env() used here, not in app code
'stripe' => ['secret' => env('STRIPE_SECRET')],

// Code — config(), never env()
$key = config('services.stripe.secret');
```

### 14.1 Encryption at rest

Sensitive columns: `protected $casts = ['ssn' => 'encrypted'];` on the model. Elsewhere, `encrypt($plain)` / `decrypt($enc)` (keyed by `APP_KEY`).

### 14.2 Production secret stores

AWS Secrets Manager (+ IAM role), GCP Secret Manager (+ Workload Identity), HashiCorp Vault (sidecar or boot-time fetch), or Forge dashboard env vars — load into env at boot, never bake into images.

### 14.3 Secret rotation

- Rotate API keys on a cadence (90 days for high-value)
- Rotate immediately on developer offboarding
- After any leak (commit history, log file): rotate, then audit access logs

⚠️ Anti-pattern: secret committed to git history. Rotation is mandatory — `git filter-branch` does not save you (clones still have the secret).

## 15. Audit logging

Detect `spatie/laravel-activitylog` (`composer show spatie/laravel-activitylog`); if present, use `LogsActivity` with `LogOptions::defaults()->logOnly([...])->logOnlyDirty()`. Without the package, an Observer + dedicated `audit_log` table works. Key requirements:

- **Immutable** — append-only; no UPDATE/DELETE on audit rows
- **Includes actor** — user ID, session ID, IP
- **Includes context** — what changed, before/after
- **Tamper-evident** — chain hashes between rows for high-stakes systems
- **Retention** — keep at least as long as legal/compliance requires (LGPD: 5 years for some categories)

### 15.1 What to log

Log: login success/fail, password change/reset, MFA enable/disable, permission changes, sensitive-data access (PII, financial), data exports. Do NOT log routine reads — too noisy.

### 15.2 Where to send audit records

Stack channels in `config/logging.php` toward a centralized destination (Sentry, Datadog, CloudWatch, ELK) — never *only* local files in production.

⚠️ **Anti-pattern:** logging the raw request body:

```php
Log::info('payment.received', $request->all());   // BAD — leaks card, email, password
```

Always scrub. Load `laravel-backend` (`security` reference §7) for scrub helpers.

Operational logs, metrics, job monitoring, health checks, alerts, and incident response are canonical in `laravel-observability`. Use that skill instead of duplicating operational telemetry here.

## 16. PHP-specific gotchas

### 16.1 Type juggling

`==` (loose equality) compares with type coercion — exploitable: `"0" == false` and `[] == null` are `true`; `"abc" == 0` was `true` on PHP 7. Always use `===`. PHP 8.x mitigates many but not all cases.

### 16.2 Deserialization

The `unserialize` function on user-controlled data executes magic methods (`__wakeup`, `__destruct`). Code execution risk.

```bash
grep -rn 'unserialize(' app/ | grep -v 'safe_unserialize'
```

If used, restrict allowed classes: `unserialize($data, ['allowed_classes' => [SafeClass::class]])`. Better: use JSON for serialized payloads when possible.

### 16.3 Dynamic code execution and file inclusion

The `eval` keyword and dynamic `include` / `require` with user input enable direct code execution. Audit:

```bash
grep -rnE '\beval\b|\b(include|require|require_once|include_once)\s*\(\s*\$' app/
```

These should never appear with user input. If found, refactor immediately.

### 16.4 Header injection

User input in headers (CRLF) can split responses. Strip before setting:

```php
return response('ok')->header('X-User', preg_replace('/[\r\n]/', '', $request->input('name')));
```

---

## Rules & anti-patterns

### 18. Consolidated checklist

Single-page scan list for `security` and `code-review` agents. Every row has a runnable detection command — this is the grep battery of audit runbook step 3.

| Smell | Section | Detection |
|---|---|---|
| `APP_DEBUG=true` in production | §6 | `php artisan config:show app.debug` |
| `{!! !!}` in Blade with user input | §4 | `grep -rn '{!!' resources/views/` |
| Frontend raw-HTML escape hatch (React, Vue) with user input | §4 | `grep -rnE 'InnerHTML\|v-html' resources/js/` |
| Routes excluded from CSRF without HMAC verification | §5 | `grep -n 'validateCsrfTokens' bootstrap/app.php` then review each pattern |
| User upload stored on `public` disk | §10 | `grep -rn "store(.*'public'" app/` |
| `===` for HMAC/signature comparison | §12 | `grep -rnE '===' app/ \| grep -iE 'signature\|hmac\|webhook'` |
| `md5`/`sha1`/`crypt` used for passwords | §11 | `grep -rnE 'md5\(\|sha1\(\|crypt\(' app/` |
| `unserialize` on user data without allowlist | §16.2 | `grep -rn 'unserialize(' app/` |
| Dynamic `include`/`require` with `$variable` | §16.3 | `grep -rnE '\b(include\|require)(_once)?\s*\(\s*\$' app/` |
| User input in raw HTTP headers without CRLF strip | §16.4 | `grep -rnE '->header\([^)]*\$request' app/` |
| Dep with critical/high CVE on main branch | §13 | `composer audit`, `npm audit` |
| Secret committed to git history | §14 | `git log --all -p \| grep -iE 'password\|secret\|api[_-]?key'` |
| `Log::info($request->all())` | §15.2 | `grep -rnE 'Log::\w+\([^)]*\$request->all\(\)' app/` |
| Audit log writable (UPDATE/DELETE allowed) | §15 | `SHOW GRANTS FOR CURRENT_USER;` — review for audit table |
| No CSP header | §7 | `curl -sI https://<host> \| grep -i content-security-policy` |
| `SESSION_SECURE_COOKIE=false` in prod | §9 | `php artisan config:show session.secure` |
| Login route without `throttle` middleware | §8 | `php artisan route:list --path=login` — check middleware column |
| Outbound HTTP with user-controlled URL, no allowlist (SSRF) | §1 (A01) | `grep -rnE 'Http::\w+\([^)]*\$(request\|input)\|file_get_contents\(\s*\$' app/` — heuristic; review each hit for a URL allowlist |
| Telescope/Pulse/Debugbar visible in prod | §6 | `php artisan route:list \| grep -iE 'telescope\|pulse\|debugbar'` |
| Authorization via `if ($user->role === ...)` | (laravel-backend §13) | `grep -rnE '->role\s*===?' app/` |

---

## Reference routing

| Need | Load |
|---|---|
| Full OWASP Top 10:2025 walkthrough / STRIDE threat modeling / audit greps / review cadence | `references/laravel_php_security.md` |
| LGPD / GDPR (consent, data subject rights, retention, breach notification) / SOC 2 / PCI (tokenize, segregate) / HIPAA (PHI encryption, BAA), data-subject erasure jobs, audit-log schema and retention | `references/compliance.md` |

---

## Cross-references

| Topic | Skill / reference |
|---|---|
| Auth flow (Sanctum, Fortify, MFA, password reset, hashing config, session regeneration) | `laravel-auth` skill |
| Backend security touchpoints (mass assignment, FormRequest, raw queries, log scrubbing) | `laravel-backend` skill (`security` reference) |
| Authorization patterns (Policy, Gate, multi-tenant, Sanctum tokens) | `laravel-auth` skill (`authorization_patterns` reference) |
| Webhook signature verification (HMAC + idempotency) | `laravel-backend` skill (`api_design_patterns` reference §9) |
| CI gates for `composer audit` / static analysis | `laravel-static-analysis` skill |
| Test scenarios for security regressions | `laravel-qa` skill |
| WCAG / a11y audits | `laravel-a11y` skill |
