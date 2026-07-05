# QA Best Practices — Laravel

Test discipline that survives the codebase growing past prototype. Loaded when designing test strategy or auditing test quality. Kept deliberately short: naming, AAA, and factory basics are assumed — this file carries only the opinionated stances.

## 1. The pyramid (and why it inverts in Laravel)

Classic test pyramid: many unit tests at the base, fewer integration, very few end-to-end. In Laravel the pyramid usually **inverts** — most tests are Feature tests (HTTP-driven, hit DB):

- Laravel boots fast (~50ms) — Feature tests aren't slow enough to push toward unit
- Most code interacts with the framework — pure unit tests would mock half of Laravel
- The bug surface users care about is HTTP behavior, not pure logic
- Behavior-level tests survive refactors; implementation-level tests break with them

**Pragmatic stance:** default to **Feature** for endpoints and multi-class flows; drop to **Unit** for pure logic (calculators, parsers, value objects); **Dusk** only for true JS/UI flows; **arch tests** for structural rules. Don't optimize for "more unit tests" — optimize for tests that catch bugs users would notice.

## 2. Coverage — signal, not metric

Line coverage says which lines ran, not whether assertions were meaningful. The valuable signals: **coverage drops on a PR** (code added without tests) and **untouched branches**. Use `--min` as a floor (~80%), never as a target — chasing 100% drives shallow assertions. Pair with mutation testing for branch-quality signal.

## 3. Determinism — kill flakiness fast

A flaky test is worse than no test: it desensitizes the team to real failures. Fix or delete within the sprint; never `markTestSkipped` indefinitely.

| Source | Fix |
|---|---|
| Random data triggering edge case | `fake()->seed(N)` or pin values |
| Time-dependent logic | `Carbon::setTestNow(...)`, clear in teardown |
| Order-dependent DB state | `RefreshDatabase`; review parallel safety |
| Async/queue running | `Queue::fake()` / `Bus::fake()` |
| External HTTP / mail / storage | `Http::fake(...)`, `Mail::fake()`, `Storage::fake(...)` |
| DB sequencing assumptions | Never assume IDs are 1, 2, 3; assert by attribute |
| Eventual-consistency reads (search, cache) | Fake, or wait deterministically |
| Static state in classes | Avoid; else reset in `beforeEach` |

## 4. What to test / what NOT to test

Test: public contracts (endpoints, commands, events), business rules (pricing, state transitions, authorization), edge cases (empty, max length, unicode, time boundaries), and every bug fix (regression test = the bug report).

Don't test: framework behavior (Eloquent saving is Laravel's job), trivial getters, config values, private methods directly (test through the public surface; extract if it needs its own test), generated code.

## 5. Anti-patterns — consolidated

| Smell | Why |
|---|---|
| Test name = method name | Hides intent; name the behavior |
| Single test asserting many unrelated behaviors | Hard to debug failures |
| Setup > 10 lines | God class under test; refactor |
| Test hitting real HTTP/S3/email | Flaky, slow |
| Skipping flaky tests indefinitely | Compounds debt |
| Coverage as a goal (100% target) | Drives shallow assertions |
| Tests using shared seeder data | Implicit coupling, order dependency |
| Assertions only on status code | Misses content regressions |
| Mocking what should be faked (Queue, Mail) | Loses Laravel's assertion API |
| Browser test where Feature would suffice | 10× slower for no gain |
| Tests that exist just for coverage | Flag and delete |

CI gate wiring (what blocks merge, cadence, parallel mode) lives in the `laravel-static-analysis` skill.
