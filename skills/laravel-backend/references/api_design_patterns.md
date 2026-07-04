# API Design Patterns — Laravel

REST design choices for Laravel APIs. Loaded when designing or refactoring API endpoints, choosing versioning strategy, or designing error responses.

## 1. Resource controllers

```php
// routes/api.php
Route::apiResource('posts', PostController::class);
// Generates: GET /posts, POST /posts, GET /posts/{post}, PUT/PATCH /posts/{post}, DELETE /posts/{post}
```

Generate the controller with FormRequests:

```bash
php artisan make:controller Api/PostController --api --requests --model=Post
```

Route-model binding handles 404 implicitly:

```php
public function show(Post $post): PostResource
{
    return PostResource::make($post);
}
```

Nested resources:

```php
Route::apiResource('users.posts', UserPostController::class)->shallow();
// "shallow" produces /users/{user}/posts and /posts/{post}, avoiding deep URLs
```

## 2. Versioning

| Strategy | Example | Trade-off |
|---|---|---|
| URL prefix | `/api/v1/posts`, `/api/v2/posts` | Most explicit; simplest tooling |
| Header | `Accept: application/vnd.app.v2+json` | Cleaner URLs; harder to test in browsers |
| Subdomain | `v2.api.example.com` | Independent deploys per version; DNS overhead |

Default to URL prefix unless there's a specific reason. Implement via grouped routes:

```php
// routes/api.php
Route::prefix('v1')->group(base_path('routes/api/v1.php'));
Route::prefix('v2')->group(base_path('routes/api/v2.php'));
```

Namespace controllers per version: `App\Http\Controllers\Api\V1\PostController`.

⚠️ Anti-pattern: branching with `if ($version === 2)` inside a controller. Split into versioned namespaces — divergence becomes orthogonal.

## 3. API Resources — advanced

```php
class PostResource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id'       => $this->id,
            'title'    => $this->title,

            // Conditional attributes — only when truthy
            'is_owner' => $this->when($request->user()?->id === $this->user_id, true),

            // Relationships — only if eager-loaded (avoids N+1)
            'author'   => UserResource::make($this->whenLoaded('author')),
            'tags'     => TagResource::collection($this->whenLoaded('tags')),

            // Pivot data when present
            'role'     => $this->whenPivotLoaded('memberships', fn () => $this->pivot->role),

            // Counts loaded by withCount()
            'comments_count' => $this->whenCounted('comments'),

            // Computed
            'links'    => ['self' => route('posts.show', $this)],
        ];
    }

    // Top-level wrapping — applied to every response
    public function with($request): array
    {
        return ['meta' => ['api_version' => 'v2']];
    }
}
```

### Disable the `data` envelope

If the API does not use the `data` wrapper, disable globally:

```php
// AppServiceProvider::boot()
JsonResource::withoutWrapping();
```

## 4. Error response format

Laravel's default JSON shape after FormRequest validation:

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "email":  ["The email field is required."],
    "tags.0": ["The tags.0 field must be a string."]
  }
}
```

Customize for consistency across all error types in `bootstrap/app.php`:

```php
->withExceptions(function (Exceptions $e) {
    $e->render(function (Throwable $ex, Request $req) {
        if (! $req->expectsJson()) return null;

        return response()->json([
            'error' => [
                'code'    => errorCodeFor($ex),
                'message' => $ex->getMessage(),
                'details' => $ex instanceof ValidationException ? $ex->errors() : null,
            ],
        ], statusFor($ex));
    });
})
```

Choose **one** shape per API and stick to it. Common options:

- Laravel default — `{message, errors}`
- Custom envelope — `{error: {code, message, details}}`
- RFC 7807 (Problem Details) — `{type, title, status, detail, instance}`

## 5. Pagination

| Method | Use | Output |
|---|---|---|
| `paginate(15)` | UI with page numbers | `data`, `links`, `meta` (total, per_page, current_page, last_page) |
| `simplePaginate(15)` | "Next/prev" only | Cheaper — no `COUNT(*)` |
| `cursorPaginate(15)` | Infinite scroll, large datasets | Stable across inserts; opaque cursor |

```php
// Page-numbered
return PostResource::collection(Post::with('author')->paginate(15));

// Cursor — must order by indexed columns
return PostResource::collection(
    Post::orderBy('created_at')->orderBy('id')->cursorPaginate(15)
);
```

## 6. Sorting & filtering

Manual approach (small APIs):

```php
public function index(Request $request)
{
    $allowed = ['created_at', 'title', 'updated_at'];
    $sort    = $request->string('sort', 'created_at')->toString();
    $column  = ltrim($sort, '-');

    abort_unless(in_array($column, $allowed, true), 422, 'Invalid sort column');

    return PostResource::collection(
        Post::query()
            ->when($request->status, fn ($q, $s) => $q->where('status', $s))
            ->when($request->author, fn ($q, $a) => $q->where('user_id', $a))
            ->orderBy($column, str_starts_with($sort, '-') ? 'desc' : 'asc')
            ->paginate()
    );
}
```

Detect `spatie/laravel-query-builder` (`composer show spatie/laravel-query-builder`):

```php
QueryBuilder::for(Post::class)
    ->allowedFilters(['status', AllowedFilter::exact('user_id')])
    ->allowedSorts(['created_at', 'title'])
    ->allowedIncludes(['author', 'tags'])
    ->paginate();
```

⚠️ Anti-pattern: passing user input directly to `orderBy` or column names without an allowlist — column-name injection.

## 7. Idempotency keys

For non-idempotent endpoints (`POST` that creates a charge), accept an `Idempotency-Key` header and cache the response:

```php
public function store(Request $request)
{
    $key = $request->header('Idempotency-Key');
    if ($key) {
        $cached = Cache::get("idempotent:$key");
        if ($cached) return response()->json($cached['body'], $cached['status']);
    }

    $charge   = $this->createCharge(/* ... */);
    $response = ['id' => $charge->id, 'status' => 'created'];

    if ($key) {
        Cache::put("idempotent:$key", ['body' => $response, 'status' => 201], 86400);
    }

    return response()->json($response, 201);
}
```

⚠️ Cache TTL for idempotency keys: 24h is typical for payments, longer (7d) for resource creation. Don't cache forever — memory bloat.

## 8. Rate limiting

Define limiters in `AppServiceProvider::boot()` (Laravel 11+ has no RouteServiceProvider):

```php
RateLimiter::for('api', function (Request $request) {
    return Limit::perMinute(60)->by($request->user()?->id ?: $request->ip());
});

RateLimiter::for('login', function (Request $request) {
    return [
        Limit::perMinute(5)->by($request->ip()),
        Limit::perMinute(3)->by($request->input('email')),
    ];
});
```

Apply via middleware:

```php
Route::middleware('throttle:api')->group(/* ... */);
Route::post('/login', /* ... */)->middleware('throttle:login');
```

Laravel automatically surfaces `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers.

## 9. Webhooks

### Incoming — verify signature

```php
public function handle(Request $request): Response
{
    $signature = $request->header('X-Signature');
    $expected  = hash_hmac('sha256', $request->getContent(), config('webhooks.secret'));

    if (! hash_equals($expected, $signature ?? '')) {
        abort(401);
    }

    // Idempotency — webhooks may be re-sent
    $eventId = $request->json('id');
    if (WebhookEvent::where('event_id', $eventId)->exists()) {
        return response()->noContent();
    }

    WebhookEvent::create(['event_id' => $eventId, 'payload' => $request->all()]);
    ProcessWebhook::dispatch($eventId);

    return response()->noContent();
}
```

⚠️ Use `hash_equals` (constant-time), never `===`, for signature comparison.

### Outgoing — retry strategy

Send via a queued job with `$tries` and `$backoff`:

```php
class SendWebhook implements ShouldQueue
{
    public int $tries = 6;
    public array $backoff = [10, 60, 300, 900, 3600, 7200];   // exponential, in seconds

    public function __construct(public Webhook $webhook, public array $payload) {}

    public function handle(): void
    {
        $signature = hash_hmac('sha256', json_encode($this->payload), $this->webhook->secret);

        $response = Http::withHeaders(['X-Signature' => $signature])
            ->timeout(10)
            ->post($this->webhook->url, $this->payload);

        if (! $response->successful()) {
            throw new RuntimeException("Webhook returned {$response->status()}");
        }
    }

    public function failed(Throwable $e): void
    {
        $this->webhook->markFailed($e);
    }
}
```

After all retries fail, the job lands in `failed_jobs` (see `laravel-queues`). The webhook is then marked dead and surfaced for manual review.

## 10. Anti-patterns

| Smell | Why |
|---|---|
| Mixing versions in same controller via `if ($v === 2)` | Couples branches; split into versioned namespaces |
| Inconsistent error response shape across endpoints | Clients must handle multiple formats |
| Returning Eloquent model directly without API Resource | Exposes hidden columns; no transformation |
| Missing `whenLoaded()` for relationships in resources | N+1 |
| `paginate()` on infinite-scroll endpoint | `COUNT(*)` cost |
| User input flowing into `orderBy` / column names | Column-name injection |
| Webhook accepting events without idempotency check | Duplicate processing |
| Webhook signature compared with `===` | Timing attack — use `hash_equals` |
| Outgoing webhook without retry/backoff | Transient failures lose data |
| API without rate limiting | Abusable; resource exhaustion |
| Idempotency key cached forever | Memory bloat |
| Public API endpoint without `auth:sanctum` AND no rate limit | Trivial abuse vector |
