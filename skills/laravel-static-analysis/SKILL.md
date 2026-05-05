---
name: laravel-static-analysis
description: Static analysis and quality tooling for Laravel 12 / PHP 8.3+ — Pint (formatting, presets, --test vs apply), Larastan/PHPStan (levels, baseline, ignore patterns, bootstrapping), Rector (php83/php84/laravel-12 sets, --dry-run vs --apply), Pest --coverage / --type-coverage, frontend type-check (tsc --noEmit, vue-tsc), pre-commit hooks, CI wiring, and the verify-then-apply discipline. Consumed by the code-review and backend agents.
---

# Laravel Static Analysis — Pint, Larastan, Rector, type-check

The verification toolchain for a Laravel 12 / PHP 8.3+ codebase. Stack-agnostic on the PHP side; covers the **TS/Vue type-check** at the level of "wire it into CI" (component conventions live in `laravel-react`/`laravel-vue`). Designed for the agents that *write* (`backend`) and *review* (`code-review`).

## When to use this skill

- Setting up Pint, Larastan, Rector in a fresh project
- Picking the right Larastan level for the project's maturity
- Establishing a baseline for legacy code
- Running tools in **verify mode** (`--test`, `--dry-run`) before applying
- Wiring pre-commit hooks and CI checks
- Reading and acting on tool output during code review
- Diagnosing false positives, ignore patterns, bootstrap issues

## When NOT to use

| Topic | Use instead |
|---|---|
| Choosing test cases, factory shapes, fakes | `laravel-qa` |
| Eloquent / controller / domain conventions the tools enforce | `laravel-backend` |
| OWASP-grade dependency CVEs (`composer audit`, `npm audit`) | `laravel-security` |
| CI runner setup (GitHub Actions YAML, caching) | (devops agent) |

## Stack assumptions

- Laravel 12, PHP 8.3+
- `laravel/pint` (ships with Laravel 11+)
- `larastan/larastan` v3+ (built on PHPStan 2.x)
- `rector/rector` v2+ with `driftingly/rector-laravel`
- TypeScript on the frontend (skip §6 if pure JS/Blade)

---

## 1. The verify-then-apply discipline

**The rule:** every tool in this skill has a verify mode and an apply mode. Always run verify first, read the diff, then apply.

| Tool | Verify | Apply |
|---|---|---|
| Pint | `pint --test` | `pint` |
| Larastan/PHPStan | `phpstan analyse` (no apply mode) | n/a — surface findings, fix manually |
| Rector | `rector --dry-run` | `rector` |
| Pest | `pest --coverage` | n/a — surface findings, fix manually |
| TypeScript | `tsc --noEmit` / `vue-tsc --noEmit` | n/a — surface findings, fix manually |

⚠️ **Anti-pattern:** running `pint` or `rector` (apply mode) on a dirty working tree, or as the first action when reviewing unfamiliar code. The diff hides under whatever the tool changed.

---

## 2. Pint — formatting

Laravel's opinionated wrapper around PHP-CS-Fixer. Pint ships with Laravel; no install needed.

### 2.1 Presets

```jsonc
// pint.json
{
    "preset": "laravel",          // 'laravel' | 'psr12' | 'per' | 'symfony'
    "rules": {
        "no_unused_imports": true,
        "ordered_imports": { "sort_algorithm": "alpha" }
    },
    "exclude": ["bootstrap/cache", "storage"],
    "notPath": ["server.php"]
}
```

| Preset | Use when |
|---|---|
| `laravel` | Default. Matches the framework's own style. |
| `per` | PER-CS 2.0 (the modern PSR-12 successor). Recommended for non-framework PHP. |
| `psr12` | Strict PSR-12 only. Older codebases. |
| `symfony` | Symfony conventions. Mostly relevant if migrating from a Symfony app. |

**Recommendation:** `laravel` for app code; `per` for shared library code.

### 2.2 Commands

```bash
pint --test                           # report only — non-zero exit if changes needed
pint --test --bail                    # stop on first violation
pint                                  # apply
pint app/Models/ --test               # scope to a path
pint --dirty                          # only files modified vs main branch
pint --diff                           # show what would change without modifying
pint -v                               # verbose (which rules fired)
```

**Rules:**
- `pint --test` is the CI command. `pint` (apply) is the developer command.
- `pint --dirty` is the right call inside a hook or in a "fix-only-my-changes" workflow.
- ⚠️ **Anti-pattern:** committing `pint` apply runs without reviewing the diff. The "Refactor" preset can rewrite logic structure (e.g. `simplified_if_return`) — read before pushing.

---

## 3. Larastan / PHPStan — type & logic analysis

Larastan extends PHPStan with Laravel-aware rules (Eloquent magic, container resolution, route/config/view helpers, facades, model factories, generic Eloquent).

### 3.1 Install

```bash
composer require larastan/larastan --dev
```

### 3.2 `phpstan.neon` baseline config

```yaml
includes:
    - ./vendor/larastan/larastan/extension.neon

parameters:
    level: 6
    paths:
        - app
        - database
        - routes
        - tests
    excludePaths:
        - app/Legacy/*
    tmpDir: storage/phpstan
```

### 3.3 Level cheat-sheet

| Level | What's new |
|---|---|
| 0 | Undefined classes / methods / functions |
| 1 | Possibly undefined variables, unknown magic methods |
| 2 | Method existence on **all** expressions |
| 3 | Return types, property assignments |
| 4 | Dead code (always-true conditions, unreachable returns) |
| 5 | Argument types |
| **6** | **Missing typehints** — recommended for new code |
| 7 | Partial union types |
| 8 | Null safety (calls/properties on nullable) |
| 9 / `max` | Strictest array typing |

**Pick a level you can hold:** level 8 with 200 ignored errors is worse than level 5 with 0.

### 3.4 Baseline — the shrinking budget

```bash
./vendor/bin/phpstan analyse --generate-baseline
```

Writes `phpstan-baseline.neon`. Add `includes: - phpstan-baseline.neon` to `phpstan.neon`. CI now fails on **new** findings only.

Track baseline size in CI; fail builds that grow it. Lower the cap on each PR that fixes baseline entries.

### 3.5 Commands

```bash
./vendor/bin/phpstan analyse                                  # full project
./vendor/bin/phpstan analyse app/Models                        # scope
./vendor/bin/phpstan analyse --memory-limit=2G                 # large codebase
./vendor/bin/phpstan analyse --error-format=github             # GitHub annotations
./vendor/bin/phpstan analyse --generate-baseline               # write baseline
./vendor/bin/phpstan clear-result-cache                        # nuke incremental cache
```

### 3.6 Quick ignore recipe

```yaml
ignoreErrors:
    -
        message: '#Property .* is never read#'
        path: app/Models/Legacy/*.php
```

⚠️ **Anti-pattern:** wide regex without `path:` scope (e.g. `'#Call to an undefined method.*#'`) swallows real bugs.

For per-level deep dives with Laravel-specific error examples, the full baseline shrinking workflow (split baselines, count guards, per-level migration), bootstrap files for macros, generic Eloquent annotations, Spatie ecosystem extensions, IDE-helper integration, and the false-positive diagnosis workflow, see [`references/larastan_levels_and_baseline.md`](references/larastan_levels_and_baseline.md).

---

## 4. Rector — automated refactors

Rector applies AST-level rewrites: PHP version upgrades, Laravel upgrades, code-quality refactors.

### 4.1 Install

```bash
composer require rector/rector driftingly/rector-laravel --dev
```

### 4.2 `rector.php`

```php
<?php
use Rector\Config\RectorConfig;
use Rector\Set\ValueObject\LevelSetList;
use Rector\Set\ValueObject\SetList;
use RectorLaravel\Set\LaravelSetList;

return RectorConfig::configure()
    ->withPaths([
        __DIR__ . '/app',
        __DIR__ . '/database',
        __DIR__ . '/routes',
        __DIR__ . '/tests',
    ])
    ->withSkip([
        __DIR__ . '/app/Legacy',
    ])
    ->withSets([
        LevelSetList::UP_TO_PHP_83,
        LaravelSetList::LARAVEL_120,
        SetList::CODE_QUALITY,
        SetList::DEAD_CODE,
        SetList::TYPE_DECLARATION,
    ])
    ->withImportNames(removeUnusedImports: true);
```

### 4.3 Useful sets

| Set | What it does |
|---|---|
| `LevelSetList::UP_TO_PHP_83` | All PHP 8.0–8.3 modernizations |
| `LevelSetList::UP_TO_PHP_84` | Adds 8.4 features (property hooks, asymmetric visibility) |
| `LaravelSetList::LARAVEL_120` | Idioms specific to Laravel 12 |
| `SetList::CODE_QUALITY` | General refactors (dead conditions, simpler returns) |
| `SetList::DEAD_CODE` | Remove unreachable code |
| `SetList::TYPE_DECLARATION` | Add typehints inferred from usage |
| `SetList::EARLY_RETURN` | Flatten nested ifs |

### 4.4 Commands

```bash
./vendor/bin/rector process --dry-run                       # show diff, exit non-zero if changes
./vendor/bin/rector process                                  # apply
./vendor/bin/rector process app/Models --dry-run             # scope
./vendor/bin/rector process --debug                          # show which rules ran
./vendor/bin/rector process --clear-cache                    # nuke incremental cache
```

**Rules:**
- Always `--dry-run` first. Rector can rewrite control flow.
- Apply in **small, themed PRs** (one set at a time, one path scope at a time). One mega-PR with every set is unreviewable.
- Re-run Pint after Rector. Rector emits valid PHP, not formatted PHP.
- Re-run PHPStan after Rector. Type changes can surface previously-hidden findings.

⚠️ **Anti-pattern:** running Rector with every set enabled on first install. Hundreds of files change; review fatigue → merge anyway → silent regressions.

---

## 5. Pest coverage & type coverage

```bash
./vendor/bin/pest --coverage                                 # line coverage report
./vendor/bin/pest --coverage --min=80                        # fail if < 80%
./vendor/bin/pest --coverage-html=build/coverage             # HTML report
./vendor/bin/pest --type-coverage                            # type-decl coverage (Pest plugin)
./vendor/bin/pest --type-coverage --min=95
```

**Rules:**
- Coverage is a **flag**, not a goal. 100% line coverage with no assertions is worse than 60% with strong ones.
- Use `--type-coverage` to prevent regressions in typehint density (often more meaningful than line coverage).
- Test design and assertion patterns live in `laravel-qa` — this skill only covers wiring the runner.

---

## 6. Frontend type-check

| Stack | Command |
|---|---|
| React (TypeScript) | `npx tsc --noEmit` |
| Vue (TypeScript) | `npx vue-tsc --noEmit` |
| Both: full build (catches Vite errors too) | `npm run build` |

Wire into `package.json`:

```jsonc
"scripts": {
    "type-check": "tsc --noEmit",
    "type-check:vue": "vue-tsc --noEmit",
    "lint": "eslint resources/js"
}
```

ESLint config and component-level rules belong in `laravel-react` / `laravel-vue`. This skill stops at "run the type-checker in CI."

---

## 7. Pre-commit hooks

`captainhook/captainhook` is the PHP-native option; `husky` + `lint-staged` works if the project already has Node tooling.

### 7.1 captainhook

```bash
composer require --dev captainhook/captainhook captainhook/plugin-composer
./vendor/bin/captainhook install
```

```jsonc
// captainhook.json
{
    "pre-commit": {
        "enabled": true,
        "actions": [
            { "action": "./vendor/bin/pint --dirty --test" },
            { "action": "./vendor/bin/phpstan analyse --memory-limit=2G" }
        ]
    }
}
```

### 7.2 husky + lint-staged

```jsonc
// package.json
"lint-staged": {
    "*.php": ["./vendor/bin/pint --dirty --test"],
    "*.{ts,tsx}": ["eslint --fix", "tsc --noEmit -p tsconfig.json"]
}
```

**Rules:**
- Hooks must be **fast** (< ~3s). Run only on changed files (`--dirty`, `lint-staged`).
- Heavy checks (PHPStan, full Rector) belong in CI, not pre-commit.
- ⚠️ **Anti-pattern:** running `phpstan analyse` (full project) in pre-commit. 30s hook → developers `--no-verify` → drift.

---

## 8. CI wiring

Run **all five** in parallel (PHP and Node concurrently):

```yaml
# .github/workflows/ci.yml — sketch
jobs:
  php:
    steps:
      - run: composer install --prefer-dist --no-progress
      - run: ./vendor/bin/pint --test
      - run: ./vendor/bin/phpstan analyse --error-format=github
      - run: ./vendor/bin/rector process --dry-run
      - run: ./vendor/bin/pest --coverage --min=80
  node:
    steps:
      - run: npm ci
      - run: npm run type-check
      - run: npm run lint
      - run: npm run build
```

**Rules:**
- All five must be required checks for merge.
- Cache: `vendor/`, `node_modules/`, PHPStan's `tmpDir`, Rector's cache dir.
- Surface failures inline (use `--error-format=github` for PHPStan; ESLint and tsc emit GitHub annotations natively).

---

## 9. Diagnosing false positives

### Pint
- Tool reformats code you intentionally wrote a different way → check `pint.json#rules`. Override the offending rule (set `false`) or add the file to `exclude`.

### PHPStan / Larastan
- "Call to undefined method" on Eloquent magic → bump Larastan version; ensure `extension.neon` is included.
- Macros not recognized → add the macro registration file to `bootstrapFiles:` in `phpstan.neon`.
- Type narrows incorrectly after `if ($x === null) return;` → check for shadowed variable; add `// @phpstan-ignore-next-line` only as last resort.
- Generic class warnings everywhere → set `checkGenericClassInNonGenericObjectType: false` while you migrate types.

### Rector
- Rule rewrites valid code in surprising way → identify the rule (`--debug`), `->withSkip([SomeRector::class])`, file an upstream issue if it looks wrong.
- Rector keeps converting back-and-forth across runs → conflicting sets enabled; pick one direction.

---

## 10. Anti-patterns — consolidated

| Smell | Section | Detection |
|---|---|---|
| `pint` (apply) on dirty working tree | §1, §2 | review commit history |
| Going to PHPStan `max` on brownfield day one | §3.3 | absurdly large `phpstan-baseline.neon` |
| Wide `ignoreErrors` regex (no `path:` scope) | §3.6 | review `phpstan.neon` |
| Rector with all sets first install, mega-PR | §4 | git diff size |
| No baseline budget enforced in CI | §3.4 | CI doesn't fail on baseline growth |
| Coverage gate without assertion-quality gate | §5 | tests with `expect(true)->toBeTrue()` style filler |
| Heavy checks in pre-commit (full PHPStan) | §7 | `captainhook.json` / `lint-staged` config |
| Static-analysis steps not required for merge | §8 | branch protection settings |
| `// @phpstan-ignore` without comment explaining why | §9 | grep `phpstan-ignore` and check next line |

---

## 11. Cross-references

| Topic | Skill |
|---|---|
| Pest test design, factories, fakes, HTTP testing | `laravel-qa` |
| Eloquent / controller / Form Request conventions enforced by Larastan | `laravel-backend` |
| `composer audit`, `npm audit`, dependency CVEs | `laravel-security` |
| ESLint rules, React/Vue component conventions | `laravel-react`, `laravel-vue` |
| GitHub Actions YAML, caching, runner sizing | (devops agent) |
