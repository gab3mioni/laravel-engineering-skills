# Larastan / PHPStan — Levels, baseline, ignore patterns

Deep dive on PHPStan with the Larastan extension. Loaded when the agent is choosing a starting level, building a baseline shrinking strategy, debugging Eloquent / Facade false positives, or integrating PHPStan extensions for the Spatie ecosystem.

This document assumes Larastan v3 (PHPStan 2.x) on Laravel 12 / PHP 8.3+.

## 1. The level ladder — what each level adds

Each level **inherits all checks from lower levels**. The list below shows what's *new* at the level (not what's still enforced).

### Level 0 — sanity baseline

- Undefined classes, methods, functions, constants
- Wrong number of arguments to a method/function
- Calling methods on `null` (when the code reads `$x = null; $x->foo()` literally)

**Typical Laravel finding:** referencing a deleted controller class in `routes/web.php` after a delete.

```php
Route::get('/old', OldController::class);  // → "Class App\Http\Controllers\OldController not found"
```

### Level 1 — variable hygiene

- Possibly undefined variables (uninitialized branches)
- Unknown magic methods/properties on `__get` / `__call` classes (without proper PHPDoc)

**Typical Laravel finding:** Eloquent property access without proper `@property` annotations on the model.

```php
// Larastan resolves this via its extension — but at level 1 you'll see warnings if the model has dynamic columns not in the DB
$user->custom_attr;
```

### Level 2 — method existence on all expressions

- Unknown methods on **any** expression (not just `$this`)

**Typical Laravel finding:** calling a relationship as a method on the wrong return type.

```php
$user->posts()->wherePublished();  // if `wherePublished` doesn't exist on Builder, level 2 catches it
```

### Level 3 — return types & property assignments

- Return type mismatches (`function (): int { return 'no'; }`)
- Type mismatches in property assignments (`int $x = 'no';`)

**Typical Laravel finding:** controller method declared `: View` returning a `RedirectResponse` on the error path.

### Level 4 — dead code

- Always-true / always-false conditions
- Unreachable returns (code after `return`)
- Useless `instanceof`

**Typical Laravel finding:** old null-checks on properties typed as non-nullable.

```php
if ($this->config !== null) { /* unreachable: $config is always set */ }
```

### Level 5 — argument types

- Wrong types passed to method/function arguments

**Typical Laravel finding:** passing a string ID to a method typed as `Model`.

```php
public function notify(User $user) { /* ... */ }

// Caller
$service->notify(123);  // → "Parameter #1 expects User, int given"
```

### Level 6 — missing typehints

- Functions without parameter types
- Functions without return types
- `array` typehints without value types (`array<string>` instead of bare `array`)

**Recommended starting point for new code.**

**Typical Laravel finding:** existing methods missing return types.

```php
public function index() { return view('posts.index'); }  // → "Method has no return type specified"
```

### Level 7 — partial union types

- Calling a method that exists on one type of the union but not all

**Typical Laravel finding:** working with `string|null` and forgetting the null branch.

```php
$slug = $request->input('slug');  // string|null
strtoupper($slug);                // → "Parameter #1 expects string, string|null given"
```

### Level 8 — null safety

- Method calls / property access on nullable types
- The "every nullable must be handled" level

**Typical Laravel finding:** `$user = User::find(...)` (nullable) followed by `$user->email`.

```php
$user = User::find($id);  // User|null
echo $user->email;        // → "Cannot access property on User|null"
```

### Level 9 — strictest array typing

- Unspecified `array` parameters and returns flagged
- All array shapes must be expressed: `array{name: string, age: int}` or `array<string, mixed>`

**Typical Laravel finding:** controller returning unstructured arrays.

```php
public function show(): array
{
    return ['user' => $user, 'posts' => $posts];  // → "Method should return array<...> but returns array{user: ..., posts: ...}"
}
```

### Level 10

Strict about **implicit** mixed too: a parameter with no type declaration is treated as `mixed` and reported, not just values explicitly typed `mixed`. Added in PHPStan 2.0.

### Level `max`

Alias for the highest available level — currently **10**. Tracks the latest as PHPStan adds checks.

⚠️ **Anti-pattern:** pinning to `max` and skipping levels. When PHPStan adds new checks, your CI breaks at random; predict-and-bump is calmer.

## 2. Choosing a starting level

| Codebase state | Start at | Path forward |
|---|---|---|
| Greenfield (< 50 PHP files) | **6** | Bump to 8 within 3 months, hit `max` within 6 |
| Small mature app (< 500 files) with no static analysis | **0** with baseline | One level per quarter |
| Large brownfield (> 500 files) | **0** with baseline | One level per quarter; cap at 6 if 8/9 generates churn |
| Migration from Psalm or no analysis | **6** with baseline | Same as greenfield once baseline is at 0 |

**The single best decision:** pick a level you can hold. Level 8 with 200 ignored errors is worse than level 5 with 0 — the first lies about its rigor.

## 3. Baseline workflow — the shrinking budget

Brownfield apps generate too many findings to fix at once. The baseline says "I accept these for now; block any new ones".

### 3.1 Generate

```bash
./vendor/bin/phpstan analyse --generate-baseline
```

Writes `phpstan-baseline.neon`. Add to `phpstan.neon`:

```yaml
includes:
    - phpstan-baseline.neon
```

CI now passes for current state and fails on **new** findings.

### 3.2 Shrink

The baseline is debt. Pay it down:

```bash
# Show baseline size
wc -l phpstan-baseline.neon

# After fixing some errors, regenerate
./vendor/bin/phpstan analyse --generate-baseline
```

Track baseline size as a CI metric — fail builds that grow it:

```yaml
# .github/workflows/ci.yml
- name: PHPStan
  run: ./vendor/bin/phpstan analyse --error-format=github

- name: Baseline size guard
  run: |
    BASELINE_LINES=$(wc -l < phpstan-baseline.neon || echo 0)
    MAX_LINES=$(cat .phpstan-baseline-max || echo 99999)
    if [ "$BASELINE_LINES" -gt "$MAX_LINES" ]; then
      echo "Baseline grew from $MAX_LINES to $BASELINE_LINES — fix before merge"
      exit 1
    fi
```

Commit `.phpstan-baseline-max` with the current size; lower it on each PR that fixes baseline entries.

### 3.3 The "split baseline" pattern

For very large baselines, split per directory:

```yaml
# phpstan.neon
includes:
    - phpstan-baseline-app.neon
    - phpstan-baseline-database.neon
    - phpstan-baseline-tests.neon
```

Generate scoped baselines:

```bash
./vendor/bin/phpstan analyse app --generate-baseline=phpstan-baseline-app.neon
./vendor/bin/phpstan analyse database --generate-baseline=phpstan-baseline-database.neon
./vendor/bin/phpstan analyse tests --generate-baseline=phpstan-baseline-tests.neon
```

Lets you assign ownership and track shrinkage per area.

### 3.4 Per-level baseline progression

When bumping levels, generate a fresh baseline at the new level, then shrink:

```bash
# In phpstan.neon: bump level: 6 → 7
./vendor/bin/phpstan analyse --generate-baseline
git add phpstan-baseline.neon phpstan.neon
git commit -m "chore: phpstan level 7 with baseline"
```

Now you can **fix** level-7-specific errors without being blocked by the noise.

## 4. Larastan — the Laravel-aware bits

`larastan/larastan` adds:

- **Eloquent magic** — `User::where('email', ...)` resolves to `Builder` correctly
- **Facade resolution** — `Cache::get(...)` resolves to the underlying `CacheRepository::get(...)`
- **Helper functions** — `route()`, `config()`, `view()`, `app()` are typed
- **Container resolution** — `app(SomeService::class)` returns `SomeService`
- **Model factories** — `User::factory()->create()` returns `User`
- **Generic Eloquent** — `Builder<User>`, `HasMany<Post>`, `Collection<int, User>`

```yaml
# phpstan.neon
includes:
    - ./vendor/larastan/larastan/extension.neon
```

Without `extension.neon`, ~80% of Laravel-specific code reads as untyped at level 6+.

## 5. Common ignore patterns

### 5.1 Patterns that almost always need ignoring

```yaml
parameters:
    ignoreErrors:
        # Macroable methods — Eloquent Builder, Collection, Request
        - '#Call to an undefined method.*::macro\(\)#'

        # Facade dynamic methods that PHPStan can't resolve through the underlying class
        - '#Call to an undefined static method Illuminate\\Support\\Facades\\.*#'

        # HighOrderProxy chains: Collection methods on collections of methods
        - '#Call to an undefined method Illuminate\\Support\\HighOrderCollectionProxy.*#'

        # Eloquent \$attributes property access (when accessed directly)
        - '#Access to an undefined property.*::\$attributes#'

        # Pivot models on belongsToMany — pivot data isn't typed
        - '#Access to an undefined property.*\\Pivot::.*#'
```

### 5.2 Per-file ignore (preferred over global)

```yaml
ignoreErrors:
    -
        message: '#Property .* is never read#'
        path: app/Models/Legacy/*.php

    -
        message: '#Cannot call method .* on .*\|null#'
        paths:
            - app/Http/Controllers/Legacy/*.php
            - tests/Legacy/*.php
        count: 14                    # exact count — fails if more or fewer
```

`count:` is useful as a regression guard — adds break the build, fixes also break it (forcing you to remove the ignore).

### 5.3 Inline ignore — last resort

```php
// @phpstan-ignore-next-line
$thing->doSomething();

// @phpstan-ignore-next-line method.notFound
$thing->doSomething();   // identifier-scoped (preferred)

/** @phpstan-ignore-next-line Reason: Spatie Data property hooks not understood by PHPStan 2.x */
$data->someProperty;     // with explanation (mandatory in code review)
```

⚠️ **Anti-pattern:** `// @phpstan-ignore-next-line` without an inline comment. The next reader has zero context.

⚠️ **Anti-pattern:** wide regex in `ignoreErrors:` that swallows real bugs. `'#Call to an undefined method.*#'` is a regex bomb — it silences every method-not-found error in the project.

## 6. Bootstrapping macros and runtime extensions

Macros registered at boot time (`AppServiceProvider::boot()`) are invisible to PHPStan unless told to load them.

```yaml
# phpstan.neon
parameters:
    bootstrapFiles:
        - phpstan-bootstrap.php
```

```php
// phpstan-bootstrap.php
require_once __DIR__ . '/vendor/autoload.php';

use Illuminate\Support\Collection;
use Illuminate\Support\Str;

// Re-declare custom macros so PHPStan sees their signatures
Collection::macro('pluckUnique', fn (string $key) => collect($this->pluck($key))->unique()->values());
Str::macro('squish', fn (string $value) => preg_replace('/\s+/', ' ', trim($value)));
```

For runtime-resolved bindings (e.g. `app('myService')` returning a class chosen at runtime), use a stub file:

```yaml
parameters:
    stubFiles:
        - stubs/MyServiceStub.php
```

## 7. Third-party PHPStan extensions

Install `phpstan/extension-installer` so any PHPStan extension shipped by a dependency (including Larastan itself) registers automatically — no manual `includes:` per package:

```bash
composer require --dev phpstan/extension-installer
```

Some ecosystem packages bundle their own PHPStan extension or stubs; others have community extensions. **Verify the package exists on Packagist before recommending it** (`composer show -a <vendor/package>` or search packagist.org filtered by type `phpstan-extension`) — never install from a guessed name.

## 8. Generic Eloquent — making relationships precise

Larastan adds generic templates to Eloquent base classes. Annotate models for full inference:

```php
/**
 * @property int    $id
 * @property string $title
 * @property string $body
 * @property-read User              $author
 * @property-read Collection<int, Comment> $comments
 *
 * @method static Builder<self> published()
 * @method static Builder<self> draft()
 */
final class Post extends Model
{
    /** @return BelongsTo<User, self> */
    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    /** @return HasMany<Comment> */
    public function comments(): HasMany
    {
        return $this->hasMany(Comment::class);
    }

    /** @param Builder<self> $query */
    public function scopePublished(Builder $query): Builder
    {
        return $query->whereNotNull('published_at');
    }
}
```

The `barryvdh/laravel-ide-helper` package generates much of this automatically:

```bash
composer require --dev barryvdh/laravel-ide-helper
php artisan ide-helper:models --write
```

⚠️ Re-run after schema changes; commit the generated `_ide_helper_models.php` so CI sees the same picture as devs.

## 9. Run order with Pint and Rector

Static analysis is one of three tools; the order matters.

```bash
# Recommended pre-commit / CI order
./vendor/bin/pint                              # 1. Format (apply or --test)
./vendor/bin/rector process --dry-run          # 2. Refactor opportunities (verify)
./vendor/bin/phpstan analyse                   # 3. Type / logic checks
./vendor/bin/pest                              # 4. Tests
```

**Why this order:**
- Pint first — Rector's diffs are unreadable on unformatted code.
- Rector dry-run before PHPStan — Rector's output may include new typehints that PHPStan reads. Apply Rector first if you're doing a sweep.
- PHPStan after Rector — type-narrowing changes from Rector can surface previously-hidden findings.

⚠️ **Anti-pattern:** running PHPStan on a tree where Rector has unrun changes. PHPStan sees old types; results look stale.

## 10. CI integration patterns

### 10.1 GitHub Actions

```yaml
- uses: actions/cache@v4
  with:
    path: storage/phpstan
    key: phpstan-${{ github.sha }}
    restore-keys: phpstan-

- name: PHPStan
  run: ./vendor/bin/phpstan analyse --error-format=github --memory-limit=2G
```

`--error-format=github` emits `::error file=<path>,line=<n>::<message>` lines that surface as inline annotations in PRs.

### 10.2 GitLab CI

```yaml
phpstan:
  script:
    - ./vendor/bin/phpstan analyse --error-format=gitlab > phpstan-report.json
  artifacts:
    reports:
      codequality: phpstan-report.json
```

### 10.3 Diff-only mode

For incremental adoption without baseline:

```bash
# Run only on changed files
./vendor/bin/phpstan analyse $(git diff --name-only origin/main...HEAD --diff-filter=AM | grep '\.php$')
```

⚠️ Doesn't catch errors *introduced* by other-file changes. Use as a stop-gap, not the primary gate.

## 11. Diagnosing false positives

Workflow when PHPStan reports something you believe is wrong:

1. **Reproduce in isolation.** `./vendor/bin/phpstan analyse path/to/file.php` — narrow scope.
2. **Check Larastan version.** `composer show larastan/larastan` — bump if behind.
3. **Check if the extension is loaded.** `phpstan.neon` must `include:` `./vendor/larastan/larastan/extension.neon`.
4. **Read the type the analyzer sees.** Add `\PHPStan\dumpType($value);` temporarily — runs no actual code, prints the inferred type during analysis.
5. **Macros / runtime registration?** See §6 — `bootstrapFiles:`.
6. **Spatie / third-party class without typing?** See §7 — install the extension or write a stub.
7. **Genuinely a PHPStan bug?** File upstream with a minimal repro. In the meantime, scoped `ignoreErrors` with a comment.

## 12. Common Eloquent / Laravel patterns and how PHPStan reads them

| Pattern | What PHPStan sees with Larastan |
|---|---|
| `Post::find(1)` | `Post|null` |
| `Post::findOrFail(1)` | `Post` (never null) |
| `Post::where('user_id', 1)->first()` | `Post|null` |
| `Post::where('user_id', 1)->firstOrFail()` | `Post` |
| `Post::all()` | `Collection<int, Post>` |
| `Post::query()` | `Builder<Post>` |
| `Post::factory()->create()` | `Post` |
| `Post::factory()->count(3)->create()` | `Collection<int, Post>` |
| `auth()->user()` | `Authenticatable|null` |
| `request()->user()` | `User|null` (with proper `@method` on Request) |
| `Cache::get('key')` | `mixed` (untyped) — wrap in a typed accessor for stricter handling |
| `config('app.name')` | `mixed` — wrap with `assert(is_string($x))` for level 8+ |

## 13. Cross-references

- `laravel-static-analysis` SKILL.md §3 — summary that links here
- `laravel-static-analysis` §4 — Rector run order
- `laravel-static-analysis` §7 — pre-commit hook integration
- `laravel-backend` — the patterns Larastan validates (Eloquent, Form Request, Resource, Service)
- `laravel-qa` — Pest type coverage as a complementary metric
