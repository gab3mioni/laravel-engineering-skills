# QA Best Practices — Laravel

Test discipline that survives the codebase growing past prototype. Loaded when designing test strategy, training a team, or auditing test quality.

## 1. The pyramid (and why it inverts in Laravel)

Classic test pyramid: many unit tests at the base, fewer integration in the middle, very few end-to-end at the top. This shape minimizes total runtime while preserving coverage.

In Laravel projects, the pyramid often **inverts** — most tests are Feature tests (HTTP-driven, hit DB). That's because:

- Laravel boots fast (~50ms) — Feature tests aren't slow enough to push toward unit
- Most code lives in Controllers + Eloquent + Services that interact with the framework — pure unit tests would mock half of Laravel
- The bug surface most users care about is HTTP behavior, not pure logic
- Refactoring is easier when tests cover behavior, not implementation

**Pragmatic stance:**
- Default to **Feature tests** for HTTP endpoints and multi-class flows
- Drop to **Unit** for pure logic that doesn't touch Laravel (calculators, parsers, value objects, domain rules)
- **Browser** (Dusk) only for true JS or UI flows
- **Architecture tests** for structural rules (no controllers using models directly, etc.)

Don't optimize for "more unit tests" as a goal. Optimize for tests that catch bugs your users would notice.

## 2. Naming

Test names describe **behavior**, not the method under test.

```php
// BAD — mirrors method
test('store method returns 201', function () { /* ... */ });

// GOOD — describes behavior
it('creates a post when given valid data', function () { /* ... */ });
it('returns 422 when title is missing', function () { /* ... */ });
it('forbids creation for unauthenticated users', function () { /* ... */ });
```

A reader unfamiliar with the codebase should understand the contract from the test name alone.

Pest convention: `it('does something')` reads as "it does something". Use `test('action verb')` only when "it" doesn't fit grammatically.

## 3. Arrange / Act / Assert (AAA)

Every test has three phases. Make them visible:

```php
it('publishes a post', function () {
    // Arrange
    $user = User::factory()->create();
    $post = Post::factory()->for($user)->create();

    // Act
    $response = $this->actingAs($user)->postJson("/api/posts/{$post->id}/publish");

    // Assert
    $response->assertOk();
    expect($post->fresh()->published_at)->not->toBeNull();
});
```

Variants: Given/When/Then (BDD), Setup/Exercise/Verify (xUnit). Same idea — pick one and stay consistent.

⚠️ Anti-pattern: a single test with multiple AAA cycles. Split it.

## 4. Test isolation

Each test must run independently of others — order, parallelism, retry should all work.

Sources of order dependency:

| Source | Mitigation |
|---|---|
| DB state | `RefreshDatabase` or `DatabaseTransactions` |
| Static state in classes | Avoid; if unavoidable, reset in `beforeEach` |
| File system | `Storage::fake(...)` |
| Cached config | Don't `config:cache` for tests; let it read fresh |
| External services | `Http::fake(...)`, `Mail::fake()`, etc. |
| Time-sensitive logic | `Carbon::setTestNow(...)` and clear in teardown |
| Random data | Pin `fake()->seed(N)` or hard-code values |

## 5. Test data — factories over fixtures

Factories generate data on demand with realistic randomization:

```php
Post::factory()->published()->for($user)->create();
```

Anti-patterns:
- **Hard-coded SQL fixtures** — drift from schema, no relationships, brittle
- **Shared "test data" seeder** — implicit dependencies between tests, order coupling
- **Factory definitions that change frequently** — old tests break; pin test-specific shape via `state()`

When you need *realistic* edge values (max length, special chars, nullable), state them explicitly:

```php
Post::factory()->state(['title' => str_repeat('x', 255)])->create();
Post::factory()->state(['body' => "👋 unicode and \"quotes\""])->create();
```

## 6. Coverage — signal, not metric

Line coverage tells you which lines ran. It does **not** tell you whether the assertions were meaningful.

```php
// 100% line coverage, 0% behavior coverage
it('does something', function () {
    Post::create(['title' => 'X']);
    expect(true)->toBeTrue();
});
```

The valuable signal coverage gives you:
- **Drops in coverage on a PR** — code added without tests
- **Untouched paths** — branches your tests never enter

Use `--min` as a **floor** (don't drop below 80%), not a **target** (chasing 100% drives shallow tests). Pair with mutation testing for branch-quality signal.

## 7. Determinism — kill flakiness fast

A flaky test is worse than no test — it desensitizes the team to real failures.

Common sources:

| Source | Fix |
|---|---|
| Random data triggering edge case | `fake()->seed(N)` or pin specific values |
| Time-dependent logic | `Carbon::setTestNow(...)` |
| Order-dependent state | `RefreshDatabase`; review parallel safety |
| Async/queue running | `Queue::fake()` or `Bus::fake()` |
| External HTTP | `Http::fake(...)` |
| Filesystem race | `Storage::fake(...)` |
| DB sequencing assumptions | Don't assume IDs are 1, 2, 3; assert by attribute |
| Eventual-consistency reads (search, cache) | Don't trust immediate read; either fake or wait deterministically |

When a test goes flaky, **fix or delete within the same sprint**. Don't `markTestSkipped` indefinitely — that compounds.

## 8. CI gates

Block merge on:

1. **All tests pass** — Pest exit 0
2. **Static analysis passes** — Larastan/PHPStan, Pint
3. **Coverage doesn't drop** — `--min` floor enforced
4. **Architecture tests pass** — Pest `arch()` rules

Cadence:
- **Per-PR**: full Pest + static analysis + coverage check
- **Nightly**: mutation testing
- **Per-release**: full mutation across changed modules + integration suite

Run tests on every PR, not on every push (cost). Use parallel mode (`--parallel`) to keep PR feedback under 5 minutes.

## 9. What to test

- **Public contracts** — HTTP endpoints, public class methods, console commands, broadcasted events
- **Business rules** — pricing, scheduling, state transitions, authorization, validation rules with semantics
- **Edge cases** — empty input, max length, concurrency, time boundaries, unicode
- **Regressions** — every bug fix lands with a test that would have caught it (the test is the bug report)

## 10. What NOT to test

- **Framework code** — don't test that Eloquent saves to DB; trust Laravel
- **Trivial getters/setters** — pure data movement; no logic
- **Configuration values** — `config('foo.bar')` is just a value
- **Private methods directly** — test through the public surface; if a private method needs its own test, extract it to a separate class
- **Generated code** — model files from `make:model` etc. don't need tests

## 11. The test as documentation

Tests double as living examples of how to use a class or endpoint. Optimize them for readability:

- **Named factories states** that say what they mean (`->published()`, `->expired()`)
- **Helper functions** in `tests/Pest.php` for repeated setup (`asAdmin()`, `withSubscription()`)
- **Custom expectations** that read like business language (`expect($post)->toBePublished()`)

When a new dev reads `tests/Feature/PostTest.php`, they should learn what posts do and how to interact with them.

## 12. Anti-patterns — consolidated

| Smell | Why |
|---|---|
| Test name = method name | Hides intent |
| Single test asserting many unrelated behaviors | Hard to debug failures |
| Setup > 10 lines | God class under test; refactor |
| Test that hits real HTTP/S3/email | Flaky, slow |
| Skipping flaky tests indefinitely | Compounds debt; desensitizes team |
| Coverage as a goal (100% target) | Drives shallow assertions |
| Factory hitting external service | Slows every test using it |
| Tests using shared seeder data | Implicit coupling |
| Order-dependent suite | Parallel breaks; debugging hell |
| Assertions only on status code | Misses content regressions |
| Mocking what should be faked (Queue, Mail) | Loses Laravel's assertion API |
| Browser test where Feature would suffice | 10× slower for no gain |
| Tests that exist just for coverage | Flag and delete |
| Comments inside tests explaining what assertions mean | Refactor; assertions should self-document |
