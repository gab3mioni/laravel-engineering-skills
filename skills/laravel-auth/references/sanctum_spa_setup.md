# Sanctum SPA cookie mode — Setup, topology, troubleshooting

End-to-end Sanctum SPA configuration. Loaded when the agent is wiring an Inertia/React/Vue SPA against Laravel auth, debugging "419 Page Expired" or "logged out on every request" symptoms, or moving an app between domain topologies (apex/subdomain/multi-port).

This is the **cookie-based** Sanctum mode, not the API token mode. Tokens are covered in the `laravel-auth` SKILL.md §3.2.

## 1. When to use SPA mode

| Scenario | Use SPA mode? |
|---|---|
| Inertia 2 + Laravel on same registrable domain | **yes** — the default |
| React/Vue SPA + Laravel API on subdomains of same parent (`app.example.com` + `api.example.com`) | **yes** |
| Mobile app (iOS / Android native) consuming the API | **no** — use API tokens |
| Third-party app consuming your API | **no** — use API tokens or Passport |
| SPA hosted on completely different domain (`app.netlify.app` ↔ `api.example.com`) | **no** — cross-site cookies are unreliable; use tokens |
| SPA + API on same origin (port and host) | **yes** — easiest case |

⚠️ The split is **registrable domain**, not "same site". `app.example.com` and `api.example.com` share `example.com` → SPA mode works. `app.example.com` and `api.someoneelse.com` do not → tokens.

## 2. Domain topology decision matrix

| Frontend origin | Backend origin | `SESSION_DOMAIN` | `SANCTUM_STATEFUL_DOMAINS` | `CORS allowed_origins` | Notes |
|---|---|---|---|---|---|
| `localhost:5173` | `localhost:8000` | `localhost` | `localhost:5173,localhost:8000` | `http://localhost:5173` | Standard local dev |
| `127.0.0.1:5173` | `127.0.0.1:8000` | `127.0.0.1` | `127.0.0.1:5173,127.0.0.1:8000` | `http://127.0.0.1:5173` | If using IP — **don't mix with `localhost`** |
| `app.example.com` | `app.example.com` (same origin) | `app.example.com` | `app.example.com` | `https://app.example.com` | Inertia default — simplest |
| `app.example.com` | `api.example.com` | `.example.com` (leading dot) | `app.example.com` | `https://app.example.com` | Cookie scoped to all subdomains |
| `staging.example.com` | `api-staging.example.com` | `.example.com` | `staging.example.com` | `https://staging.example.com` | Same pattern, different prefix |
| `app.example.com` | `api.example.io` | n/a — different registrable domain | n/a | n/a | **Not supported** — switch to tokens |

**Rules:**
- `SANCTUM_STATEFUL_DOMAINS` is the **frontend** origin (host + port, no scheme, no path).
- `SESSION_DOMAIN` is the cookie scope. Cross-subdomain → leading dot (`.example.com`). Same-origin → bare host (`app.example.com`).
- Never mix `localhost` and `127.0.0.1` — browsers treat them as different origins; the cookie scoped to one isn't sent to the other.
- HTTPS in production is mandatory — Sanctum cookies are issued with `Secure` (so HTTP can't read them).

## 3. Step-by-step setup

### 3.1 Install

```bash
composer require laravel/sanctum
php artisan install:api          # Laravel 11+ scaffold (publishes config + creates migrations)
php artisan migrate
```

`install:api` creates:
- `config/sanctum.php`
- `database/migrations/*_create_personal_access_tokens_table.php`
- The `routes/api.php` file (if not present)
- Registers `EnsureFrontendRequestsAreStateful` middleware via `bootstrap/app.php#withMiddleware`

### 3.2 `config/sanctum.php`

```php
return [
    'stateful' => explode(',', env('SANCTUM_STATEFUL_DOMAINS', sprintf(
        '%s%s',
        'localhost,localhost:3000,localhost:5173,127.0.0.1,127.0.0.1:8000,::1',
        Sanctum::currentApplicationUrlWithPort(),
    ))),

    'guard' => ['web'],

    'expiration' => null,                                 // SPA sessions: leave null (uses session cookie lifetime)

    'middleware' => [
        'authenticate_session'    => AuthenticateSession::class,
        'encrypt_cookies'         => EncryptCookies::class,
        'validate_csrf_token'     => ValidateCsrfToken::class,
    ],
];
```

### 3.3 `bootstrap/app.php`

```php
return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(/* ... */)
    ->withMiddleware(function (Middleware $middleware) {
        $middleware->statefulApi();                       // adds EnsureFrontendRequestsAreStateful to 'api' group
    })
    ->withExceptions(/* ... */)
    ->create();
```

`statefulApi()` is what makes Sanctum recognize the SPA. It checks `SANCTUM_STATEFUL_DOMAINS` against the request's `Origin` / `Referer` and, if matched, swaps the request's authentication from token-based to session-based.

### 3.4 `config/cors.php`

```php
return [
    'paths' => [
        'api/*',
        'sanctum/csrf-cookie',
        'login',
        'logout',
        'register',
        'forgot-password',
        'reset-password',
        'email/verification-notification',
        'verify-email/*',
    ],

    'allowed_methods'         => ['*'],
    'allowed_origins'         => [env('FRONTEND_URL', 'http://localhost:5173')],
    'allowed_origins_patterns' => [],
    'allowed_headers'         => ['*'],
    'exposed_headers'         => [],
    'max_age'                 => 0,
    'supports_credentials'    => true,                    // ← MANDATORY for Sanctum SPA
];
```

**Rules:**
- `paths` must include every endpoint the SPA hits, **plus** `sanctum/csrf-cookie`. Most apps want `api/*` + the auth endpoints.
- `allowed_origins` is a strict list. Wildcards (`*`) **do not work** with `supports_credentials: true`.
- `supports_credentials: true` enables `Access-Control-Allow-Credentials: true`. Without it, the browser refuses to send cookies cross-origin.

### 3.5 `.env` (local dev — same domain, different ports)

```env
APP_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173

SESSION_DRIVER=database         # NOT 'array' — it has to persist across requests
SESSION_DOMAIN=localhost
SESSION_SAME_SITE=lax
SESSION_SECURE_COOKIE=false     # HTTP in dev

SANCTUM_STATEFUL_DOMAINS=localhost:5173,localhost:8000

CORS_ALLOWED_ORIGINS=http://localhost:5173
```

### 3.6 `.env` (staging — cross-subdomain)

```env
APP_URL=https://api-staging.example.com
FRONTEND_URL=https://staging.example.com

SESSION_DRIVER=redis
SESSION_DOMAIN=.example.com
SESSION_SAME_SITE=lax
SESSION_SECURE_COOKIE=true      # HTTPS required

SANCTUM_STATEFUL_DOMAINS=staging.example.com

CORS_ALLOWED_ORIGINS=https://staging.example.com
```

### 3.7 `.env` (production)

```env
APP_URL=https://api.example.com
FRONTEND_URL=https://app.example.com

SESSION_DRIVER=redis
SESSION_DOMAIN=.example.com
SESSION_SAME_SITE=lax
SESSION_SECURE_COOKIE=true

SANCTUM_STATEFUL_DOMAINS=app.example.com

CORS_ALLOWED_ORIGINS=https://app.example.com
```

## 4. Client-side flow

### 4.1 With axios (Inertia default)

```ts
// resources/js/bootstrap.ts
import axios from 'axios';

window.axios = axios;
window.axios.defaults.headers.common['X-Requested-With'] = 'XMLHttpRequest';
window.axios.defaults.withCredentials = true;
window.axios.defaults.withXSRFToken = true;
window.axios.defaults.baseURL = import.meta.env.VITE_API_URL || '/';
```

```ts
// On app start (or before first auth-protected call)
await axios.get('/sanctum/csrf-cookie');                  // sets XSRF-TOKEN + laravel_session cookies

// Login
await axios.post('/login', { email, password });          // session is now established

// Subsequent calls — cookie auth works automatically
const { data } = await axios.get('/api/posts');
```

### 4.2 With fetch

```ts
async function csrf() {
  await fetch('/sanctum/csrf-cookie', { credentials: 'include' });
}

function getXsrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

async function login(email: string, password: string) {
  await csrf();
  const res = await fetch('/login', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'X-XSRF-TOKEN': getXsrfToken(),
    },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error('login failed');
}
```

⚠️ With `fetch`, the `XSRF-TOKEN` header is **not** auto-set — you have to read the cookie and forward it. Axios does this for free when `withXSRFToken: true`.

### 4.3 The CSRF cookie endpoint

```
GET /sanctum/csrf-cookie
→ 204 No Content
   Set-Cookie: XSRF-TOKEN=<value>; Path=/; Domain=...; SameSite=lax
   Set-Cookie: laravel_session=<value>; Path=/; Domain=...; HttpOnly; SameSite=lax
```

The XSRF cookie is **not** HttpOnly (intentionally — JS reads it and echoes it in the `X-XSRF-TOKEN` header). The session cookie is HttpOnly.

**You only need to call `/sanctum/csrf-cookie` once per session.** The token rotates on login/logout; clients that re-read the cookie before each write request are robust to that.

## 5. Per-environment troubleshooting matrix

| Symptom | Likely env / config | Fix |
|---|---|---|
| `419 Page Expired` on first POST | XSRF cookie not in request | Call `/sanctum/csrf-cookie` first; ensure `withCredentials: true` and `withXSRFToken: true` (axios) |
| `419` on every POST | XSRF token expired / different per request | `SESSION_DOMAIN` mismatch — cookie set for a domain the API doesn't read |
| Login returns 200 but next request is 401 | Session cookie not sent back | `supports_credentials: true` missing in CORS, or `SESSION_DOMAIN` doesn't cover both subdomains |
| Login works in dev but breaks in staging | Mixing `localhost` + `127.0.0.1`, or HTTP→HTTPS scheme change with `SESSION_SECURE_COOKIE=true` | Standardize on one host; set `SESSION_SECURE_COOKIE` per env |
| `403 Forbidden` from CSRF middleware | Custom POST endpoint not in `paths:` of CORS or excluded from `web` middleware | Add the route to CORS `paths`; ensure it's not in `VerifyCsrfToken::$except` accidentally |
| `Access-Control-Allow-Origin: *` error | Wildcard origin with credentials | Replace `*` with explicit origin in `CORS_ALLOWED_ORIGINS` |
| Cookie set but `document.cookie` empty | Cookie is HttpOnly (only `XSRF-TOKEN` should be visible) | Confirm in DevTools → Application → Cookies; HttpOnly is correct for `laravel_session` |
| 2FA or login flow loops | Session lost between requests | `SESSION_DRIVER=array` in env (use `database` or `redis`) |
| First request after deploy returns 419 | Session cache cleared during deploy | Use Redis sessions; never `php artisan session:clear` while users are active |
| Cross-subdomain works in Chrome, fails in Safari | Safari ITP (Intelligent Tracking Prevention) blocks third-party cookies | Sanctum SPA is **first-party** if same registrable domain — verify subdomain setup; ensure `SameSite=lax` (not `none`) |

## 6. SameSite attribute deep-dive

| Value | Cookie sent on | Use when |
|---|---|---|
| `strict` | Top-level navigation only (no cross-site, no iframe, no XHR from another origin) | High-security context where cross-site requests must never carry the cookie |
| **`lax`** (default) | Top-level navigation + safe cross-site requests (GET) | **Standard for SPA mode** — works for same-site cross-subdomain + first-party flows |
| `none` | Always (requires `Secure`) | Cross-domain cookie sharing — relevant only for token mode, not SPA mode |

**Rule:** for Sanctum SPA mode, `SESSION_SAME_SITE=lax` and `SESSION_SECURE_COOKIE=true` (in any env that's not local HTTP). Don't use `none` for SPA mode — if you need it, you've left SPA territory and want tokens.

## 7. Mixing SPA + tokens in the same app

Common pattern: an Inertia app for first-party users + a token-based API for mobile / partners.

**Configuration is identical.** `auth:sanctum` middleware accepts both:
1. Browser request from a stateful domain → resolves session cookie → uses `web` guard.
2. Request with `Authorization: Bearer <token>` → resolves token → uses Sanctum's token guard.

Both authenticate the same `User` model. The `auth:sanctum` middleware "guesses" based on request shape.

⚠️ **Anti-pattern:** issuing tokens to first-party SPA users alongside session cookies "for flexibility". Doubles the attack surface (XSS now exposes the token). Pick cookies or tokens per consumer.

## 8. Logout and session lifecycle

```php
// Login
$request->session()->regenerate();                        // mandatory — protects against session fixation

// Logout
Auth::guard('web')->logout();
$request->session()->invalidate();
$request->session()->regenerateToken();                   // rotates the CSRF token
```

```ts
// Client side — after a successful logout
import { router } from '@inertiajs/react';
router.flushAll();                                        // clear Inertia cache
router.clearHistory();                                    // clear encrypted history (see laravel-inertia §11)
```

**Rules:**
- Always `regenerate()` after login. Without it, an attacker who knew the session ID before login holds the authenticated session.
- Always `invalidate()` + `regenerateToken()` after logout. Without it, the same cookie is replayable.
- Pair logout with Inertia's history clear (`clearHistory()`) so back-button doesn't expose cached props.

## 9. Session driver choice

| Driver | OK for SPA mode? | Notes |
|---|---|---|
| `array` | **no** | Lives in memory only; lost between requests |
| `cookie` | yes (small data only) | Limited to ~4KB; encrypts payload into cookie |
| `database` | yes | Requires `sessions` table; fine for small/medium traffic |
| `redis` | **recommended** | Default for prod; survives deploy; works for clustered apps |
| `file` | yes (single server only) | Not viable on multi-server clusters |
| `dynamodb` | yes (AWS) | High-throughput, multi-region |

⚠️ Switching drivers invalidates all active sessions. Plan around it (announce maintenance / accept that everyone gets logged out).

## 10. Reverse proxy considerations

When Laravel runs behind nginx, Caddy, Cloudflare, or AWS ALB, Sanctum must trust the proxy headers to compute the correct origin and scheme.

**`bootstrap/app.php` (Laravel 11+):**
```php
->withMiddleware(function (Middleware $middleware) {
    $middleware->trustProxies(at: '*', headers:
        Request::HEADER_X_FORWARDED_FOR |
        Request::HEADER_X_FORWARDED_HOST |
        Request::HEADER_X_FORWARDED_PORT |
        Request::HEADER_X_FORWARDED_PROTO |
        Request::HEADER_X_FORWARDED_AWS_ELB
    );
})
```

Restrict `at: '*'` to the proxy's IP / CIDR in production (otherwise client-spoofed `X-Forwarded-*` headers can lie to your app).

⚠️ **Anti-pattern:** trusting `*` proxies in production behind a non-restricted load balancer. Lets a malicious client claim any `Host` / IP.

## 11. End-to-end smoke test

```bash
# 1. Get CSRF cookie
curl -i -c cookies.txt http://localhost:8000/sanctum/csrf-cookie

# 2. Extract XSRF token from cookies.txt
XSRF=$(grep -i XSRF-TOKEN cookies.txt | awk '{print $7}' | sed 's/%3D/=/g')

# 3. Login
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-XSRF-TOKEN: $XSRF" \
  -H "Origin: http://localhost:5173" \
  -X POST http://localhost:8000/login \
  -d '{"email":"test@example.com","password":"secret"}'

# 4. Authenticated request
curl -i -b cookies.txt \
  -H "Origin: http://localhost:5173" \
  http://localhost:8000/api/user
```

If step 4 returns 200 with the user data, SPA mode is working.

## 12. Cross-references

- `laravel-auth` SKILL.md §3 — Sanctum overview and decision tree
- `laravel-auth` §3.2 — API token mode (the other Sanctum mode)
- `laravel-auth` §13 — common pitfalls table
- `laravel-frontend` §6 — Ziggy and route filtering for the SPA
- `laravel-inertia` §4 — sharing `auth.user` via `HandleInertiaRequests`
- `laravel-inertia` §11 — `clearHistory()` on logout
- `laravel-security` — broader CSP/headers context (this doc focuses on Sanctum mechanics)
