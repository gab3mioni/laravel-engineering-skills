# Job design and failure handling — deep-dive

How Laravel 12 queue primitives interact when things fail. Loaded when the agent is writing batches or chains, wiring `failed()` handlers, designing unique jobs, reasoning about release-vs-fail attempt accounting, or building failure-handling recipes (final-failure alerts, dead-letter triage, safe replays).

SKILL.md covers the basics (dispatch options, retry policy table, middleware, idempotency patterns). This doc covers the **failure-mode interactions** — what actually happens when a batched job throws, a chain link dies, a unique lock expires, or a release loop exhausts `$tries`.

## 1. Batches

Every job placed in a batch must use the `Illuminate\Bus\Batchable` trait (in addition to `Queueable`). Without it, `$this->batch()` is unavailable and cancellation checks are impossible.

### 1.1 Callback semantics — which fires when

| Callback | Fires | Fires if a job failed? |
|---|---|---|
| `before(Batch $b)` | Batch created, before any job runs | n/a |
| `progress(Batch $b)` | Each time one job completes **successfully** | not for failed jobs |
| `then(Batch $b)` | All jobs completed **successfully** | **no** — even with `allowFailures()` |
| `catch(Batch $b, Throwable $e)` | **First** job failure only — not once per failure | yes (once) |
| `finally(Batch $b)` | Batch finished executing | yes — always |

Consequences:

- With `allowFailures()`, a batch where 1 of 500 jobs failed fires `catch` (once) and `finally` — **never `then`**. If "batch is done, some failed" is a state you must handle, put that logic in `finally` and inspect `$b->failedJobs` / `$b->hasFailures()`.
- `catch` firing only on the *first* failure means it is an alerting hook, not an accounting hook. Count failures in `finally`.

⚠️ **Batch callbacks are serialized and run later by a worker.** Do not use `$this` inside them, and keep them thin — a `Log::` line or a dispatch of a follow-up job. Heavy logic belongs in a job the callback dispatches.

### 1.2 `allowFailures()` — what it actually changes

| | Default (no `allowFailures`) | With `allowFailures()` |
|---|---|---|
| First job failure | Batch marked **cancelled** | Batch continues |
| Pending jobs | Still on the queue — they run unless they check cancellation | Run normally |
| Failed job | Lands in `failed_jobs` as usual | Same; also recorded on the batch (`failedJobs`) |
| `catch` callback | Fires | Fires |
| Retry story | `queue:retry` per job | `php artisan queue:retry-batch <uuid>` retries all failed jobs of the batch |

⚠️ **"Cancelled" does not mean "stopped."** Cancelling a batch (first failure, or explicit `$batch->cancel()`) only flips a flag. Queued and in-flight jobs keep running unless each job opts in:

```php
use Illuminate\Queue\Middleware\SkipIfBatchCancelled;

public function middleware(): array
{
    return [new SkipIfBatchCancelled];
}
```

Put `SkipIfBatchCancelled` on **every** batchable job (or check `$this->batch()->cancelled()` at the top of `handle()`). A batch without it burns worker time on work whose result nobody will read.

### 1.3 Adding jobs to a running batch

Only a job **inside** the batch may add jobs to it — useful for fan-out where a "loader" job discovers the workload:

```php
public function handle(): void
{
    $this->batch()->add(
        Collection::times(1000, fn () => new ImportContacts)
    );
}
```

Dispatch the batch with just the loader job; it inflates the batch at runtime. `progress`/`then` account for the added jobs automatically (total count grows).

### 1.4 Chains inside batches — ordering guarantees

An **array of arrays** makes each inner array a chain; chains run in parallel with each other:

```php
Bus::batch([
    [new ReleasePodcast(1), new SendReleaseNotification(1)],   // sequential
    [new ReleasePodcast(2), new SendReleaseNotification(2)],   // parallel with the above
])->then(fn (Batch $b) => /* all chains finished */)->dispatch();
```

Guarantees: **within** an inner array, strict order (each job dispatches the next on success). **Across** inner arrays, none — chain 2 may finish before chain 1 starts. A chain link failing kills only that chain; the batch-level failure rules (§1.2) then apply.

The inverse also works — a chain may contain whole batches (`Bus::chain([new Prepare, Bus::batch([...]), new Finalize])`): the chain waits for the entire batch before moving on.

### 1.5 Pruning

`job_batches` grows fast and nothing prunes it by default:

```php
Schedule::command('queue:prune-batches --hours=48 --unfinished=72 --cancelled=72')->daily();
```

`--hours` prunes finished batches; `--unfinished` and `--cancelled` catch batches that never completed (failed job never retried) or were cancelled — without those two flags they accumulate forever.

## 2. Chains

### 2.1 Failure stops the chain — and how to resume anyway

When a chain link fails, the remaining jobs are **never dispatched**. There is no built-in "resume from step 3" API. Two recovery paths:

1. **`queue:retry` the failed job.** A chained job carries the *rest of the chain in its own payload* — retrying the failed link and having it succeed dispatches the next link. The chain resumes exactly where it died. This is the cheap path; it requires nothing extra.
2. **Re-dispatch the whole chain.** Only safe if every link is idempotent (SKILL.md §11 Idempotency) — links 1..N-1 will run again.

```php
Bus::chain([
    new ChargeCard($order),
    new SendReceipt($order),
    new UpdateInventory($order),
])->catch(function (Throwable $e) {
    // A link failed — remaining links will NOT run. Serialized closure: no $this.
    Log::error('order.chain.failed', ['error' => $e->getMessage()]);
})->dispatch();
```

`catch` on the chain fires in addition to the failed job's own `failed()` method — chain-level awareness vs job-level cleanup (§3).

### 2.2 Routing a chain

```php
Bus::chain([...])->onConnection('redis')->onQueue('payments')->dispatch();
```

- `onConnection` / `onQueue` on `Bus::chain(...)` set the default for **every** link; an individual job's own `$connection`/`$queue` (or `onQueue()` at construction) overrides it for that link.
- From *inside* a job that has a chain attached, `$this->allOnConnection(...)` / `$this->allOnQueue(...)` set the chain-wide defaults (they write the `$chainConnection` / `$chainQueue` properties on the `Queueable` trait). There are **no** `chainOnConnection()` / `chainOnQueue()` methods in Laravel 12 — only the properties, set via the `allOn*` methods.
- A running chained job can extend its own chain: `$this->prependToChain($job)` (runs immediately after the current job) / `$this->appendToChain($job)` (runs at the end).

### 2.3 Chain vs batch — decision table

| Question | Chain | Batch |
|---|---|---|
| Order matters? | Strict sequence | None (except chains-in-batch, §1.4) |
| Parallelism | None — one job at a time | Full — limited only by worker count |
| One failure means | Stop; rest never dispatched | Cancel (default) or continue (`allowFailures`) |
| Completion hook | None (last job *is* the hook) | `then` / `catch` / `finally` |
| Progress tracking | No | `$batch->progress()`, dashboard-friendly |
| Infra required | Nothing extra | `job_batches` table + pruning |
| Typical use | Pipeline: charge → receipt → inventory | Fan-out: resize 500 images, import 10k rows |

Rule of thumb: need order → chain; need aggregate completion state over parallel work → batch; need both → chains inside a batch.

## 3. `failed()` vs `Queue::failing()`

Two hooks, different jobs (pun intended):

| | `failed(Throwable $e)` on the job | `Queue::failing(fn (JobFailed $e))` global |
|---|---|---|
| Scope | This job class only | Every failed job on every queue |
| Purpose | **Cleanup / compensation** — release reservations, mark the order errored, notify the affected user | **Alerting / metrics** — Sentry, Slack, failure-rate counters |
| Fires | Once, on **final** failure (not per retry) | Once per final failure, any job |
| Where | Job class | `AppServiceProvider::boot()` |

Use both: `failed()` knows the domain, `Queue::failing` knows the pager. Wiring recipes for the global listener: `horizon_ops.md` §9.

### 3.1 ⚠️ The new-instance trap

`failed()` runs on a **fresh instance** of the job. Any property mutated in `handle()` is gone — you get the constructor-time state, re-deserialized from the payload.

```php
// ❌ BAD — $this->chargeId was set in handle(); failed() sees null
public function handle(PaymentGateway $gw): void
{
    $this->chargeId = $gw->charge($this->order)->id;   // property lost on failure
    throw_if(...);
}

public function failed(Throwable $e): void
{
    $gw->refund($this->chargeId);                      // null — refund never happens
}

// ✅ GOOD — persist intermediate state outside the job instance
public function handle(PaymentGateway $gw): void
{
    $charge = $gw->charge($this->order);
    $this->order->update(['charge_id' => $charge->id]); // durable, visible to failed()
}

public function failed(Throwable $e): void
{
    if ($this->order->refresh()->charge_id) {
        RefundCharge::dispatch($this->order);
    }
}
```

### 3.2 What `$e` actually is

A job "fails" when it exhausts attempts — which can be consumed by unhandled exceptions, timeouts, **or releases** (§5). The `Throwable` passed to `failed()` reflects the terminal cause:

| Terminal cause | `$e` instance |
|---|---|
| Last attempt threw | the actual exception |
| Attempts exhausted (e.g. release loop) | `Illuminate\Queue\MaxAttemptsExceededException` |
| Timeout on final attempt | `Illuminate\Queue\TimeoutExceededException` |
| `$this->fail($e)` called in `handle()` | whatever you passed (or a generic exception for `fail('message')`) |

`$this->fail()` is the deliberate exit: fail *now*, skip remaining retries, run `failed()`.

## 4. `ShouldBeUnique` lifecycle

Mechanics: at **dispatch time** Laravel tries to acquire a cache lock keyed by `uniqueId()`. If the lock is held, the dispatch is **silently dropped** — no exception, no log line, the job simply never enters the queue. The lock is released when the job **completes processing or fails all retries**.

```php
final class UpdateSearchIndex implements ShouldQueue, ShouldBeUnique
{
    use Queueable;

    public int $uniqueFor = 3600;

    public function uniqueId(): string
    {
        return (string) $this->product->id;
    }

    public function uniqueVia(): Repository
    {
        return Cache::driver('redis');                 // lock store ≠ queue connection
    }
}
```

### 4.1 ⚠️ The `uniqueFor` expiry trap

`uniqueFor` is a **lock TTL, not a job TTL**. If the lock expires while the original job is still queued (backlog) or still running (slow job), a second dispatch acquires a fresh lock and **both jobs run** — the exact duplicate `ShouldBeUnique` was meant to prevent.

Rule: `uniqueFor` > worst-case queue wait + worst-case runtime + margin. If you can't bound the wait (deep backlogs), rely on an idempotency guard inside `handle()` as the real defense (SKILL.md §11) and treat `ShouldBeUnique` as a dispatch-rate optimization, not a correctness guarantee.

### 4.2 `ShouldBeUniqueUntilProcessing`

Releases the lock when the job **starts** processing instead of when it finishes. Semantics change from "at most one queued *or running*" to "at most one **queued**" — a new dispatch is accepted the moment the old job begins running. Use for debounce-style jobs ("rebuild the index at most once per queue pass") where a run overlapping a re-dispatch is fine.

### 4.3 Boundaries

- Requires a cache driver with atomic locks (`redis`, `memcached`, `database`, `dynamodb`, `file`, `array`). Multi-server apps must point `uniqueVia` at a **shared** cache — a per-box `file` cache silently breaks uniqueness.
- Dispatch-time dedupe (`ShouldBeUnique`) ≠ run-time mutual exclusion (`WithoutOverlapping`, SKILL.md §5). The first stops duplicate *enqueues*; the second stops concurrent *execution* of jobs already queued. Deduping retries of distinct dispatches usually needs both or a DB constraint.

## 5. Releases vs fails — attempt accounting

`$this->release($delay)` puts the job back on the queue. Three counters interact:

| Counter | Incremented by | Caps |
|---|---|---|
| `$tries` | **Every** attempt: unhandled exception, timeout, manual/middleware `release()` | Total attempts of any kind |
| `$maxExceptions` | **Only** unhandled exceptions — releases do NOT count | Genuine failures |
| `retryUntil()` | Wall clock | Everything — takes precedence over `$tries` |

The canonical combo — lock-contention releases are cheap, real errors are not:

```php
public int $tries = 25;             // room for release loops (lock busy, rate limited)
public int $maxExceptions = 3;      // but 3 real exceptions → fail

public function handle(): void
{
    Redis::throttle('key')->block(0)->allow(10)->every(60)->then(
        fn () => $this->process(),
        fn () => $this->release(30)  // consumes a try, not an exception
    );
}
```

⚠️ **Release-loop starvation:** middleware that releases (`RateLimited`, `WithoutOverlapping` without `dontRelease()`, `ThrottlesExceptions`) burns `$tries`. A job with `tries=3` behind a hot rate limiter can exhaust all attempts without ever executing — and fail with `MaxAttemptsExceededException`. If a job sits behind release-happy middleware, raise `$tries` and bound real failures with `$maxExceptions`, or switch to `retryUntil()`:

```php
public function retryUntil(): DateTime
{
    return now()->addMinutes(30);   // overrides $tries entirely
}
```

With `retryUntil()`, attempt count is irrelevant — the job retries (and releases) freely until the deadline, then fails. Best for "this is only useful for the next N minutes" work. Remember `failed()` still fires at the deadline.

## 6. Job events and worker hooks

Registered in `AppServiceProvider::boot()`:

```php
Queue::before(function (JobProcessing $event) {
    // $event->connectionName, $event->job, $event->job->payload()
});

Queue::after(function (JobProcessed $event) {
    StatsD::timing('queue.job.runtime', /* ... */);
});

Queue::looping(function () {
    while (DB::transactionLevel() > 0) {
        DB::rollBack();              // heal transactions leaked by a previously killed job
    }
});
```

| Hook / event | Fires | Use for |
|---|---|---|
| `Queue::before` (`JobProcessing`) | Just before `handle()` | Request-id / tenant context binding, start timers |
| `Queue::after` (`JobProcessed`) | After successful `handle()` | Throughput / runtime metrics |
| `Queue::looping` | Before the worker pops the **next** job | Resetting leaked state: open transactions, stale scopes |
| `JobFailed` (via `Queue::failing`) | Final failure | Alerting (§3, `horizon_ops.md` §9) |

The `Queue::looping` transaction-rollback closure above is the documented pattern — a job killed mid-transaction otherwise poisons the next job on the same worker process.

## 7. Failure-handling recipes

### 7.1 Notify on final failure only

Per-retry notifications are noise (a `tries=5` job pages 5 times for one incident). Two correct shapes:

```php
// ✅ Preferred: failed() only runs after the FINAL attempt — no attempt math needed
public function failed(Throwable $e): void
{
    Notification::route('slack', config('alerts.webhook'))
        ->notify(new JobPermanentlyFailed(self::class, $e));
}

// ✅ Inside handle(), when you must act before rethrowing on the last attempt:
catch (TransientApiException $e) {
    if ($this->attempts() >= $this->tries) {
        $this->order->update(['status' => 'failed']);   // last chance — about to fail for good
    }
    throw $e;
}
```

⚠️ The `attempts() >= tries` check breaks silently if `retryUntil()` is in play (`$tries` is ignored then) — prefer `failed()` unless you truly need pre-failure logic in `handle()`.

### 7.2 Dead-letter triage

`failed_jobs` is your dead-letter queue — but only if something reads it. Pattern: a scheduled triage job classifies failures and routes them.

```php
Schedule::job(new TriageFailedJobs)->hourly();
```

The triage job reads `DB::table('failed_jobs')` since the last run, groups by exception class and queue, then: known-transient (vendor 5xx, deadlock) → collect UUIDs for replay; known-permanent (validation, 4xx) → alert + `queue:forget`; unknown → escalate. Pair with `queue:prune-failed --hours=168` so the table stays a working set, not an archive.

### 7.3 Replaying safely

```bash
php artisan queue:retry ce7bb17c-...                # one job (UUID)
php artisan queue:retry uuid-1 uuid-2               # several
php artisan queue:retry --queue=payments            # all failed on one queue
php artisan queue:retry --range=1-5                 # numeric id range (failed_jobs.id)
php artisan queue:retry all                         # everything
php artisan queue:retry-batch <batch-uuid>          # all failed jobs of a batch
```

Rules:

- **Idempotency is the prerequisite.** A replayed job may have half-executed before failing (charge made, receipt row missing). Every job you intend to replay must pass SKILL.md's **§11 Idempotency** — one of the four patterns, verified, before you type `queue:retry all`.
- Replay **narrow to wide**: one UUID → confirm effect → `--queue`/`--range` → `all`. Never start at `all` during an incident.
- Retried chain links resume their chain (§2.1); retried batch jobs re-attach to their batch — `queue:retry-batch` exists precisely for that.
- Under Horizon use `horizon:forget` (not `queue:forget`) to drop a failed job.

## 8. Anti-patterns — consolidated

| Smell | Section | Detection |
|---|---|---|
| Batched job without `SkipIfBatchCancelled` (or a `cancelled()` check) | §1.2 | grep jobs using `Batchable` for missing `SkipIfBatchCancelled` in `middleware()` |
| Post-batch logic in `then()` when `allowFailures()` is set (never fires on partial failure) | §1.1 | grep `allowFailures()` chained with `->then(` — verify a `finally` exists |
| `$this` used inside batch/chain `catch`/`then` closures | §1.1, §2.1 | grep `->then(fn` / `->catch(fn` bodies for `$this->` |
| No `queue:prune-batches` schedule (or missing `--unfinished`/`--cancelled`) | §1.5 | grep `routes/console.php` for `prune-batches` |
| Compensation logic reading properties set in `handle()` from `failed()` | §3.1 | review `failed()` bodies for properties not set in the constructor |
| Alerting via per-job `failed()` copy-paste instead of `Queue::failing` | §3 | grep `Sentry` / `Notification::route` inside multiple `failed()` methods |
| `ShouldBeUnique` with short `uniqueFor` on a queue with backlog | §4.1 | compare `uniqueFor` vs queue P95 wait (Horizon metrics) |
| `ShouldBeUnique` treated as the idempotency guarantee | §4.1, §4.3 | review unique jobs' `handle()` for missing idempotency guard |
| Low `$tries` on a job behind `RateLimited` / `WithoutOverlapping` (release starvation) | §5 | grep jobs with those middleware and `$tries` ≤ 3 |
| Per-retry notifications (alert inside `handle()` catch without attempt guard) | §7.1 | grep `catch` blocks containing `Notification::` / `Mail::` |
| `queue:retry all` in runbooks with no idempotency audit step | §7.3 | grep deploy/runbook scripts for `queue:retry all` |

## 9. Cross-references

- SKILL.md §4.2 — batch/chain quickstart this doc deepens
- SKILL.md §5 — middleware referenced here (`SkipIfBatchCancelled`, `WithoutOverlapping`, `RateLimited`)
- SKILL.md §11 — **Idempotency**: the prerequisite for every replay recipe in §7
- SKILL.md §2 — retry-policy table; `retry_after > timeout` calibration
- `references/horizon_ops.md` §9 — `Queue::failing` alert wiring (Sentry / Slack / pager)
- `references/horizon_ops.md` §14 — queue wait metrics used to calibrate `uniqueFor` (§4.1)
- `laravel-qa` — `Bus::fake()` assertions: `assertBatched`, `assertChained`, batch/chain testing
