---
name: laravel-static-analysis
description: Static analysis and quality tooling for Laravel 12 / PHP 8.3+ — Pint (formatting, presets, --test vs apply), Larastan/PHPStan (levels, baseline, ignore patterns, bootstrapping), Rector (php83/php84/laravel-12 sets, --dry-run vs --apply), Pest --coverage / --type-coverage, frontend type-check (tsc --noEmit, vue-tsc), pre-commit hooks, CI wiring, and the verify-then-apply discipline. Use when wiring or running pint/phpstan/rector, choosing a PHPStan level, adopting analysis on a legacy codebase, setting up CI quality gates, or debugging type-check failures. Consumed by the code-review and backend agents.
---

# Laravel Static Analysis — Pint, Larastan, Rector, type-check

The verification toolchain for a Laravel 12 / PHP 8.3+ codebase. Stack-agnostic on the PHP side; covers the **TS/Vue type-check** at the level of "wire it into CI" (component conventions live with the `laravel-react`/`laravel-vue` agents). Designed for the agents that *write* (`backend`) and *review* (`code-review`). This skill also **owns CI quality-gate wiring for the whole plugin** — `laravel-qa`, `laravel-a11y`, and `laravel-security` route their CI questions here (§8).

## When to use this skill

- Setting up Pint, Larastan, Rector in a fresh project
- Picking the right Larastan level; establishing a baseline for legacy code
- Running tools in **verify mode** (`--test`, `--dry-run`) before applying
- Wiring pre-commit hooks and CI checks
- Reading and acting on tool output during code review
- Diagnosing false positives, ignore patterns, bootstrap issues

## When NOT to use

| Topic | Use instead |
|---|---|
| Choosing test cases, factory shapes, fakes | `laravel-qa` skill |
| Eloquent / controller / domain conventions the tools enforce | `laravel-backend` skill |
| OWASP-grade dependency CVEs (`composer audit`, `npm audit`) | `laravel-security` skill |
| ESLint rules, React/Vue component conventions | `laravel-react` / `laravel-vue` **agents** |
| CI runner infra (self-hosted runners, deploy pipelines) | `devops` **agent** — quality-gate jobs themselves live here (§8) |

## Stack assumptions

- Laravel 12, PHP 8.3+, `laravel/pint` (ships with Laravel 11+)
- `larastan/larastan` v3+ (built on PHPStan 2.x)
- `rector/rector` v2+ with `driftingly/rector-laravel`
- TypeScript on the frontend (skip §6 if pure JS/Blade)

---

## Workflows

### Run the quality gate

The canonical local sequence. Every other skill in this plugin that says "run the quality gate" means this. Run in order; stop and branch on failure.

1. `vendor/bin/pint --test --dirty` — expect exit 0. Non-zero → run `vendor/bin/pint --dirty`, review the diff, re-run step 1.
2. `vendor/bin/phpstan analyse` — expect exit 0. Non-zero → fix the findings; for **pre-existing debt only**, baseline (§3.4). Never inline-ignore errors in new code.
3. `vendor/bin/rector process --dry-run` — expect exit 0. Non-zero → review the proposed diff; apply only deliberate sets via the Rector procedure below. Advisory, not an auto-apply.
4. `vendor/bin/pest --dirty` — expect exit 0. Failure → fix the code or the test; do not skip.
5. If TypeScript is present: `npx tsc --noEmit` (React) or `npx vue-tsc --noEmit` (Vue) — expect exit 0. Non-zero → fix the type errors before shipping.

### Adopt on a brownfield project

1. Install the tools (§3.1, §4.1). Pint already ships with Laravel.
2. Pick a starting level: **5** for a typical brownfield app, **0** for true legacy. Starting-level table with symptoms lives in [`references/larastan_levels_and_baseline.md`](references/larastan_levels_and_baseline.md).
3. `vendor/bin/phpstan analyse --generate-baseline` and include `phpstan-baseline.neon` in `phpstan.neon`.
4. Gate CI on two conditions: **no new errors** and **baseline only shrinks** (fail builds that grow it).
5. Raise the level using the shrinking-budget strategy (§3.4): fix baseline entries in every PR, lower the cap, bump the level when the baseline for the current level empties.

### Rector procedure

1. `vendor/bin/rector process --dry-run` with exactly **one** set enabled.
2. Review the full diff — Rector can rewrite control flow.
3. Apply: `vendor/bin/rector process`.
4. Re-run `vendor/bin/pint` (Rector emits valid PHP, not formatted PHP).
5. Re-run `vendor/bin/phpstan analyse` (type changes surface hidden findings).
6. Commit as a themed change.
7. Move to the next set and repeat from step 1.

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
    "exclude": ["bootstrap/cache", "storage"]
}
```

| Preset | Use when |
|---|---|
| `laravel` | Default. Matches the framework's own style. |
| `per` | PER-CS 2.0 (the modern PSR-12 successor). Recommended for non-framework PHP. |
| `psr12` | Strict PSR-12 only. Older codebases. |
| `symfony` | Symfony conventions. Mostly relevant if migrating from a Symfony app. |

**Recommendation:** `laravel` for app code, `per` for shared library code.

### 2.2 Commands

```bash
pint --test                           # report only — non-zero exit if changes needed
pint                                  # apply
pint app/Models/ --test               # scope to a path
pint --dirty                          # only uncommitted files
pint --diff=main --test               # only files changed vs a branch (CI-friendly)
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
| 9 | Strict about `mixed` — only mixed-to-mixed operations allowed |
| 10 / `max` | Stricter `mixed` — flags operations on explicit `mixed` too |

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
./vendor/bin/phpstan analyse app/Models --memory-limit=2G      # scope; raise memory on large codebases
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
    ->withSkip([__DIR__ . '/app/Legacy'])
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

### 4.4 Commands

```bash
./vendor/bin/rector process --dry-run                       # show diff, exit non-zero if changes
./vendor/bin/rector process                                  # apply
./vendor/bin/rector process app/Models --dry-run             # scope
./vendor/bin/rector process --debug                          # show which rules ran
```

**Rules:**
- Follow the **Rector procedure** workflow at the top of this skill: dry-run → review → one set → pint → phpstan → commit → next set.
- Apply in **small, themed PRs** (one set at a time, one path scope at a time). One mega-PR with every set is unreviewable.

⚠️ **Anti-pattern:** running Rector with every set enabled on first install. Hundreds of files change; review fatigue → merge anyway → silent regressions.

---

## 5. Pest coverage & type coverage

```bash
./vendor/bin/pest --coverage                                 # line coverage report
./vendor/bin/pest --coverage --min=80                        # fail if < 80%
./vendor/bin/pest --coverage-html=build/coverage             # HTML report
./vendor/bin/pest --type-coverage --min=95                   # type-decl coverage (Pest plugin)
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

ESLint config and component-level rules belong to the `laravel-react` / `laravel-vue` agents. This skill stops at "run the type-checker in CI."

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
            { "action": "./vendor/bin/pint --dirty --test" }
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

## 8. CI wiring — the authoritative pipeline

This is the single quality-gate pipeline for the plugin. `laravel-qa`, `laravel-a11y`, and `laravel-security` all plug into it; per-tool configuration for a11y scanners (axe-core, pa11y) and security scanners (`composer audit`, `npm audit`) lives in those skills' references — the CI jobs get wired here.

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  php:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: shivammathur/setup-php@v2
        with: { php-version: '8.3', coverage: xdebug }
      - uses: actions/cache@v4
        with: { path: vendor, key: "php-${{ hashFiles('composer.lock') }}" }
      - run: composer install --prefer-dist --no-progress
      - run: ./vendor/bin/pint --test
      - run: ./vendor/bin/phpstan analyse --error-format=github
      - run: ./vendor/bin/rector process --dry-run
      - run: ./vendor/bin/pest --coverage --min=80

  node:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: npm }
      - run: npm ci
      - run: npm run type-check        # tsc --noEmit / vue-tsc --noEmit
      - run: npm run lint
      - run: npm run build
```

**Rules:**
- Run PHP and Node jobs in **parallel**; all steps are required checks for merge.
- Cache: `vendor/`, npm cache, PHPStan's `tmpDir`, Rector's cache dir.
- Surface failures inline (use `--error-format=github` for PHPStan; ESLint and tsc emit GitHub annotations natively).
- Baseline budget (§3.4): fail the build if `phpstan-baseline.neon` grows.

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

## Reference routing

| Need | Reference |
|---|---|
| Level meanings, baseline mechanics, generics annotations, false-positive diagnosis | [`references/larastan_levels_and_baseline.md`](references/larastan_levels_and_baseline.md) |

---

## Cross-references

| Topic | Where |
|---|---|
| Pest test design, factories, fakes, HTTP testing | `laravel-qa` skill |
| Eloquent / controller / Form Request conventions enforced by Larastan | `laravel-backend` skill |
| `composer audit`, `npm audit`, dependency CVEs | `laravel-security` skill |
| a11y scanner config (axe-core, pa11y) for the CI jobs in §8 | `laravel-a11y` skill references |
| ESLint rules, React/Vue component conventions | `laravel-react` / `laravel-vue` **agents** |
| CI runner infra, deploy pipelines, caching strategy at scale | `devops` **agent** |
