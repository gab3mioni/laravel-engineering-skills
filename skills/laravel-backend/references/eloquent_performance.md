# Eloquent — Performance & Query Optimization

Practical patterns for apps that have outgrown the prototype. Loaded when scaling reads, processing large datasets, or fixing N+1 issues.

## 1. Iterating large datasets

Loading a million rows via `->get()` exhausts memory. Pick the right primitive:

| Method | Behavior | When |
|---|---|---|
| `chunk($n, $cb)` | Pages of N rows; offset-based | Read-only iteration over stable data |
| `chunkById($n, $cb)` | Pages ordered by primary key | Iteration that may mutate rows |
| `cursor()` | Generator, one row at a time | Streaming over arbitrary size |
| `lazy($n)` | LazyCollection wrapping chunked load | Composable transformations |
| `lazyById($n)` | LazyCollection over `chunkById` | Composable + safe under mutation |

```php
// Process posts without loading all in memory
Post::where('archived_at', null)->chunkById(500, function ($posts) {
    foreach ($posts as $post) {
        $post->refreshSlug();
    }
});

// Streaming with cursor
foreach (Post::cursor() as $post) { /* ... */ }

// Composable transformation
Post::lazyById(500)
    ->filter(fn ($p) => $p->shouldIndex())
    ->each(fn ($p) => $p->index());
```

⚠️ `chunk()` while updating the rows you iterate breaks pagination — rows shift across pages and some are skipped. Always use `chunkById()` when mutating.

## 2. Reading the query plan

Capture queries while reproducing the slow path:

```php
DB::listen(function (QueryExecuted $q) {
    if ($q->time > 100) {
        Log::warning('slow.query', [
            'sql'      => $q->sql,
            'bindings' => $q->bindings,
            'ms'       => $q->time,
        ]);
    }
});
```

For ad-hoc analysis:

```php
DB::enableQueryLog();
// ... run code ...
dd(DB::getQueryLog());
```

Run `EXPLAIN <query>` directly:

| Sign | Meaning |
|---|---|
| `Seq Scan` (Postgres) / `ALL` (MySQL) | No index used — full table scan |
| `Index Scan` / `range` | Index in use |
| `Filesort` (MySQL) / `Sort` (Postgres) | ORDER BY not covered by index |
| `Using temporary` | Aggregation/DISTINCT building intermediate table |
| `Using join buffer` | Join column lacks index |

## 3. Indexes that cover Eloquent queries

| Query pattern | Index |
|---|---|
| `where('user_id', X)` | Single column on `user_id` |
| `where('user_id', X)->orderBy('created_at')` | Composite `(user_id, created_at)` |
| `where('status', 'active')->where('user_id', X)` | Composite `(user_id, status)` if `user_id` is more selective |
| `whereIn('id', [...])` | Primary key suffices |
| `cursorPaginate()` ordered by `(created_at, id)` | Composite `(created_at, id)` |
| `whereHas('comments', fn ($q) => $q->where('approved', 1))` | Index on `comments.approved` (subquery uses it) |

Composite-index column order: most-selective first, then the column used in `ORDER BY`.

## 4. N+1 detection

Enable strict mode in non-production environments:

```php
// AppServiceProvider::boot()
Model::shouldBeStrict(! app()->isProduction());

// Or explicit toggles
Model::preventLazyLoading(! app()->isProduction());
Model::preventSilentlyDiscardingAttributes(! app()->isProduction());
Model::preventAccessingMissingAttributes(! app()->isProduction());
```

`preventLazyLoading` throws `LazyLoadingViolationException` whenever a relationship is accessed without prior `with()`/`load()`. Catching N+1 in CI keeps it out of production.

For projects without strict mode, `barryvdh/laravel-debugbar` (dev only) and `beyondcode/laravel-query-detector` report N+1 in the response.

## 5. Eager-loading constraints

```php
// Limit loaded relationship rows
Post::with(['comments' => fn ($q) => $q->latest()->limit(3)])->get();

// Aggregate without loading children
Post::withCount('comments')->get();        // adds comments_count
Post::withSum('orders', 'total')->get();   // adds orders_sum_total
Post::withAvg('reviews', 'rating')->get();
Post::withMin('events', 'happens_at')->get();
Post::withMax('events', 'happens_at')->get();

// Single query with relation filter
Post::withWhereHas('comments', fn ($q) => $q->where('approved', true))->get();

// Conditional eager
Post::query()
    ->when($includeAuthor, fn ($q) => $q->with('author'))
    ->get();
```

## 6. Pagination performance

| Method | Cost | When |
|---|---|---|
| `paginate()` | One COUNT + one SELECT | Page numbers, jumping pages |
| `simplePaginate()` | SELECT with `LIMIT N+1` | "Next/prev" only, no total count |
| `cursorPaginate()` | SELECT keyed by ordered column | Infinite scroll, large datasets |

`paginate()`'s COUNT(*) on a multi-million-row table dominates total query time. For feeds and infinite lists, `cursorPaginate()` ordered by an indexed `(created_at, id)` pair is dramatically cheaper.

```php
// Cursor pagination — stable ordering required
$posts = Post::orderBy('created_at')->orderBy('id')->cursorPaginate(20);
```

## 7. Read replicas

When read load saturates the primary:

```php
// config/database.php
'mysql' => [
    'read'   => ['host' => env('DB_READ_HOST')],
    'write'  => ['host' => env('DB_WRITE_HOST')],
    'sticky' => true,           // route reads to writer for the rest of the request after a write
    // ... other keys ...
],
```

`sticky` keeps reads on the writer for the rest of the request after any write — avoids reading stale data from a replica that hasn't caught up.

## 8. Anti-patterns

| Smell | Why |
|---|---|
| `Model::all()` without limit/paginate | Loads entire table into memory |
| `chunk()` while mutating iterated rows | Breaks pagination, skips rows |
| `paginate()` on million-row table for infinite scroll | COUNT(*) dominates total time |
| `whereHas` on relation column without index | Subquery does full scan |
| Lazy loading inside an iteration | N+1 |
| `get()` then `count($result)` | Materializes data; use `->count()` directly |
| `select *` when you need 2 columns | Wastes IO and memory |
| Default eager `$with` for heavy relations | Pays the cost on every query, even where unused |
| Missing index on FK | `belongsTo` lookup does a scan |
| `whereNotIn` with very large list | Slow; rephrase as `whereNotExists` or LEFT JOIN |
