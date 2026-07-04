---
name: laravel-backend
description: Server-side core for Laravel 12 / PHP 8.3+ — Eloquent (models, relationships, eager loading, scopes, casts, observers), migrations, factories, seeders, FormRequests, validation, Resource Controllers, API Resources, Actions/Services/DTOs, service container, providers, events/listeners, mail, notifications, cache, middleware, config, policies, gates, logging, transactions, PSR/SOLID alignment, and consolidated anti-patterns. Consumed by the backend, security, and code-review agents.
---

# Laravel Backend — Server-side core

Idiomatic Laravel 12 / PHP 8.3+ patterns for server-side code. Optimized for agents that *write* (`backend`), *audit* (`security`), or *review* (`code-review`) backend code.

## When to use this skill

- Designing or modifying Eloquent models, migrations, controllers, FormRequests, API Resources, Actions/Services, jobs, events, observers, policies
- Reviewing server-side code in PRs
- Detecting server-side anti-patterns (N+1, mass assignment, env leakage, missing FormRequest)

## When NOT to use

| Topic | Use instead |
|---|---|
| Authentication, guards, Sanctum, Fortify, Breeze | `laravel-auth` |
| Queue execution, Horizon, scheduler internals | `laravel-queues` |
| Vite, `resources/js`, Ziggy, asset pipeline | `laravel-frontend` |
| Inertia protocol (shared data, partial reloads, deferred props) | `laravel-inertia` |
| Pest, factories *for tests*, fakes, HTTP testing | `laravel-qa` |
| Pint, Larastan, Rector | `laravel-static-analysis` |
| OWASP, CSP, hardening, dep CVEs, compliance | `laravel-security` |
| WCAG, ARIA | `laravel-a11y` |

## Stack assumptions

- Laravel 12, PHP 8.3+ (use 8.4 features when project's `composer.json` allows)
- Eloquent for persistence
- Pest as the default test runner (testing details in `laravel-qa`)
- **Detection-based**: agent runs `composer show <pkg>` to adapt to ecosystem packages (Spatie Data, Permission, Query Builder). Skill documents native patterns; only adopts a third-party convention when detected in the project.

---

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

    public function comments(): HasMany
    {
        return $this->hasMany(Comment::class);
    }

    public function tags(): MorphToMany
    {
        return $this->morphToMany(Tag::class, 'taggable');
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

| Type | Methods | Example |
|---|---|---|
| One-to-one | `hasOne`, `belongsTo` | User → Profile |
| One-to-many | `hasMany`, `belongsTo` | User → Posts |
| Many-to-many | `belongsToMany` | User ↔ Role (pivot) |
| Has-many-through | `hasManyThrough` | Country → Posts via User |
| Polymorphic 1:N | `morphMany`, `morphTo` | Comment on Post or Video |
| Polymorphic M:N | `morphToMany`, `morphedByMany` | Tag on multiple types |

For pivot models, recursive relationships, and JSON column relationships, see `references/eloquent_advanced.md`.

### 1.3 Eager loading & N+1

```php
// Up-front
$posts = Post::with(['author', 'tags'])->get();

// After fetch
$posts->load('comments');
$posts->loadMissing('comments');     // skip if already loaded

// Nested
Post::with('author.profile')->get();

// Constrained
Post::with(['comments' => fn ($q) => $q->latest()->limit(3)])->get();

// Counts
Post::withCount('comments')->get();  // adds `comments_count`
```

⚠️ **Anti-pattern:** relationship access inside a loop without prior `with()`/`load()` — N+1.

For runtime N+1 detection (`Model::preventLazyLoading`), `chunk`/`cursor`/`lazy` iteration, query-plan reading, indexes that cover Eloquent queries, and read-replica config, see `references/eloquent_performance.md`.

### 1.4 Scopes

**Local scope** — instance method `scopeXxx`, called as `Model::xxx()`:

```php
Post::published()->latest()->paginate();
```

**Global scope** — registered via `static::addGlobalScope(new MyScope)` in the model's `booted()` method, applied to every query. Use sparingly; document in the model docblock. Multi-tenant pattern (tenant_id scope + Policy as defense in depth) lives in `references/authorization_patterns.md` §5.

⚠️ Global scopes hide rows from queries — easy to forget when debugging "missing data". Use `Model::withoutGlobalScope(...)` only with awareness.

### 1.5 Casts (built-in & custom)

Built-in: `int`, `float`, `bool`, `string`, `array`, `collection`, `datetime`, `date`, `decimal:2`, `encrypted`, `encrypted:array`, `enum:Backed`.

Custom casts for value objects: implement `CastsAttributes` (`get`/`set` methods that translate between DB and PHP). Generate with `php artisan make:cast Money`. See `references/eloquent_advanced.md` for a full example.

### 1.6 Model events & Observers

```php
class PostObserver
{
    public function created(Post $post): void
    {
        Cache::forget("posts.feed.{$post->user_id}");
    }

    public function deleting(Post $post): void
    {
        Log::info('post.deleting', ['id' => $post->id]);
    }
}

// AppServiceProvider::boot()
Post::observe(PostObserver::class);
```

**Heuristic:**
- **Observer** — behavior tied to model lifecycle (created/updated/deleted), runs on every save regardless of caller.
- **Event + Listener** — domain action with multiple subscribers, can be queued, can fail independently.
- **Direct call** — single, synchronous follow-up; trivial.

⚠️ Don't put HTTP calls or queue dispatches in observers without `afterCommit()` (see §15).

---

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
            $t->json('meta')->nullable();
            $t->timestamps();
            $t->softDeletes();

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
- Production: never drop a column without first deploying code that stops reading it.

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

For zero-downtime migration patterns, FK cascade choices, JSON-vs-side-table decisions, and multi-DB compatibility, see `references/schema_and_migration_safety.md`.

---

## 3. Controllers

### 3.1 Resource controller

```php
class PostController extends Controller
{
    public function __construct(private PostRepository $posts) {}

    public function index(): View
    {
        return view('posts.index', ['posts' => $this->posts->paginated()]);
    }

    public function store(StorePostRequest $request): RedirectResponse
    {
        $post = $this->posts->create($request->validated());
        return to_route('posts.show', $post);
    }
}
```

Generate: `php artisan make:controller PostController --resource --requests --model=Post`.

### 3.2 Single-action controller

```php
final class PublishPost
{
    public function __invoke(Post $post): RedirectResponse
    {
        $this->authorize('publish', $post);
        $post->update(['published_at' => now()]);
        PostPublished::dispatch($post);
        return back()->with('status', 'Published');
    }
}

// routes/web.php
Route::post('/posts/{post}/publish', PublishPost::class);
```

⚠️ **Anti-pattern:** controller > 200 LOC. Move logic to Action, Service, or Job.

### 3.3 Route-model binding

```php
Route::get('/posts/{post}', [PostController::class, 'show']);     // by primary key
Route::get('/posts/{post:slug}', [PostController::class, 'show']); // by `slug` column
```

Custom resolution:

```php
Route::bind('post', fn ($value) => Post::published()->whereSlug($value)->firstOrFail());
```

---

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

    public function prepareForValidation(): void
    {
        $this->merge(['title' => trim($this->title)]);
    }

    public function messages(): array
    {
        return ['tags.*.exists' => 'Unknown tag: :input'];
    }
}
```

**Rules:**
- Use FormRequest for every endpoint that accepts input. ⚠️ Anti-pattern: `$request->all()` reaching the DB.
- Always pass `$request->validated()` (or a DTO built from it) downstream — never `$request->input(...)` after validation.
- `$request->validate([...])` inline is acceptable for trivial 1–2 rule cases.

### 4.1 Custom rule

Implement `Illuminate\Contracts\Validation\ValidationRule` — single `validate(string $attribute, mixed $value, Closure $fail): void` method. Generate with `php artisan make:rule Uppercase`. Apply inline: `'code' => ['required', new Uppercase]`.

### 4.2 Conditional rules

```php
'discount' => ['required_if:type,promo', 'numeric', 'min:0'],
```

For complex conditional logic, build the array dynamically inside `rules()` based on `$this->input(...)`. Built-in helpers: `required_if`, `required_unless`, `required_with`, `prohibited_if`, `sometimes`.

---

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
            'links'     => ['self' => route('posts.show', $this)],
        ];
    }
}

// Controller
return PostResource::collection(Post::with('author')->paginate());
```

**Rules:**
- Always use `whenLoaded()` for relationships — exposing an unloaded relation triggers N+1.
- Disable the `data` envelope globally with `JsonResource::withoutWrapping()` in `AppServiceProvider::boot()` if not used.
- For versioning, conditional attributes (`when`, `whenPivotLoaded`, `whenCounted`), error format (Laravel default vs RFC 7807), pagination, sorting/filtering, idempotency keys, rate limiting, and webhooks (HMAC + retry), see `references/api_design_patterns.md`.

---

## 6. Domain layer — Actions, Services, DTOs

### 6.1 Where does logic go?

| Location | When |
|---|---|
| Controller | Trivial (1–3 lines, no business rule) |
| **Action** class | One business operation, called from 1–2 places |
| **Service** | Cohesive group of operations on the same aggregate |
| Model | Pure data behavior (accessors, scopes, simple calculations) |
| Job | Same as Action, but async |

### 6.2 Action class — plain PHP (recommended)

```php
final class PublishPost
{
    public function __construct(
        private PostRepository $posts,
        private Dispatcher $events,
    ) {}

    public function handle(Post $post): Post
    {
        $post->update(['published_at' => now()]);
        $this->events->dispatch(new PostPublished($post));
        return $post;
    }
}

// Usage
app(PublishPost::class)->handle($post);
```

⚠️ **Anti-pattern:** introducing `spatie/laravel-actions`. The community has consolidated on plain classes; the package adds magic without enough payoff. Stick to `handle()` or `__invoke()`.

### 6.3 DTO — detect the project's convention

Run `composer show spatie/laravel-data --quiet 2>/dev/null` to detect.

**If the project uses `spatie/laravel-data`** — use `Data` classes; auto-mapping from FormRequest is the win:

```php
final class PostData extends Data
{
    public function __construct(
        public string $title,
        public string $body,
        public ?Carbon $published_at = null,
    ) {}
}

// In controller
$data = PostData::from($request);
```

**If not (greenfield default)** — readonly classes + a static factory:

```php
final readonly class PostData
{
    public function __construct(
        public string $title,
        public string $body,
        public ?Carbon $published_at = null,
    ) {}

    public static function fromRequest(StorePostRequest $r): self
    {
        return new self(
            title: $r->validated('title'),
            body: $r->validated('body'),
            published_at: $r->date('published_at'),
        );
    }
}
```

---

## 7. Service container & providers

### 7.1 Bindings

In a `ServiceProvider::register()` — **only** bindings, no logic, no IO:

```php
$this->app->singleton(PostRepository::class, EloquentPostRepository::class);
$this->app->bind(PaymentGateway::class, StripeGateway::class);
$this->app->scoped(RequestContext::class);   // per request (Octane-aware)
```

| Method | Lifetime |
|---|---|
| `bind` | New instance every resolution |
| `singleton` | Same instance for app lifetime |
| `scoped` | Same instance per request (works correctly under Octane) |
| `instance` | Pre-built object |

### 7.2 Contextual binding

```php
$this->app->when(LegacyImporter::class)
          ->needs(PostRepository::class)
          ->give(LegacyPostRepository::class);
```

### 7.3 register() vs boot()

- `register()` — only `$this->app->bind/singleton(...)`. Container isn't booted; **no DB calls, no facade calls, no env reads at runtime**.
- `boot()` — observer registration, route macros, view composers, custom validation rules, event subscriptions, config publishing.

⚠️ **Anti-pattern:** IO in `register()` (`DB::`, `Http::`, `env()` indirectly via models).

---

## 8. Events, listeners, observers

### 8.1 Choice

| Use | When |
|---|---|
| Observer | Reaction tied to model lifecycle |
| Event + Listener | Domain action with subscribers; can be queued; can fail independently |
| Direct call | Single, synchronous follow-up; trivial |

### 8.2 Queued listener

```php
class SendPostPublishedNotification implements ShouldQueue
{
    use InteractsWithQueue;

    public function handle(PostPublished $event): void
    {
        $event->post->author->notify(new PostPublishedNotification($event->post));
    }

    public function failed(PostPublished $event, Throwable $e): void
    {
        Log::error('listener.failed', ['post' => $event->post->id, 'error' => $e->getMessage()]);
    }
}
```

For `Event::fake()` and assertion helpers, see `laravel-qa`.

---

## 9. Mail & notifications

### 9.1 Mailable

```php
class PostPublished extends Mailable
{
    use Queueable, SerializesModels;

    public function __construct(public Post $post) {}

    public function envelope(): Envelope
    {
        return new Envelope(subject: "Your post is live: {$this->post->title}");
    }

    public function content(): Content
    {
        return new Content(markdown: 'mail.posts.published');
    }
}

// Usage
Mail::to($user)->queue(new PostPublished($post));
```

### 9.2 Notification (multi-channel)

```php
class PostPublishedNotification extends Notification implements ShouldQueue
{
    use Queueable;

    public function __construct(public Post $post) {}

    public function via($notifiable): array
    {
        return ['mail', 'database'];
    }

    public function toMail($notifiable): MailMessage  { /* ... */ }
    public function toArray($notifiable): array       { return ['post_id' => $this->post->id]; }
}
```

**Rule:** prefer **Notification** when delivery may span multiple channels or needs DB persistence; **Mailable** for email-only.

---

## 10. Cache

```php
$posts = Cache::remember(
    "posts.feed.{$userId}",
    300,
    fn () => Post::feed($userId)->get(),
);
```

⚠️ **Anti-pattern:** cache key derived from raw user input without hashing. Risks key injection and oversized keys. Use `hash('xxh128', $input)` for arbitrary input.

For stampede prevention (lock + recompute, `Cache::flexible`, jitter), tagged invalidation, atomic locks (`Cache::lock`), layered caches, invalidation strategies (TTL/event/tag/versioned keys), and Redis-specific patterns, see `references/cache_patterns.md`.

---

## 11. Middleware

```php
class EnsureFeatureEnabled
{
    public function handle(Request $request, Closure $next, string $feature): Response
    {
        abort_unless(Feature::active($feature), 404);
        return $next($request);
    }
}

// Route::middleware(['feature:beta-search'])->group(...);
```

In Laravel 11+, middleware is registered in `bootstrap/app.php`:

```php
->withMiddleware(function (Middleware $m) {
    $m->alias(['feature' => EnsureFeatureEnabled::class]);
    $m->web(append: [SetLocale::class]);
    $m->throttleApi('60,1');
})
```

**Terminable middleware** — implement `terminate(Request, Response): void` for post-response work.

---

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

---

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

```blade
@can('update', $post) ... @endcan
```

### 13.3 Gate (no model)

```php
// AppServiceProvider::boot()
Gate::define('access-admin', fn (User $u) => $u->is_admin);

Gate::allows('access-admin');
```

⚠️ **Anti-pattern:** authorization via inline role checks (`if ($user->role === 'admin')`). Use Policies/Gates — roles change, abstraction stays.

For Policy composition, `Gate::before`/`after` patterns, multi-tenant authorization (global scope + Policy), Spatie Permission integration when detected, super-admin escape hatches, and authorization in jobs/schedule, see `references/authorization_patterns.md`.

---

## 14. Logging & exceptions

```php
Log::info('post.published', ['post_id' => $post->id, 'user_id' => $post->user_id]);
Log::channel('slack')->error('payment.failed', $context);

report($exception);                           // log + send to handler
report_if($condition, $exception);            // conditional
throw_if($condition, ModelNotFoundException::class);
rescue(fn () => $risky(), fallback: null);    // catch + report, return fallback
```

In Laravel 11+, exception handling lives in `bootstrap/app.php`:

```php
->withExceptions(function (Exceptions $e) {
    $e->render(function (NotFoundHttpException $ex, Request $req) {
        return $req->is('api/*')
            ? response()->json(['message' => 'Not found'], 404)
            : null;
    });

    $e->report(fn (Throwable $ex) => Sentry::captureException($ex));
})
```

⚠️ **Anti-pattern:** `Log::info($request->all())` without scrubbing — leaks PII, tokens, passwords. Mask before logging.

---

## 15. DB transactions, locks, atomicity

```php
DB::transaction(function () use ($order) {
    $order->update(['status' => 'paid']);
    $order->user->increment('credits', $order->total);
    PaymentRecorded::dispatch($order);
});
```

`DB::transaction($callback, $attempts = 1)` — defaults to no retry. Pass `$attempts = 3` to retry on deadlock.

Pessimistic lock:

```php
DB::transaction(function () use ($id) {
    $row = Inventory::where('id', $id)->lockForUpdate()->first();
    $row->decrement('stock');
});
```

⚠️ **Anti-pattern:** `DB::beginTransaction()` without a matching `commit()`/`rollBack()` in a `try/catch`. Always prefer the closure form.

⚠️ **Anti-pattern:** queueing a job inside a transaction without `afterCommit()` — the worker may pick it up before the transaction commits and read stale data:

```php
PostPublished::dispatch($post)->afterCommit();
```

---

## 16. PSR alignment

| PSR | What | In Laravel |
|---|---|---|
| **PSR-4** | Autoload mapping | `composer.json` — `App\\` → `app/` |
| **PER-CS 2.0** | Code style (replaces PSR-12) | Pint `per` preset; details in `laravel-static-analysis` |
| **PSR-3** | Logger interface | `Log` facade is a PSR-3 instance |
| **PSR-11** | Container | `app(...)` and `Container::make` are PSR-11 compatible |
| **PSR-7/15/17** | HTTP messages/middleware | Only when exposing reusable middleware libraries |

---

## 17. SOLID applied

| Principle | Laravel application |
|---|---|
| **SRP** | Slim controllers; one Action per business operation; split god services |
| **OCP** | Use Policies and Events for extension instead of branching on roles |
| **LSP** | Type-hint contracts (`Illuminate\Contracts\*`) before concrete classes |
| **ISP** | Small interfaces; Laravel's own `Illuminate\Contracts\*` (often single-method) are exemplary |
| **DIP** | Inject interfaces via constructor; the container resolves; never `new SomeService()` |

---

## 18. Tooling — `php artisan` quick reference

| Command | Output |
|---|---|
| `make:model Post -mfsrc` | Model + migration + factory + seeder + resource controller + cast |
| `make:controller PostController --api --requests --model=Post` | API controller + StorePostRequest + UpdatePostRequest |
| `make:request StorePostRequest` | FormRequest stub |
| `make:resource PostResource` | API resource |
| `make:policy PostPolicy --model=Post` | Policy with stub methods bound to model |
| `make:observer PostObserver --model=Post` | Observer pre-bound |
| `make:event PostPublished` | Event class |
| `make:listener SendPostPublishedNotification --event=PostPublished` | Listener pre-bound |
| `make:job ProcessPost` | Queued job stub |
| `make:cast Money` | Custom cast |
| `make:rule Uppercase` | Validation rule object |
| `make:middleware EnsureFeatureEnabled` | Middleware stub |
| `route:list --except-vendor` | Project-only routes (skip framework) |
| `db:show`, `db:table users` | Schema introspection |
| `model:show Post` | Properties, relationships, casts of a model |

---

## 19. HTTP status codes — Laravel idioms

| Code | When | Idiomatic helper |
|---|---|---|
| 200 | OK with body | `response()->json($payload)` |
| 201 | Created | `response()->json($r, 201)` |
| 202 | Accepted (async) | `response()->noContent(202)` |
| 204 | No content (DELETE success) | `response()->noContent()` |
| 302 | Redirect (web) | `to_route(...)`, `back()` |
| 400 | Bad request (malformed) | `abort(400)` |
| 401 | Unauthenticated | thrown by `auth` middleware |
| 403 | Authorization denied | thrown by `$this->authorize()` |
| 404 | Not found | thrown by route-model binding, `abort(404)` |
| 409 | Conflict | `abort(409, 'Already published')` |
| 422 | Validation failed | thrown by FormRequest |
| 429 | Rate limited | thrown by `throttle` middleware |
| 5xx | Server error | unhandled exception → handler |

---

## 20. Anti-patterns — consolidated checklist

Single-page scan list for `code-review` and `security`. Each row links to the section that defines the *correct* pattern.

For backend-specific security touchpoints (mass assignment depth, raw query bindings, file upload, queue payload hygiene, safe logging), see `references/security.md`. For broader OWASP, hardening, headers, dependency CVEs, and compliance, see the `laravel-security` skill.

| Smell | Section | Detection |
|---|---|---|
| Model with neither `$fillable` nor `$guarded` | §1.1 | grep `extends Model` then inspect |
| `$request->all()` reaching DB | §4 | grep `\$request->all\(\)` near `create\|update\|fill` |
| `{!! !!}` in Blade (XSS surface) | (laravel-security) | grep `{!!` |
| Relationship access in loop without `with()`/`load()` | §1.3 | review or `Model::preventLazyLoading()` |
| Controller > 200 LOC | §3.2 | `wc -l app/Http/Controllers/**/*.php` |
| `env(` outside `config/` | §12 | `grep -rn "env(" app/ routes/ database/` |
| `Log::info($request->all())` (PII leak) | §14 | grep |
| `DB::beginTransaction` without try/catch with rollback | §15 | review |
| Queued job inside transaction without `afterCommit()` | §15 | review of `dispatch` inside `DB::transaction` |
| Authorization via `if ($user->role === ...)` | §13 | grep `->role ==` |
| Cache key from raw user input (no hash) | §10 | grep `Cache::.*\$request->` |
| `spatie/laravel-actions` (deprecated pattern) | §6.2 | `composer show` |
| Endpoint accepting input without FormRequest | §4 | route inspection |
| Raw SQL with string interpolation | (laravel-security) | grep `DB::raw\(.*\$` |
| IO in `ServiceProvider::register()` | §7.3 | review |
| Missing `whenLoaded()` in API Resource | §5 | review |
| Migration `down()` deleting data | §2.1 | review |
| Global scope undocumented | §1.4 | review |
| `$with` lazy-loading whole graph in default model | §1.1 | review |
| `getXxxAttribute` legacy accessor in new code | §1.1 | grep `function get.*Attribute\(` |

---

## 21. Cross-references

| Topic | Skill |
|---|---|
| Authentication, guards, Sanctum, Fortify | `laravel-auth` |
| Queue execution mechanics, Horizon, scheduler | `laravel-queues` |
| Inertia protocol (shared, partial, deferred, polling) | `laravel-inertia` |
| Vite, `resources/js`, Ziggy | `laravel-frontend` |
| Pest, factories *for tests*, fakes, HTTP testing | `laravel-qa` |
| Pint, Larastan, Rector, architecture tests | `laravel-static-analysis` |
| OWASP, hardening, headers, dep CVEs, compliance | `laravel-security` |
| WCAG, ARIA | `laravel-a11y` |
