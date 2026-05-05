---
name: laravel-qa
description: QA and testing for Laravel 12 — Pest 3 (expectations, datasets, higher-order, arch tests), feature/unit/integration tests, fakes (Queue, Mail, Event, Http, Storage, Notification, Bus), factories and seeders for tests, RefreshDatabase/DatabaseTransactions, HTTP testing (actingAs, assertJsonPath, assertInertia), Dusk browser tests, coverage and mutation testing, CI integration. Universal — consumed by every agent in the plugin.
---

# Laravel QA — Tests, factories, fakes

Pest-first testing for Laravel 12 / PHP 8.3+. Universal skill — every agent that writes, runs, or audits code consumes this.

## When to use this skill

- Writing or modifying any test (feature, unit, integration, browser)
- Designing test strategy (what to mock, what to fake, what to hit real)
- Setting up test database, factories, seeders for tests
- Running coverage or mutation analysis
- Configuring CI test gates

## When NOT to use

| Topic | Use instead |
|---|---|
| Server-side patterns being tested (Eloquent, Controllers, FormRequests, Policies) | `laravel-backend` |
| Auth flow being tested (Sanctum, Fortify, guards) | `laravel-auth` |
| Queue mechanics being tested (Horizon, batching, retries) | `laravel-queues` |
| Inertia protocol being tested (props, deferred, partial) | `laravel-inertia` |
| Static analysis output (Pint, Larastan, Rector) | `laravel-static-analysis` |
| Accessibility checks | `laravel-a11y` |
| Security regression auditing | `laravel-security` |

## Stack assumptions

- **Pest 3+** is the default test runner
- Laravel 12, PHP 8.3+
- Test layout: `tests/Feature/`, `tests/Unit/`, `tests/Browser/` (when Dusk present)
- `tests/Pest.php` is the global config; `tests/TestCase.php` is the base class

For best practices (pyramid, AAA, naming, coverage as signal), strategy (when feature/unit/integration, fakes vs real), and the deep Pest automation guide (datasets, higher-order, arch, mutation, parallel, CI), see:
- `references/best_practices.md`
- `references/testing_strategies.md`
- `references/test_automation.md`

---

## 1. Test types — quick decision

| Type | Boots Laravel? | Hits DB? | When |
|---|---|---|---|
| **Feature** | Yes | Yes | HTTP endpoints, full request flow, multi-class behavior |
| **Unit** | No | No | Single class, pure logic, no framework |
| **Integration** | Yes | Yes | Cross-class behavior without HTTP (services, jobs running together) |
| **Browser** (Dusk) | Yes | Yes | UI flows that depend on JavaScript |

When unsure: **start with a Feature test**. Drop to Unit only when speed or isolation justifies. See `references/testing_strategies.md` §1 for full decision rationale.

---

## 2. Pest fundamentals

```php
use App\Models\{Post, User};

it('lists published posts', function () {
    Post::factory()->published()->count(3)->create();
    Post::factory()->count(2)->create();   // unpublished

    $response = $this->getJson('/api/posts');

    $response->assertOk()->assertJsonCount(3, 'data');
});

test('post creation requires title', function () {
    $this->actingAs(User::factory()->create())
         ->postJson('/api/posts', ['body' => 'no title'])
         ->assertStatus(422)
         ->assertJsonValidationErrors(['title']);
});
```

`it(...)` and `test(...)` are aliases. Convention: `it` for behavior phrases ("creates a post"), `test` for action verbs ("post creation requires title"). Pick one and stay consistent.

### 2.1 Expectations

```php
expect($post->title)->toBe('Hello');
expect($post->is_published)->toBeTrue();
expect($posts)->toHaveCount(3);
expect($post->tags)->toContain('php');
expect(fn () => Post::create([]))->toThrow(QueryException::class);
```

Higher-order chained:

```php
expect($user)
    ->name->toBe('Gabriel')
    ->email->toBeString()
    ->is_admin->toBeFalse();
```

### 2.2 Hooks

```php
beforeEach(function () {
    $this->user = User::factory()->create();
});

it('greets the user', function () {
    $this->actingAs($this->user)
         ->getJson('/api/me')
         ->assertJsonPath('data.name', $this->user->name);
});
```

`beforeAll`, `afterEach`, `afterAll` exist but are rare in Laravel — DB state is reset per test via `RefreshDatabase`.

For datasets, custom expectations, architecture tests, and helpers in `tests/Pest.php`, see `references/test_automation.md`.

---

## 3. HTTP testing

### 3.1 Methods

```php
$response = $this->getJson('/api/posts');
$response = $this->postJson('/api/posts', ['title' => 'X']);
$response = $this->putJson('/api/posts/1', [/* ... */]);
$response = $this->patchJson('/api/posts/1', [/* ... */]);
$response = $this->deleteJson('/api/posts/1');

// Web (HTML, redirects, sessions)
$response = $this->get('/posts');
$response = $this->post('/login', [/* ... */]);
```

### 3.2 Acting as a user

```php
$this->actingAs($user);                              // default web guard
$this->actingAs($user, 'sanctum');                   // specific guard
Sanctum::actingAs($user, ['posts:write']);           // Sanctum with abilities
```

### 3.3 Asserts

```php
$response->assertOk();                              // 200
$response->assertCreated();                         // 201
$response->assertNoContent();                       // 204
$response->assertStatus(422);
$response->assertRedirect('/dashboard');
$response->assertRedirectToRoute('posts.show', $post);

$response->assertJson(['data' => ['id' => 1]]);     // partial match
$response->assertJsonPath('data.author.id', $user->id);
$response->assertJsonStructure(['data' => [['id', 'title']]]);
$response->assertJsonCount(3, 'data');
$response->assertJsonValidationErrors(['title']);
$response->assertJsonMissing(['hidden_field']);

$response->assertSessionHas('status');
$response->assertSessionHasErrors(['email']);
```

⚠️ **Anti-pattern:** asserting only on status code (`assertOk()`) for JSON endpoints. Misses content regressions. Always pair with `assertJsonPath` or `assertJsonStructure`.

---

## 4. Database testing

### 4.1 Reset strategies

| Trait | Behavior | When |
|---|---|---|
| `RefreshDatabase` | Migrates fresh, wraps each test in a transaction | Most tests — fast, isolated |
| `DatabaseTransactions` | Wraps each test in a transaction; no migration | DB already seeded; very fast |
| `DatabaseMigrations` | Migrates fresh per test, no transaction | Testing transactions themselves |

Apply globally in `tests/Pest.php`:

```php
uses(RefreshDatabase::class)->in('Feature');
```

### 4.2 Asserts on DB

```php
$this->assertDatabaseHas('posts', ['title' => 'Hello']);
$this->assertDatabaseMissing('posts', ['id' => 999]);
$this->assertDatabaseCount('posts', 3);
$this->assertSoftDeleted($post);
$this->assertModelExists($post);
$this->assertModelMissing($post);
```

### 4.3 Factories quick reference

```php
$user  = User::factory()->create();                                // single, persisted
$users = User::factory()->count(5)->create();                      // many
$user  = User::factory()->make();                                  // not persisted

$post = Post::factory()->for(User::factory())->create();           // belongsTo
$user = User::factory()->has(Post::factory()->count(3))->create(); // hasMany

$user = User::factory()->state(['admin' => true])->create();       // ad-hoc state
$post = Post::factory()->published()->create();                    // named state

Post::factory()->count(3)->recycle($user)->create();               // share parent across tree

// Different values per row
User::factory()->count(3)->sequence(
    ['role' => 'admin'],
    ['role' => 'editor'],
    ['role' => 'viewer'],
)->create();
```

⚠️ **Anti-pattern:** factories that hit external services (HTTP, S3) in `definition()`. Keep factories pure.

---

## 5. Fakes

Replace a Laravel facade with an inspector:

```php
Queue::fake();
Mail::fake();
Notification::fake();
Event::fake();
Bus::fake();
Http::fake();
Storage::fake('s3');

// ... run code under test ...

Queue::assertPushed(ProcessPost::class);
Queue::assertPushed(ProcessPost::class, fn ($job) => $job->postId === $post->id);
Queue::assertNotPushed(SomeOtherJob::class);
Queue::assertCount(1);

Mail::assertSent(WelcomeMail::class, fn ($m) => $m->hasTo($user->email));
Mail::assertNotSent(WelcomeMail::class);
Mail::assertQueued(WelcomeMail::class);

Notification::assertSentTo($user, WelcomeNotification::class);
Notification::assertNothingSent();

Event::assertDispatched(PostPublished::class);
Event::assertDispatched(PostPublished::class, 1);   // exactly once
Event::assertNotDispatched(PostDeleted::class);

Bus::assertDispatched(ProcessPost::class);
Bus::assertChained([JobA::class, JobB::class]);
Bus::assertBatched(fn (PendingBatch $b) => $b->jobs->count() === 5);

Http::fake([
    'api.example.com/*' => Http::response(['ok' => true], 200),
    '*'                 => Http::response('Not found', 404),
]);
Http::assertSent(fn (Request $r) => $r->url() === 'https://api.example.com/users');

Storage::disk('s3')->assertExists("uploads/{$file->id}.jpg");
Storage::disk('s3')->assertMissing('uploads/old.jpg');
```

⚠️ **Anti-pattern:** code that uses `new Mailable(...)` directly bypasses `Mail::fake()`. Always send via `Mail::to(...)->send(...)`.

---

## 6. Mocking (Mockery)

For non-facade dependencies:

```php
$gateway = $this->mock(PaymentGateway::class);
$gateway->shouldReceive('charge')->once()->andReturn(true);

// Pest helpers
$mock    = $this->mock(PaymentGateway::class);
$spy     = $this->spy(PaymentGateway::class);
$partial = $this->partialMock(PaymentGateway::class);
```

**Heuristic:** prefer fakes (real Laravel collaborators with assertion API) over mocks (Mockery doubles). Mocks are for non-Laravel services.

---

## 7. Inertia testing

```php
$this->actingAs($user)
     ->get('/posts')
     ->assertInertia(fn (AssertableInertia $page) => $page
         ->component('Posts/Index')
         ->has('posts.data', 5)
         ->where('posts.data.0.title', 'First post')
         ->missing('debug')
     );
```

Asserts the Inertia component name, props shape, and absence of leaked data. Deeper Inertia-specific helpers in `laravel-inertia`.

---

## 8. Browser testing (Dusk)

Detect: `composer show laravel/dusk`. Dusk drives a real browser via ChromeDriver — slow, but the only path to JS-driven flows.

```php
// tests/Browser/LoginTest.php
$this->browse(function (Browser $browser) use ($user) {
    $browser->visit('/login')
            ->type('email', $user->email)
            ->type('password', 'password')
            ->press('Log In')
            ->assertPathIs('/dashboard')
            ->assertSee("Welcome, {$user->name}");
});
```

**When Dusk:** UI flows that Feature + Inertia testing cannot reach (drag-and-drop, complex JS state, third-party widgets). Default to Feature testing for everything else — Dusk is ~10× slower.

---

## 9. Architecture tests

Pest's `arch()` enforces structural rules across the codebase, run as part of the suite:

```php
arch('controllers do not access models directly')
    ->expect('App\Http\Controllers')
    ->not->toUse(['App\Models']);

arch('actions are final and have handle method')
    ->expect('App\Actions')
    ->toBeFinal()
    ->toHaveMethod('handle');

arch('no debug calls in production code')
    ->expect(['dd', 'dump', 'var_dump', 'die', 'print_r', 'ray'])
    ->not->toBeUsed();

arch()->preset()->laravel();    // built-in Laravel rules
arch()->preset()->security();   // forbids eval, exec, system, unserialize
arch()->preset()->php();        // PHP-level safety rules
```

---

## 10. Coverage

```bash
vendor/bin/pest --coverage                       # text in terminal
vendor/bin/pest --coverage --min=80              # fail if below 80%
vendor/bin/pest --coverage-html=coverage         # HTML report
vendor/bin/pest --coverage-clover=coverage.xml   # for Codecov / Sonar
```

Requires Xdebug or PCOV. PCOV is faster (coverage-only).

⚠️ Coverage is a **signal**, not a goal. 100% with shallow assertions is worse than 70% with meaningful ones. Pair with mutation testing for branch-quality signal.

---

## 11. Mutation testing (Pest 3+)

```bash
vendor/bin/pest --mutate                    # full mutation run (slow)
vendor/bin/pest --mutate --bail             # stop at first survivor
vendor/bin/pest --mutate --covered-only     # only mutate covered code
vendor/bin/pest --mutate --min=80           # fail if score below 80%
```

**Strategy:** target critical business logic (billing, auth, permissions, scheduling). Run nightly or per-release in CI, not per-PR — too slow.

---

## 12. Parallel testing

```bash
vendor/bin/pest --parallel              # auto-detect cores
vendor/bin/pest --parallel --processes=4
```

Each process gets its own DB (`testing_1`, `testing_2`, …). Speeds the suite ~3-4× on 8 cores.

⚠️ Tests sharing state (filesystem writes, external services without faking) break under parallel. Audit isolation first.

---

## 13. Filtering for fast local TDD

```bash
vendor/bin/pest --filter=PostTest               # by file/class name
vendor/bin/pest --filter='it creates'           # by test name
vendor/bin/pest --group=critical                # by group annotation
vendor/bin/pest tests/Feature/Auth              # by path
vendor/bin/pest --bail                          # stop at first failure
vendor/bin/pest --retry                         # retry failed once
vendor/bin/pest --dirty                         # only tests touching changed files (gold for TDD)
```

---

## 14. CI integration

Recommended GitHub Actions block:

```yaml
- name: Pint
  run: vendor/bin/pint --test

- name: Larastan
  run: vendor/bin/phpstan analyse --memory-limit=2G

- name: Pest
  run: vendor/bin/pest --parallel --coverage --min=80
```

Run on every PR. Block merge on test failure, coverage drop below floor, or static analysis failure. Run mutation testing nightly or per-release.

For full GitHub Actions YAML with PHP version matrix, MySQL service, Composer cache, and PCOV setup, see `references/test_automation.md` §10.

---

## 15. Anti-patterns — consolidated checklist

| Smell | Why |
|---|---|
| Test that hits real HTTP / external service | Slow, flaky; use `Http::fake()` |
| Factory hitting external service in `definition()` | Slows every test using it |
| Test depending on prior test's state | Order-dependent; isolation broken |
| `actingAs` without `RefreshDatabase` | Stale users carry across tests |
| `Mail::to(...)->send(new ...)` outside facade | Bypasses `Mail::fake()` |
| Mocking what should be faked (Queue, Mail, Event) | Misuses Mockery; lose Laravel's assertion API |
| Asserting only `assertOk()` on JSON endpoints | Misses content regressions |
| Test name that mirrors the method name | Hides intent — describe behavior |
| Test with > 5 setup lines | Sign of God class; refactor |
| Missing `RefreshDatabase` on Feature test | Pollutes DB across runs |
| Coverage as a hard target, not a signal | Drives shallow assertions |
| `markTestSkipped` left for > 1 sprint | Compounds debt; fix or delete |
| Architecture rules not run in CI | Drift goes undetected |
| Browser test where Feature would suffice | 10× slower for no gain |
| Sleeping in tests | Use `Carbon::setTestNow(...)` instead |
| Single test asserting many unrelated behaviors | Hard to debug failures; split |
| `--retry` masking flakiness | Hides root cause; investigate |

---

## 16. Cross-references

| Topic | Skill |
|---|---|
| Domain logic being tested (Eloquent, Controllers, FormRequests, Policies) | `laravel-backend` |
| Auth flow being tested (Sanctum, Fortify, guards) | `laravel-auth` |
| Queue/job test patterns (`Bus::fake`, `Queue::fake`, batching, chains) | `laravel-queues` |
| Inertia-specific assertions (`assertInertia` deep) | `laravel-inertia` |
| Pint, Larastan, Rector in CI gates | `laravel-static-analysis` |
| Browser a11y testing (axe via Dusk) | `laravel-a11y` |
| Security regression tests | `laravel-security` |
