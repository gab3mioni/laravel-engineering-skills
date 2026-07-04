---
name: laravel-security
description: Application security posture for Laravel 12 / PHP 8.3+ — OWASP Top 10 applied (mass assignment, SQL injection, XSS, CSRF, SSRF, IDOR, auth failures, vulnerable deps), security headers (CSP, HSTS, X-Frame-Options), rate limiting, cookies and sessions, password hashing, timing attacks, file upload safety, dependency CVEs (composer audit, npm audit), secret management, audit logging, PHP-specific gotchas (deserialization, type juggling), and compliance (LGPD, GDPR, SOC 2, PCI, HIPAA). Consumed by security, code-review, and backend agents.
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
| Auth flow implementation (Sanctum, Fortify, login/MFA) | `laravel-auth` |
| Backend security touchpoints (mass assignment, FormRequest, raw queries) | `laravel-backend` (§ 4, §13) and `references/security.md` there |
| Policy / Gate authoring patterns | `laravel-backend` §13 + `authorization_patterns.md` reference |
| Test scenarios for security regressions | `laravel-qa` |
| WCAG / a11y audits | `laravel-a11y` |

## Stack assumptions

- Laravel 12, PHP 8.3+
- HTTPS in production (TLS 1.2+, prefer 1.3)
- Composer 2 + npm/pnpm for dependency management
- Detection-based: agent runs `composer audit`, `npm audit`, `composer show <pkg>` to adapt

## Philosophy — defense in depth

A single control is one bypass away from compromise. Layered controls create resilience:

| Layer | Example |
|---|---|
| Network | TLS, WAF, rate limit upstream |
| Application | CSP, CSRF, auth, Policies |
| Data | Encryption at rest, scoped queries, RLS |
| Operational | Audit log, monitoring, dependency scanning |

For a deeper walkthrough of OWASP Top 10 in Laravel and framework-agnostic security principles, see:

- `references/laravel_php_security.md` — OWASP Top 10 applied, PHP-specific gotchas
- `references/general_security.md` — principles independent of framework
- `references/compliance.md` — LGPD, GDPR, SOC 2, PCI, HIPAA

---

## 1. OWASP Top 10 — quick map

OWASP Top 10:2025 codes. SSRF (formerly A10:2021) is now part of A01.

| OWASP | Laravel touchpoint | Where in skills |
|---|---|---|
| A01 Broken Access Control | IDOR, missing Policy, route-model binding without authorize | `laravel-backend` §13 + `authorization_patterns.md` |
| A01 — SSRF (folded in) | outbound HTTP with user-controlled URL, no allowlist | `references/laravel_php_security.md` §1 |
| A02 Security Misconfiguration | `APP_DEBUG=true` prod, weak CSP, exposed `.env` | §6 (this skill) |
| A03 Software Supply Chain Failures | unpatched deps, lockfile integrity, CI dependencies | §13 (this skill) |
| A04 Cryptographic Failures | weak hashing, hardcoded keys, missing TLS | §11 (this skill) |
| A05 Injection | SQL (raw + interpolation), command, LDAP, header | `laravel-backend/references/security.md` §4 + §3 (this skill) |
| A06 Insecure Design | architectural — covered in design review | `references/laravel_php_security.md` §6 |
| A07 Authentication Failures | weak passwords, brute force, session fixation | `laravel-auth` + §10–§11 here |
| A08 Software or Data Integrity Failures | unsigned packages, deserialization | §15 (this skill) |
| A09 Security Logging & Alerting Failures | missing audit trail, no alerting | §14 (this skill) |
| A10 Mishandling of Exceptional Conditions | `APP_DEBUG` leaks, fail-open catch blocks, exception detail in APIs | `references/laravel_php_security.md` §10 |

For each category in depth, see `references/laravel_php_security.md`.

---

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

---

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

⚠️ Column names are not bindable. For sortable columns from user input, use an allowlist (see `laravel-backend/references/api_design_patterns.md` §6).

```bash
grep -rnE 'DB::raw\(.*\$|whereRaw\(.*\$|orderByRaw\(.*\$|selectRaw\(.*\$' app/
```

---

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

---

## 5. CSRF

Laravel's `web` middleware group ships `VerifyCsrfToken`. Forms get a token via `@csrf`:

```blade
<form method="POST" action="/posts">
    @csrf
    <input name="title">
</form>
```

For Inertia, the token is auto-injected (no `@csrf` needed in the SPA). For pure API endpoints under `auth:sanctum`, CSRF doesn't apply (token replaces it).

### 5.1 Webhook exceptions

Inbound webhooks (Stripe, GitHub) can't include the CSRF token. Exclude their routes:

```php
// bootstrap/app.php (Laravel 11+)
->withMiddleware(function (Middleware $m) {
    $m->validateCsrfTokens(except: ['stripe/*', 'webhooks/github']);
})
```

⚠️ When excluding from CSRF, **always** verify request authenticity via the provider's signature (HMAC, JWT). See `laravel-backend/references/api_design_patterns.md` §9.

---

## 6. Security misconfiguration

Production hardening checklist:

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
grep -E '^APP_DEBUG' .env.example .env.production 2>/dev/null
```

---

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

For full CSP recipes per stack (Inertia SPA, server-rendered, mixed), see `references/laravel_php_security.md` §2.

---

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

---

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

Always regenerate session ID on login:

```php
// In login handler — Fortify/Breeze do this automatically
$request->session()->regenerate();
```

On logout, invalidate:

```php
$request->session()->invalidate();
$request->session()->regenerateToken();
```

### 9.2 Sensitive ops — session timeout

For sensitive routes (account settings, password change), use Laravel's `password.confirm` middleware to require password re-entry within a short window:

```php
Route::middleware(['auth', 'password.confirm'])->group(function () {
    Route::get('/settings/security', /* ... */);
});
```

---

## 10. File upload safety

Quick recap (full coverage in `laravel-backend/references/security.md` §9):

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

For S3 with signed URLs, content-type sniffing prevention, and AV scanning, see `laravel-backend/references/security.md` §9.

---

## 11. Password hashing

Laravel ships bcrypt by default. Argon2id is supported and stronger.

```php
// config/hashing.php
'driver' => 'argon2id',           // or 'bcrypt'
'argon' => ['memory' => 65536, 'threads' => 1, 'time' => 4],
'bcrypt' => ['rounds' => 12],
```

Use the `Hash` facade — never `password_hash` directly:

```php
Hash::make($password);                       // hash
Hash::check($input, $user->password);        // verify (constant-time)
Hash::needsRehash($user->password);          // true if cost params changed
```

⚠️ Anti-pattern: `md5(...)`, `sha1(...)`, or `crypt(...)` for passwords. Always `Hash::make()`.

---

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

---

## 13. Dependency security

### 13.1 Composer

```bash
composer audit                           # check for known CVEs
composer audit --format=json
composer outdated --direct               # what's old in your direct deps
composer why-not <pkg> <version>         # explain blocking constraints
```

Run `composer audit` in CI. Block merge on critical/high vulns. Triage medium/low based on exploitability.

### 13.2 npm / pnpm

```bash
npm audit                                # or `pnpm audit`
npm audit fix                            # auto-fix non-breaking
npm audit fix --force                    # may break — review diff
```

### 13.3 Dependabot / Renovate

Enable in `.github/dependabot.yml` or `renovate.json`. Cadence: weekly for non-security, daily for security advisories.

⚠️ Anti-pattern: auto-merging dependency updates without CI gates. Always run full test suite + security scan on the PR.

---

## 14. Secret management

```php
// .env (NEVER commit)
APP_KEY=base64:...
DB_PASSWORD=...
STRIPE_SECRET=sk_live_...

// config/services.php — env() used here, not in app code
'stripe' => ['secret' => env('STRIPE_SECRET')],

// Code — config(), never env()
$key = config('services.stripe.secret');
```

### 14.1 Encryption at rest

```php
// Encrypted cast on a column
class User extends Model
{
    protected $casts = ['ssn' => 'encrypted'];
}

// Symmetric encrypt/decrypt elsewhere
$enc = encrypt($plain);
$plain = decrypt($enc);
```

### 14.2 Production secret stores

| Provider | Approach |
|---|---|
| AWS | Secrets Manager + IAM role; load into env at boot |
| GCP | Secret Manager + Workload Identity |
| Vault (HashiCorp) | Sidecar or boot-time fetch |
| Forge | Environment variables in dashboard |

### 14.3 Secret rotation

- Rotate API keys on a cadence (90 days for high-value)
- Rotate immediately on developer offboarding
- After any leak (commit history, log file): rotate, then audit access logs

⚠️ Anti-pattern: secret committed to git history. Rotation is mandatory — `git filter-branch` does not save you (clones still have the secret).

---

## 15. Audit logging & monitoring

```php
// Detect spatie/laravel-activitylog
// composer show spatie/laravel-activitylog

class Post extends Model
{
    use LogsActivity;

    public function getActivitylogOptions(): LogOptions
    {
        return LogOptions::defaults()
            ->logOnly(['title', 'body', 'published_at'])
            ->logOnlyDirty()
            ->dontSubmitEmptyLogs();
    }
}
```

Without the package, an Observer + dedicated `audit_log` table works. Key requirements:

- **Immutable** — append-only; no UPDATE/DELETE on audit rows
- **Includes actor** — user ID, session ID, IP
- **Includes context** — what changed, before/after
- **Tamper-evident** — chain hashes between rows for high-stakes systems
- **Retention** — keep at least as long as legal/compliance requires (LGPD: 5 years for some categories)

### 15.1 What to log

| Event | Yes/no |
|---|---|
| Login (success/fail) | yes |
| Password change / reset | yes |
| MFA enable/disable | yes |
| Permission change | yes |
| Sensitive data access (PII, financial) | yes |
| Data export | yes |
| Routine read | no — too noisy |

### 15.2 Where to send logs

`config/logging.php` channels stack:

```php
'stack' => [
    'driver' => 'stack',
    'channels' => ['single', 'sentry', 'cloudwatch'],
],
```

Centralized log destination (Sentry, Datadog, CloudWatch, ELK) — never *only* local files in production.

⚠️ **Anti-pattern:** logging request body cru:

```php
Log::info('payment.received', $request->all());   // BAD — leaks card, email, password
```

Always scrub. See `laravel-backend/references/security.md` §7 for scrub helpers.

---

## 16. PHP-specific gotchas

### 16.1 Type juggling

`==` (loose equality) compares with type coercion — exploitable:

```php
"0" == false        // true
"abc" == 0          // true (PHP 7) — fixed in PHP 8
[] == null          // true
```

Always use `===` for comparisons. PHP 8.x mitigates many but not all cases.

### 16.2 Deserialization

The `unserialize` function on user-controlled data executes magic methods (`__wakeup`, `__destruct`). Code execution risk.

```bash
grep -rn 'unserialize(' app/ | grep -v 'safe_unserialize'
```

If used, restrict allowed classes:

```php
unserialize($data, ['allowed_classes' => [SafeClass::class]]);
```

Better: use JSON for serialized payloads when possible.

### 16.3 Dynamic code execution and file inclusion

The `eval` keyword and dynamic `include` / `require` with user input enable direct code execution. Audit:

```bash
grep -rnE '\beval\b|\b(include|require|require_once|include_once)\s*\(\s*\$' app/
```

These should never appear with user input. If found, refactor immediately.

### 16.4 Header injection

User input in headers (CRLF) can split responses:

```php
// BAD
return response('ok')->header('X-User', $request->input('name'));

// GOOD — strip CRLF
return response('ok')->header('X-User', preg_replace('/[\r\n]/', '', $request->input('name')));
```

---

## 17. Compliance overview

Most regulated apps need:

- **LGPD (BR)** / **GDPR (EU)** — consent, data subject rights (access, deletion, portability), retention, breach notification, DPO
- **SOC 2** — control framework: availability, security, processing integrity, confidentiality, privacy
- **PCI-DSS** — when handling card data: tokenization preferred; segregate cardholder environment
- **HIPAA** — when handling US health data: PHI encryption, audit, BAA with subprocessors

For full implementation in Laravel (data-subject request endpoints, retention jobs, encryption strategies, audit log retention, breach response), see `references/compliance.md`.

---

## 18. Anti-patterns — consolidated checklist

Single-page scan list for `security` and `code-review`.

| Smell | Section | Detection |
|---|---|---|
| `APP_DEBUG=true` in production | §6 | `grep APP_DEBUG .env.production` |
| `{!! !!}` in Blade with user input | §4 | `grep -rn '{!!' resources/views/` |
| Frontend raw-HTML escape hatch (React, Vue) with user input | §4 | `grep -rnE 'InnerHTML\|v-html' resources/js/` |
| Routes excluded from CSRF without HMAC verification | §5 | review `bootstrap/app.php` `validateCsrfTokens(except:)` |
| User upload stored on `public` disk | §10 | `grep -rn "store(.*'public'" app/` |
| `===` for HMAC/signature comparison | §12 | grep |
| `md5`/`sha1`/`crypt` used for passwords | §11 | grep |
| `unserialize` on user data without allowlist | §16.2 | grep |
| Dynamic `include`/`require` with `$variable` | §16.3 | grep |
| User input in raw HTTP headers without CRLF strip | §16.4 | review |
| Dep with critical/high CVE on main branch | §13 | `composer audit`, `npm audit` |
| Secret committed to git history | §14 | `git log --all -p \| grep -iE 'password\|secret\|key'` |
| `Log::info($request->all())` | §15.2 | grep |
| Audit log writable (UPDATE/DELETE allowed) | §15 | DB grant review |
| No CSP header | §7 | `curl -I | grep -i content-security-policy` |
| `SESSION_SECURE_COOKIE=false` in prod | §9 | env review |
| Login route without `throttle` middleware | §8 | route inspection |
| Outbound HTTP with user-controlled URL, no allowlist (SSRF) | §1 (A01) | grep |
| Telescope/Pulse/Debugbar visible in prod | §6 | route review + middleware |
| Authorization via `if ($user->role === ...)` | (laravel-backend §13) | grep `->role ==` |

---

## 19. Cross-references

| Topic | Skill / reference |
|---|---|
| OWASP Top 10 — full Laravel walkthrough | `references/laravel_php_security.md` |
| Framework-agnostic security principles | `references/general_security.md` |
| LGPD / GDPR / SOC 2 / PCI / HIPAA implementation | `references/compliance.md` |
| Auth flow (Sanctum, Fortify, MFA, password reset) | `laravel-auth` |
| Backend security touchpoints (mass assignment, FormRequest, raw queries) | `laravel-backend/references/security.md` |
| Authorization patterns (Policy, Gate, multi-tenant, Sanctum tokens) | `laravel-backend/references/authorization_patterns.md` |
| Test scenarios for security regressions | `laravel-qa` |
| Webhook signature verification (HMAC + idempotency) | `laravel-backend/references/api_design_patterns.md` §9 |
