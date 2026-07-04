---
name: laravel-queues
description: Queues and background jobs in Laravel 12 — connections (sync, database, redis, sqs, beanstalkd), Horizon (balance strategies, supervisors, dashboard auth), worker config (queue:work flags, supervisord, FrankenPHP), dispatching (::dispatch, onQueue, onConnection, delay, afterCommit), retries and backoff, uniqueness, rate limiting, job middleware (RateLimited, WithoutOverlapping, ThrottlesExceptions, SkipIfBatchCancelled), batches and chains, failed jobs, encrypted payloads, scheduler integration, idempotency. Consumed by the backend, devops, and code-review agents.
---

# Laravel Queues — Background jobs at runtime

Reliable async work for Laravel 12 / PHP 8.3+. Covers the **mechanics** (connections, workers, retries, batching, Horizon) — not how to model your domain operations as jobs (that lives in `laravel-backend` §6, §8). Designed for the agents that *write* (`backend`), *operate* (`devops`), and *review* (`code-review`) queue code.

## When to use this skill

- Choosing a queue connection (database vs redis vs sqs vs beanstalkd)
- Configuring `queue:work`, supervisord, or Horizon supervisors
- Dispatching jobs with the right options (`afterCommit`, `delay`, `onQueue`, `onConnection`)
- Designing retries, backoff, uniqueness, rate limiting
- Writing batches and chains
- Wiring failed-job handling (DB, Sentry, Slack alerts)
- Scheduling: `schedule:run`, `withoutOverlapping`, `runInBackground`
- Diagnosing worker crashes, stuck jobs, payload bloat, memory leaks

## When NOT to use

| Topic | Use instead |
|---|---|
| Choosing **what** to encapsulate as a job (Action vs Job vs Listener) | `laravel-backend` §6 |
| Event/Listener design and `ShouldQueue` listener mechanics | `laravel-backend` §8 |
| Mail / Notification queue dispatch | `laravel-backend` §9 |
| `Bus::fake()`, `Queue::fake()`, assertion helpers | `laravel-qa` |
| Octane/FrankenPHP runtime, supervisord deploy templates | (devops agent) |
| Encrypted payload threat model, secret leakage in failed-job table | `laravel-security` |

## Stack assumptions

- Laravel 12, PHP 8.3+
- Redis (most common) or SQS for production; `database` for low-volume / staging
- Horizon for any non-trivial Redis deployment
- Workers run under supervisord or FrankenPHP's worker mode
- ⚠️ `sync` and `array` connections only in dev/tests; never in production

---

## 1. Choosing a connection

| Driver | Throughput | Ordering | Visibility | Use |
|---|---|---|---|---|
| `sync` | n/a | inline | n/a | dev, tests — **never** prod |
| `array` | n/a | none (in-memory) | n/a | tests with `Bus::fake()` |
| `database` | low (~100/s) | yes (per `available_at`) | low | low-volume apps, staging, no Redis available |
| `redis` | high (10k+/s) | yes (priority via queue ordering) | Horizon | default for production at scale |
| `sqs` | high, durable | weak (FIFO queue → strong, lower TPS) | CloudWatch | AWS-native, multi-region durability |
| `beanstalkd` | high | yes | low | legacy / niche |

**Default recommendation:** `redis` + Horizon. `database` is acceptable for small apps but won't scale past a few workers (table contention).

```env
QUEUE_CONNECTION=redis
REDIS_HOST=127.0.0.1
REDIS_QUEUE=default
```

⚠️ **Anti-pattern:** `QUEUE_CONNECTION=sync` in `.env.production`. Jobs run inline on the request thread — kills throughput and defeats every reason to use a queue.

---

## 2. Job anatomy

```php
final class ProcessPayment implements ShouldQueue
{
    use Queueable;

    public int $tries = 3;
    public int $backoff = 30;                          // seconds — or array for exponential
    public int $timeout = 60;
    public int $maxExceptions = 2;
    public bool $deleteWhenMissingModels = true;
    public string $queue = 'payments';
    public string $connection = 'redis';

    public function __construct(public Order $order) {}

    public function handle(PaymentGateway $gateway): void
    {
        $gateway->charge($this->order);
    }

    public function failed(Throwable $e): void
    {
        Log::error('payment.job.failed', [
            'order_id' => $this->order->id,
            'error'    => $e->getMessage(),
        ]);
    }

    public function backoff(): array
    {
        return [10, 30, 60];                           // overrides $backoff
    }

    public function middleware(): array
    {
        return [
            (new WithoutOverlapping($this->order->id))->expireAfter(120),
            (new RateLimited('payments-bucket'))->releaseAfterMinutes(1),
        ];
    }

    public function tags(): array
    {
        return ["order:{$this->order->id}", "tenant:{$this->order->tenant_id}"];   // Horizon
    }
}
```

**Rules:**
- Mark domain jobs `final`. Inheritance complicates serialization.
- Constructor args are **serialized**. Use `SerializesModels` (included in `Queueable`) so models are stored as IDs and re-resolved at handle time.
- `$timeout < $tries × max($backoff)` is meaningless — calibrate together.
- ⚠️ **Anti-pattern:** passing entire request payloads into a job constructor. Bloats Redis, leaks PII, breaks `SerializesModels`. Pass IDs + minimal scalars.

---

## 3. Dispatching

```php
ProcessPayment::dispatch($order);                                    // immediately
ProcessPayment::dispatch($order)->afterCommit();                     // wait for surrounding DB tx
ProcessPayment::dispatch($order)->delay(now()->addMinutes(5));       // delayed
ProcessPayment::dispatch($order)->onQueue('high');                   // custom queue
ProcessPayment::dispatch($order)->onConnection('sqs');               // override connection
ProcessPayment::dispatchIf($order->isPaid(), $order);                // conditional
ProcessPayment::dispatchUnless($order->isVoid(), $order);
ProcessPayment::dispatchSync($order);                                // run inline (testing)
ProcessPayment::dispatchAfterResponse($order);                       // run after HTTP response sent
```

### 3.1 `afterCommit()` — the single most important rule

If you dispatch a job inside `DB::transaction(...)` **without** `afterCommit()`, a worker on a different machine can pick up the job before your transaction commits — and read stale or missing data.

```php
// ❌ wrong — race
DB::transaction(function () use ($order) {
    $order->update(['status' => 'paid']);
    ProcessPayment::dispatch($order);
});

// ✅ right
DB::transaction(function () use ($order) {
    $order->update(['status' => 'paid']);
    ProcessPayment::dispatch($order)->afterCommit();
});
```

You can flip the default in `config/queue.php` per connection:

```php
'redis' => ['after_commit' => true, /* ... */],
```

⚠️ **Anti-pattern:** any `dispatch(...)` inside a `DB::transaction(...)` without `afterCommit()` and without the connection-level default. Auditable: grep `dispatch` inside `DB::transaction`.

### 3.2 Chains and batches

```php
// Chain — sequential, abort on failure
Bus::chain([
    new ChargeCard($order),
    new SendReceipt($order),
    new UpdateInventory($order),
])->dispatch();

// Batch — parallel, with overall callbacks
Bus::batch([
    new ResizeImage($photo, 'sm'),
    new ResizeImage($photo, 'md'),
    new ResizeImage($photo, 'lg'),
])
    ->name("resize:photo:{$photo->id}")
    ->onQueue('media')
    ->allowFailures()
    ->then(fn (Batch $b) => Log::info('batch.done', ['id' => $b->id]))
    ->catch(fn (Batch $b, Throwable $e) => Sentry::captureException($e))
    ->finally(fn (Batch $b) => $photo->update(['processed_at' => now()]))
    ->dispatch();
```

**Rules:**
- Chains halt on first failure. Batches continue (use `allowFailures()`) and report aggregate state.
- For batches, the `job_batches` table is required (`php artisan queue:batches-table` then migrate).
- `SkipIfBatchCancelled` middleware lets in-flight jobs short-circuit when the batch is cancelled (§5).

---

## 4. Workers — `queue:work`

```bash
php artisan queue:work redis \
    --queue=high,default,low \
    --tries=3 \
    --backoff=30 \
    --timeout=60 \
    --memory=256 \
    --max-jobs=1000 \
    --max-time=3600 \
    --sleep=3
```

| Flag | Meaning |
|---|---|
| `--queue` | Comma-separated **priority list** — left = higher priority |
| `--tries` | Default attempts for jobs without `$tries` |
| `--backoff` | Default seconds between retries |
| `--timeout` | Hard kill after N seconds (must be < supervisord's `stopwaitsecs`) |
| `--memory` | Restart worker when usage exceeds N MB |
| `--max-jobs` | Restart after N jobs (counters memory creep) |
| `--max-time` | Restart after N seconds (counters slow leaks) |
| `--sleep` | Idle sleep when no jobs (only relevant for `database` driver; Redis blocks) |

**Rules:**
- Always cap `--max-jobs` and `--max-time` to recycle workers; long-lived PHP processes accumulate memory.
- `--queue=high,default,low` drains in order — `low` only runs when `high` and `default` are empty. ⚠️ Starvation risk.
- Use `queue:work`, **not** `queue:listen`. `listen` reboots the framework per job — slow.
- After deploys, run `php artisan queue:restart` so workers re-load code.

⚠️ **Anti-pattern:** `php artisan queue:work` started by `nohup` or a shell script without a supervisor. Workers crash; nobody restarts them; jobs pile up silently.

---

## 5. Job middleware

Drop-ins that wrap `handle()`. Returned from `middleware(): array` on the job (or applied per-dispatch via `->through([...])`).

| Middleware | Purpose |
|---|---|
| `WithoutOverlapping($key)` | Only one job with this key runs at a time (Redis lock) |
| `RateLimited('bucket')` | Defer if bucket exhausted (defined via `RateLimiter::for`) |
| `ThrottlesExceptions(N, M)` | Stop retrying for M minutes after N consecutive failures |
| `Skip::when($condition)` | Skip the job at handle time if condition is true |
| `SkipIfBatchCancelled` | For batched jobs — exit cleanly if the batch was cancelled |

```php
public function middleware(): array
{
    return [
        (new WithoutOverlapping($this->order->id))
            ->dontRelease()                              // drop instead of requeue if locked
            ->expireAfter(180),

        new ThrottlesExceptions(3, 10),                  // 3 fails → pause this job's bucket 10 min

        (new RateLimited('stripe-api')),
    ];
}

// Define the rate limiter
RateLimiter::for('stripe-api', fn () => Limit::perMinute(100));
```

⚠️ **Anti-pattern:** dispatching jobs that touch a 3rd-party API without `RateLimited` and `ThrottlesExceptions`. A vendor outage cascades into worker churn and 429 storms.

---

## 6. Retries & backoff

| Failure mode | Recommended policy |
|---|---|
| Transient network error | `tries=5`, exponential backoff `[10, 30, 60, 180, 600]` |
| Vendor 429 (rate limited) | `RateLimited` middleware + `tries=10` + long backoff |
| Vendor 5xx | `ThrottlesExceptions(3, 10)` + `tries=5` |
| Vendor 4xx (logic error) | `tries=1`; failing again won't help |
| Database deadlock | `tries=3`, short backoff |
| `ModelNotFoundException` | `deleteWhenMissingModels = true` — drop instead of retry |

```php
public function retryUntil(): DateTime
{
    return now()->addMinutes(30);                        // give up regardless of $tries
}
```

**Rules:**
- Always set `$tries` explicitly. The framework default is unlimited (subject to worker `--tries`); easy to dispatch a job that retries forever.
- `retryUntil()` overrides `$tries` for time-bounded jobs (e.g. "this only matters within 30 minutes").
- Idempotency is yours to enforce. Workers will retry; the job must be safe to run twice.

---

## 7. Failed jobs

```bash
php artisan queue:failed-table && php artisan migrate
php artisan queue:failed
php artisan queue:retry <id|all>
php artisan queue:forget <id>
php artisan queue:flush
php artisan queue:prune-failed --hours=168
```

The `failed_jobs` table stores the connection, queue, payload, exception, and `failed_at`.

**Hooks:**
```php
// In a ServiceProvider::boot()
Queue::failing(function (JobFailed $e) {
    Sentry::captureException($e->exception, ['extra' => [
        'queue'   => $e->job->getQueue(),
        'payload' => $e->job->payload(),
    ]]);
});
```

⚠️ **Anti-pattern:** no failed-job alerting. Failures land in a table nobody reads. Always wire `Queue::failing` to Sentry / Slack / on-call.

---

## 8. Rate limiting

Define limiters in `AppServiceProvider::boot()` or anywhere wired during boot:

```php
RateLimiter::for('emails', function ($job) {
    return Limit::perMinute(50)->by($job->user_id);
});

RateLimiter::for('exports', function ($job) {
    return $job->priority === 'high'
        ? Limit::none()
        : Limit::perHour(10)->by($job->user_id);
});
```

Apply via the `RateLimited` middleware (§5).

For Redis-native throttle (older Laravel pattern, still works):

```php
Redis::throttle('payments')
    ->allow(10)
    ->every(60)
    ->then(
        fn () => $this->process(),
        fn () => $this->release(10),
    );
```

The middleware approach is preferred — declarative, composable.

---

## 9. Horizon

Required for any serious Redis deployment. Provides supervisors, balance strategies, dashboard, and metrics.

```bash
composer require laravel/horizon
php artisan horizon:install
php artisan horizon                  # starts the master (run under supervisord/systemd in prod)
```

**`config/horizon.php` essentials:**
```php
'environments' => [
    'production' => [
        'supervisor-default' => [
            'connection'           => 'redis',
            'queue'                => ['high', 'default', 'low'],
            'balance'              => 'auto',          // 'simple' | 'auto' | 'false'
            'autoScalingStrategy'  => 'time',          // 'time' | 'size'
            'minProcesses'         => 1,
            'maxProcesses'         => 20,
            'tries'                => 3,
            'timeout'              => 60,
            'memory'               => 256,
            'maxJobs'              => 1000,
            'maxTime'              => 3600,
        ],
    ],
],
```

| Balance | When |
|---|---|
| `simple` | Equal split — predictable, ignores load. |
| **`auto`** | Backlog-aware — best default. |
| `false` | Strict priority — workers drain `high` before `default`. Starvation risk on `low`. |

**Dashboard auth — mandatory:**

```php
// HorizonServiceProvider::gate()
Gate::define('viewHorizon', fn ($user) => in_array($user->email, ['ops@example.com']));
```

⚠️ **Anti-pattern:** Horizon dashboard without `viewHorizon` gate. The dashboard reveals job payloads — possibly tokens / PII.

**Tags** (`tags(): array` on the job) make jobs filterable in the dashboard.

For balance-strategy scenario tables, autoscaling calibration (`time` vs `size`), per-workload sizing matrix, supervisord and systemd unit templates, deploy-hook ordering, multi-server cluster behavior, failed-job alerting wiring (Sentry / Slack / pager), the metrics-to-watch table, and the full troubleshooting matrix, see [`references/horizon_ops.md`](references/horizon_ops.md).

---

## 10. Encrypted payloads

For jobs whose payload includes secrets (tokens, PII), encrypt at rest in Redis/DB:

```php
final class RotateApiKey implements ShouldQueue, ShouldBeEncrypted
{
    use Queueable;
    public function __construct(public string $newKey) {}
    public function handle(): void { /* ... */ }
}
```

`ShouldBeEncrypted` encrypts the serialized payload using the app key. Failed-job table also stores it encrypted.

**Rule:** any job constructor receiving a token, password, full PII record, or webhook secret should be `ShouldBeEncrypted`. Threat model details in `laravel-security`.

---

## 11. Scheduler integration

`routes/console.php` — Laravel 11+ has no Console Kernel:

```php
use Illuminate\Support\Facades\Schedule;

Schedule::job(new PruneStalePayments)->hourly()->onQueue('low');
Schedule::command('reports:weekly')
    ->weekly()
    ->withoutOverlapping(60)
    ->onOneServer()
    ->runInBackground()
    ->emailOutputOnFailure('ops@example.com');
```

| Method | Effect |
|---|---|
| `withoutOverlapping($expireMinutes)` | Skip if previous run still active (Redis lock) |
| `onOneServer()` | When multiple boxes run scheduler, only one fires (requires Redis or DB cache) |
| `runInBackground()` | Don't block the next tick (defaults to inline) |
| `evenInMaintenanceMode()` | Run despite `php artisan down` |

**The cron entry:**
```cron
* * * * * cd /var/www && php artisan schedule:run >> /dev/null 2>&1
```

In Octane / FrankenPHP setups, the scheduler runs as a separate process. Do **not** rely on long-lived workers to also handle scheduled jobs.

⚠️ **Anti-pattern:** scheduling on every server in a cluster without `onOneServer()`. The same job fires N times per tick.

---

## 12. Idempotency — the worker's contract

Workers retry. Network blips cause duplicates. **Every job that mutates state must tolerate being run twice.** Patterns:

- **Idempotency key** check at the start: `if (Receipt::where('order_id', $id)->exists()) return;`
- **Conditional update**: `Order::where('id', $id)->where('status', 'pending')->update(['status' => 'paid']);` — second run sees no rows.
- **`WithoutOverlapping`** for timeline-style work (§5).
- **DB constraints**: unique index on `(order_id, intent)` so a second insert errors instead of duplicating.

⚠️ **Anti-pattern:** assuming `tries=1` makes a job safe. The worker can crash *after* the side effect but *before* marking the job done; on restart the job re-fires.

---

## 13. Common pitfalls

| Symptom | Likely cause |
|---|---|
| Jobs dispatched but never run | Wrong `QUEUE_CONNECTION`, wrong `--queue` priority list, or worker not running |
| Job runs but data missing | Dispatched inside transaction without `afterCommit()` (§3.1) |
| `Job has been attempted too many times` | `$tries` exceeded; check exception in `failed_jobs` |
| Worker memory creep | Missing `--max-jobs` / `--max-time`; or holding refs in singleton bindings |
| `MaxAttemptsExceededException` for jobs that didn't fail | Worker `--timeout` killed mid-handle; raise timeout or split job |
| Horizon dashboard "no data" | Wrong env name in `horizon.php#environments`, or `HORIZON_PREFIX` mismatch |
| Failed-job payload contains secrets in plain text | Job not marked `ShouldBeEncrypted` (§10) |
| Stuck "reserved" jobs after a crash | Stale visibility timeout — `php artisan horizon:terminate`, or for raw Redis tune `block_for` |

---

## 14. Anti-patterns — consolidated

| Smell | Section | Detection |
|---|---|---|
| `QUEUE_CONNECTION=sync` in production | §1 | grep `.env.production` / deploy script |
| Full request payload in job constructor | §2 | review `__construct(Request $r)` patterns |
| `dispatch(...)` inside `DB::transaction` without `afterCommit()` | §3.1 | grep `dispatch` inside `DB::transaction` |
| `queue:work` not under supervisor | §4 | review init scripts |
| `queue:listen` in production | §4 | grep deploy scripts |
| 3rd-party API job with no `RateLimited`/`ThrottlesExceptions` | §5 | review `middleware()` returns |
| `$tries` not set on job | §6 | grep `implements ShouldQueue` without `$tries` declared |
| No `Queue::failing` alert wiring | §7 | grep ServiceProvider for `Queue::failing` |
| Horizon dashboard with no `viewHorizon` gate | §9 | review `HorizonServiceProvider` |
| Job constructor receives secrets without `ShouldBeEncrypted` | §10 | review jobs with `string $token` / similar |
| Scheduled task in cluster without `onOneServer()` | §11 | review `Schedule::command/job` calls |
| Mutation job with no idempotency guard | §12 | review job `handle()` for unconditional writes |

---

## 15. Cross-references

| Topic | Skill |
|---|---|
| Choosing Action vs Job vs Listener | `laravel-backend` §6, §8 |
| `Bus::fake`, `Queue::fake`, `assertDispatched`, `assertChained`, `assertBatched` | `laravel-qa` |
| Mailable / Notification queue dispatch | `laravel-backend` §9 |
| Encrypted payload threat model, secret hygiene in `failed_jobs` | `laravel-security` |
| Octane / FrankenPHP worker mode interplay | (devops agent) |
| Supervisord / systemd unit templates, deploy hooks | (devops agent) |
