# Fortify 2FA — Headless two-factor authentication

End-to-end Fortify two-factor authentication. Loaded when the agent is wiring or debugging Fortify 2FA, building the SPA/Inertia 2FA flow (enable → confirm → challenge), or reviewing a PR that touches `two_factor_*` columns or `/two-factor-challenge`.

Facts verified against the Laravel 12.x Fortify docs (Fortify 1.x). Threat model (TOTP drift, code brute-force) lives in `laravel-security`; this doc owns the flow mechanics.

## 1. What Fortify is — and is not

| Fortify IS | Fortify IS NOT |
|---|---|
| A frontend-agnostic **backend**: routes + controllers for login, registration, password reset, email verification, 2FA | A UI — it ships zero pages; you build every screen |
| The engine inside Laravel's starter kits (Breeze-style kits use it internally) | A starter kit — installing a starter kit means Fortify is already there; don't install it twice |
| Pairable with Sanctum SPA mode: Fortify owns `/login` + flows, Sanctum owns the session/cookie recognition | A competitor to Sanctum — they solve different problems (flows vs request authentication) |
| Optional — you can hand-roll every flow with Laravel's auth services | Mandatory for 2FA — but hand-rolling TOTP + recovery codes correctly is exactly the wheel it already implements |

**Decision:** app needs 2FA (or reset/verification flows) and has its own UI → Fortify. App uses a starter kit → Fortify is already installed; customize via `app/Actions/Fortify/*`. App only needs "is this request authenticated?" → that's Sanctum, not Fortify.

## 2. Install and configure (Laravel 12)

```bash
composer require laravel/fortify
php artisan fortify:install      # publishes config, app/Actions/Fortify, FortifyServiceProvider, migrations
php artisan migrate
```

`fortify:install` (older Fortify 1.x releases: `vendor:publish --provider="Laravel\Fortify\FortifyServiceProvider"`) publishes the migration that adds the three 2FA columns to `users` (§3).

### 2.1 `config/fortify.php`

```php
'features' => [
    // ... other features
    Features::twoFactorAuthentication([
        'confirm' => true,             // require a valid TOTP code before 2FA becomes active
        'confirmPassword' => true,     // require password.confirm before touching 2FA settings
    ]),
],

'views' => false,                      // SPA/Inertia-API: don't register the GET view routes
```

**Rules:**
- Keep `'confirm' => true`. Without it, 2FA activates the moment the secret is generated — if the user never scans the QR code, they are locked out at next login (§4.3).
- Keep `'confirmPassword' => true`. It wraps every 2FA management endpoint in `password.confirm` — a hijacked session cannot silently disable 2FA.
- `'views' => false` removes the GET routes that render views (`/two-factor-challenge` GET included). The POST/DELETE/JSON endpoints stay. Full SPAs want this; Blade or Inertia apps that use `Fortify::twoFactorChallengeView(...)` keep views on.

### 2.2 `User` model

```php
use Laravel\Fortify\TwoFactorAuthenticatable;

class User extends Authenticatable
{
    use Notifiable, TwoFactorAuthenticatable;
}
```

### 2.3 `FortifyServiceProvider` — rate limiters

The published provider defines the limiters Fortify's routes reference. Do not delete them:

```php
RateLimiter::for('login', fn (Request $request) => Limit::perMinute(5)
    ->by(Str::transliterate(Str::lower($request->input(Fortify::username())).'|'.$request->ip())));

RateLimiter::for('two-factor', fn (Request $request) => Limit::perMinute(5)
    ->by($request->session()->get('login.id')));
```

## 3. Schema

The published migration adds three nullable columns to `users`:

| Column | Type | Content |
|---|---|---|
| `two_factor_secret` | `text` | **Encrypted** TOTP secret (Laravel `encrypt()`) |
| `two_factor_recovery_codes` | `text` | **Encrypted** JSON array of recovery codes |
| `two_factor_confirmed_at` | `timestamp` | Set when the user proves they can generate a valid code — the flag that makes 2FA actually enforced (with `confirm => true`) |

All access goes through the `TwoFactorAuthenticatable` trait (`twoFactorQrCodeSvg()`, `recoveryCodes()`, `hasEnabledTwoFactorAuthentication()`). Never read or write these columns directly.

## 4. The full 2FA lifecycle — endpoints

All `/user/*` endpoints require an authenticated session; with `confirmPassword => true` they additionally require a recent password confirmation (§5.1).

| Step | Endpoint | XHR response |
|---|---|---|
| 1. Enable (generate secret + codes) | `POST /user/two-factor-authentication` | `200` |
| 2. Get QR code | `GET /user/two-factor-qr-code` | `200` JSON `{ "svg": "<svg ...>" }` (recent releases also include the otpauth `url`) |
| 2b. Get secret for manual entry | `GET /user/two-factor-secret-key` | `200` JSON `{ "secretKey": "..." }` |
| 3. **Confirm** with a TOTP code | `POST /user/confirmed-two-factor-authentication` `{ code }` | `200`; invalid code → `422` |
| 4. Get recovery codes | `GET /user/two-factor-recovery-codes` | `200` JSON array of strings |
| 4b. Regenerate recovery codes | `POST /user/two-factor-recovery-codes` | `200` (GET again to display) |
| 5. Login (later session) | `POST /login` | `200` JSON `{ "two_factor": true }` when a challenge is required |
| 6. Challenge | `POST /two-factor-challenge` `{ code }` **or** `{ recovery_code }` | `204` on success; `422` on invalid code |
| Disable | `DELETE /user/two-factor-authentication` | `200` |

Non-XHR requests get redirects back with a `status` session variable instead (`two-factor-authentication-enabled`, `two-factor-authentication-confirmed`).

### 4.1 Setup phase (steps 1-4)

Enable generates and stores the encrypted secret and recovery codes — **2FA is not enforced yet** (with `confirm => true`). The user scans the QR (or types the secret), then submits a live TOTP code to the confirm endpoint. Only then is `two_factor_confirmed_at` set and the login challenge activated. Show the recovery codes immediately after confirmation and tell the user to store them.

### 4.2 Login phase (steps 5-6)

```text
SPA                                    Laravel (Fortify)
 |  POST /login {email, password}       |
 |------------------------------------->|  credentials valid + 2FA confirmed?
 |  200 { "two_factor": true }          |  → session['login.id'] = user id (NOT logged in yet)
 |<-------------------------------------|
 |  render challenge screen             |
 |  POST /two-factor-challenge {code}   |
 |------------------------------------->|  verify TOTP against decrypted secret
 |  204 No Content                      |  → Auth::login(), session regenerated
 |<-------------------------------------|
 |  GET /api/user  (session cookie)     |
 |------------------------------------->|  200 — authenticated
```

`RedirectIfTwoFactorAuthenticatable` sits in Fortify's login pipeline. When credentials are valid **and** the user has confirmed 2FA, Fortify does not log the user in. Instead it stores `login.id` (+ `login.remember`) in the **session** and:

- XHR login → `200` with `{ "two_factor": true }` (no user, no token — inspect this flag)
- Browser login → redirect to `/two-factor-challenge`

The client then POSTs to `/two-factor-challenge` with either `code` (6-digit TOTP) or `recovery_code` (one of the stored strings). Success establishes the real authenticated session (`204` for XHR, redirect to `fortify.home` otherwise). A used recovery code is single-use — Fortify replaces it with a freshly generated one automatically.

⚠️ The challenge is **session-bound**: it only works in the same session that just passed the password step. There is no user id in the challenge payload — Fortify reads it from `login.id`.

### 4.3 Why the confirm step is not optional

With `confirm => false`, `hasEnabledTwoFactorAuthentication()` is true as soon as the secret exists. A user who clicks "enable" and closes the tab before scanning the QR code is now challenged at every login with a code they can never produce. With `confirm => true`, an unconfirmed secret is inert: login proceeds normally until the user proves they can generate codes. **Always ship confirmable 2FA.**

## 5. SPA / Inertia integration (no Blade views)

Fortify's endpoints speak JSON when the request is XHR (`X-Requested-With: XMLHttpRequest` / `Accept: application/json`). Combined with Sanctum SPA cookie mode, the whole flow is driven client-side:

```ts
// Settings page — setup flow
await axios.post('/user/two-factor-authentication');                    // 200
const { data: qr } = await axios.get('/user/two-factor-qr-code');      // { svg }
// render qr.svg, collect the user's first TOTP code
await axios.post('/user/confirmed-two-factor-authentication', { code });// 200 or 422
const { data: codes } = await axios.get('/user/two-factor-recovery-codes'); // string[]
// display codes once, force acknowledgment

// Login flow
const { data } = await axios.post('/login', { email, password });      // Fortify login
if (data.two_factor) {
    // navigate to the SPA's challenge screen — same session, no new CSRF dance needed
    await axios.post('/two-factor-challenge', { code });               // 204, or { recovery_code }
}
// authenticated — fetch /api/user or Inertia-visit the dashboard
```

**Status codes the SPA must handle:**

| Response | Meaning | SPA action |
|---|---|---|
| `200` + `{ two_factor: true }` from `/login` | Credentials OK, challenge pending | Show challenge screen |
| `204` from `/two-factor-challenge` | Challenge passed, session authenticated | Redirect to app |
| `422` | Invalid TOTP / recovery code (validation errors in body) | Show error, let user retry |
| `423` from any `/user/two-factor-*` endpoint | Password confirmation required (§5.1) | Show password prompt, POST `/user/confirm-password`, retry |
| `429` | `two-factor` rate limiter hit (5/min per challenged user) | Back off, show wait message |

**Inertia specifics:** with Inertia, prefer form submissions through the Inertia router for `/login` and `/two-factor-challenge` (non-XHR semantics — Fortify redirects, Inertia follows). Fortify's redirect target after login/challenge is `config('fortify.home')`. The JSON-flag pattern above applies when the login call is a raw axios/fetch XHR (token-less API SPA on Sanctum cookies). Pick one transport per flow — don't mix Inertia visits and raw axios for the same form.

### 5.1 Password confirmation for the settings endpoints

With `confirmPassword => true`, the 2FA management endpoints are behind `password.confirm`. For XHR requests, an unconfirmed session gets **`423 Locked`** (`{ "message": "Password confirmation required." }`). Flow:

```ts
const { data } = await axios.get('/user/confirmed-password-status');   // { confirmed: boolean }
if (!data.confirmed) {
    await axios.post('/user/confirm-password', { password });          // 201
}
await axios.post('/user/two-factor-authentication');                    // now passes
```

Confirmation lasts `config/auth.php#password_timeout` (default 10800s / 3h).

### 5.2 Inertia view bindings (views on, no Blade)

Inertia apps keep `'views' => true` and bind the Fortify view hooks to Inertia pages in `FortifyServiceProvider::boot`. Fortify still owns the routes; Inertia renders the screens:

```php
use Inertia\Inertia;
use Laravel\Fortify\Fortify;

public function boot(): void
{
    Fortify::loginView(fn () => Inertia::render('Auth/Login'));

    Fortify::twoFactorChallengeView(fn () => Inertia::render('Auth/TwoFactorChallenge'));

    Fortify::confirmPasswordView(fn () => Inertia::render('Auth/ConfirmPassword'));
}
```

With this wiring the login POST goes through the Inertia router (`useForm().post('/login')`); when 2FA is required Fortify redirects to `/two-factor-challenge`, Inertia follows the redirect, and your `TwoFactorChallenge` page posts `code` or `recovery_code` back through `useForm()`. Validation failures come back as standard Inertia `errors` props — no manual 422 handling.

The settings screen (enable/confirm/QR/recovery codes) is still driven with axios XHR calls as in §5 — those endpoints are JSON-first and have no view counterpart.

## 6. Events — hooking the lifecycle

Fortify fires an event at every 2FA transition (all in `Laravel\Fortify\Events`). Use them for audit logging and notifications instead of wrapping the endpoints:

| Event | Fired when |
|---|---|
| `TwoFactorAuthenticationEnabled` | Secret + recovery codes generated (enable endpoint) |
| `TwoFactorAuthenticationConfirmed` | Confirm endpoint accepted a valid code — 2FA now enforced |
| `TwoFactorAuthenticationDisabled` | DELETE endpoint cleared the columns |
| `TwoFactorAuthenticationChallenged` | Login stopped at the challenge (session `login.id` set) |
| `TwoFactorAuthenticationFailed` | Challenge received an invalid code |
| `ValidTwoFactorAuthenticationCodeProvided` | Challenge passed with a TOTP code |
| `RecoveryCodeReplaced` | A recovery code was consumed and regenerated |
| `RecoveryCodesGenerated` | Full recovery-code set (re)generated |

Typical listeners: notify the user on `TwoFactorAuthenticationDisabled` (account-takeover signal), rate-alert on repeated `TwoFactorAuthenticationFailed`, audit-log `RecoveryCodeReplaced` so support can see when codes are burning down.

## 7. Troubleshooting matrix

| Symptom | Likely cause | Fix |
|---|---|---|
| `POST /two-factor-challenge` returns **404** | `Features::twoFactorAuthentication()` not in `config/fortify.php` features array — route never registered | Enable the feature; `php artisan route:list \| grep two-factor` to verify |
| Challenge returns 422 "invalid code" for a correct code, or redirects to login | `login.id` gone from the session — session lost between `/login` and the challenge | Check `SESSION_DRIVER` (never `array`), `SESSION_DOMAIN` covers the SPA origin, cookies sent (`withCredentials`) |
| QR / enable endpoint returns **423** | `password.confirm` gate — session has no recent password confirmation | POST `/user/confirm-password` first (§5.1); don't remove `confirmPassword` to "fix" this |
| User enabled 2FA but login never challenges | `confirm => true` and the confirm step was skipped — `two_factor_confirmed_at` is null, so 2FA is inert | Drive the user through `POST /user/confirmed-two-factor-authentication`; treat setup UI without a confirm input as a bug |
| User enabled 2FA and is now locked out | `confirm => false` — secret activated without proof the authenticator works | Switch to `confirm => true`; unlock via recovery code or, last resort, null the `two_factor_*` columns from a console session |
| Challenge loops back to the challenge screen | Session regenerated/lost per request (see row 2), or SPA re-POSTing `/login` instead of `/two-factor-challenge` | Fix session config; challenge screen must POST the challenge endpoint |
| `429` on the challenge | `two-factor` rate limiter (5/min) | Expected under brute force; if legit users hit it, review the limiter in `FortifyServiceProvider` |
| Valid TOTP codes always rejected | Server clock drift — TOTP is time-based | Sync server time (NTP); check container/VM clock |
| `GET /two-factor-challenge` 404 in an SPA | `'views' => false` removes the GET view routes | Expected — the SPA renders its own screen; only the POST exists |

## 8. Anti-patterns

| Smell | Why it's wrong | Detection |
|---|---|---|
| Exposing `/user/two-factor-secret-key` (or the QR) after setup is confirmed | The secret is write-once for the user; re-displaying it turns any session/XSS compromise into a permanent 2FA bypass | Settings UI renders QR/secret when `two_factor_confirmed_at` is set |
| No recovery-code regeneration UI | Codes are consumed one by one; a user with 0 left and a lost phone is locked out permanently | grep frontend for `two-factor-recovery-codes` — GET without the POST |
| Treating 2FA as enabled without the confirm step | With `confirm => true` it silently does nothing; with `confirm => false` it locks users out | Setup flow lacking a `confirmed-two-factor-authentication` call |
| `confirmPassword => false` to dodge the 423 | Any hijacked session can disable 2FA or read recovery codes | `Features::twoFactorAuthentication` options in config |
| Reading `two_factor_secret` directly / decrypting it in app code | Bypasses the trait, leaks the secret into logs/responses | grep `two_factor_secret` outside migrations |
| Hand-rolled TOTP endpoint alongside Fortify | Duplicates a hardened flow; usually misses throttling, encryption, recovery codes | grep for a second TOTP library (`pragmarx/google2fa` used directly) with Fortify installed |
| Login response handling that ignores `two_factor` | Users with 2FA enabled appear "logged in" client-side but every API call is 401 | Review SPA login handler for the flag check |

## 9. Cross-references

- `laravel-auth` SKILL.md §4 — Fortify overview, feature toggles, contract bindings
- `laravel-auth` SKILL.md §7 — `password.confirm` middleware
- [`references/sanctum_spa_setup.md`](sanctum_spa_setup.md) — the session/cookie layer the challenge rides on (2FA loop symptoms are usually session config)
- `laravel-security` — 2FA threat model: TOTP window, recovery-code entropy, brute-force policy
- `laravel-qa` — testing the challenge flow with Pest (`withSession(['login.id' => ...])`)
- `laravel-react` / `laravel-vue` agents — building the challenge and settings screens
