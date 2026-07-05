---
name: laravel-auth
description: Authentication and authorization in Laravel 12 — Sanctum (SPA cookie mode + API tokens with abilities), Fortify (headless 2FA, password reset, email verification), Breeze (starter kit), Passport (legacy/full OAuth2), session vs token guards, auth/auth:sanctum/verified/password.confirm middleware, route protection, password hashing and rehash, login throttling, remember-me, multi-guard apps, Policies and Gates, authorizing in jobs and console. Consumed by the security, backend, and code-review agents.
---

# Laravel Auth — Authentication & authorization

Identity and access for Laravel 12. Covers **who you are** (authentication: Sanctum, Fortify, Breeze, sessions, tokens) and **what you can do** (authorization: Policies, Gates, middleware). Stack-neutral on the frontend — examples that mention Inertia/SPA delegate UI specifics to `laravel-react`/`laravel-vue`.

## When to use this skill

- Choosing between Sanctum SPA mode, Sanctum tokens, Fortify, Breeze, or Passport
- Wiring a new auth flow (login, register, password reset, email verification, 2FA)
- Designing token abilities/scopes for an API
- Protecting routes with the right middleware (`auth`, `auth:sanctum`, `verified`, `password.confirm`, `throttle`)
- Writing or reviewing Policies and Gates
- Auditing auth-related code in PRs
- Debugging "logged out on first request", CSRF/CORS issues, stale Sanctum cookies

## When NOT to use

| Topic | Use instead |
|---|---|
| OWASP Top 10, password hashing internals, dependency CVEs, rate-limit headers, 2FA threat model | `laravel-security` |
| Eloquent for `User`, FormRequests for login, controller patterns | `laravel-backend` |
| Inertia shared `auth.user` prop, encryptHistory on logout | `laravel-inertia` |
| Vite/Ziggy filtering of auth-protected route names | `laravel-frontend` |
| Pest auth helpers (`actingAs`, `Sanctum::actingAs`) | `laravel-qa` |

## Stack assumptions

- Laravel 12, PHP 8.3+
- `App\Models\User` extends `Authenticatable`
- Default `web` (session) and `api` guards in `config/auth.php`
- **Detection-based:** the agent runs `composer show laravel/sanctum laravel/fortify laravel/breeze laravel/passport --quiet 2>/dev/null` to discover which auth packages are installed before recommending a flow.

---

## 1. The decision tree

| Need | Use |
|---|---|
| Server-rendered Blade app, traditional login form | Sessions (built-in) — optionally Breeze for scaffolding |
| Inertia / Vue / React SPA on the **same domain or apex** | **Sanctum SPA mode** (cookie auth) |
| Mobile app or 3rd-party API client | **Sanctum API tokens** with abilities |
| Headless flows (no UI scaffolding) — 2FA, password reset, email verification | **Fortify** (often combined with Sanctum SPA) |
| Full OAuth2 server (you issue tokens to other apps' users) | **Passport** |
| Both an SPA and a public API on the same app | **Sanctum** in both modes (one config) |

⚠️ **Anti-pattern:** Passport when Sanctum suffices. Passport implements full OAuth2 — appropriate when you're an **identity provider** to third parties, overkill for first-party apps.

⚠️ **Anti-pattern:** Sanctum tokens for a same-domain SPA when SPA cookie mode is available. Tokens in localStorage are XSS-exposed; cookies are HttpOnly.

---

## 2. The session guard (built-in)

Default for any traditional web flow. No extra package.

```php
// Login (manual)
if (Auth::attempt(['email' => $email, 'password' => $password], remember: $remember)) {
    $request->session()->regenerate();           // protect against session fixation
    return redirect()->intended('/dashboard');
}

return back()->withErrors(['email' => 'Invalid credentials.']);

// Logout
Auth::logout();
$request->session()->invalidate();
$request->session()->regenerateToken();
return redirect('/');
```

**Rules:**
- Always `session()->regenerate()` after login and `invalidate()` + `regenerateToken()` after logout. Without these, session fixation and CSRF token reuse are real risks.
- Use the `web` guard (default) — no `auth('api')` for browser flows.
- `Auth::user()`, `auth()->user()`, `$request->user()` are equivalent inside the request lifecycle.

### 2.1 Login throttling

Use the trait or the `throttle` middleware.

```php
// app/Http/Controllers/Auth/LoginController.php
use Illuminate\Foundation\Auth\ThrottlesLogins;

class LoginController extends Controller
{
    use ThrottlesLogins;

    protected int $maxAttempts = 5;
    protected int $decayMinutes = 1;
}
```

Or per-route: `Route::post('/login', ...)->middleware('throttle:5,1');`

⚠️ **Anti-pattern:** custom login endpoint with no throttle. Brute-force trivially exploitable. See `laravel-security` for credential-stuffing detection patterns.

---

## 3. Sanctum

Single package, two distinct modes. Pick **one** per consumer; the same Laravel app can serve both.

```bash
composer require laravel/sanctum
php artisan install:api          # Laravel 11+ scaffold (publishes config + migrations)
php artisan migrate
```

### 3.1 SPA cookie mode (the Inertia / first-party SPA default)

The SPA and the API live on the same registrable domain (`app.example.com` + `api.example.com` work; cross-site does not). Authentication uses Laravel's session cookie + CSRF — no tokens involved.

**Four config touch points:**

```php
// config/sanctum.php
'stateful' => explode(',', env('SANCTUM_STATEFUL_DOMAINS', 'localhost:5173,localhost:8000,127.0.0.1')),
'guard'    => ['web'],
```

```php
// bootstrap/app.php
->withMiddleware(fn (Middleware $m) => $m->statefulApi())
```

```php
// config/cors.php
'paths'                => ['api/*', 'sanctum/csrf-cookie', 'login', 'logout'],
'allowed_origins'      => [env('FRONTEND_URL', 'http://localhost:5173')],
'supports_credentials' => true,
```

```env
# .env (cross-subdomain prod example)
SESSION_DOMAIN=.example.com
SESSION_SAME_SITE=lax
SESSION_SECURE_COOKIE=true
SANCTUM_STATEFUL_DOMAINS=app.example.com
```

**Client flow:**
```ts
await axios.get('/sanctum/csrf-cookie');     // once per session — sets XSRF-TOKEN + laravel_session
await axios.post('/login', { email, password });
await axios.get('/api/posts');                // authenticated by the session cookie
```

**The four rules that catch most mistakes:**
1. `SANCTUM_STATEFUL_DOMAINS` is the **frontend** origin (host + port, no scheme).
2. `SESSION_DOMAIN` is `.example.com` (leading dot) for cross-subdomain; bare host for same-origin.
3. `supports_credentials: true` in CORS **and** `withCredentials: true` / `withXSRFToken: true` on the client (axios sets both when configured; `fetch` requires manual `X-XSRF-TOKEN` header).
4. Never mix `localhost` and `127.0.0.1` — different origins to the browser.

For the full domain-topology decision matrix (apex/subdomain/multi-port), per-environment `.env` templates (local/staging/prod), `SameSite` deep-dive, reverse-proxy considerations, the troubleshooting matrix for "419 Page Expired" and "logged out on every request" symptoms, and an end-to-end curl smoke test, see [`references/sanctum_spa_setup.md`](references/sanctum_spa_setup.md).

⚠️ **Anti-pattern:** mixing `auth:sanctum` middleware with token logins for an SPA on the same domain. Stick to cookies for SPAs; tokens add XSS surface.

### 3.2 API token mode

For mobile clients, CLI tools, third-party integrations.

```php
// Issue a token
$token = $user->createToken('mobile-app', ['posts:read', 'posts:write'])->plainTextToken;
return ['token' => $token];

// Protect routes
Route::middleware('auth:sanctum')->get('/api/posts', PostController::class);

// Check abilities
if ($request->user()->tokenCan('posts:write')) { /* ... */ }

// Or as middleware
Route::middleware(['auth:sanctum', 'ability:posts:write'])
    ->post('/api/posts', PostController::class);
```

**Rules:**
- Plain-text token is returned **once**. Store the hash (`personal_access_tokens.token`) only. Stand by `tokenable_id` + name + last_used_at for audit.
- Abilities are app-defined strings. Define a canonical list in a Service or enum and reuse across `createToken`, middleware, and policies.
- Revoke on logout: `$request->user()->currentAccessToken()->delete()`.
- Rotate aggressively: short-lived tokens + refresh, or per-device tokens revoked from the user's settings page.

For per-token expiration, last-used tracking, transferring abilities to Policies, and Sanctum + Octane gotchas, see **`laravel-security`**.

---

## 4. Fortify

Headless implementation of the **flows** Breeze scaffolds with a UI: registration, login, password reset, email verification, two-factor authentication, profile updates, password confirmation. **You build the UI.** Fortify exposes routes and event hooks.

```bash
composer require laravel/fortify
php artisan vendor:publish --provider="Laravel\Fortify\FortifyServiceProvider"
php artisan migrate
```

**Config (`config/fortify.php`) — feature toggles:**
```php
'features' => [
    Features::registration(),
    Features::resetPasswords(),
    Features::emailVerification(),
    Features::updateProfileInformation(),
    Features::updatePasswords(),
    Features::twoFactorAuthentication(['confirm' => true, 'confirmPassword' => true]),
],
```

**Customize what each flow does — bind contracts in `FortifyServiceProvider`:**
```php
Fortify::createUsersUsing(CreateNewUser::class);
Fortify::resetUserPasswordsUsing(ResetUserPassword::class);
Fortify::loginView(fn () => Inertia::render('Auth/Login'));
```

**Fortify pairs with Sanctum SPA mode out of the box** — login posts to `/login` (Fortify), session is established, future requests use the cookie.

**Rules:**
- Fortify owns the **routes**; you own the **views/components** (Inertia Pages, Blade, etc.).
- Hook business rules via `Fortify::createUsersUsing(...)` etc. — don't subclass controllers.
- ⚠️ **Anti-pattern:** writing your own password reset endpoint when Fortify is installed. Use Fortify; it handles token expiry, single-use, throttle.

### 4.1 Two-factor authentication

```php
// Enable for current user
$user->forceFill([
    'two_factor_secret'           => encrypt(app(TwoFactorAuthenticationProvider::class)->generateSecretKey()),
    'two_factor_recovery_codes'   => encrypt(json_encode(Collection::times(8, fn () => RecoveryCode::generate()))),
])->save();

// Confirm
POST /user/confirmed-two-factor-authentication { code: '123456' }
```

Recovery codes are single-use; regenerate after any used. Threat-model details (TOTP drift, brute-force on codes) live in `laravel-security`.

---

## 5. Breeze

Starter kit. Generates auth controllers, Blade/Inertia/Vue/React pages, and routes. Designed to be **read, then modified or replaced** — not a runtime dependency.

```bash
composer require laravel/breeze --dev
php artisan breeze:install react        # or vue, blade, api
php artisan migrate
npm install && npm run build
```

**When to use:**
- Greenfield app where you want a working login screen in 5 minutes.
- Reference implementation when wiring Sanctum SPA + Fortify-style flows by hand.

**When not to use:**
- Existing app with a custom auth UI — Breeze will overwrite views.
- Stripped-down API (use `breeze:install api` if you must, but consider Sanctum tokens directly).

---

## 6. Passport

Full OAuth2 server. Issues tokens to **third-party** clients via standard grant types (authorization code, client credentials, password — deprecated upstream).

**Use only when** you are an identity provider to other apps. For first-party SPAs, Sanctum SPA mode is the right answer.

Install: `composer require laravel/passport && php artisan passport:install`. Beyond that, Passport's surface area is too large for this skill — defer to the official docs.

---

## 7. Middleware

| Middleware | Purpose |
|---|---|
| `auth` | Requires authenticated user (default guard) — redirects to `login` route on web, returns 401 on JSON |
| `auth:sanctum` | Sanctum-specific — checks SPA cookie OR `Authorization: Bearer <token>` |
| `auth:web,api` | Multi-guard — first guard that authenticates wins |
| `auth.session` | Logout other devices when password changes (requires `Authenticate Session` table) |
| `verified` | Requires `email_verified_at` is not null |
| `password.confirm` | Forces re-entry of current password before destructive action |
| `throttle:60,1` | 60 requests / 1 minute per user (or IP if guest) |
| `signed` | Signed URL middleware (used by Fortify for email verification links) |
| `ability:<ability>` | Sanctum token must have the listed ability |
| `abilities:<a>,<b>` | Sanctum token must have **all** listed abilities |

```php
Route::middleware(['auth:sanctum', 'verified'])->group(function () {
    Route::get('/dashboard', DashboardController::class);
    Route::middleware('password.confirm')
        ->delete('/account', AccountController::class);
});
```

⚠️ **Anti-pattern:** destructive endpoints (delete account, change email, rotate API token) without `password.confirm`. Lets a hijacked session do permanent damage.

---

## 8. Authorization — Policies & Gates

The `laravel-backend` skill (§13) covers the basics: defining a Policy, calling `$this->authorize()`, registering Gates, route middleware `can:`. **All of that applies.** This skill adds the auth-adjacent angles.

### 8.1 Authorization in jobs / console

`auth()->user()` returns `null` outside an HTTP request. Pass the actor explicitly:

```php
final class PublishPost implements ShouldQueue
{
    public function __construct(public Post $post, public User $actor) {}

    public function handle(): void
    {
        Gate::forUser($this->actor)->authorize('publish', $this->post);
        $this->post->update(['published_at' => now()]);
    }
}

PublishPost::dispatch($post, auth()->user());
```

`Gate::forUser($user)->...` is the canonical way to authorize against a non-current user.

### 8.2 Token abilities vs Policies

- **Abilities** (Sanctum) gate **what an API client can do** — coarse, set at token creation.
- **Policies** gate **whether this user can act on this resource** — fine, evaluated per call.

Combine both: `Route::middleware(['auth:sanctum', 'ability:posts:write'])` covers the token; the controller still calls `$this->authorize('update', $post)` for the per-resource check.

⚠️ **Anti-pattern:** treating token abilities as authorization. They prove the *client* asked for the capability — they do not prove the *user* owns the resource.

### 8.3 Multi-tenant authorization

Combine a global scope (tenant_id) with Policies as defense in depth. Pattern lives in **`references/authorization_patterns.md`** (multi-tenant section).

For broader Policy composition, `Gate::before`/`after`, super-admin escape hatches, Spatie Permission integration, see the same reference doc.

---

## 9. Password hashing & rehash

Laravel uses bcrypt by default (`config/hashing.php`). Argon2id is available; switch via `'driver' => 'argon2id'`.

```php
Hash::make($plain);                            // hash
Hash::check($plain, $user->password);          // verify
Hash::needsRehash($user->password);            // returns true if cost or algorithm changed
```

**Rules:**
- After raising bcrypt rounds or switching algorithms, rehash on next successful login:
  ```php
  if (Hash::needsRehash($user->password)) {
      $user->update(['password' => Hash::make($plain)]);
  }
  ```
- Never compare passwords with `==`. Always `Hash::check`.
- ⚠️ **Anti-pattern:** `md5($password)` or `sha1($password)` anywhere. Even for "non-sensitive" tokens — a leak teaches users you don't take crypto seriously.

For algorithm trade-offs (bcrypt vs argon2id, cost calibration, timing attacks), see `laravel-security`.

---

## 10. Email verification

```php
// User must implement MustVerifyEmail
class User extends Authenticatable implements MustVerifyEmail
{
    use Notifiable;
}

// Routes (Fortify or Breeze provides these by default)
Route::middleware(['auth', 'verified'])->get('/dashboard', ...);

// Resend
$request->user()->sendEmailVerificationNotification();

// Manually mark as verified (e.g. when admin verifies on behalf)
$user->markEmailAsVerified();
```

**Rules:**
- The `verified` middleware blocks unverified users. Pair with a "Verify your email" page on the unverified path.
- Verification links are signed (`signed` middleware) and have a TTL (`config/auth.php#verification.expire`, default 60 minutes).
- ⚠️ **Anti-pattern:** treating an unverified email as authenticated for important actions. `verified` middleware on every meaningful route, not just `/dashboard`.

---

## 11. Password reset

Built-in via `Password::sendResetLink()` and `Password::reset()`. Fortify and Breeze wire the views. The token is stored hashed in `password_reset_tokens` and has a TTL.

```php
// Send link
Password::sendResetLink(['email' => $email]);

// Reset
$status = Password::reset(
    $request->only('email', 'password', 'password_confirmation', 'token'),
    function (User $user, string $password) {
        $user->forceFill(['password' => Hash::make($password)])->save();
        event(new PasswordReset($user));
    }
);
```

**Rules:**
- Throttle reset-link requests (`throttle:6,1` or stricter). Prevents email-bombing a known account.
- Invalidate other sessions after a reset: pair `auth.session` middleware with the `Authenticate Session` table.

---

## 12. Multi-guard apps

Two distinct user types (e.g. `User` and `Admin`) with separate tables and login flows.

```php
// config/auth.php
'guards' => [
    'web'   => ['driver' => 'session', 'provider' => 'users'],
    'admin' => ['driver' => 'session', 'provider' => 'admins'],
],
'providers' => [
    'users'  => ['driver' => 'eloquent', 'model' => App\Models\User::class],
    'admins' => ['driver' => 'eloquent', 'model' => App\Models\Admin::class],
],

// Route protection
Route::middleware('auth:admin')->prefix('admin')->group(...);

// Check
if (Auth::guard('admin')->check()) { /* ... */ }
```

⚠️ **Anti-pattern:** modeling "admin" as a flag on the same `User` model and **also** adding a separate guard. Pick one. A flag-on-User with Policies is simpler; a separate guard is justified only when admins truly are a different domain entity (different schema, different login UI, different session lifetime).

---

## 13. Common pitfalls

| Symptom | Likely cause |
|---|---|
| "419 Page Expired" right after login (SPA) | XSRF cookie not sent — missing `withCredentials` or wrong CORS / SANCTUM_STATEFUL_DOMAINS |
| Logged out on every request (SPA) | `SESSION_DOMAIN` doesn't cover both subdomains — set to `.example.com` |
| `auth()->user()` is null in queued job | No HTTP context — pass actor explicitly (§8.1) |
| 2FA challenge loop | Session lost between login + challenge — check `SESSION_DRIVER` (don't use `array` in prod) |
| `Hash::needsRehash` always true | Different algorithm/cost between hash creation and check — verify `config/hashing.php` |
| Token-protected route returns 401 with valid token | Token revoked, expired, or `ability:` middleware mismatch — log `currentAccessToken()` |

---

## 14. Anti-patterns — consolidated

| Smell | Section | Detection |
|---|---|---|
| Passport for first-party SPA | §1 | `composer show laravel/passport` + Inertia/SPA app |
| Sanctum tokens for same-domain SPA | §1, §3.1 | tokens stored in localStorage |
| Custom login endpoint with no throttle | §2.1 | grep `Route::post('/login'` without `->middleware('throttle')` |
| `Auth::login()` without `session()->regenerate()` | §2 | review login controllers |
| Custom password reset when Fortify is installed | §4 | composer + grep `Password::reset` outside Fortify |
| Destructive route without `password.confirm` | §7 | review `DELETE` routes |
| `auth()->user()` inside a Job/Command | §8.1 | grep `auth\(\)->user\(\)` in `app/Jobs`, `app/Console` |
| Token abilities used as ownership check | §8.2 | review controllers gating with `tokenCan` only |
| `md5`/`sha1` of passwords or auth tokens | §9 | grep `md5\|sha1` near `password` |
| Unverified email allowed past `/dashboard` | §10 | grep `auth` middleware without `verified` |
| Reset-link endpoint not throttled | §11 | grep `sendResetLink` route without `throttle` |
| Flag-on-User AND separate guard for "admin" | §12 | `is_admin` column + multiple guards |

---

## 15. Cross-references

| Topic | Skill |
|---|---|
| OWASP, password hashing internals, 2FA threat model, dep CVEs | `laravel-security` |
| Eloquent `User` model, FormRequests for login/register | `laravel-backend` |
| Policy composition, `Gate::before`/`after`, multi-tenant pattern | `references/authorization_patterns.md` (this skill) |
| Inertia shared `auth.user`, encryptHistory on logout | `laravel-inertia` (§4, §11) |
| Ziggy filtering of admin routes | `laravel-frontend` (§6) |
| Pest helpers `actingAs`, `Sanctum::actingAs($user, ['ability'])` | `laravel-qa` |
