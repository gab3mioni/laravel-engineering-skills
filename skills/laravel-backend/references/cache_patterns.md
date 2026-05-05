# Cache Patterns

Patterns for correctness under load. Loaded when designing cache strategy, debugging stampede issues, or coordinating invalidation across writers.

## 1. Cache stampede

When TTL expires, every concurrent request misses simultaneously and rebuilds the value, hammering the data source. Four mitigations.

### 1.1 Lock + recompute

```php
$value = Cache::get('feed.user.42');
if ($value !== null) {
    return $value;
}

$lock = Cache::lock('feed.user.42:lock', 10);
if ($lock->get()) {
    try {
        $value = Feed::for(42)->get();
        Cache::put('feed.user.42', $value, 300);
    } finally {
        $lock->release();
    }
} else {
    // Another worker is rebuilding — wait briefly and retry, or return stale
    sleep(1);
    return Cache::get('feed.user.42');
}
return $value;
```

### 1.2 Stale-while-revalidate (`Cache::flexible`)

Laravel 11+ ships a primitive for this:

```php
$value = Cache::flexible('feed.user.42', [60, 300], fn () => Feed::for(42)->get());
```

- Fresh up to 60 seconds — return cached value
- Between 60 and 300 — return cached AND trigger background refresh
- After 300 — full miss, recompute synchronously

### 1.3 TTL jitter

Spread expirations across a window so they don't all stampede at once:

```php
Cache::put($key, $value, 300 + random_int(0, 60));
```

### 1.4 Cache warming

After a deploy, populate the hot keys before traffic does:

```php
foreach (User::active()->cursor() as $user) {
    Cache::remember("feed.user.{$user->id}", 300, fn () => Feed::for($user->id)->get());
}
```

Schedule warmup ahead of known traffic peaks (e.g., 5 minutes before a marketing email send).

## 2. Read-through pattern

```php
$value = Cache::remember(
    "posts.feed.{$userId}",
    300,
    fn () => Post::feed($userId)->get(),
);
```

Combine with stampede protection above when the underlying query is heavy.

## 3. Layered cache

For very hot data, an in-process layer beats Redis (no network round-trip):

```php
final class PostCache
{
    private array $local = [];

    public function get(string $key): mixed
    {
        if (isset($this->local[$key])) {
            return $this->local[$key];
        }

        $value = Cache::remember($key, 300, fn () => $this->loadFromDb($key));
        $this->local[$key] = $value;
        return $value;
    }
}
```

Bind as singleton in a ServiceProvider. Under Octane, the singleton lives across requests in the same worker, so the local layer is meaningful between requests. Under FPM, it lasts for one request — still useful for repeated calls within the request.

## 4. Invalidation strategies

| Strategy | When | Trade-offs |
|---|---|---|
| TTL only | Eventually-consistent reads acceptable | Simplest; staleness window equal to TTL |
| TTL + event invalidation | Need fresh-after-write | Observer calls `Cache::forget(...)` |
| Tag-based flush | Flush groups (Redis/Memcached only) | `Cache::tags(...)->flush()` |
| Versioned keys | No flush needed; cheap GC | Increment version on write; old keys expire by TTL |

### TTL + event

```php
class PostObserver
{
    public function saved(Post $post): void
    {
        Cache::forget("posts.feed.{$post->user_id}");
        Cache::forget("posts.show.{$post->id}");
    }
}
```

### Tag-based

```php
Cache::tags(['posts', "user:{$userId}"])
     ->remember("posts.feed.{$userId}", 300, fn () => /* ... */);

// Invalidate all of user 42's cached posts
Cache::tags("user:42")->flush();
```

⚠️ Tags require Redis or Memcached store. Calling `Cache::tags()` on `database` or `file` store throws `BadMethodCallException`.

### Versioned keys

```php
$version = Cache::rememberForever("posts.version.{$userId}", fn () => 1);
$key     = "posts.feed.{$userId}.v{$version}";
$value   = Cache::remember($key, 300, fn () => /* ... */);

// Invalidate by bumping the version
Cache::increment("posts.version.{$userId}");
```

Old `v1` keys remain in Redis but expire by TTL — no flush needed, no scan, constant time.

## 5. Cache key design

| Rule | Why |
|---|---|
| Namespace by domain | Avoid collisions: `posts.feed.42`, not `feed-42` |
| Hash arbitrary input | `hash('xxh128', $input)` — bounded length, no special chars |
| Embed version when format changes | `posts.v2.feed.42` allows safe rollouts |
| Never embed secrets | Keys appear in logs, monitoring, slow-query dumps |
| Deterministic ordering of params | Sort array keys before hashing — `[a=1,b=2]` and `[b=2,a=1]` should yield the same key |

## 6. Atomic locks

```php
// Try-lock — non-blocking
$lock = Cache::lock('payment.process.123', 10);
if ($lock->get()) {
    try {
        processPayment(123);
    } finally {
        $lock->release();
    }
} else {
    abort(409, 'Payment already in progress');
}

// Block-lock — wait up to N seconds
Cache::lock('feed.rebuild', 10)->block(5, function () {
    rebuildFeed();
});
```

Use locks for:
- Idempotent jobs that may be re-dispatched
- Mutually-exclusive operations (rebuilds, migrations, payment processing)
- Stampede prevention (§1.1)

## 7. When NOT to cache

- Per-request data with no reuse (current request's params)
- Trivial computations cheaper than the cache round-trip
- Data that must be perfectly consistent (counters: prefer DB increment + atomic lock)
- Security-sensitive data — tokens and sessions have dedicated stores (`session`, `auth`), not `Cache`

## 8. Anti-patterns

| Smell | Why |
|---|---|
| `Cache::remember` on heavy compute without lock | Stampede on every TTL expiry |
| TTL = forever without invalidation strategy | Silent staleness builds up |
| Cache key from raw user input without hash | Key injection, oversized keys |
| `Cache::tags(...)->flush()` on `database` store | Throws at runtime |
| `KEYS *` in Redis production | Blocks the server (use `SCAN`) |
| Caching whole DB query when only a derived value is needed | Wastes memory; should cache the processed result |
| Cache writes with zero coordination across writers | Last write wins; inconsistencies pile up |
| Storing serialized model objects | Brittle to schema changes; cache plain arrays |
| Cache key without app/version namespace | Cross-environment collisions in shared Redis |
