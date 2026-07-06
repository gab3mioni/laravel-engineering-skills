# Sanctum tokens vs Passport — Token mode decision

Deciding between Sanctum (tokens or SPA cookies) and Passport, and designing Sanctum token abilities. Loaded when the agent is choosing an API auth mechanism, reviewing a PR that adds `createToken(` calls or installs Passport, or designing ability/scope names.

Facts verified against the Laravel 12.x Sanctum and Passport docs (Passport 13.x). Default posture: **Sanctum until proven otherwise** — training data over-suggests Passport; the official docs say the opposite ("If you are attempting to authenticate a single-page application, mobile application, or issue API tokens, you should use Laravel Sanctum").

## 1. Decision matrix

| Consumer | Use | Why |
|---|---|---|
| First-party SPA, same registrable domain | **Sanctum SPA cookies** | HttpOnly session cookie, CSRF-protected, zero token storage — see [`sanctum_spa_setup.md`](sanctum_spa_setup.md) |
| First-party mobile app | **Sanctum tokens** (per-device) | Simple bearer token exchanged for credentials + device name; no OAuth redirect dance |
| CLI tools, scripts, personal access tokens (GitHub-style) | **Sanctum tokens** | Passport docs themselves: "If your application is using Passport primarily to issue personal access tokens, consider using Laravel Sanctum" |
| Machine-to-machine (your service ↔ your service) | **Sanctum token** on a service user, or **Passport client credentials** if OAuth is already in place | Sanctum is enough; client credentials only pays off when an OAuth server already exists |
| Third-party apps acting **for your users** (consent screen, "Sign in with YourApp") | **Passport** — authorization code (+ PKCE for public clients) | This is real OAuth2: client registration, scoped consent, refresh tokens |
| You are an OAuth **identity provider** to other companies | **Passport** | The only case where the full OAuth2 server surface is the requirement itself |
| Input-constrained devices (TVs, consoles) | **Passport** device authorization grant | Standardized `device_code` flow — don't hand-roll it |

Two questions settle it: **(1)** Do third parties need your users' consent to act on their behalf? **(2)** Do external developers register OAuth clients with you? Both "no" → Sanctum. Either "yes" → Passport.

⚠️ **Not a factor:** "we might open an API someday" (see §4), "OAuth is more secure" (it isn't for first-party — it adds moving parts), "mobile needs OAuth" (Sanctum's token exchange is the documented mobile flow).

### 1.1 Detection before recommending

Run before proposing either package:

```bash
composer show laravel/sanctum laravel/passport --quiet 2>/dev/null   # what's installed
grep -rn "createToken(" app/                                          # token issuance sites
grep -rn "enablePasswordGrant\|enableImplicitGrant" app/              # deprecated grants in use
```

Passport already installed + only first-party consumers → flag it (see §5), don't extend it. Sanctum already installed → stay unless a real third-party OAuth requirement appears in the diff.

## 2. Sanctum token design

### 2.1 Abilities — naming and granting

Abilities are app-defined strings, granted at creation, checked at request time. Use `resource:action` naming and keep the canonical list in one place:

```php
// app/Enums/TokenAbility.php — single source of truth
enum TokenAbility: string
{
    case PostsRead   = 'posts:read';
    case PostsWrite  = 'posts:write';
    case OrdersRead  = 'orders:read';
}

// Issue — always pass an explicit abilities array
$token = $user->createToken('ci-deploy-bot', [TokenAbility::PostsRead->value]);
return ['token' => $token->plainTextToken];   // shown once; only a SHA-256 hash is stored

// Check in code
$request->user()->tokenCan('posts:write');

// Check as middleware — register aliases in bootstrap/app.php (Laravel 12)
$middleware->alias([
    'abilities' => CheckAbilities::class,       // must have ALL listed
    'ability'   => CheckForAnyAbility::class,   // must have AT LEAST ONE
]);
Route::middleware(['auth:sanctum', 'abilities:posts:read,posts:write'])->post(...);
```

**Rules:**
- `createToken('name')` with no second argument grants `['*']` — every ability. Always pass the narrowest array.
- **`tokenCan()` is not authorization.** It proves the *token* was granted a capability — not that the *user* may touch this resource. Pair with a Policy: `tokenCan('posts:write')` + `$this->authorize('update', $post)`.
- `tokenCan()` returns `true` unconditionally for first-party SPA cookie requests — by design, so Policies can call it uniformly. Never use it as the only gate.

**Granularity guidance:**

| Granularity | Example | Verdict |
|---|---|---|
| Per resource + read/write split | `posts:read`, `posts:write` | ✅ The default — maps to REST verbs, small enough to reason about |
| Coarse role-shaped | `admin`, `full-access` | ⚠️ Only for internal service tokens; useless for least-privilege user tokens |
| Per endpoint | `posts:index`, `posts:show`, `posts:store` | ❌ Explodes the catalog; ability drift on every route change |
| Wildcard | `['*']` | ❌ Only acceptable for the user's own short-lived session-equivalent token — never for third parties or CI |

### 2.2 Per-device tokens (the mobile flow)

Mobile login exchanges credentials + `device_name` for a token — this is the documented Sanctum mobile pattern, not OAuth:

```php
Route::post('/sanctum/token', function (Request $request) {
    $request->validate([
        'email' => 'required|email',
        'password' => 'required',
        'device_name' => 'required',
    ]);

    $user = User::where('email', $request->email)->first();

    if (! $user || ! Hash::check($request->password, $user->password)) {
        throw ValidationException::withMessages([
            'email' => ['The provided credentials are incorrect.'],
        ]);
    }

    return $user->createToken($request->device_name, ['posts:read', 'posts:write'])->plainTextToken;
})->middleware('throttle:5,1');
```

One token per device, named so the user recognizes it ("Nuno's iPhone 17") in a settings page listing `$user->tokens` with a revoke button per row. Login on the same device again → issue a new token; don't share one token across devices. Store it in the platform keychain/keystore, never in plain app storage.

### 2.3 Expiration and rotation

```php
// config/sanctum.php — global cap in MINUTES (default null = never expires)
'expiration' => 525600,          // 1 year

// Per-token override — third argument to createToken
$user->createToken('ci-bot', ['posts:read'], now()->addWeek());

// Prune expired rows (schedule it once expiration is on)
Schedule::command('sanctum:prune-expired --hours=24')->daily();
```

Rotation on refresh — issue-new-then-delete-old in one request:

```php
$new = $request->user()->createToken($name, $abilities, now()->addDays(30));
$request->user()->currentAccessToken()->delete();
return ['token' => $new->plainTextToken];
```

Custom token model (extra columns, tenant scoping) → extend `Laravel\Sanctum\PersonalAccessToken` and register with `Sanctum::usePersonalAccessTokenModel(PersonalAccessToken::class)` in `AppServiceProvider::boot`.

### 2.4 Revocation

```php
$user->tokens()->delete();                              // all (password change, "log out everywhere")
$request->user()->currentAccessToken()->delete();       // this device's logout
$user->tokens()->where('id', $tokenId)->delete();       // settings-page revoke button
```

Revocation is a row delete — immediate, no denylist infrastructure. Hook `$user->tokens()->delete()` into password-reset and compromise-response listeners.

## 3. Passport 13 on Laravel 12 — essentials

Only what's needed to recognize when Passport is justified and wire it minimally. Full surface → official docs.

```bash
php artisan install:api --passport      # migrations, keys, config
```

- `User` gets `Laravel\Passport\HasApiTokens` + implements `Laravel\Passport\Contracts\OAuthenticatable` (never both Passport's and Sanctum's `HasApiTokens` on the same model).
- `config/auth.php`: `api` guard with `'driver' => 'passport'`; protect routes with `auth:api`.
- Clients: `php artisan passport:client` (confidential), `--public` (PKCE), `--client` (client credentials), `--device` (device flow). Passport 13 stores allowed grants in a `grant_types` column (replaces the old `personal_access_client`/`password_client` flags).
- Scopes: `Passport::tokensCan(['orders:read' => 'Check order status', ...])` + `Passport::defaultScopes([...])` in a provider — descriptions appear on the consent screen.

The authorization-code shape (what Sanctum has no equivalent for): the third-party app redirects the user to your `/oauth/authorize?client_id=...&redirect_uri=...&response_type=code&scope=...&state=...`; your app renders the **consent screen**; on approval the user returns to the third party's `redirect_uri` with a code, which the third party exchanges at `POST /oauth/token` for `access_token` + `refresh_token` + `expires_in`. First-party clients may skip the prompt by overriding the Client model with a `skipsAuthorization()` method returning `true` — but if every client skips authorization, that's the §5 smell: you didn't need Passport.

### 3.1 Grant types — current status (verified against 12.x docs)

| Grant | Status | Use |
|---|---|---|
| Authorization code | ✅ Recommended | Third-party server-side apps acting for your users |
| Authorization code + PKCE | ✅ Recommended | Third-party SPAs / mobile apps (public clients, `passport:client --public`) |
| Client credentials | ✅ Recommended | Machine-to-machine, no user context |
| Device authorization | ✅ Available | Input-constrained devices |
| Password grant | ⚠️ **Deprecated** — docs: "We no longer recommend using password grant tokens"; disabled by default, opt-in via `Passport::enablePasswordGrant()` | Legacy only — new first-party mobile apps should use Sanctum tokens instead |
| Implicit grant | ⚠️ **Deprecated** — disabled by default, opt-in via `Passport::enableImplicitGrant()` | Never for new code — PKCE replaced it |
| Personal access tokens | ✅ Available, but docs point to Sanctum for this use case | Only if Passport is already installed for real OAuth |

**Cost of Passport** (what you buy into): encryption keypair management across deploys, client registration + secrets lifecycle, consent screens, scope catalog, refresh-token rotation, `oauth_*` tables, League OAuth2 server upgrades. Justified when third parties integrate; dead weight otherwise.

## 4. Migration note — don't pre-buy Passport

Moving Sanctum → Passport later is a bounded, additive change:

- Both authenticate the same `User`; swapping means installing Passport, moving routes from `auth:sanctum` to `auth:api` (or running both guards side by side during transition), and mapping abilities to scopes (`posts:read` translates 1:1 to a Passport scope name).
- First-party consumers (SPA cookies, mobile Sanctum tokens) can **stay on Sanctum** — Passport is added only for the third-party surface. The two packages coexist in one app (keep their `HasApiTokens` traits on different models or alias carefully).
- What does NOT migrate automatically: issued Sanctum tokens (third parties re-authorize via OAuth — which is the point of the move).

Migration order that avoids downtime:

1. Install Passport alongside Sanctum; register clients for the pilot third party.
2. Expose the OAuth routes under `auth:api` while first-party routes keep `auth:sanctum`.
3. Map each Sanctum ability to a Passport scope in `Passport::tokensCan` (same strings — the naming convention pays off here).
4. Retire Sanctum tokens only for consumers that actually moved; first-party stays on Sanctum indefinitely.

So: starting with Sanctum costs almost nothing later; starting with Passport "to be safe" costs OAuth operational overhead from day one for zero users of it.

## 5. Anti-patterns

| Smell | Why it's wrong | Detection |
|---|---|---|
| `createToken(` without an abilities array | Token silently gets `['*']` — full account power in one bearer string | `grep -rn "createToken(" app/ \| grep -v "\["` (review hits without a second arg) |
| Tokens in localStorage for a same-domain SPA | XSS reads localStorage; the HttpOnly cookie alternative was available | grep frontend for `localStorage.setItem` near `token`; SPA + `createToken` on login |
| Passport installed, only first-party clients exist | Full OAuth server maintained for consumers Sanctum covers in one table | `composer show laravel/passport` + no third-party client registration flow, `oauth_clients` only holds first-party rows |
| Password grant for a new mobile app | Deprecated grant; Sanctum's token exchange is the documented flow | grep `enablePasswordGrant` |
| Implicit grant anywhere new | Deprecated; PKCE is the public-client answer | grep `enableImplicitGrant` |
| `tokenCan()` as the only ownership check | Proves capability, not resource ownership — IDOR waiting to happen | controllers gating with `tokenCan` and no `authorize()`/Policy call |
| One shared token across a user's devices | Can't revoke a single lost device; last_used audit is meaningless | token issuance not keyed by `device_name` |
| `'expiration' => null` + no revocation UI | Leaked token is valid forever and the user can't kill it | `config/sanctum.php` + no settings page listing `$user->tokens` |
| Sanctum's and Passport's `HasApiTokens` on the same model | Method collision; ambiguous `createToken`/`tokens()` | grep both `use` lines in `app/Models/User.php` |

## 6. Cross-references

- `laravel-auth` SKILL.md §1 — the top-level decision tree this doc expands
- `laravel-auth` SKILL.md §3.2 — API token mode quickstart
- `laravel-auth` SKILL.md §8.2 — token abilities vs Policies
- [`references/sanctum_spa_setup.md`](sanctum_spa_setup.md) — the cookie mode this doc keeps steering same-domain SPAs toward
- `laravel-security` — token leakage response, audit logging of token use
- `laravel-qa` — `Sanctum::actingAs($user, ['posts:read'])` for testing ability-gated routes
