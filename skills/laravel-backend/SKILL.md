---
name: laravel-backend
description: Server-side core for Laravel 12 / PHP 8.3+. Use when editing models, controllers, migrations, FormRequests, API Resources, Actions/Services, events, observers, or policies; designing an API endpoint or building a new resource end-to-end; reviewing a backend diff; or chasing symptoms like "N+1 queries", "mass assignment", "env() returns null in production", "job reads stale data", or "403 from authorize()". Provides workflows (new resource, diff review, safe migration), decision tables, and a grep-able anti-pattern checklist. Used by shared Laravel roles.
---

# Laravel Backend — Server-side core

Idiomatic Laravel 12 / PHP 8.3+ patterns for server-side code, packaged as executable workflows. Optimized for agents that *write* (`backend`), *audit* (`security`), or *review* (`code-review`) backend code.

## When to use

- Designing or modifying Eloquent models, migrations, controllers, FormRequests, API Resources, Actions/Services, jobs, events, observers, policies
- Building a new resource end-to-end (see Workflows)
- Reviewing server-side code in PRs (see Workflows)
- Detecting server-side anti-patterns (N+1, mass assignment, env leakage, missing FormRequest)

## When NOT to use

| Topic | Use instead |
|---|---|
| Authentication, guards, Sanctum, Fortify, Breeze | `laravel-auth` skill |
| Queue execution, Horizon, scheduler internals | `laravel-queues` skill |
| Vite, `resources/js`, Wayfinder, asset pipeline | `laravel-frontend` skill |
| Inertia protocol (shared data, partial reloads, deferred props) | `laravel-inertia` skill |
| Pest, factories *for tests*, fakes, HTTP testing | `laravel-qa` skill |
| Pint, Larastan, Rector | `laravel-static-analysis` skill |
| OWASP, CSP, hardening, dep CVEs, compliance | `laravel-security` skill |
| WCAG, ARIA | `laravel-a11y` skill |
| React/Vue components, pages, client-side state | `laravel-role-react` / `laravel-role-vue` |
| Deploy, Docker, CI/CD, Octane runtime, infra | `laravel-role-devops` |

## Reference routing

Load a reference only when the task hits its trigger — the sections below cover the default cases.

| Trigger | Load |
|---|---|
| N+1 / slow queries at scale, `chunk`/`cursor`/`lazy`, query plans, indexes, read replicas | `references/eloquent_performance.md` |
| Morphs, pivot models, JSON column relationships, custom builders, custom cast examples | `references/eloquent_advanced.md` |
| Production migration on a big table, zero-downtime schema change, FK cascade choices | `references/schema_and_migration_safety.md` |
| Cache stampede, tagged invalidation, atomic locks, layered caches | `references/cache_patterns.md` |
| Public API: pagination, versioning, error format, sorting/filtering | `references/api_design_patterns.md` |
| External webhooks, idempotency keys, retries, and vendor APIs | `laravel-integrations` skill |
| Backend security touchpoints (mass assignment depth, raw bindings, uploads, payload hygiene) | `references/security.md` |
| Policy composition, multi-tenant authorization, Spatie Permission | `laravel-auth` skill (not a local reference) |

## Stack assumptions

- Laravel 12, PHP 8.3+ (use 8.4 features when the project's `composer.json` allows)
- Eloquent for persistence
- Pest as the default test runner (testing details in `laravel-qa`)
- **Detection-based**: run the plugin's `scripts/detect-stack.sh` from the project root and adapt to the emitted `HAS_*` flags (e.g. `HAS_SPATIE_DATA`, `HAS_SPATIE_PERMISSION`, `HAS_WAYFINDER`, `HAS_OCTANE`). The skill documents native patterns; only adopt a third-party convention when its flag is present.

---

## Workflows

### Workflow A — New resource end-to-end

1. **Scaffold** everything in one command:

   ```bash
   php artisan make:model Post -mfsc --requests --policy --resource
   ```

   Verify the generated file list: model, migration, `PostFactory`, `PostSeeder`, resource `PostController`, `StorePostRequest` + `UpdatePostRequest`, `PostPolicy`. Add the API Resource separately: `php artisan make:resource PostResource`.

2. **Migration** — rules in "Migrations": `foreignId()->constrained()`, `timestampTz`, index FKs and `WHERE`/`ORDER BY` columns, structural `down()`.
3. **Model** — rules in "Model anatomy": declare `$fillable`, cast every non-string column, type-hinted relationships, `Attribute` API for accessors.
4. **FormRequests** — fill `rules()` and `authorize()` per "FormRequests & validation"; every accepted field gets a rule.
5. **Controller** — lean per "Controllers": authorize (policy), pass only `$request->validated()` downstream, business rules go to an Action ("Domain layer").
6. **API Resource** — per "API Resources": every relationship wrapped in `whenLoaded()`; the controller eager-loads what the Resource exposes.
7. **Verify**:

   ```bash
   php artisan migrate
   php artisan model:show Post            # confirms fillable, casts, relationships, policy binding
   php artisan route:list --except-vendor # confirms routes + middleware
   ```

8. **Tests in the same diff** — feature test per endpoint, factory states as needed. Load the `laravel-qa` skill; "tests later" is not an option.

### Workflow B — Review a backend diff

**Step 1 — grep battery**: run the Detection column of "Rules & anti-patterns — consolidated checklist" top to bottom, scoped to the files in the diff. Pure-grep rows first (mass assignment, `env(` outside config, SQL interpolation, inline role checks, legacy accessors, PII logging, unhashed cache keys), then the introspection rows (`route:list`, `model:show`, `wc -l`).

**Step 2 — judgment checks** (no grep can decide these):

- Every `dispatch()` / `Mail::queue()` / queued listener fired inside a transaction is paired with `afterCommit()` — see "Transactions & afterCommit".
- API Resources don't leak hidden/sensitive fields and don't touch unloaded relations — see "API Resources".
- Relations accessed in loops, Resources, or Blade have a matching `with()`/`load()` upstream — see "Eager loading & N+1".
- New endpoints have a FormRequest and a policy check — see "FormRequests & validation" and "Authorization".

**Output format**: one line per finding — `finding → section name → concrete fix`.

### Workflow C — Safe migration on a live table

1. **Additive-only by default**: add nullable columns / new tables; never rename or drop in the same deploy as code that still reads the old shape.
2. **Dry-run first**: `php artisan migrate --pretend` and read the SQL it would execute.
3. **Never edit a committed migration** — write a new migration that corrects the schema. Editing breaks every environment that already ran it.
4. Dropping a column: deploy code that stops reading it first, drop in a later deploy.
5. Big table (locks, long ALTERs, backfills) → load `references/schema_and_migration_safety.md` before touching it.

---

## Decision tables

### Where does logic go? (rule of 3)

| Location | When |
|---|---|
| Controller | Trivial (1–3 lines, no business rule) |
| **Action** class | One business operation, called from 1–2 places |
| **Service** | Cohesive group of ~3+ operations on the same aggregate |
| Model | Pure data behavior (accessors, scopes, simple calculations) |
| Job | Same as Action, but async |

Rule of 3: start in the controller; extract to an Action at the first business rule or second caller; promote to a Service only when 3+ related Actions share state or dependencies. Don't pre-build layers.

### Quick-reference defaults

| Need | Default |
|---|---|
| Accept input | FormRequest, pass `$request->validated()` downstream |
| Return JSON | API Resource with `whenLoaded()` |
| Accessor/mutator | `Attribute` API (never `getXxxAttribute` in new code) |
| FK column | `foreignId()->constrained()` |
| Business operation | Plain PHP Action class with `handle()` |
| Transaction | `DB::transaction(fn () => ...)` closure form |
| Async side effect in a transaction | `dispatch(...)->afterCommit()` |
| Authorization | Policy (model-bound) / Gate (no model) |
| Multi-channel message | Notification; email-only → Mailable |
| Runtime config value | `config(...)` — `env()` only inside `config/*.php` |

## 1. Eloquent

### 1.1 Model anatomy

```php
final class Post extends Model
{
    protected $fillable = ['title', 'body', 'user_id'];

    protected $casts = [
        'published_at' => 'datetime',
        'meta'         => 'array',
        'is_featured'  => 'boolean',
        'status'       => PostStatus::class,   // PHP enum
    ];

    protected $with    = ['author'];           // always eager-loaded
    protected $hidden  = ['secret_token'];     // hidden in array/JSON
    protected $appends = ['excerpt'];          // accessor included in array/JSON

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'user_id');
    }

    public function scopePublished(Builder $q): Builder
    {
        return $q->whereNotNull('published_at');
    }

    protected function excerpt(): Attribute
    {
        return Attribute::get(fn () => Str::limit(strip_tags($this->body), 140));
    }
}
```

**Rules:**
- Always declare `$fillable` **or** `$guarded = []` — never both, never neither. ⚠️ Anti-pattern: model with neither.
- Cast every non-string column (datetime, int, bool, array, decimal, enum).
- `$with` only for relationships *always* loaded. Otherwise prefer per-query `with()`.
- Use the **Attribute API** (Laravel 9+) for accessors/mutators. The legacy `getXxxAttribute()` form should not be added in new code.
- Mark domain models `final` unless inheritance is intended.

### 1.2 Relationships

- Always type-hint the return (`BelongsTo`, `HasMany`, ...) — Larastan and IDEs depend on it.
- Pass the FK explicitly only when it deviates from convention; don't restate defaults.
- Polymorphic relations (`morphMany`, `morphToMany`), pivot models, recursive relationships, and JSON column relationships → `references/eloquent_advanced.md`.

### 1.3 Eager loading & N+1

```php
Post::with(['author', 'tags'])->get();                    // up-front
$posts->loadMissing('comments');                          // after fetch, skip if loaded
Post::with(['comments' => fn ($q) => $q->latest()->limit(3)])->get();  // constrained
Post::withCount('comments')->get();                       // adds `comments_count`, no load
```

⚠️ **Anti-pattern:** relationship access inside a loop without prior `with()`/`load()` — N+1. Enable runtime detection in dev: `Model::preventLazyLoading(! app()->isProduction())` in `AppServiceProvider::boot()`.

For `chunk`/`cursor`/`lazy` iteration, query-plan reading, indexes that cover Eloquent queries, and read-replica config, see `references/eloquent_performance.md`.

### 1.4 Scopes

**Local scope** — instance method `scopeXxx`, called as `Post::published()->latest()->paginate()`.

**Global scope** — registered via `static::addGlobalScope(new MyScope)` in the model's `booted()` method, applied to every query. Use sparingly; document in the model docblock. Multi-tenant pattern (tenant_id scope + Policy as defense in depth) lives in the `laravel-auth` skill.

⚠️ Global scopes hide rows from queries — easy to forget when debugging "missing data". Use `Model::withoutGlobalScope(...)` only with awareness.

### 1.5 Casts

Built-in: `int`, `float`, `bool`, `string`, `array`, `collection`, `datetime`, `date`, `decimal:2`, `encrypted`, `encrypted:array`, `enum:Backed`.

Custom casts for value objects: implement `CastsAttributes`, generate with `php artisan make:cast Money`. Full example in `references/eloquent_advanced.md`.

### 1.6 Model events & Observers

Observer = class with lifecycle-named methods (`created`, `updating`, `deleting`, ...); register with `Post::observe(PostObserver::class)` in `AppServiceProvider::boot()`.

**Heuristic:**

| Use | When |
|---|---|
| Observer | Reaction tied to model lifecycle (created/updated/deleted), runs on every save regardless of caller |
| Event + Listener | Domain action with multiple subscribers; can be queued; can fail independently |
| Direct call | Single, synchronous follow-up; trivial |

⚠️ Don't put HTTP calls or queue dispatches in observers without `afterCommit()` (see "Transactions & afterCommit").

## 2. Migrations, factories, seeders

### 2.1 Migrations

```php
return new class extends Migration {
    public function up(): void
    {
        Schema::create('posts', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->constrained()->cascadeOnDelete();
            $t->string('title', 255);
            $t->text('body');
            $t->timestampTz('published_at')->nullable();
            $t->timestamps();

            $t->index(['user_id', 'published_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('posts');
    }
};
```

**Rules:**
- Use `foreignId(...)->constrained()` over raw `bigInteger` + manual FK.
- `timestampTz` for timezone-aware audit timestamps.
- Index FKs and columns used in `WHERE` / `ORDER BY`.
- Inspect the result with `php artisan db:show` / `php artisan db:table posts`.
- Production changes follow "Workflow C — Safe migration on a live table".

⚠️ **Anti-pattern:** `down()` that uses `delete()` / `truncate()`. Down is the structural inverse, not data-aware.

### 2.2 Factories

```php
class PostFactory extends Factory
{
    public function definition(): array
    {
        return [
            'user_id'      => User::factory(),
            'title'        => fake()->sentence(),
            'body'         => fake()->paragraphs(3, true),
            'published_at' => null,
        ];
    }

    public function published(): static
    {
        return $this->state(['published_at' => now()]);
    }
}

// Usage
Post::factory()->published()->for(User::factory())->count(5)->create();
```

`recycle($model)` shares a parent across the factory tree (avoids creating duplicate parents). Deeper factory patterns (state, sequence, polymorphic) live in `laravel-qa`.

### 2.3 Seeders

`DatabaseSeeder` is the entry point. Keep seeders **idempotent** (`updateOrCreate` for non-test fixtures) so reruns don't duplicate.

## 3. Controllers

**Rules (corrective only):**
- Constructor-inject dependencies; never `new SomeService()` inside an action method.
- Generate with `php artisan make:controller PostController --resource --requests --model=Post` (or `--api` for the 5-method API variant).
- Prefer a **single-action controller** (`__invoke`) for one-off operations like `PublishPost` — routed as `Route::post('/posts/{post}/publish', PublishPost::class)`.
- ⚠️ **Anti-pattern:** controller > 200 LOC. Move logic to Action, Service, or Job ("Domain layer").

**Route-model binding (corrective only):**
- Bind by column with `{post:slug}`; implicit binding 404s automatically.
- Custom resolution only when the default can't express it: `Route::bind('post', fn ($v) => Post::published()->whereSlug($v)->firstOrFail());`

## 4. FormRequests & validation

```php
final class StorePostRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user()->can('create', Post::class);
    }

    public function rules(): array
    {
        return [
            'title'        => ['required', 'string', 'max:255'],
            'body'         => ['required', 'string'],
            'tags'         => ['array', 'max:5'],
            'tags.*'       => ['string', 'distinct', 'exists:tags,name'],
            'published_at' => ['nullable', 'date', 'after_or_equal:now'],
        ];
    }
}
```

**Rules:**
- Use FormRequest for every endpoint that accepts input. ⚠️ Anti-pattern: `$request->all()` reaching the DB.
- Always pass `$request->validated()` (or a DTO built from it) downstream — never `$request->input(...)` after validation.
- `$request->validate([...])` inline is acceptable for trivial 1–2 rule cases.
- Custom messages via `messages()`; normalize input in `prepareForValidation()` before rules run.
- Custom rule: implement `ValidationRule` (`php artisan make:rule Uppercase`), apply inline: `'code' => ['required', new Uppercase]`.
- Conditional rules: `required_if`, `required_unless`, `required_with`, `prohibited_if`, `sometimes`; for complex cases build the array dynamically inside `rules()`.

## 5. API Resources

```php
class PostResource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id'        => $this->id,
            'title'     => $this->title,
            'excerpt'   => $this->excerpt,
            'author'    => UserResource::make($this->whenLoaded('author')),
            'tags'      => TagResource::collection($this->whenLoaded('tags')),
            'published' => $this->published_at !== null,
        ];
    }
}

// Controller
return PostResource::collection(Post::with('author')->paginate());
```

**Rules:**
- Always use `whenLoaded()` for relationships — exposing an unloaded relation triggers N+1.
- Disable the `data` envelope globally with `JsonResource::withoutWrapping()` in `AppServiceProvider::boot()` if not used.
- For versioning, conditional attributes (`when`, `whenPivotLoaded`, `whenCounted`), error format, pagination, sorting/filtering, idempotency keys, rate limiting, and webhooks, see `references/api_design_patterns.md`.

## 6. Domain layer — Actions, Services, DTOs

Placement decision: see "Where does logic go?" in Decision tables.

### 6.1 Action class — plain PHP (recommended)

```php
final class PublishPost
{
    public function __construct(private Dispatcher $events) {}

    public function handle(Post $post): Post
    {
        $post->update(['published_at' => now()]);
        $this->events->dispatch(new PostPublished($post));
        return $post;
    }
}

// Usage: constructor-inject, or app(PublishPost::class)->handle($post)
```

⚠️ **Anti-pattern:** introducing `spatie/laravel-actions`. The community has consolidated on plain classes; the package adds magic without enough payoff. Stick to `handle()` or `__invoke()`.

### 6.2 DTO — detect the project's convention

Check the `HAS_SPATIE_DATA` flag from `scripts/detect-stack.sh`.

**If `spatie/laravel-data` is present** — use `Data` classes; auto-mapping from the FormRequest is the win: `$data = PostData::from($request);`.

**If not (greenfield default)** — readonly class + a static factory:

```php
final readonly class PostData
{
    public function __construct(
        public string $title,
        public string $body,
    ) {}

    public static function fromRequest(StorePostRequest $r): self
    {
        return new self(
            title: $r->validated('title'),
            body: $r->validated('body'),
        );
    }
}
```

## 7. Service container & providers

### 7.1 Bindings

In a `ServiceProvider::register()` — **only** bindings, no logic, no IO:

```php
$this->app->singleton(PostRepository::class, EloquentPostRepository::class);
$this->app->bind(PaymentGateway::class, StripeGateway::class);
$this->app->scoped(RequestContext::class);   // per request (Octane-aware)
```

⚠️ Under Octane, a `singleton` lives across requests — request-dependent state in a singleton leaks between users. Use `scoped` for anything derived from the current request.

Contextual binding: `$this->app->when(LegacyImporter::class)->needs(PostRepository::class)->give(LegacyPostRepository::class);`

### 7.2 register() vs boot()

- `register()` — only `$this->app->bind/singleton(...)`. Container isn't booted; **no DB calls, no facade calls, no env reads at runtime**.
- `boot()` — observer registration, route macros, view composers, custom validation rules, event subscriptions, config publishing.

⚠️ **Anti-pattern:** IO in `register()` (`DB::`, `Http::`, `env()` indirectly via models).

## 8. Events & queued listeners

Choice heuristic: see the table in "Model events & Observers".

**Rules (corrective only):**
- Queue a listener by implementing `ShouldQueue` + `use InteractsWithQueue` — don't queue inline closures for domain events.
- Give every queued listener a `failed(Event $e, Throwable $t)` method that logs context; silent listener death is invisible in production.
- Listener dispatched inside a transaction → `afterCommit` applies (see "Transactions & afterCommit").
- For `Event::fake()` and assertion helpers, see `laravel-qa`.

## 9. Mail & notifications

**Rule:** prefer **Notification** when delivery may span multiple channels or needs DB persistence (`via()` returning `['mail', 'database']`); **Mailable** for email-only (`envelope()` + `content()`, Laravel 9+ shape).

Queue by default — `Mail::to($user)->queue(...)` or `implements ShouldQueue` on the Notification. If sent inside a transaction, pair with `afterCommit` (see "Transactions & afterCommit").

## 10. Cache

```php
$posts = Cache::remember("posts.feed.{$userId}", 300, fn () => Post::feed($userId)->get());
```

⚠️ **Anti-pattern:** cache key derived from raw user input without hashing. Risks key injection and oversized keys. Use `hash('xxh128', $input)` for arbitrary input.

For stampede prevention (lock + recompute, `Cache::flexible`, jitter), tagged invalidation, atomic locks (`Cache::lock`), layered caches, and invalidation strategies, see `references/cache_patterns.md`.

## 11. Middleware

In Laravel 11+, middleware is registered in `bootstrap/app.php` — there is no `Kernel.php`:

```php
->withMiddleware(function (Middleware $m) {
    $m->alias(['feature' => EnsureFeatureEnabled::class]);
    $m->web(append: [SetLocale::class]);
    $m->throttleApi('60,1');
})
```

**Terminable middleware** — implement `terminate(Request, Response): void` for post-response work.

## 12. Config & environment

**The hard rule:** `env()` is allowed **only inside `config/*.php`**. Anywhere else, it returns `null` after `php artisan config:cache` (which is mandatory in production).

```php
// config/services.php
return ['stripe' => ['key' => env('STRIPE_KEY')]];

// Anywhere else
$key = config('services.stripe.key');
```

⚠️ **Anti-pattern detector:** `grep -rn "env(" app/ routes/ database/` — anything matching is a bug waiting to happen.

**Convention:** third-party config under `config/services.php`; app-specific config gets its own file (`config/billing.php`).

## 13. Authorization — Policies & Gates

### 13.1 Policy

```php
class PostPolicy
{
    public function update(User $user, Post $post): Response
    {
        return $user->id === $post->user_id
            ? Response::allow()
            : Response::deny('You do not own this post.');
    }
}
```

Laravel 11+ auto-discovers `App\Models\Post` ↔ `App\Policies\PostPolicy`. Explicit registration if naming differs:

```php
// AppServiceProvider::boot() — Laravel 11+ has no AuthServiceProvider
Gate::policy(Post::class, PostPolicy::class);
```

### 13.2 Invocation

```php
$this->authorize('update', $post);                                              // controller — throws AuthorizationException → 403
Gate::allows('update', $post);                                                  // anywhere
auth()->user()->can('update', $post);                                           // anywhere
$this->authorizeResource(Post::class, 'post');                                  // resource shortcut — maps index/show/store/update/destroy in __construct
Route::put('/posts/{post}', [...])->middleware('can:update,post');              // route middleware
```

Blade: `@can('update', $post) ... @endcan`.

### 13.3 Gate (no model)

```php
Gate::define('access-admin', fn (User $u) => $u->is_admin);   // AppServiceProvider::boot()
Gate::allows('access-admin');
```

⚠️ **Anti-pattern:** authorization via inline role checks (`if ($user->role === 'admin')`). Use Policies/Gates — roles change, abstraction stays.

For Policy composition, `Gate::before`/`after` patterns, multi-tenant authorization (global scope + Policy), Spatie Permission integration when detected, super-admin escape hatches, and authorization in jobs/schedule, load the `laravel-auth` skill.

## 14. Logging & exceptions

**Convention:** dot-notation message + structured context, never interpolated strings — `Log::info('post.published', ['post_id' => $post->id])`.

In Laravel 11+, exception handling lives in `bootstrap/app.php` — there is no `app/Exceptions/Handler.php`:

```php
->withExceptions(function (Exceptions $e) {
    $e->render(fn (NotFoundHttpException $ex, Request $req) => $req->is('api/*')
        ? response()->json(['message' => 'Not found'], 404)
        : null);
    $e->report(fn (Throwable $ex) => Sentry::captureException($ex));
})
```

⚠️ **Anti-pattern:** `Log::info($request->all())` without scrubbing — leaks PII, tokens, passwords. Mask before logging.

## 15. Transactions & afterCommit

```php
DB::transaction(function () use ($order) {
    $order->update(['status' => 'paid']);
    $order->user->increment('credits', $order->total);
    PaymentRecorded::dispatch($order)->afterCommit();
}, attempts: 3);   // retries on deadlock; default is 1
```

Pessimistic lock: `Inventory::where('id', $id)->lockForUpdate()->first()` inside the transaction closure.

⚠️ **Anti-pattern:** `DB::beginTransaction()` without a matching `commit()`/`rollBack()` in a `try/catch`. Always prefer the closure form.

**afterCommit in 3 lines:** any job, queued listener, mail, or notification dispatched inside a transaction may execute before the commit and read stale (or nonexistent) rows. Append `->afterCommit()` to the dispatch, or set `after_commit: true` on the queue connection. Deep treatment (connection-level config, `ShouldQueueAfterCommit`, rollback behavior) is owned by the `laravel-queues` skill.

---

## Rules & anti-patterns — consolidated checklist

Single-page scan list for `code-review` and `security`. Each row names the section that defines the *correct* pattern and gives a runnable detection command.

For backend-specific security touchpoints, see `references/security.md`. For broader OWASP, hardening, headers, dependency CVEs, and compliance, see the `laravel-security` skill.

| Smell | Section | Detection |
|---|---|---|
| Model with neither `$fillable` nor `$guarded` | Model anatomy | `grep -L '\$fillable\|\$guarded' app/Models/*.php` |
| `$request->all()` reaching DB | FormRequests | `grep -rn '\->all()' app/ \| grep -E 'create\|update\|fill'` |
| `{!! !!}` in Blade (XSS surface) | (`laravel-security`) | `grep -rn '{!!' resources/views/` |
| Relationship access in loop without `with()`/`load()` | Eager loading & N+1 | `grep -rn 'preventLazyLoading' app/` (empty = detection off; enable it) |
| Controller > 200 LOC | Controllers | `find app/Http/Controllers -name '*.php' \| xargs wc -l \| sort -rn \| head` |
| `env(` outside `config/` | Config & environment | `grep -rn "env(" app/ routes/ database/` |
| `Log::info($request->all())` (PII leak) | Logging & exceptions | `grep -rn 'Log::' app/ \| grep '\$request->all()'` |
| `DB::beginTransaction` without try/catch + rollback | Transactions & afterCommit | `grep -rn 'beginTransaction' app/` then inspect each hit |
| Queued dispatch inside transaction without `afterCommit()` | Transactions & afterCommit | `grep -rn -A6 'DB::transaction' app/ \| grep 'dispatch('` |
| Authorization via `if ($user->role === ...)` | Authorization | `grep -rn '\->role ==' app/ resources/views/` |
| Cache key from raw user input (no hash) | Cache | `grep -rn 'Cache::' app/ \| grep '\$request->'` |
| `spatie/laravel-actions` (vetoed pattern) | Domain layer | `grep -q 'spatie/laravel-actions' composer.json && echo FOUND` |
| Endpoint accepting input without FormRequest | FormRequests | `grep -rn '(Request \$request' app/Http/Controllers/` + `php artisan route:list --except-vendor` |
| Raw SQL with string interpolation | (`laravel-security`) | `grep -rn 'DB::raw(.*\$' app/` |
| IO in `ServiceProvider::register()` | Service container | `grep -n -A15 'function register' app/Providers/*.php \| grep -E 'DB::\|Http::\|Cache::'` |
| Missing `whenLoaded()` in API Resource | API Resources | `grep -rn '::make(\$this->\|::collection(\$this->' app/Http/Resources/ \| grep -v whenLoaded` |
| Migration `down()` deleting data | Migrations | `grep -rn 'delete()\|truncate()' database/migrations/` |
| Global scope undocumented | Scopes | `grep -rn 'addGlobalScope' app/Models/` then check model docblocks |
| `$with` lazy-loading whole graph in default model | Model anatomy | `grep -rn 'protected \$with' app/Models/` |
| `getXxxAttribute` legacy accessor in new code | Model anatomy | `grep -rn 'function get[A-Z].*Attribute(' app/Models/` |

---

## Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| Changes save locally but a job/listener sees old data | Dispatch inside an uncommitted transaction | Transactions & afterCommit |
| Changes "not persisting" at all | Field missing from `$fillable` (silent discard) or observer mutating on save | Model anatomy; Model events & Observers |
| 403 from `$this->authorize()` on an action that should pass | Policy discovery mismatch (model/policy namespaces differ) | Authorization — `php artisan model:show Post` shows the bound policy; register with `Gate::policy` |
| `config()` returns `null` in production only | `env()` outside `config/` + `config:cache` | Config & environment |
| Rows "missing" from queries | Global scope silently filtering | Scopes |
| Sudden query count spike on a list page | Relation accessed per-row without eager load | Eager loading & N+1 |
| 422 on a field you didn't send | `prepareForValidation` merge or a `required_*` conditional rule | FormRequests & validation |

---

## Cross-references

| Topic | Owner |
|---|---|
| Authentication, guards, Sanctum, Fortify | `laravel-auth` skill |
| Queue execution mechanics, Horizon, scheduler, afterCommit depth | `laravel-queues` skill |
| Inertia protocol (shared, partial, deferred, polling) | `laravel-inertia` skill |
| Vite, `resources/js`, Wayfinder | `laravel-frontend` skill |
| Pest, factories *for tests*, fakes, HTTP testing | `laravel-qa` skill |
| Pint, Larastan, Rector, architecture tests | `laravel-static-analysis` skill |
| OWASP, hardening, headers, dep CVEs, compliance | `laravel-security` skill |
| WCAG, ARIA | `laravel-a11y` skill |
| React/Vue implementation in `resources/js` | `laravel-role-react` / `laravel-role-vue` |
| Deploy, containers, CI/CD, Octane runtime | `laravel-role-devops` |
