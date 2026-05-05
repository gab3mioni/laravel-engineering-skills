# Security Touchpoints — Backend

Security concerns that show up in the backend developer's daily work — controllers, models, FormRequests, queries, queues, logs. Loaded when writing or reviewing server-side code.

For application-wide security posture (OWASP Top 10, hardening, headers, dependency CVEs, compliance), see the `laravel-security` skill.

## 1. Mass assignment

The single highest-leverage server-side smell. Always declare `$fillable` or `$guarded = []`, never both, never neither.

```php
class User extends Model
{
    protected $fillable = ['name', 'email'];   // explicit allowlist
}
```

The dangerous case — `User` mass-update where the model has an `is_admin` column:

```php
// BAD — anything in the request becomes a column
$user->fill($request->all())->save();

// BAD — same problem
User::create($request->all());

// GOOD — validated data only, with FormRequest guarantees
$user->fill($request->validated())->save();
User::create($request->validated());
```

⚠️ `$request->only(['name', 'email'])` is a workaround, not a substitute for FormRequest. FormRequest co-locates validation, authorization, and field allowlist.

## 2. FormRequest enforcement

Every endpoint accepting input should have a FormRequest. The pattern:

```php
public function store(StorePostRequest $request): RedirectResponse
{
    $post = Post::create($request->validated());
    return to_route('posts.show', $post);
}
```

Detection grep for missing FormRequest:

```bash
grep -rn 'function (store\|update)\(' app/Http/Controllers \
  | grep -v '\(StorePostRequest\|UpdatePostRequest\|FormRequest\)'
```

Methods that receive only the base `Illuminate\Http\Request` are the audit list.

## 3. Authorization in controllers

Never trust the route alone. Authorize explicitly:

```php
// Per action
public function update(UpdatePostRequest $request, Post $post): RedirectResponse
{
    $this->authorize('update', $post);
    $post->update($request->validated());
    return back();
}

// All resource actions in one line
public function __construct()
{
    $this->authorizeResource(Post::class, 'post');
}
```

Route-model binding silently 404s on missing rows but does **not** authorize on found rows. Always pair binding with a Policy.

⚠️ Anti-pattern: assuming "the route is admin-only via middleware" without `$this->authorize()`. Middleware is a coarse net; Policy is the gate.

## 4. Raw queries — bindings only

```php
// BAD — input interpolated
DB::select("SELECT * FROM posts WHERE author = '{$request->author}'");
DB::raw("title = '{$request->title}'");

// GOOD — bindings
DB::select('SELECT * FROM posts WHERE author = ?', [$request->author]);
DB::table('posts')->whereRaw('title = ?', [$request->title]);
```

For Eloquent, `where('column', $value)` is always safely parameterized — the issue is only when `whereRaw`, `selectRaw`, `orderByRaw`, `havingRaw`, or `DB::raw()` is used with concatenation.

⚠️ Column names from user input are not bindable — they require an allowlist. Never `orderBy($request->column)`. See `api_design_patterns.md` §6 for the sorting/filtering pattern.

## 5. Soft delete is not security

`SoftDeletes` adds `deleted_at IS NULL` to default queries — but the data lives. Anything calling `withTrashed()` reads it.

```php
// User "deleted" — but compliance request says erase
$user->delete();

// Days later — a DPO request comes in
User::withTrashed()->find($user->id);   // still there
```

For real erasure (LGPD/GDPR right-to-be-forgotten), use `forceDelete()` or anonymize then soft-delete:

```php
$user->update([
    'name'  => '[deleted user]',
    'email' => "deleted-{$user->id}@example.invalid",
]);
$user->delete();
```

Pair with cascade scrubbing of related PII (logs, audit trails, queue payloads, search indexes).

## 6. Queue payload hygiene

Queued jobs serialize their constructor args. Never pass:
- Plain credentials (API keys, passwords)
- Raw user input that could leak in failed-job storage
- Large objects (full models — they auto-reload via `SerializesModels`)

```php
// BAD — credentials persist in failed_jobs forever
ProcessPayment::dispatch($apiKey, $amount);

// GOOD — fetch credentials inside handle()
ProcessPayment::dispatch($amount);

class ProcessPayment implements ShouldQueue
{
    public function __construct(public int $amount) {}

    public function handle(): void
    {
        $apiKey = config('services.stripe.key');
        // ...
    }
}
```

⚠️ `failed_jobs` is a plain DB table. Anyone with read access sees historical payloads. Audit periodically; rotate any secrets that may have leaked.

## 7. Safe logging

```php
// BAD — leaks credentials, tokens, PII
Log::info('payment.received', $request->all());
Log::info('user.login', ['request' => $request]);

// GOOD — explicit allowlist of fields
Log::info('payment.received', [
    'user_id'    => $request->user()->id,
    'amount'     => $request->amount,
    'request_id' => $request->header('X-Request-Id'),
]);
```

For request-context logging, scrub fields:

```php
function scrub(array $data, array $sensitive = ['password', 'token', 'card', 'cvv', 'secret']): array
{
    foreach ($sensitive as $key) {
        if (isset($data[$key])) {
            $data[$key] = '[REDACTED]';
        }
    }
    return $data;
}

Log::info('user.signup', scrub($request->all()));
```

For deeper structured logging, sampling, and channel design, see `laravel-security` references.

## 8. Cache key safety

Caching by raw user input creates two risks:

1. **Key injection / pollution** — special characters in the input pollute the cache namespace
2. **Oversized keys** — Redis stores the key; large input means large keys (and slow lookups)

```php
// BAD
$key = "search.results.{$request->query}";

// GOOD
$key = 'search.results.' . hash('xxh128', $request->query);
```

For input that combines multiple params, sort then hash:

```php
$params = $request->only(['q', 'tag', 'sort']);
ksort($params);
$key = 'search.' . hash('xxh128', json_encode($params));
```

## 9. File upload — backend touchpoints

```php
// FormRequest
'file' => [
    'required',
    File::types(['pdf', 'jpg', 'png'])->max(10 * 1024),   // KB; checks MIME + extension
    Rule::dimensions()->maxWidth(2000)->maxHeight(2000), // for images
],
```

```php
// Controller
$path = $request->file('file')->store('uploads', 'private');
// 'private' disk — never 'public' for sensitive uploads
```

Serve via a controller that re-checks authorization:

```php
public function show(Upload $upload): StreamedResponse
{
    $this->authorize('view', $upload);
    return Storage::disk('private')->download($upload->path);
}
```

⚠️ Anti-pattern: `move()` to `public/` and serving the file directly. A malicious upload (XSS in SVG, polyglot file) becomes executable from the public folder.

For deeper file-upload security (real MIME validation vs. claimed, content scanning, signed URLs, S3 server-side encryption), see `laravel-security`.

## 10. Anti-patterns

| Smell | Why |
|---|---|
| Model with neither `$fillable` nor `$guarded` | Mass assignment risk |
| `$request->all()` reaching `create()`/`update()`/`fill()` | Unknown columns assignable |
| `whereRaw`/`orderByRaw` with concatenated input | SQL injection |
| `orderBy($request->column)` | Column-name injection |
| Trusting route middleware as the only authorization | Easy to miss; Policy is the real gate |
| Treating soft delete as deletion (compliance) | Data still readable |
| Credentials in job constructor args | Persisted in `failed_jobs` |
| `Log::info($request->all())` without scrubbing | PII / credential leak |
| Raw user input in cache keys without hash | Key injection, oversized keys |
| Storing user uploads on `public` disk | Direct execution risk |
| `===` for HMAC signature comparison | Timing attack — use `hash_equals` |
| FormRequest with `authorize() { return true; }` placeholder | No authorization on input |
| Raw `Auth::id()` in scope without null guard | Crashes for unauthenticated context (jobs, schedule) |
