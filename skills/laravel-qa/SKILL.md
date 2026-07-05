---
name: laravel-qa
description: QA and testing for Laravel 12 with Pest 3 — TDD workflow, regression tests, test-type and fake-vs-real decisions, HTTP/database/browser testing, arch tests, coverage and mutation. Use when writing any test, when a bug fix needs a regression test, when deciding what to fake vs hit real, when the suite is slow or flaky or fails only in parallel, or when a behavior change is about to land without a test. Universal — consumed by every agent in the plugin.
---

# Laravel QA — Tests, factories, fakes

Pest-first testing for Laravel 12 / PHP 8.3+. Universal skill — every agent that writes, runs, or audits code consumes this.

## When to use this skill

- Writing or modifying any test (feature, unit, integration, browser)
- A bug fix needs a regression test
- Deciding what to mock, what to fake, what to hit real
- The suite is slow, flaky, or fails only in parallel
- Running coverage or mutation analysis

## When NOT to use

| Topic | Use instead |
|---|---|
| Server-side patterns being tested (Eloquent, Controllers, FormRequests, Policies) | `laravel-backend` skill |
| Auth flow being tested (Sanctum, Fortify, guards) | `laravel-auth` skill |
| Queue mechanics being tested (Horizon, batching, retries) | `laravel-queues` skill |
| Inertia protocol being tested (props, deferred, partial) | `laravel-inertia` skill |
| Static analysis output (Pint, Larastan, Rector) and CI gate wiring | `laravel-static-analysis` skill |
| Accessibility checks | `laravel-a11y` skill |
| Security regression auditing | `laravel-security` skill |
| JS component tests (Vitest, Testing Library) | (owned by the `laravel-react` / `laravel-vue` agents) |
| CI runner infra, containers, pipelines | (owned by the `devops` agent) |

## Stack assumptions

- **Pest 3+** is the default test runner; Laravel 12, PHP 8.3+
- Test layout: `tests/Feature/`, `tests/Unit/`, `tests/Browser/` (when Dusk present)
- `tests/Pest.php` is the global config; `tests/TestCase.php` is the base class
- `it(...)` and `test(...)` are aliases — match whichever the suite already uses

---

## Workflows

### W1. TDD loop (any behavior change)

1. **Write the failing test first.** Name it after the behavior ("it rejects expired coupons"), not the method under test.
2. **Confirm it fails for the right reason:**
   ```bash
   vendor/bin/pest --dirty --bail
   ```
   - Passes immediately → the behavior already exists or the test asserts nothing. Rewrite the test.
   - Fails with an *error* (exception, missing class) instead of an *assertion failure* → fix the test setup before implementing.
3. **Implement** the minimal code that satisfies the test.
4. **Confirm green, including neighbors:**
   ```bash
   vendor/bin/pest --dirty
   ```
   - Your test fails → back to step 3.
   - *Other* tests fail → collateral regression; run workflow W3 before touching anything else.
5. **Format gate:**
   ```bash
   vendor/bin/pint --dirty --test
   ```
   On failure, apply with `vendor/bin/pint --dirty` and re-run step 4.

⚠️ **Hard gate: a behavior change without a test in the same diff is not done.** No "tests in the next PR".

### W2. Regression test for a bug fix

1. **Reproduce the bug as a failing test** before touching the fix. The test name states the correct behavior, not the ticket:
   ```bash
   vendor/bin/pest --filter='rejects expired coupons'
   ```
   Can't reproduce → you don't understand the bug yet; stop and investigate, don't fix blind.
2. **Fix** the code.
3. **Verify** the new test passes and nothing else broke: `vendor/bin/pest --dirty`.
4. **If the bug is in billing, auth, or permissions**, mutation-check the fix so the test actually pins the branch:
   ```bash
   vendor/bin/pest --mutate --covered-only --bail tests/Feature/CheckoutTest.php
   ```
   Survivors on the fixed lines → the regression test is too shallow; strengthen assertions.

### W3. Triage a failing suite

1. **Get the first failure fast:**
   ```bash
   vendor/bin/pest --bail
   ```
2. **Classify the failure:**

   | Kind | Signal | Action |
   |---|---|---|
   | Assertion failure | `Failed asserting that ...` | Real behavior change. Fix the code — or the test, only if the intent legitimately changed. |
   | Error | Exception, missing table/class | Environment or setup: run `php artisan migrate:fresh --env=testing`, check `.env.testing`, composer autoload. |
   | Flaky | Passes on re-run with `--filter` | Deterministic cause exists — find it via the flakiness table in `references/best_practices.md` §3. Never mask with `--retry`. |

3. **Re-run only the fixed area** (`--filter=`, `--dirty`, or a path) until green, then the full suite once before declaring done.

---

## Decision tables

### Test type

| Type | Boots Laravel? | Hits DB? | When |
|---|---|---|---|
| **Feature** | Yes | Yes | HTTP endpoints, full request flow, multi-class behavior |
| **Unit** | No | No | Single class, pure logic, no framework |
| **Integration** | Yes | Yes | Cross-class behavior without HTTP (services, jobs together) |
| **Browser** (Dusk) | Yes | Yes | UI flows that depend on JavaScript |
| **Arch** | No | No | Structural rules (layering, no debug calls) |

When unsure: **start with a Feature test**. Drop to Unit only when speed or isolation justifies. Full rationale in `references/testing_strategies.md` §1.

### Fake vs real

| Dependency | Decision |
|---|---|
| Queue / jobs | `Queue::fake()` / `Bus::fake()` — unless the job's own logic is under test |
| Mail / Notification | Fake, always — assert sent, never deliver |
| External HTTP | `Http::fake([...])`, always — real HTTP in tests is a bug |
| Storage / filesystem | `Storage::fake('disk')` |
| Events | **Real** unless asserting dispatch; then `Event::fake([Only::class])` so listeners still run |
| Database | **Real**, via `RefreshDatabase` — do not mock Eloquent |
| Container services | **Real** — resolve from the container |
| Non-Laravel SDKs (payment gateway, etc.) | Mockery: `$this->mock(Gateway::class)` |

**Heuristic:** prefer fakes (real Laravel collaborators with an assertion API) over mocks (Mockery doubles). Mocks are for non-Laravel services only.

### DB reset strategy

| Trait | Behavior | When |
|---|---|---|
| `RefreshDatabase` | Migrates fresh once, wraps each test in a transaction | Default for Feature tests |
| `DatabaseTransactions` | Transaction only, no migration | DB already migrated/seeded |
| `DatabaseMigrations` | Migrates fresh per test, no transaction | Testing transaction behavior itself |

Apply globally in `tests/Pest.php`: `uses(RefreshDatabase::class)->in('Feature');`

---

## Core patterns (kept minimal)

### HTTP assertion depth

⚠️ **Anti-pattern:** asserting only the status code (`assertOk()`) on JSON endpoints. It misses content regressions. Always pair with `assertJsonPath(...)` or `assertJsonStructure(...)`.

### Factories — test-specific usage

```php
$user = User::factory()->state(['admin' => true])->create();   // ad-hoc state
$post = Post::factory()->published()->create();                // named state
Post::factory()->count(3)->recycle($user)->create();           // share parent across tree
User::factory()->count(3)->sequence(['role' => 'admin'], ['role' => 'editor'])->create();
```

Deep factory design (definitions, relationships, seeders) is owned by the `laravel-backend` skill.

⚠️ **Anti-pattern:** factories that hit external services (HTTP, S3) in `definition()`. Keep factories pure.

### Mail fake bypass

⚠️ Code that instantiates and sends a Mailable outside the facade chain bypasses `Mail::fake()`. Always send via `Mail::to(...)->send(new WelcomeMail(...))` so the fake intercepts it.

### Inertia responses

Assert component name and props with `assertInertia(fn (AssertableInertia $page) => $page->component('Posts/Index')->has('posts.data', 5))`. Deep prop assertions, deferred/partial testing: load the `laravel-inertia` skill (§14).

### Browser testing (Dusk)

Detect: `composer show laravel/dusk`. Reserve Dusk for flows Feature + Inertia testing cannot reach (drag-and-drop, complex JS state, third-party widgets) — **Dusk is ~10× slower** than a Feature test covering the same route.

### Architecture tests

```php
arch('controllers do not access models directly')
    ->expect('App\Http\Controllers')
    ->not->toUse(['App\Models']);

arch('no debug calls in production code')
    ->expect(['dd', 'dump', 'var_dump', 'die', 'print_r', 'ray'])
    ->not->toBeUsed();

arch()->preset()->laravel();    // built-in Laravel rules
arch()->preset()->security();   // forbids eval, exec, system, unserialize
```

Run them as part of the normal suite so structural drift fails CI.

### Coverage and mutation

```bash
vendor/bin/pest --coverage --min=80              # floor, not target
vendor/bin/pest --mutate --covered-only          # mutation on covered code
```

⚠️ Coverage is a **floor and a signal**, never a goal — 100% with shallow assertions is worse than 70% with meaningful ones. **Mutation strategy:** target critical business logic (billing, auth, permissions, scheduling); run nightly or per-release, not per-PR — too slow.

CI wiring (which gates block merge, cadence, YAML): load the `laravel-static-analysis` skill.

---

## Rules & anti-patterns

| Smell | Why | Detect |
|---|---|---|
| Test hits real HTTP / external service | Slow, flaky | `grep -rLn "Http::fake" tests/Feature` on tests using `Http::` |
| Factory calls external service in `definition()` | Slows every test using it | `grep -rn "Http::\|Storage::disk" database/factories/` |
| Mailable sent outside the facade | Bypasses `Mail::fake()` | `grep -rn "(new .*Mail" app/ \| grep -v "Mail::"` |
| Mocking what should be faked (Queue, Mail, Event) | Loses Laravel's assertion API | `grep -rn "shouldReceive" tests/ \| grep -iE "queue\|mail\|event"` |
| Only `assertOk()` on JSON endpoints | Misses content regressions | `grep -rn "assertOk();$" tests/` |
| Missing `RefreshDatabase` on Feature tests | State bleeds across tests and runs | `grep -n "RefreshDatabase" tests/Pest.php` (must exist) |
| `sleep()` in tests | Slow and still racy | `grep -rn "sleep(" tests/` — use `Carbon::setTestNow(...)` |
| `markTestSkipped` / `->skip()` older than a sprint | Compounds debt | `grep -rn "markTestSkipped\|->skip(" tests/` |
| `--retry` in CI masking flakiness | Hides the root cause | `grep -rn "retry" .github/workflows/` |
| Coverage as a hard target (chasing 100%) | Drives shallow assertions | `--min` above ~85 in CI config |
| Browser test where Feature would suffice | 10× slower for no gain | Dusk test with no JS interaction steps |
| Arch rules not run in CI | Structural drift goes undetected | Arch tests in an excluded group |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Suite fails randomly (flaky) | Time, random data, order, or unfaked external | Match the source against the flakiness table in `references/best_practices.md` §3; pin with `Carbon::setTestNow(...)`, fake externals. Fix or delete within the sprint. |
| Tests pass solo, fail in parallel | Shared state: same file paths, static properties, hardcoded DB names | `Storage::fake()` per test; reset statics in `beforeEach`; let Pest's per-process DBs (`testing_1`, `testing_2`, …) work — never hardcode the test DB name. Setup: `references/test_automation.md` §8. |
| `RefreshDatabase` suite is slow | Long migration chain replayed on boot; or `DatabaseMigrations` used by mistake | `php artisan schema:dump` to squash migrations; confirm `RefreshDatabase` (transaction per test), not `DatabaseMigrations` (migration per test). |
| Factory unique collisions (`UniqueConstraintViolation`, `unique()` overflow) | Fixed values under `count()`, or `fake()->unique()` pool exhausted | Use `sequence(...)` for per-row values; `recycle($parent)` instead of re-creating parents; widen the faker pool or derive uniqueness from a sequence index. |
| Tests fail only in CI | Missing `.env.testing` values, missing PHP extension (PCOV/Xdebug), MySQL service not ready | Diff local vs CI env; coverage needs PCOV or Xdebug installed. |

---

## Reference routing

| Task | Load |
|---|---|
| Designing a suite, arguing Feature vs Unit vs integration boundaries | `references/testing_strategies.md` |
| Pyramid/coverage/flakiness stances (opinionated positions only — file is deliberately short) | `references/best_practices.md` |
| Datasets, custom expectations, parallel setup, mutation setup, full CI YAML | `references/test_automation.md` |

---

## Cross-references

| Topic | Where |
|---|---|
| Domain logic being tested (Eloquent, Controllers, FormRequests, Policies) | `laravel-backend` skill |
| Auth flow being tested (Sanctum, Fortify, guards) | `laravel-auth` skill |
| Queue/job test patterns (`Bus::fake`, `Queue::fake`, batching, chains) | `laravel-queues` skill |
| Inertia-specific assertions (`assertInertia` deep) | `laravel-inertia` skill |
| Pint, Larastan, Rector, CI gates | `laravel-static-analysis` skill |
| Browser a11y testing (axe via Dusk) | `laravel-a11y` skill |
| Security regression tests | `laravel-security` skill |
| Vitest / Testing Library for JS components | (owned by the `laravel-react` / `laravel-vue` agents) |
| CI infrastructure, runners, containers | (owned by the `devops` agent) |
