# Test Automation — Pest, CI, Mutation, Parallel

Deep Pest reference and CI integration. Loaded when configuring Pest features beyond the basics or designing a CI pipeline.

## 1. Pest setup

### 1.1 Install (greenfield)

```bash
composer require pestphp/pest --dev --with-all-dependencies
composer require pestphp/pest-plugin-laravel --dev
php artisan pest:install
```

### 1.2 Files

| File | Purpose |
|---|---|
| `tests/Pest.php` | Global Pest config — `uses()`, custom expectations, helpers |
| `tests/TestCase.php` | Base test class — extends Laravel's, app-wide setup |
| `tests/Feature/*` | Feature tests (HTTP, integration) |
| `tests/Unit/*` | Unit tests (pure logic) |
| `tests/Browser/*` | Dusk tests (when present) |
| `phpunit.xml` | PHPUnit config — Pest reads it |

### 1.3 Recommended `tests/Pest.php`

```php
<?php

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

uses(TestCase::class)->in('Feature', 'Unit');
uses(RefreshDatabase::class)->in('Feature');

// Custom expectations
expect()->extend('toBeUuid', function () {
    return $this->toMatch('/^[0-9a-f-]{36}$/i');
});

expect()->extend('toBePublished', function () {
    return $this->toBeInstanceOf(Post::class)
                ->and($this->value->published_at)->not->toBeNull();
});

// Global helper functions
function asAdmin(): TestCase
{
    return test()->actingAs(User::factory()->admin()->create());
}
```

## 2. Higher-order testing

Pest's higher-order syntax chains expectations across the same subject:

```php
// Without higher-order
test('user attributes', function () {
    $user = User::factory()->create();
    expect($user->name)->toBeString();
    expect($user->email)->toBeString();
    expect($user->is_admin)->toBeFalse();
});

// With higher-order
test('user attributes', function () {
    expect(User::factory()->create())
        ->name->toBeString()
        ->email->toBeString()
        ->is_admin->toBeFalse();
});
```

Property access chains:

```php
expect($user)->name->toBe('Gabriel')->email->toEndWith('@example.com');
```

## 3. Datasets

Run the same test with multiple inputs.

### 3.1 Inline

```php
it('rejects invalid emails', function (string $email) {
    expect(filter_var($email, FILTER_VALIDATE_EMAIL))->toBeFalse();
})->with(['no-at', '@no-local', 'spaces @email.com']);
```

### 3.2 Named (clearer failures)

```php
it('rejects invalid emails', function (string $email) {
    expect(filter_var($email, FILTER_VALIDATE_EMAIL))->toBeFalse();
})->with([
    'missing @' => 'no-at',
    'no local'  => '@no-local',
    'spaces'    => 'spaces @email.com',
]);
```

### 3.3 Shared datasets

```php
// tests/Pest.php
dataset('admin_users', fn () => User::factory()->admin()->count(3)->create());

// Anywhere
it('lists admins only', function (User $admin) {
    $this->getJson('/api/admins')->assertJsonFragment(['id' => $admin->id]);
})->with('admin_users');
```

### 3.4 Multi-arg datasets

```php
it('computes total', function (int $a, int $b, int $expected) {
    expect($a + $b)->toBe($expected);
})->with([
    [1, 2, 3],
    [10, -5, 5],
]);
```

## 4. Custom expectations

Add domain expectations once, use everywhere:

```php
// tests/Pest.php
expect()->extend('toBePublished', function () {
    return $this->toBeInstanceOf(Post::class)
                ->and($this->value->published_at)->not->toBeNull();
});

// Usage
expect($post)->toBePublished();
```

For chained expectations, return `$this`:

```php
expect()->extend('toHaveErrorOn', function (string $field) {
    expect($this->value->errors())->toHaveKey($field);
    return $this;
});

// Chain
expect($validator)->toHaveErrorOn('email')->toHaveErrorOn('password');
```

## 5. Architecture tests

Enforce structural rules — they're tests, run as part of the suite, no separate command.

```php
arch('controllers do not access models directly')
    ->expect('App\Http\Controllers')
    ->not->toUse(['App\Models']);

arch('actions are final and have a handle method')
    ->expect('App\Actions')
    ->toBeFinal()
    ->toHaveMethod('handle');

arch('no debug functions in production code')
    ->expect(['dd', 'dump', 'var_dump', 'die', 'print_r', 'ray'])
    ->not->toBeUsed();

arch('models live in App\Models')
    ->expect('App\Models')
    ->toExtend('Illuminate\Database\Eloquent\Model');

// Built-in presets
arch()->preset()->laravel();        // Laravel-specific common rules
arch()->preset()->security();       // forbids eval, exec, system, unserialize
arch()->preset()->php();            // PHP-level safety rules
```

## 6. Coverage

```bash
vendor/bin/pest --coverage                          # text in terminal
vendor/bin/pest --coverage --min=80                 # fail if below 80%
vendor/bin/pest --coverage-html=coverage            # HTML report
vendor/bin/pest --coverage-clover=coverage.xml      # for Codecov / Sonar
vendor/bin/pest --coverage-cobertura=cobertura.xml  # for GitLab
```

Required: Xdebug or PCOV PHP extension. PCOV is faster (coverage-only, no debugging).

```ini
; php.ini for CI
zend_extension=pcov.so
pcov.enabled=1
```

## 7. Mutation testing (Pest 3+)

```bash
vendor/bin/pest --mutate                       # run mutation against full suite
vendor/bin/pest --mutate --bail                # stop at first survivor
vendor/bin/pest --mutate --covered-only        # only mutate code with coverage
vendor/bin/pest --mutate --min=80              # fail if mutation score < 80%
vendor/bin/pest --mutate --filter=Post         # filter by test name
```

What it does: flips operators (`==` → `!=`), conditions (`if (a)` → `if (!a)`), return values, etc., then runs the suite. Survivors = mutations no test caught = test gap.

**Strategy:**
- Don't run mutation on the whole suite by default — too slow
- Target critical business logic (billing, auth, permissions, scheduling, state machines)
- Run nightly or per-release in CI, not per-PR

## 8. Parallel testing

```bash
vendor/bin/pest --parallel                       # auto-detect cores
vendor/bin/pest --parallel --processes=4
vendor/bin/pest --parallel --runner=ParaTest\\Runners\\PHPUnit\\Runner
```

What happens:
1. Pest spawns N processes
2. Each process gets its own DB (`testing_1`, `testing_2`, …)
3. Tests are distributed across processes
4. Results merged at the end

Speedup: ~3-4× on 8 cores for typical suites.

**Pre-flight checks before going parallel:**
- All tests use `RefreshDatabase` or `DatabaseTransactions` (no shared DB state)
- File system writes are faked (`Storage::fake()`)
- External services are faked (`Http::fake()`, `Mail::fake()`, etc.)
- No shared static state in classes
- No `markTestSkipped` because of "depends on previous test"

## 9. Filtering for fast local TDD

```bash
vendor/bin/pest --filter=PostTest               # by file/class name
vendor/bin/pest --filter='it creates'           # by test name
vendor/bin/pest --group=critical                # by group annotation
vendor/bin/pest tests/Feature/Auth              # by path
vendor/bin/pest --bail                          # stop at first failure
vendor/bin/pest --retry                         # retry failed once
vendor/bin/pest --dirty                         # only tests touching changed files (gold for TDD)
```

`--dirty` is the killer feature for inner-loop TDD — runs only the tests affected by your unstaged changes.

## 10. Full GitHub Actions CI

```yaml
# .github/workflows/tests.yml
name: tests
on: [pull_request, push]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      mysql:
        image: mysql:8
        env:
          MYSQL_ROOT_PASSWORD: secret
          MYSQL_DATABASE: testing
        ports: ['3306:3306']
        options: >-
          --health-cmd="mysqladmin ping"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=3

      redis:
        image: redis:7
        ports: ['6379:6379']

    strategy:
      matrix:
        php: ['8.3', '8.4']

    steps:
      - uses: actions/checkout@v4

      - name: Setup PHP ${{ matrix.php }}
        uses: shivammathur/setup-php@v2
        with:
          php-version: ${{ matrix.php }}
          coverage: pcov
          extensions: mbstring, pdo, pdo_mysql, redis, intl, bcmath

      - name: Cache Composer
        uses: actions/cache@v4
        with:
          path: vendor
          key: ${{ runner.os }}-php${{ matrix.php }}-composer-${{ hashFiles('composer.lock') }}

      - name: Install dependencies
        run: composer install --no-interaction --prefer-dist

      - name: Copy environment
        run: cp .env.example .env && php artisan key:generate

      - name: Pint (style)
        run: vendor/bin/pint --test

      - name: Larastan (static analysis)
        run: vendor/bin/phpstan analyse --memory-limit=2G

      - name: Pest (tests + coverage)
        env:
          DB_CONNECTION: mysql
          DB_HOST: 127.0.0.1
          DB_USERNAME: root
          DB_PASSWORD: secret
          DB_DATABASE: testing
          REDIS_HOST: 127.0.0.1
          CACHE_STORE: redis
          QUEUE_CONNECTION: redis
        run: vendor/bin/pest --parallel --coverage --min=80

      - name: Upload coverage to Codecov
        if: matrix.php == '8.3'
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

## 11. Deprecations & warnings as failures

Catch deprecations as they ship — much cheaper than a Laravel-version-bump-day surprise.

```xml
<!-- phpunit.xml -->
<phpunit
    failOnWarning="true"
    failOnDeprecation="true"
    failOnNotice="true"
    failOnRisky="true">
```

## 12. Seeders for tests

```php
// tests/Pest.php
uses(RefreshDatabase::class)->beforeEach(function () {
    $this->seed(PermissionSeeder::class);
})->in('Feature');
```

Or per test:

```php
it('uses seeded permissions', function () {
    $this->seed(PermissionSeeder::class);
    // ... rest of test
});
```

⚠️ Anti-pattern: seeders that create application-domain fixtures (test users, test posts). Seeders should set up *immutable reference data* (permissions, countries, currencies). Test data comes from factories.

## 13. Anti-patterns

| Smell | Why |
|---|---|
| `markTestSkipped` left for > 1 sprint | Compounds debt; either fix or delete |
| Mutation testing on whole suite per PR | Cripples CI; nightly is the right cadence |
| Coverage as a hard gate without quality signal | Drives shallow assertions; pair with mutation |
| Architecture tests not running in CI | Drift goes undetected |
| Parallel testing without isolation review | Random failures, hard to debug |
| `--retry` masking flaky tests | Hides root cause; investigate, don't paper over |
| CI without Pint and static analysis | Style and type bugs leak to production |
| `--bail` in CI by default | Misses parallel failures; only useful local |
| Seeder used for app-domain fixtures (users, posts) | Hidden coupling; use factories |
| Coverage required to merge but not measured per-feature | Drives game-the-metric tests |
