# OWASP Top 10 — Laravel & PHP

Walkthrough of OWASP Top 10:2025 categories applied to Laravel 12 / PHP 8.3+. Loaded when auditing security posture or investigating a specific OWASP category.

## A01 — Broken access control

The most common high-impact category. Since 2025 it also absorbs SSRF (formerly its own category). Manifestations in Laravel:

### IDOR (Insecure Direct Object Reference)

```php
// BAD — any authenticated user can update any post
public function update(Request $request, Post $post)
{
    $post->update($request->all());
    return $post;
}

// GOOD — Policy gates ownership
public function update(UpdatePostRequest $request, Post $post)
{
    $this->authorize('update', $post);
    $post->update($request->validated());
    return $post;
}
```

Route-model binding loads the model by route param — but **does not authorize**. Pair with Policy.

### Missing authorization on admin routes

```php
// BAD
Route::middleware('auth')->group(function () {
    Route::get('/admin', AdminController::class);   // any auth'd user is admin?
});

// GOOD
Route::middleware(['auth', 'can:access-admin'])->group(function () {
    Route::get('/admin', AdminController::class);
});
```

### Cross-tenant access

In multi-tenant apps, every query and Policy must filter by tenant. See `laravel-backend/references/authorization_patterns.md` §5 for defense-in-depth (global scope + Policy).

### Token abilities (Sanctum)

```php
// BAD — token can do anything its user can
Route::post('/api/posts', [...])->middleware('auth:sanctum');

// GOOD — also check token has the ability
Route::post('/api/posts', [...])->middleware(['auth:sanctum', 'abilities:posts:write']);
```

### SSRF (folded into A01 in 2025)

Server-Side Request Forgery — the server fetches a URL the user controls, reaching hosts the user couldn't:

```php
// BAD — server fetches whatever URL the user provides
public function fetchUrl(Request $request)
{
    return Http::get($request->input('url'));
}

// GOOD — allowlist of hosts
private array $allowedHosts = ['api.example.com', 'cdn.partner.com'];

public function fetchUrl(Request $request)
{
    $url = $request->input('url');
    $host = parse_url($url, PHP_URL_HOST);

    abort_unless(in_array($host, $this->allowedHosts, true), 422);

    return Http::timeout(5)->get($url);
}
```

Additional defenses:
- Resolve hostname before request; reject if it resolves to private IP (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8)
- Disable HTTP redirects (`->withoutRedirecting()`) or follow only to allowed hosts
- Set tight timeouts

⚠️ Cloud metadata services (`169.254.169.254`) are common SSRF targets — leak instance credentials. Always block private IP ranges.

### Audit grep

```bash
# Routes with auth but no policy/can middleware
grep -rn 'middleware.*auth' routes/ | grep -v 'can:\|abilities:'
```

---

## A02 — Security misconfiguration

### Production hardening checklist

| Setting | Required |
|---|---|
| `APP_ENV=production` | yes |
| `APP_DEBUG=false` | yes — prevents stack trace leaks |
| `APP_KEY` set | yes |
| `php artisan config:cache` | yes |
| `php artisan route:cache` | yes |
| `.env` permissions: 600, web user owner | yes |
| Telescope/Pulse/Debugbar disabled or auth-gated | yes |
| Default web server pages removed | yes |
| Directory listing disabled | yes |

### CSP (Content Security Policy)

A well-tuned CSP contains XSS even when output encoding fails. Recommended starting baseline:

```text
default-src 'self';
script-src 'self' https://cdn.example.com;
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
connect-src 'self' https://api.example.com;
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
```

Tighten over time:
1. Start with `'unsafe-inline'` for styles to avoid breaking
2. Use Report-Only mode (`Content-Security-Policy-Report-Only`) to find violations
3. Remove `'unsafe-inline'` once violations are fixed (use nonces/hashes)
4. Move scripts off CDN to your own domain when possible

For Inertia SPAs, CSP is challenging due to inline scripts in the initial page render — use nonces.

### Other headers

See `laravel-security` SKILL.md §7 for the baseline header set (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy).

---

## A03 — Software supply chain failures

Expands the old "vulnerable & outdated components" category: supply chain covers lockfile integrity, typosquatted packages, and CI-side dependencies — not just outdated packages with CVEs.

### Detection

```bash
composer audit                    # PHP deps with known CVEs
composer outdated --direct        # what's old in your direct deps
npm audit                         # JS deps
npm audit fix                     # auto-fix non-breaking
```

Run `composer audit` and `npm audit` in CI. Block merge on critical/high vulns.

### Triage

| Severity | Action |
|---|---|
| Critical / High | Patch immediately or accept risk with mitigation (e.g., not using the vulnerable code path) |
| Medium | Patch within sprint; document if deferred |
| Low | Patch within next minor cycle |

### Automation

- **Dependabot** (GitHub) — automated PRs for security advisories
- **Renovate** — more configurable; supports composer + npm + docker
- **Snyk / Socket** — third-party scanners; some CVEs they catch before official disclosure

⚠️ Anti-pattern: auto-merging dependency PRs without CI gates. Always run full test suite + audit on the PR.

---

## A04 — Cryptographic failures

### Password storage

Always `Hash::make()` and `Hash::check()` — never `md5`, `sha1`, raw `password_hash`. Driver in `config/hashing.php`: `argon2id` (preferred) or `bcrypt`.

```php
$user->password = Hash::make($plain);
if (Hash::check($plain, $user->password)) { /* ... */ }
```

### Encryption

Laravel ships `encrypt()` / `decrypt()` (AES-256-CBC with HMAC). Use it; don't roll your own.

```php
$encrypted = encrypt($sensitive);
$plain     = decrypt($encrypted);
```

For column-level encryption:

```php
class User extends Model
{
    protected $casts = ['ssn' => 'encrypted'];
}
```

### TLS

- Enforce HTTPS in production via `URL::forceScheme('https')` in `AppServiceProvider::boot()` when behind a load balancer terminating TLS
- Set HSTS header (see `laravel-security` SKILL.md §7)
- TLS 1.2 minimum (1.3 preferred); disable old ciphers at the LB or web server

### App key

`APP_KEY` (32 random bytes, base64) is the master key for sessions, encrypt/decrypt, signed URLs. Generated by `php artisan key:generate`.

⚠️ Anti-patterns:
- Sharing `APP_KEY` across environments — leak in dev compromises prod
- Storing `APP_KEY` in source — rotate immediately if leaked
- Rotating `APP_KEY` without re-encrypting existing data — encrypted fields become unreadable

---

## A05 — Injection

### SQL injection

Eloquent + Query Builder are safe by default (parameterized). The risk is in raw queries with concatenation:

```php
// BAD
DB::raw("title = '{$title}'")
DB::select("SELECT * FROM x WHERE id = {$id}")
->whereRaw("name = '{$name}'")
->orderByRaw("col_{$direction}")     // column-name injection

// GOOD
DB::select('SELECT * FROM x WHERE id = ?', [$id])
->whereRaw('name = ?', [$name])
->orderBy(in_array($column, $allowed) ? $column : 'created_at')   // allowlist for column names
```

### Command injection

Functions that spawn shells (`passthru`, `shell_exec`, `system`, `proc_open`, and the lower-case shell-exec family) interpolated with user input enable command injection. Mitigations, in order of preference:

1. **Avoid the shell entirely.** Use Symfony's Process facade with array args — no shell parsing happens:
   ```php
   use Symfony\Component\Process\Process;
   $process = new Process(['convert', $file, 'output.png']);
   $process->run();
   ```
2. **If shell is unavoidable**, escape every interpolated value with `escapeshellarg()` and `escapeshellcmd()`.
3. **In production `php.ini`**, disable functions you don't need:
   ```ini
   disable_functions = passthru,shell_exec,system,proc_open,popen
   ```

### XSS in Inertia / SPA frontends

Laravel apps with React or Vue via Inertia have a frontend XSS surface — the framework-level "raw HTML" escape hatches (the React prop ending in `InnerHTML`, the Vue `v-html` directive). Audit:

```bash
grep -rnE 'InnerHTML|v-html' resources/js/
```

For each match: confirm the value is trusted (constant, server-generated and sanitized) or sanitized via DOMPurify before injection.

### LDAP / NoSQL injection

Rare in Laravel; relevant when integrating with LDAP servers or NoSQL stores. Always use parameterized queries from the respective library.

### Header injection

```php
// BAD
return response('ok')->header('X-Custom', $request->input('value'));

// GOOD — strip CRLF
return response('ok')->header('X-Custom', preg_replace('/[\r\n]/', '', $request->input('value')));
```

CRLF in user input can split HTTP responses, enabling cache poisoning or session fixation.

---

## A06 — Insecure design

Architectural failures — covered at design review, not by code grep.

### Examples

- Password reset flow with predictable tokens (sequential, time-based) instead of `Str::random(80)` cryptographic
- Webhook endpoint without idempotency key (replays cause duplicate side effects)
- Background job that processes whatever the queue says without re-validating preconditions
- API that exposes internal IDs (auto-increment sequence guesses adjacent records)
- Rate limit on login but not on password-reset trigger (account enumeration via timing)

### Mitigation: threat modeling at design time

Run STRIDE on the feature before coding. See `general_security.md` §4.

---

## A07 — Authentication failures

(Auth flow details live in `laravel-auth`.)

### Brute force

- Rate limit login by IP **and** by email/username (covers single-account targeting)
- After N failures, require captcha or email verification
- Log all auth failures with IP and email (for incident response)

### Session fixation

Always regenerate session ID on login (Fortify / Breeze do this automatically):

```php
$request->session()->regenerate();
```

### Credential stuffing

Attackers reuse leaks from other breaches. Mitigation:
- MFA (the strongest single control)
- HaveIBeenPwned check on password create / reset
- Anomaly detection (login from new country/device)

### Password reset

- Token: `Str::random(80)` — cryptographic
- Single-use — invalidate after first redemption
- Short lifetime — 1 hour typical
- Tied to user — token can't be redeemed by a different user

### MFA

TOTP (Google Authenticator) is the baseline. SMS is weak (SIM swap) but better than nothing. WebAuthn is the strongest.

Recovery codes: generate 10 single-use codes at MFA enable. Store hashed.

---

## A08 — Software or data integrity failures

### Deserialization

`unserialize()` on user-controlled data executes magic methods (`__wakeup`, `__destruct`). Code execution risk.

```bash
grep -rn 'unserialize(' app/
```

If used, restrict allowed classes:

```php
unserialize($data, ['allowed_classes' => [SafeClass::class]]);
```

Better: use JSON for serialized payloads.

### Supply chain

(Dependency CVE detection and triage live in A03.)

- Pin dependency versions in `composer.lock` and `package-lock.json` — commit them
- Verify package authenticity (Composer checks PGP signatures when available)
- Review new dependencies before adding (license, maintainer reputation, recent activity)
- Use a private Composer repo (Packagist mirror) for sensitive projects

### CI integrity

- CI secrets scoped to environments
- CI cannot push directly to main without review
- Build artifacts signed where possible

---

## A09 — Security logging & alerting failures

(See `laravel-security` SKILL.md §15 for what to log and how.)

### Failure modes

- **Too little**: can't investigate incidents; compliance gap
- **Too much**: PII/credentials in logs; cost; signal lost in noise

### Right balance

- Log all auth events (login, logout, MFA, password change/reset)
- Log all authorization failures (403)
- Log permission changes
- Log access to sensitive data categories (not every read)
- Scrub request bodies — explicit allowlist

### Centralization

Production logs go to a central destination (Sentry, Datadog, CloudWatch, ELK). Never *only* local files — disk fills, lost on instance termination, no cross-correlation.

### Alerting

Trigger on:
- Auth failure spike
- 5xx error rate change
- Anomalous queries (large data exports)
- New CVE in a dependency

---

## A10 — Mishandling of exceptional conditions

New category in 2025. Errors handled badly either leak internals or fail open.

### Debug mode leaks

`APP_DEBUG=true` in production renders full stack traces — file paths, env values, executed queries. Always `false` in prod (see A02 checklist).

### Fail-open exception handling

```php
// BAD — authorization exception swallowed; execution continues
try {
    $this->authorize('update', $post);
} catch (Throwable $e) {
    Log::warning('authorize failed');
}
$post->update($request->validated());

// GOOD — let AuthorizationException propagate (403), or abort explicitly
$this->authorize('update', $post);
$post->update($request->validated());
```

Any `catch` that continues past a security check fails open. Default is fail-closed: rethrow, `abort()`, or return an error response.

### Exception detail in JSON APIs

Never return `$e->getMessage()` to clients — internal messages leak table names, class names, business rules. Normalize rendering in `bootstrap/app.php`:

```php
->withExceptions(function (Exceptions $exceptions) {
    $exceptions->render(function (Throwable $e, Request $request) {
        if ($request->is('api/*') && ! config('app.debug')) {
            return response()->json(['message' => 'Server error'], 500);
        }
    });
})
```

Laravel converts `ModelNotFoundException` to 404 automatically — but a manual catch that echoes the exception leaks the model class name. Prefer `abort(404)` over exposing exception internals.

### Audit grep

```bash
# Exception internals surfaced to clients
grep -rn 'getMessage()' app/Http/
```

---

## PHP-specific gotchas

### Type juggling

`==` (loose equality) compares with type coercion. PHP 8 mitigated some cases but not all:

```php
"0" == false        // true
"abc" == 0          // true (PHP 7) — fixed in PHP 8
[] == null          // true
"1abc" == 1         // true (PHP 7) — fixed in PHP 8
```

Always use `===` for comparisons. Especially:
- Token comparison
- Status checks
- Branching on user-controlled values

### Dynamic code execution

The `eval` keyword and dynamic `include` / `require` / `include_once` / `require_once` with user input enable direct code execution.

```bash
grep -rnE '\beval\b|\b(include|require|require_once|include_once)\s*\(\s*\$' app/
```

These should never appear with user input. Refactor immediately.

### Path traversal

```php
// BAD
return file_get_contents($request->input('path'));

// BAD even with check
return file_get_contents("uploads/" . $request->input('name'));   // ../../etc/passwd

// GOOD — basename and disk
$name = basename($request->input('name'));
return Storage::disk('uploads')->get($name);
```

`Storage::disk()` confines to the disk's root.

### Disabled functions

In `php.ini` for production, disable functions that aren't needed:

```ini
disable_functions = passthru,shell_exec,system,proc_open,popen
```

If the app needs none of them, disabling closes off whole classes of issues.

---

## Audit grep checklist

```bash
# Mass assignment risk
grep -rn '\$request->all()' app/

# Raw SQL with interpolation
grep -rnE 'DB::raw\(.*\$|whereRaw\(.*\$|orderByRaw\(.*\$|selectRaw\(.*\$' app/

# Blade XSS surface
grep -rn '{!!' resources/views/

# Inertia / SPA XSS surface
grep -rnE 'InnerHTML|v-html' resources/js/

# Deserialization
grep -rn 'unserialize(' app/

# Dynamic code execution
grep -rnE '\beval\b|\b(include|require|require_once|include_once)\s*\(\s*\$' app/

# Weak password hashing
grep -rnE 'md5|sha1|crypt' app/ | grep -i 'password'

# Timing-unsafe signature compare
grep -rnE '===' app/ | grep -i 'signature\|token'

# Public disk for uploads
grep -rn "store.*'public'" app/

# env() outside config
grep -rn 'env(' app/ routes/ database/

# APP_DEBUG in production env files
grep APP_DEBUG .env.example .env.production 2>/dev/null

# Exception internals surfaced to clients
grep -rn 'getMessage()' app/Http/
```

Run as part of pre-release security review or as a CI step.
