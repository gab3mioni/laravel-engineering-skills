# Testing Strategies — Laravel

When to choose each test type, what to fake vs. hit real, how to structure database state. Loaded when designing the approach for a new feature or auditing existing strategy.

## 1. Test type by use case

### 1.1 Feature tests (HTTP)

```php
it('creates a post', function () {
    $user = User::factory()->create();

    $this->actingAs($user)
         ->postJson('/api/posts', ['title' => 'X', 'body' => '...'])
         ->assertCreated()
         ->assertJsonPath('data.title', 'X');

    $this->assertDatabaseHas('posts', ['title' => 'X', 'user_id' => $user->id]);
});
```

**When:** any HTTP endpoint, full request → response → DB cycle, multi-class flow.
**Trade-off:** slowest test type per assertion, but catches the most realistic bugs.

### 1.2 Unit tests

```php
// tests/Unit/MoneyTest.php
it('converts cents to BRL', function () {
    expect((new Money(199, 'USD'))->convertTo('BRL', rate: 5.0)->amount)->toBe(995);
});
```

**When:** pure logic — value objects, calculators, parsers, validators that don't touch the framework.
**Trade-off:** fastest, but limited reach (most Laravel code touches the framework).

If your "unit" test imports any `Illuminate\*`, it's a Feature test in disguise — convert it.

### 1.3 Integration tests

```php
// tests/Feature/PublishPostTest.php — boots Laravel, hits DB, no HTTP
it('publishes the post and dispatches the event', function () {
    Event::fake();
    $post = Post::factory()->create();

    app(PublishPost::class)->handle($post);

    expect($post->fresh()->published_at)->not->toBeNull();
    Event::assertDispatched(PostPublished::class);
});
```

**When:** testing service / Action / Job interaction without going through HTTP.
**Trade-off:** slightly faster than full HTTP feature; same isolation needs.

### 1.4 Browser tests (Dusk)

**When:** UI flows that depend on JavaScript — drag-and-drop, modal interactions, real-time updates, third-party widgets.
**Trade-off:** ~10× slower than Feature tests, requires ChromeDriver, can be flaky.

Reserve Dusk for what Feature + Inertia testing cannot reach.

## 2. Fakes vs. real — what to substitute

Laravel's facades expose `fake()` methods that swap real implementation for an inspector.

### 2.1 Always fake in tests

| Fake | Why |
|---|---|
| `Queue::fake()` | Jobs don't actually run during the test |
| `Mail::fake()` | No real emails sent |
| `Notification::fake()` | No real notifications |
| `Event::fake()` | Listeners don't fire (control test scope) |
| `Bus::fake()` | Job batches don't dispatch |
| `Http::fake([...])` | No outbound HTTP — no flakiness from network |
| `Storage::fake('s3')` | File ops use a memory disk |

These are slow, flaky (network), or have side effects (sent emails) — never run them real in tests.

### 2.2 Real (don't fake)

| Component | Why real |
|---|---|
| Database | Testing query behavior matters; SQLite memory or real test DB |
| Cache | Use `array` driver — in-process, fast |
| Session | `array` driver — fast and isolated |
| Eloquent models | They're under test |
| FormRequests / validation | Same |
| Policies / Gates | Same |
| Routes | Same |

### 2.3 Sometimes fake, sometimes real

| Component | Default | Fake when | Real when |
|---|---|---|---|
| Filesystem | `Storage::fake()` | Always in tests | Never (use S3 emulator in CI integration suite if needed) |
| Queue | `Queue::fake()` | Asserting dispatch | Integration test of full job lifecycle |
| Events | `Event::fake()` | Asserting dispatch + decoupling listeners | Testing the observer + listener chain end-to-end |
| HTTP | `Http::fake()` | All HTTP outbound | Never — always fake |

## 3. Database strategies

### 3.1 RefreshDatabase

```php
// tests/Pest.php
uses(RefreshDatabase::class)->in('Feature');
```

What it does:
1. On first test of the run: drops & re-runs migrations on the test DB
2. Per test: starts a transaction; rolls back at the end
3. Test sees the schema fresh and DB empty (modulo seeders)

**Use when:** schema may change between branches, full reset needed.

### 3.2 DatabaseTransactions

Same per-test transaction, no migration. Use when DB is already in expected state (dev DB you don't want to drop).

### 3.3 DatabaseMigrations

Re-runs migrations per test, no transaction wrap. Slower; use when:
- Testing transaction behavior (the test wrapper interferes with what you're asserting)
- Specific migration paths need verification

### 3.4 In-memory SQLite for speed

```xml
<!-- phpunit.xml -->
<server name="DB_CONNECTION" value="sqlite"/>
<server name="DB_DATABASE" value=":memory:"/>
```

Trade-off: SQLite ≠ MySQL/Postgres. Some queries (JSON ops, full-text search, locking semantics, window functions) behave differently. **Run the suite at least once in CI against the production DB engine** to catch divergence.

A common split:
- Local dev + PR feedback: SQLite memory (fast)
- Per-release CI: full MySQL/Postgres run (slower, accurate)

## 4. Time and randomness

### 4.1 Freezing time

```php
Carbon::setTestNow('2026-01-15 10:00:00');
// ... test code ...
Carbon::setTestNow();   // clear

// Pest helpers
$this->freezeTime();
$this->travelTo('2026-01-15');
$this->travel(1)->days();
```

**Use when:** scheduled jobs, expiration logic, time-windowed features, audit timestamps.

### 4.2 Pinning randomness

```php
fake()->seed(12345);                // deterministic Faker
$this->seed(SomeSeeder::class);     // run a seeder
```

If a test fails only sometimes, suspect randomness. Pin the seed and reproduce.

## 5. Authorization testing

Test the **happy path** (allowed) and the **denied paths** (401, 403). Skip neither.

```php
// 401 — unauthenticated
it('blocks unauthenticated users', function () {
    $this->postJson('/api/posts', [])->assertUnauthorized();
});

// 403 — authenticated but not authorized
it('forbids editing posts you do not own', function () {
    $owner = User::factory()->create();
    $other = User::factory()->create();
    $post  = Post::factory()->for($owner)->create();

    $this->actingAs($other)
         ->putJson("/api/posts/{$post->id}", ['title' => 'X'])
         ->assertForbidden();
});

// 200 — proper user
it('allows owners to edit their own posts', function () {
    $owner = User::factory()->create();
    $post  = Post::factory()->for($owner)->create();

    $this->actingAs($owner)
         ->putJson("/api/posts/{$post->id}", ['title' => 'X'])
         ->assertOk();
});
```

For multi-tenant apps, also test **cross-tenant isolation** (user from tenant A cannot read tenant B's data).

## 6. Validation testing

```php
it('requires a title', function () {
    $this->actingAs(User::factory()->create())
         ->postJson('/api/posts', ['body' => '...'])
         ->assertJsonValidationErrors(['title']);
});

it('rejects titles longer than 255 chars', function () {
    $this->actingAs(User::factory()->create())
         ->postJson('/api/posts', ['title' => str_repeat('x', 256), 'body' => '...'])
         ->assertJsonValidationErrors(['title']);
});
```

For complex validation, datasets cover combinations succinctly:

```php
it('rejects invalid emails', function (string $email) {
    $this->postJson('/register', ['email' => $email, 'password' => 'secret'])
         ->assertJsonValidationErrors(['email']);
})->with([
    'no-at',
    '@no-local',
    'no-domain@',
    'spaces in@email.com',
]);
```

## 7. Job & queue testing

### 7.1 Asserting dispatch (no execution)

```php
Queue::fake();

CreatePost::dispatch($data);

Queue::assertPushed(CreatePost::class);
Queue::assertPushed(CreatePost::class, fn ($job) => $job->data === $data);
```

### 7.2 Running the job inline

```php
$job = new CreatePost($data);
$job->handle();   // synchronous — test handle() directly

$this->assertDatabaseHas('posts', [/* ... */]);
```

### 7.3 Full lifecycle

```php
Queue::fake();
$user = User::factory()->create();

$this->actingAs($user)->postJson('/api/posts', [/* ... */])->assertCreated();

// Job was queued
Queue::assertPushed(IndexPostForSearch::class);

// Run pushed jobs inline to test the full chain
Queue::pushed(IndexPostForSearch::class)->each->handle();
```

For batch and chain testing, see `laravel-queues`.

## 8. HTTP service testing

```php
Http::fake([
    'api.stripe.com/*'      => Http::response(['id' => 'ch_123'], 200),
    'api.example.com/error' => Http::response(['error' => 'down'], 500),
]);

// Code under test calls Http::post('https://api.stripe.com/charges', ...)

Http::assertSent(fn (Request $r) =>
    $r->url() === 'https://api.stripe.com/charges' &&
    $r['amount'] === 1000
);
Http::assertSentCount(1);
```

Sequential responses (test retry logic):

```php
Http::fake([
    'api.example.com/*' => Http::sequence()
        ->push(['error' => 'rate limit'], 429)
        ->push(['ok' => true], 200),
]);
```

## 9. Inertia response testing

```php
$this->actingAs($user)
     ->get('/posts')
     ->assertInertia(fn (AssertableInertia $page) => $page
         ->component('Posts/Index')
         ->has('posts.data', 5)
         ->where('posts.data.0.title', 'First')
         ->missing('debug')
         ->has('auth.user', fn (AssertableInertia $u) => $u
             ->where('id', $user->id)
             ->where('name', $user->name)
         )
     );
```

For component-level Inertia tests, see `laravel-inertia`.

## 10. Anti-patterns

| Smell | Why |
|---|---|
| Real HTTP requests in test suite | Flaky, slow, network-dependent |
| Real S3/email/SMS calls in tests | Same |
| Skipping `Queue::fake()` and watching jobs run | Asserts side effects of side effects |
| DB tests serial only because suite shares state | Use `--parallel` after fixing isolation |
| `sleep(...)` in tests | Use `Carbon::setTestNow(...)` |
| `assert(true)` placeholder | False sense of coverage |
| Testing private methods directly | Refactor; test through public surface |
| One mega test with many AAAs | Split |
| SQLite-only suite, never run vs. real DB engine | DB-specific behavior leaks unnoticed |
| Testing the happy path but not 401/403 | Authorization regressions undetected |
