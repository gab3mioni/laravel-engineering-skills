---
name: laravel-deploy
description: Deploy and runtime for Laravel 12 — runtime choice (FrankenPHP/Octane vs PHP-FPM), zero-downtime deploys, CI quality gates, Docker image patterns, supervisord/systemd templates, scheduler in clusters, env/secret management, health checks and rollback. Use when writing Dockerfiles, CI pipelines, deploy scripts, or supervisor configs — or when symptoms appear such as "site down during deploy", "workers running stale code", "sessions invalidated after deploy", "cron ran on every server". Used by `laravel-role-devops`.
---

# Laravel Deploy — Runtime and shipping

Predictable, reversible, observable deploys for Laravel 12 / PHP 8.3+. Covers the **runtime** (where things run, how images are built, how code goes live) — not queue mechanics or app architecture. Boring deploys are the goal: atomic swaps, drained workers, a health check before traffic, a rollback that is one symlink flip away.

## When to use this skill

- Choosing the HTTP runtime (FrankenPHP worker mode vs PHP-FPM behind nginx)
- Writing or reviewing a Dockerfile, compose file, or CI pipeline for a Laravel app
- Designing a zero-downtime deploy (Forge, Envoyer, or a shipped script)
- Writing supervisord / systemd units for workers
- Placing the scheduler in a multi-server cluster
- Wiring env vars and secrets into containers
- Deciding what to restart after a deploy (workers, OPcache, Octane)
- Diagnosing deploy-time failures: 502s during release, stale code, dropped sessions, missing assets

## When NOT to use

| Topic | Use instead |
|---|---|
| Queue mechanics — connections, retries, Horizon config, job design | `laravel-queues` skill |
| CI gate tool specifics — Pint presets, PHPStan levels, Rector sets, baselines | `laravel-static-analysis` skill |
| Application code — controllers, models, jobs, migration contents | `laravel-role-backend` |
| Image CVEs, hardening depth, secret threat models, CSP at the edge | `laravel-security` skill |
| Vite build internals, manifest contract with `@vite` | `laravel-frontend` skill |
| Test suites wired into CI (`pest --coverage` semantics) | `laravel-qa` skill |

Application logs, metrics, health semantics, SLOs, alerting, incident response, and deploy observability are owned by `laravel-observability`. This skill owns only runtime/deployment wiring and invokes those checks during rollout.

## Stack assumptions

Detect the project's actual stack before recommending anything:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"
```

Flags that change the advice in this skill:

| Flag | Consequence |
|---|---|
| `HAS_DOCKERFILE` / `HAS_COMPOSE` | Container path — image patterns, stdout logs, non-root user apply |
| `HAS_GH_ACTIONS` / `HAS_GITLAB_CI` | Wire gates into the existing pipeline; don't add a second CI system |
| `HAS_OCTANE` | Long-lived workers — `octane:reload` in deploy hooks, gotchas section applies |
| `HAS_HORIZON` | `horizon:terminate` replaces `queue:restart`; supervisor runs `php artisan horizon` |
| `HAS_DEPLOY_SCRIPT` / `HAS_ENVOY` | **Modify** the shipped script/recipe — never replace it with your own |
| `HAS_VITE` | Assets must be built in CI and shipped as an artifact |

- Laravel 12, PHP 8.3+. Health endpoint `/up` is available (Laravel 11+).
- ⚠️ If none of the deploy flags are present, ask how the project ships before inventing infrastructure.

---

## Workflows

### Zero-downtime deploy checklist

Run in order. Every step has a verification — a step without its check is not done.

1. **Build assets out-of-band.** `npm run build` runs in CI; the artifact (`public/build/`) is uploaded, never built on the prod box.
   Verify: `test -f public/build/manifest.json && echo OK`
2. **Atomic swap.** Prepare the new release dir fully (vendor installed, assets in place), then flip the `current` symlink in one operation (Forge / Envoyer / shipped script).
   Verify: `ln -sfn releases/<new> current && readlink current`
3. **Queue restart.** `php artisan queue:restart` (Horizon: `php artisan horizon:terminate`) so workers re-load code. Workers keep old code in memory until recycled.
   Verify: `php artisan horizon:status` shows running, or supervisor shows fresh worker PIDs (`supervisorctl status`)
4. **Cache warm.** `php artisan optimize` (config + route + view + event caches) in the **new** release dir, before it takes traffic.
   Verify: `php artisan config:show app.env` returns without error
5. **Migrations: additive only.** Safe migrations (add table, add nullable column, add index) run during deploy. Destructive changes (drop/rename column) ship behind a feature flag and migrate in **two deploys** — code stops reading first, schema changes second.
   Verify: `php artisan migrate --pretend` — read the SQL before applying
6. **Health check before traffic.** Hit `/up` on the new release; only flip traffic on 200.
   Verify: `curl -fsS -o /dev/null -w '%{http_code}' https://<app>/up` → `200`
7. **Rollback plan documented.** While the previous release dir is intact, rollback is a symlink flip (see next workflow). Write down the exact commands *before* deploying, not during the incident.
   Verify: `ls releases/ | tail -3` — the previous release still exists

⚠️ Steps 3 and 4 order matters: restarting workers before warming caches means the first jobs boot against cold caches — acceptable; warming caches in the *old* release dir is not.

### Roll back a bad deploy

1. **Confirm the previous release dir is intact** — `vendor/`, `public/build/`, cached config all present. If deploys prune aggressively and it's gone, rollback is a redeploy of the old ref instead.
2. **Check migrations first.** If the bad deploy shipped only additive migrations, old code runs fine against the new schema — flip freely. If it shipped a **destructive** change (dropped/renamed column), the old code will crash against the new schema: **do not flip — forward-fix only** (revert the code change, deploy forward).
3. **Flip the symlink:** `ln -sfn releases/<previous> current`.
4. **Restart everything that caches code:** `php artisan queue:restart` (or `horizon:terminate`), reload PHP-FPM (`systemctl reload php8.3-fpm`) or `php artisan octane:reload` — OPcache and long-lived workers otherwise keep serving the bad release.
5. **Verify:** `curl -fsS https://<app>/up` returns 200, error rate drops in logs.

⚠️ `migrate:rollback` in production is almost never the answer — it destroys data written since the deploy. Prefer flipping code while leaving additive schema in place.

---

## Decision tables

### Where does this run?

| Need | Default |
|---|---|
| HTTP server | **FrankenPHP** (worker mode) for greenfield. PHP-FPM behind nginx for legacy / strict requirements. |
| Workers | Octane (FrankenPHP worker mode) **or** classic `queue:work` under supervisord. Pick one per project, not both. |
| Scheduler | One server runs cron (`* * * * * php artisan schedule:run`); jobs use `->onOneServer()` for cluster safety. |
| Cache | Redis. `database` cache only for very small apps; `file` for tests. |
| Queue | Redis + Horizon. SQS when AWS-native and cross-region matters. |
| Sessions | Redis (driver: `redis`). `database` only when Redis is unavailable. |
| Logs | JSON-formatted to stdout/stderr; aggregation downstream (Loki, CloudWatch, Datadog). |
| Secrets | Env-var injection from a secret store (AWS SSM, Vault, Doppler). Never `.env` in the image. |

### Env and secret management

- **`.env` is a local-dev convenience, not a deploy artifact.** Production reads real environment variables injected by the platform (compose `env_file` from a secret store, ECS task secrets, Kubernetes Secrets, Forge env panel).
- **`.env.example` is the contract:** every variable the app reads, with safe placeholder values, committed. New variables land there in the same PR that reads them.
- **`APP_KEY` is a secret with a lifetime of forever.** Generated once, stored in the secret store, injected everywhere. Regenerating it invalidates sessions, signed cookies, and every `encrypted` cast column.
- **`php artisan config:cache` freezes env access.** After caching, `env()` calls outside `config/` return `null` — read config values via `config()`, and treat any `env()` in app code as a bug.
- Rotation: rotate real secrets (DB password, API keys) by injecting the new value and restarting processes — never by editing files on the box.

---

## CI gates

Required for merge — a red gate blocks, no exceptions, no `--no-verify`.

```yaml
# .github/workflows/ci.yml — sketch
jobs:
  php:
    steps:
      - composer install --prefer-dist --no-progress
      - ./vendor/bin/pint --test
      - ./vendor/bin/phpstan analyse --error-format=github
      - ./vendor/bin/rector process --dry-run
      - ./vendor/bin/pest --coverage --min=80
  node:
    steps:
      - npm ci
      - npm run lint
      - npm run type-check
      - npm run build       # also surfaces Vite errors
```

All gates required, all caches warmed — an uncached pipeline doubles feedback time and gets gates disabled "temporarily":

```yaml
      - uses: actions/cache@v4
        with:
          path: |
            vendor
            node_modules
            .phpstan-cache          # phpstan tmpDir (set in phpstan.neon)
            /tmp/rector             # rector cacheDirectory
          key: deps-${{ hashFiles('composer.lock', 'package-lock.json') }}
```

**Rules:**
- Gates run on every PR, not just on main — a red main means the gate ran too late.
- `pest --coverage --min=N` needs Xdebug or PCOV in the CI PHP image; PCOV is faster.
- The `node` job's `npm run build` doubles as a Vite smoke test — a broken import fails here, not on the prod box.

Per-tool config depth (Pint presets, PHPStan levels/baseline, Rector sets) lives in the `laravel-static-analysis` skill.

---

## Docker image patterns

Multi-stage: build tools never reach production.

```dockerfile
# --- Stage 1: PHP dependencies ---
FROM composer:2 AS vendor
WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --optimize-autoloader --no-scripts --prefer-dist

# --- Stage 2: frontend assets ---
FROM node:22-slim AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# --- Stage 3: runtime (FrankenPHP; swap for php:8.3-fpm behind nginx) ---
FROM dunglas/frankenphp:php8.3 AS app
WORKDIR /app
COPY . .
COPY --from=vendor /app/vendor ./vendor
COPY --from=assets /app/public/build ./public/build

# Prod OPcache: no stat calls, code is immutable inside the image
RUN { \
      echo 'opcache.enable=1'; \
      echo 'opcache.validate_timestamps=0'; \
      echo 'opcache.memory_consumption=256'; \
    } > /usr/local/etc/php/conf.d/opcache-prod.ini

RUN chown -R www-data:www-data storage bootstrap/cache
USER www-data
```

**Rules:**
- **No `.env` in the image.** No `COPY .env`, and `.env` in `.dockerignore`. Config comes from injected env vars.
- **Non-root `USER`** (`www-data` or a dedicated UID). Root containers turn any RCE into host-adjacent compromise.
- **Logs to stdout:** `LOG_CHANNEL=stderr` (or a stdout-targeting channel) — never `storage/logs/laravel.log` inside a container.
- `opcache.validate_timestamps=0` is safe **only** because a new deploy is a new image; on VMs with in-place code, keep timestamps on or reload FPM per deploy.
- `php artisan optimize` runs at container start (entrypoint), not at build time — config caching bakes env values, and build-time env is not runtime env.

Entrypoint sketch (warm caches with the *runtime* env, then hand off):

```bash
#!/usr/bin/env sh
set -e
php artisan optimize
exec "$@"            # CMD: frankenphp run / php-fpm / php artisan horizon
```

**One image, many roles.** Build a single image and vary the command per service: HTTP (`frankenphp run` or `php-fpm`), workers (`php artisan horizon`), scheduler (`php artisan schedule:work` in its own single-replica service). Per-role images drift; per-role commands don't.

⚠️ Never run migrations from every container's entrypoint — N replicas race the same DDL. Migrations are one deploy step (a job / one-shot container), not a boot side effect.

---

## Supervisord / systemd templates

Worker program (classic `queue:work`; Horizon runs `php artisan horizon` as a single program instead):

```ini
[program:laravel-worker]
command=php /var/www/current/artisan queue:work redis --queue=high,default,low --tries=3 --timeout=60 --max-jobs=1000 --max-time=3600
process_name=%(program_name)s_%(process_num)02d
numprocs=4
user=www-data
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stopwaitsecs=90
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
```

⚠️ **`stopwaitsecs` must exceed the longest job `--timeout`** (here 90 > 60). If supervisor SIGKILLs before the job finishes, the job dies mid-write and re-runs on restart — duplicate side effects.

After editing: `supervisorctl reread && supervisorctl update` (propose on prod, don't fire blind).

systemd equivalent (one unit per worker; scale with `laravel-worker@{1..4}.service`):

```ini
# /etc/systemd/system/laravel-worker@.service
[Unit]
Description=Laravel queue worker %i
After=network.target redis.service

[Service]
User=www-data
ExecStart=/usr/bin/php /var/www/current/artisan queue:work redis --queue=high,default,low --tries=3 --timeout=60 --max-jobs=1000 --max-time=3600
Restart=always
RestartSec=3
TimeoutStopSec=90

[Install]
WantedBy=multi-user.target
```

Same rule under a different name: `TimeoutStopSec` > job `--timeout`. Enable with `systemctl enable --now laravel-worker@{1..4}`; after deploy, `queue:restart` recycles them without touching systemd.

Horizon-specific supervisor sizing (processes, balance strategies, systemd units) lives in the `laravel-queues` skill (`horizon_ops` reference).

---

## Scheduler in clusters

- **One cron entry, one server:** `* * * * * cd /var/www/current && php artisan schedule:run >> /dev/null 2>&1`. Either only one box has the cron entry, or every box has it and every task uses `->onOneServer()` (requires Redis or DB cache for the lock).
- **`schedule:run` fires every minute** — the scheduler decides internally what is due. A cron entry with `*/5` silently skips every task scheduled between ticks.
- **Monitor for silent failure.** A dead cron produces no error — tasks just stop. Wire a heartbeat: `->thenPing($healthcheckUrl)` on a sentinel task, or an external monitor (Healthchecks.io, Oh Dear) that alerts when the ping stops arriving.
- Verify what's registered: `php artisan schedule:list`.

⚠️ **Anti-pattern:** cron on every server without `onOneServer()` — the same report/email/cleanup fires N times per tick.

Task-level options (`withoutOverlapping`, `runInBackground`, queue-backed schedules): `laravel-queues` skill §10.

---

## Octane gotchas

The app boots **once** and serves many requests. Everything that assumed a fresh process per request breaks.

| Symptom | Cause |
|---|---|
| State leaks between requests | Singletons holding request-scoped data. Use `scoped()` bindings. |
| Memory creep | Static caches in user code. Profile with `octane:status`. |
| Horizon doesn't pick up code | Forgot `php artisan octane:reload` after deploy. |
| Database connection refused after idle | `mysql.connect_timeout` / Redis `tcp-keepalive`. Use a connection pooler if traffic is bursty. |

**Deploy hook rule:** every deploy on an Octane runtime ends with `php artisan octane:reload` — the symlink flip alone changes nothing for a worker that booted the old code. Pair it with `queue:restart` / `horizon:terminate`; they cover different processes.

---

## Rules & anti-patterns — consolidated

| Smell | Detection |
|---|---|
| `QUEUE_CONNECTION=sync` in production config | `grep -rn 'QUEUE_CONNECTION=sync' .env.production deploy* .github/ 2>/dev/null` |
| `queue:work` under `nohup`/shell instead of supervisord/systemd/Horizon | `grep -rn 'nohup.*queue:work\|queue:work.*&$' deploy* scripts/ 2>/dev/null` |
| `queue:listen` in production (framework boots per job) | `grep -rn 'queue:listen' deploy* supervisor* .github/ 2>/dev/null` |
| Scheduler on every server without `->onOneServer()` | `grep -rn 'Schedule::' routes/console.php \| grep -v onOneServer` |
| `.env` baked into the image | `grep -n 'COPY.*\.env' Dockerfile; grep -c '^\.env' .dockerignore` (second must be ≥1) |
| `APP_DEBUG=true` in production | `grep -n 'APP_DEBUG=true' .env.production 2>/dev/null` |
| `APP_KEY` regenerated between deploys (kills sessions, cookies, encrypted columns) | `grep -rn 'key:generate' deploy* Dockerfile .github/ 2>/dev/null` — must NOT appear in deploy paths |
| No `queue:restart` in deploy hooks | `grep -rLn 'queue:restart\|horizon:terminate' deploy* Envoy.blade.php 2>/dev/null` |
| `chmod -R 777 storage/` | `grep -rn 'chmod.*777' deploy* Dockerfile scripts/ 2>/dev/null` — use `750` + correct group |
| Image runs as root | `grep -n '^USER' Dockerfile` — no match means root |
| Single-stage build shipping composer/node to prod | `grep -c '^FROM' Dockerfile` — 1 means single-stage |
| Logs to file in containers | `grep -n 'LOG_CHANNEL' .env.example compose*.yml 2>/dev/null` — expect `stderr`/`stdout`, not `single`/`daily` |
| Cron not monitored (silent scheduler death) | `grep -rn 'thenPing\|pingOnSuccess' routes/console.php` — no match means unmonitored |
| No failed-job alerting | `grep -rn 'Queue::failing' app/Providers/` — no match means failures land unread |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Site 502/503 during deploy | Non-atomic swap — traffic hit a half-written release dir, or FPM reloaded mid-copy | Prepare the release fully, then symlink flip (Zero-downtime checklist step 2) |
| Stale code after deploy | Workers / OPcache / Octane not reloaded — long-lived processes still hold the old release | `queue:restart` or `horizon:terminate` + FPM reload or `octane:reload` (checklist step 3, Octane gotchas) |
| All sessions dropped after deploy | `APP_KEY` regenerated, or session driver flipped (e.g. `file` → `redis`) mid-deploy | Never run `key:generate` in deploy paths; keep the key in the secret store; migrate session drivers deliberately |
| Assets 404 after deploy | Vite manifest mismatch — old HTML referencing new hashed files (or vice versa), or assets built after the swap | Build in CI, ship `public/build/` into the release **before** the symlink flip (checklist step 1) |
| First requests slow after deploy | Caches not warmed in the new release | `php artisan optimize` before the flip (checklist step 4) |
| `MigrationException` on rollback | Destructive migration shipped — old code incompatible with new schema | Forward-fix only (Roll back workflow step 2) |
| Scheduled tasks silently stopped | Cron entry lost on server rebuild, or crashed cron daemon | `schedule:list` + heartbeat monitoring (Scheduler in clusters) |
| Same scheduled job ran N times | Cron on every server, no `onOneServer()` | Scheduler in clusters |

---

## Cross-references

| Topic | Where |
|---|---|
| Queue connections, Horizon config, worker flags, failed-job alert wiring | `laravel-queues` skill (+ `horizon_ops` reference for supervisor sizing) |
| Pint / PHPStan / Rector configuration depth, baselines, verify-then-apply | `laravel-static-analysis` skill |
| Pest coverage gates, test-suite CI semantics | `laravel-qa` skill |
| Image CVEs, secret threat models, security headers at the edge | `laravel-security` skill |
| Vite manifest contract, asset hashing, `@vite` directive | `laravel-frontend` skill |
| Application code touched by a deploy concern (jobs, models, controllers) | `laravel-role-backend` |
| Reviewing a deploy-related PR end to end | `laravel-role-code-review` |
