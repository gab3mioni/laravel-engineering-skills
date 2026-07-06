# Rector on Laravel — sets, brownfield progression, rector-laravel rules

Deep dive on Rector with the `driftingly/rector-laravel` extension. Loaded when the agent is choosing which Rector sets to enable, ordering them for a brownfield adoption, reviewing a Rector diff, or wiring `rector --dry-run` into CI.

This document assumes Rector v2+ with `driftingly/rector-laravel` on Laravel 12 / PHP 8.3+. Execution discipline lives in the SKILL.md **Rector procedure** workflow (dry-run → review → apply one set → pint → phpstan → commit); this reference supplies the set-level depth that workflow consumes.

## 1. Setup on Laravel 12

### 1.1 Install

```bash
composer require --dev rector/rector driftingly/rector-laravel
```

### 1.2 Registering Laravel sets — two APIs

Rector currently supports two ways to enable the Laravel sets. Both are valid; pick by intent.

**Composer-based (automated).** Rector reads `composer.json`, detects the installed Laravel version, and enables the matching upgrade sets via the set provider:

```php
<?php

declare(strict_types=1);

use Rector\Config\RectorConfig;
use RectorLaravel\Set\LaravelSetProvider;

return RectorConfig::configure()
    ->withPaths([
        __DIR__ . '/app',
        __DIR__ . '/database',
        __DIR__ . '/routes',
        __DIR__ . '/tests',
    ])
    ->withPhpSets()                                    // PHP sets inferred from composer.json
    ->withSetProviders(LaravelSetProvider::class)
    ->withComposerBased(laravel: true);
```

**Manual (explicit constants).** You name every set yourself:

```php
<?php

declare(strict_types=1);

use Rector\Config\RectorConfig;
use Rector\Set\ValueObject\SetList;
use RectorLaravel\Set\LaravelSetList;

return RectorConfig::configure()
    ->withPaths([
        __DIR__ . '/app',
        __DIR__ . '/database',
        __DIR__ . '/routes',
        __DIR__ . '/tests',
    ])
    ->withSets([
        SetList::DEAD_CODE,                            // exactly ONE set per run on brownfield
    ]);
```

**Which to use:**

| Situation | Approach |
|---|---|
| Greenfield app kept current with framework releases | Composer-based — sets track `composer.json` automatically |
| Brownfield adoption, one set per commit (this skill's default) | Manual — the progression in §2 requires enabling exactly one set at a time |
| Laravel version upgrade sweep | Manual with `LaravelLevelSetList::UP_TO_LARAVEL_*` (each level set includes all earlier ones) |

⚠️ The composer-based approach enables *groups* of sets at once. That is fine as a steady-state config after adoption is done; it fights the one-set-per-commit rule during adoption.

### 1.3 Available Laravel set constants

From `RectorLaravel\Set\LaravelSetList` (verified against the rector-laravel repo — do not guess new names):

`LARAVEL_ARRAYACCESS_TO_METHOD_CALL`, `LARAVEL_ARRAY_STR_FUNCTION_TO_STATIC_CALL`, `LARAVEL_CODE_QUALITY`, `LARAVEL_COLLECTION`, `LARAVEL_CONTAINER_STRING_TO_FULLY_QUALIFIED_NAME`, `LARAVEL_ELOQUENT_MAGIC_METHOD_TO_QUERY_BUILDER`, `LARAVEL_FACADE_ALIASES_TO_FULL_NAMES`, `LARAVEL_FACTORIES`, `LARAVEL_IF_HELPERS`, `LARAVEL_LEGACY_FACTORIES_TO_CLASSES`, `LARAVEL_STATIC_TO_INJECTION`, `LARAVEL_TESTING`, `LARAVEL_TYPE_DECLARATIONS` — plus version sets (`LARAVEL_120`, …) and `RectorLaravel\Set\LaravelLevelSetList` cumulative sets (`UP_TO_LARAVEL_130`, …).

## 2. Safe-set progression for brownfield

The core decision: **which sets, in which order**. Each row is one full pass of the SKILL.md Rector procedure — one set, one commit. Stop at any tier; the later tiers are optional style choices, not requirements.

| Order | Set | Risk | What to review in the diff |
|---|---|---|---|
| 1 | `SetList::DEAD_CODE` | Low | Removed code that is only "dead" because of runtime magic (container bindings, event listeners resolved by name, reflection). Restore those via `withSkip`. |
| 2 | `SetList::CODE_QUALITY` | Low–medium | Rewritten conditionals and simplified returns — confirm boolean logic is equivalent, especially around loose comparisons and null. |
| 3 | `withPhpSets()` (php81 → php82 → php83, or all at once via composer.json) | Medium | `readonly`, enums, first-class callables, `match` conversions. Check serialization of newly-readonly classes and any code that mutated those properties dynamically. |
| 4 | `LaravelLevelSetList::UP_TO_LARAVEL_*` / `LaravelSetList::LARAVEL_120` | Medium | Framework API migrations. Run the full test suite, not just the quality gate — these change framework calls, not just style. |
| 5 | `LaravelSetList::LARAVEL_CODE_QUALITY`, `LARAVEL_COLLECTION`, `LARAVEL_IF_HELPERS` | Medium | Idiom swaps (loops → collections, `if` → helpers). Verify laziness/short-circuit semantics survived the rewrite. |
| 6 | `SetList::TYPE_DECLARATION` / `LaravelSetList::LARAVEL_TYPE_DECLARATIONS` | High | Inferred types on public methods are new **contracts**. A wrong inference (e.g. `string` where `null` flows at runtime) becomes a `TypeError` in production. Read every signature change. |
| 7 (or never) | `LaravelSetList::LARAVEL_STATIC_TO_INJECTION`, `LARAVEL_FACADE_ALIASES_TO_FULL_NAMES`, `LARAVEL_ELOQUENT_MAGIC_METHOD_TO_QUERY_BUILDER` | Opinionated | Whole-codebase style shifts (facades → injection, magic → `query()`). Only apply if the team has agreed on the style; otherwise the diff churn buys nothing. |

**Rules:**

- Tiers 1–2 first because they shrink the codebase — every later diff gets smaller and easier to review.
- PHP sets (tier 3) before Laravel sets (tier 4): the framework sets assume modern PHP syntax.
- One PHP minor at a time (`php81`, then `php82`, then `php83`) on large codebases; jump straight to the target version only when the diff stays reviewable.
- Tier 7 sets are **style decisions**, not quality improvements. Skipping them forever is a valid end state.

⚠️ **Anti-pattern:** treating the progression as a checklist to complete. The goal is a codebase the team can hold, not a maximal set list in `rector.php`.

## 3. Scoping — paths, skips, cache

### 3.1 `withSkip` — paths and rules

```php
use RectorLaravel\Rector\StaticCall\EloquentMagicMethodToQueryBuilderRector;

return RectorConfig::configure()
    ->withPaths([__DIR__ . '/app', __DIR__ . '/tests'])
    ->withSkip([
        __DIR__ . '/app/Legacy',                       // skip a path entirely
        __DIR__ . '/bootstrap/cache',
        EloquentMagicMethodToQueryBuilderRector::class, // skip one rule everywhere
        SomeRector::class => [__DIR__ . '/app/Console'], // skip one rule in one path
    ]);
```

Use `withSkip` for: generated code (`_ide_helper*`), vendored-in legacy modules, and individual rules whose rewrite you reviewed and rejected (§9 of SKILL.md — identify the rule with `--debug` first).

### 3.2 Processing only part of the tree

```bash
vendor/bin/rector process app/Models --dry-run          # one directory
vendor/bin/rector process $(git diff --name-only origin/main...HEAD -- '*.php') --dry-run
```

Path arguments override `withPaths` for that run. Scoping a huge set to one directory per commit is a legitimate way to keep tier-6/7 diffs reviewable — the themed-commit rule then becomes "one set × one path".

### 3.3 Cache

Rector caches parsed files and skips unchanged ones on re-runs. Persist the cache to disk (required for CI reuse; the default is fine locally):

```php
use Rector\Caching\ValueObject\Storage\FileCacheStorage;

return RectorConfig::configure()
    ->withCache(
        cacheDirectory: __DIR__ . '/storage/rector',
        cacheClass: FileCacheStorage::class,
    );
```

```bash
vendor/bin/rector process --dry-run --clear-cache        # bust a stale cache
```

**When results look stale** — a rule you just enabled reports nothing, or a skipped file keeps appearing — run once with `--clear-cache` before debugging the config. Add `storage/rector` to `.gitignore` and to the CI cache paths (SKILL.md §8).

## 4. Interplay discipline — why one set per commit

The SKILL.md **Rector procedure** workflow is the execution contract. This section is the *why* behind its steps:

- **Pint after every apply.** Rector emits syntactically valid PHP with no formatting guarantees — wrong indentation, spacing that violates the `laravel` preset. Committing un-Pinted Rector output makes the next `pint --test` fail on code you did not write by hand.
- **PHPStan after every apply.** Rector's changes alter what PHPStan sees: new native typehints surface previously hidden mismatches; removed "dead" branches change type narrowing. A set that is behavior-safe can still push the project over its PHPStan level — you want that failure attributed to *this* set, in *this* commit.
- **One set per commit is a bisection strategy.** Rector rewrites by AST pattern, without runtime knowledge. Edge cases exist: loose-comparison rewrites, laziness changes in collection conversions, type inference that misses a runtime `null`. When a regression appears next week, `git bisect` lands on one themed commit that names the set — mixed-set commits make the offending rule unfindable.

⚠️ **Anti-pattern:** "the dry-run diff looked fine, so I enabled three more sets and applied them together." Each set's diff was reviewable; the combined diff is not, and neither is the rollback.

## 5. Laravel-specific rule highlights

Concrete high-value rules from `driftingly/rector-laravel` (names verified against the repo's rule overview). Enable individually via `withRules([...])` or through the sets noted.

### 5.1 `AnonymousMigrationsRector`

Converts named migration classes to the anonymous-class form (default since Laravel 9; kills class-name collisions between migrations).

```php
// Before
class CreateUsersTable extends Migration { /* ... */ }

// After
return new class extends Migration { /* ... */ };
```

### 5.2 `RemoveDumpDataDeadCodeRector`

Removes leftover `dd()` / `dump()` calls — debugging residue that otherwise ships.

```php
// Before
public function store(StoreUserRequest $request): RedirectResponse
{
    dd($request->validated());
    User::create($request->validated());

// After — the dd() line is gone
```

### 5.3 `RequestStaticValidateToInjectRector`

Replaces static/helper request validation with an injected `Request` — testable and Larastan-friendly.

```php
// Before
$data = request()->validate(['name' => 'required']);

// After
public function store(Request $request): RedirectResponse
{
    $data = $request->validate(['name' => 'required']);
```

### 5.4 `EloquentMagicMethodToQueryBuilderRector` (in `LARAVEL_ELOQUENT_MAGIC_METHOD_TO_QUERY_BUILDER`)

Rewrites magic static calls on models to explicit `query()` chains — gives Larastan a real `Builder<Model>` to type against.

```php
// Before
$user = User::where('email', $email)->first();

// After
$user = User::query()->where('email', $email)->first();
```

### 5.5 `FactoryFuncCallToStaticCallRector` (in `LARAVEL_FACTORIES`)

Migrates the legacy global `factory()` helper to class-based factory notation (pair with `FactoryDefinitionRector` / `LARAVEL_LEGACY_FACTORIES_TO_CLASSES` for the definitions themselves).

```php
// Before
$user = factory(User::class)->create();

// After
$user = User::factory()->create();
```

### 5.6 `EnvVariableToEnvHelperRector`

Replaces raw superglobal env access with the `Env` helper, which respects Laravel's env resolution (and cached config).

```php
// Before
$name = $_ENV['APP_NAME'];

// After
$name = \Illuminate\Support\Env::get('APP_NAME');
```

Also worth knowing: `JsonCallToExplicitJsonCallRector` (`$this->json('POST', ...)` → `$this->postJson(...)`, in `LARAVEL_TESTING`), `HelperFuncCallToFacadeClassRector` and `AppToResolveRector` (helper-call normalization), `SubStrToStartsWithOrEndsWithStaticMethodCallRector` (`substr()` comparisons → `Str::startsWith()` / `Str::endsWith()`).

## 6. CI usage — dry-run as a gate

```yaml
# .github/workflows/ci.yml (excerpt — full pipeline in SKILL.md §8)
- uses: actions/cache@v4
  with: { path: storage/rector, key: "rector-${{ github.sha }}", restore-keys: rector- }
- run: vendor/bin/rector process --dry-run
```

- `--dry-run` exits **0** when nothing would change and **non-zero** when it would — that exit code *is* the gate. No extra parsing needed.
- The gate's meaning: "the codebase stays clean under the agreed sets." A red build means someone merged code an enabled set would rewrite — fix it locally via the Rector procedure, not in CI.
- Keep the CI config identical to the local one (same `rector.php`). A CI-only set list produces failures developers cannot reproduce.

**Why auto-applying in CI is an anti-pattern:** a bot commit that applies Rector output skips the human diff review that steps 2 and 5 of the Rector procedure exist for — behavior-altering edge cases (§4) land unreviewed, un-bisectable, and attributed to a bot. CI verifies; humans apply.

## 7. Anti-patterns — consolidated

| Smell | Why it hurts | Detection |
|---|---|---|
| Multiple sets applied in one commit | Regressions can't be bisected to a rule; diff unreviewable | commit touches hundreds of files with mixed themes |
| Running `rector process` (apply) on a dirty working tree | Rector's changes tangle with yours; neither diff is reviewable or revertable | `git status` before apply |
| Skipping the PHPStan re-run after apply | Type changes surface findings later, attributed to the wrong PR | quality-gate history; PHPStan failures on "no-op" PRs |
| Skipping Pint after apply | Unformatted machine output committed; next `pint --test` fails on it | `pint --test` right after a Rector commit |
| `--no-diffs` blind apply | Suppresses the only review artifact dry-run produces | `--no-diffs` in scripts/CI |
| Composer-based sets during brownfield adoption | Enables set groups wholesale; one-set-per-commit impossible | `withComposerBased` in `rector.php` + huge first PR |
| CI bot auto-committing Rector output | Unreviewed behavior changes; see §6 | bot commits applying refactors |
| Debugging "Rector finds nothing" without `--clear-cache` | Stale cache masks the real config state | rule enabled but no diff; skipped file still processed |

## 8. Cross-references

- `laravel-static-analysis` SKILL.md — **Rector procedure** workflow (the execution contract this reference feeds), §4 summary, §8 CI pipeline, §9 false-positive triage (`--debug` → `withSkip`)
- [`references/larastan_levels_and_baseline.md`](larastan_levels_and_baseline.md) §9 — run order with Pint and PHPStan
- `laravel-backend` — the idioms tier-5/7 sets push toward (collections, injection, query-builder style)
- `laravel-qa` — the test suite that must pass after tier-3/4 sets (framework/PHP upgrades)
