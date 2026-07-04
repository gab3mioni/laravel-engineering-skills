# Horizon — Operational deep-dive

Running Laravel Horizon in production. Loaded when the agent is choosing balance strategies, calibrating autoscaling, writing supervisor templates, wiring failed-job alerting, troubleshooting "no data" dashboards, or sizing workers for a known traffic profile.

This doc assumes Redis as the queue connection and Laravel 12. SQS-only deployments don't use Horizon.

## 1. The mental model

Horizon is a **process manager and dashboard for Redis-queued jobs**. It replaces hand-rolled supervisord configs with declarative `config/horizon.php` and adds:

- Auto-balancing workers across queues based on backlog
- Per-queue process supervisors with health checks
- A web dashboard with metrics, recent failures, and tag-based search
- Throughput/runtime/wait-time metrics aggregated per queue and per tag
- Pause/resume controls for graceful traffic shaping

**One Horizon process supervises many workers.** You run *one* `php artisan horizon` per app server (under systemd / supervisord). Horizon spawns and reaps the actual worker subprocesses.

## 2. Architecture and process tree

```
systemd / supervisord
   └─ php artisan horizon                                (1 master)
        ├─ supervisor: supervisor-default
        │    ├─ worker (queue=high,default,low)
        │    ├─ worker (queue=high,default,low)
        │    └─ worker (queue=high,default,low)
        ├─ supervisor: supervisor-emails
        │    └─ worker (queue=emails)
        └─ supervisor: supervisor-payments
             ├─ worker (queue=payments)
             └─ worker (queue=payments)
```

Each `supervisor-*` block in `config/horizon.php` defines a pool. Pools are independent — you can pause one without affecting the others.

## 3. Configuration anatomy

```php
// config/horizon.php
'environments' => [
    'production' => [
        'supervisor-default' => [
            'connection'           => 'redis',
            'queue'                => ['high', 'default', 'low'],
            'balance'              => 'auto',
            'autoScalingStrategy'  => 'time',
            'minProcesses'         => 1,
            'maxProcesses'         => 20,
            'balanceMaxShift'      => 1,
            'balanceCooldown'      => 3,
            'maxTime'              => 3600,
            'maxJobs'              => 1000,
            'memory'               => 256,
            'tries'                => 3,
            'timeout'              => 60,
            'nice'                 => 0,
        ],

        'supervisor-emails' => [
            'connection'    => 'redis',
            'queue'         => ['emails'],
            'balance'       => 'simple',
            'minProcesses'  => 2,
            'maxProcesses'  => 4,
            'memory'        => 128,
            'timeout'       => 30,
        ],
    ],
],
```

| Key | Meaning |
|---|---|
| `connection` | Redis connection name (from `config/queue.php`) |
| `queue` | Priority list — left = highest priority |
| `balance` | `simple` / `auto` / `false` (see §4) |
| `autoScalingStrategy` | `time` / `size` (see §5) |
| `minProcesses` | Floor — workers always alive |
| `maxProcesses` | Ceiling — never exceeded |
| `balanceMaxShift` | Max worker count change per `balanceCooldown` window |
| `balanceCooldown` | Seconds between rebalance decisions |
| `maxTime` | Worker recycles after N seconds (counters slow leaks) |
| `maxJobs` | Worker recycles after N jobs (counters memory creep) |
| `memory` | MB ceiling per worker — exceeding triggers restart |
| `tries` | Default attempts (job-level `$tries` overrides) |
| `timeout` | Seconds before SIGTERM mid-job |
| `nice` | Linux process priority (0 = normal, 19 = low) |

## 4. Balance strategies — when to use which

### 4.1 `simple` — equal split

```php
'balance' => 'simple',
'queue'   => ['high', 'default', 'low'],
'minProcesses' => 6,
'maxProcesses' => 6,
```

Each queue gets `maxProcesses / queue_count` workers. With 6 processes and 3 queues, 2 workers per queue.

**Use when:**
- Each queue has predictable, similar load.
- You want determinism over efficiency.
- The number of queues is small (≤ 3).

⚠️ **Anti-pattern:** `simple` with one queue dominating. Idle workers on quiet queues while the busy queue backlogs.

### 4.2 `auto` — backlog-aware (recommended default)

```php
'balance'             => 'auto',
'autoScalingStrategy' => 'time',
'minProcesses'        => 1,
'maxProcesses'        => 20,
'balanceMaxShift'     => 1,
'balanceCooldown'     => 3,
```

Horizon polls each queue's metrics (size or time-to-clear). Workers move toward queues with backlog, away from idle queues, capped by `balanceMaxShift` per `balanceCooldown`.

**Use when:**
- Mixed queue load (bursts on one, steady on another).
- You want the system to self-tune.
- Most production setups.

**Calibration:**
- `balanceMaxShift: 1` is gentle; raise to 3-5 only if you have 30+ workers and slow rebalance is hurting.
- `balanceCooldown: 3` means decisions every 3 seconds. Lower = more responsive but more Redis polling.

### 4.3 `false` — manual priority

```php
'balance' => false,
'queue'   => ['high', 'default', 'low'],
'maxProcesses' => 10,
```

Workers drain `high` first; only when `high` is empty do they pull from `default`. Strict priority.

**Use when:**
- You truly need strict ordering (e.g. `high` is "user is waiting", `low` is "batch report").
- You accept that `low` may starve under load.

⚠️ **Anti-pattern:** `false` without monitoring `low` queue depth. Background work silently piles up; nobody notices until disk fills.

## 5. Autoscaling strategies (`auto` mode)

| Strategy | Decision input | Use when |
|---|---|---|
| `time` | Estimated time-to-clear the queue (jobs × avg runtime) | Most cases — accounts for slow jobs, not just count |
| `size` | Raw job count | Jobs are uniform / short; or when you can't measure runtime accurately yet |

**`time` example:** queue `payments` has 50 jobs averaging 2s = 100s estimated. Horizon scales workers until estimated clear time falls below a threshold.

**`size` example:** queue `notifications` has 10000 jobs of unknown runtime. Horizon scales by raw count.

Default `time` is the right starting point. Switch to `size` only if your jobs have wildly varying runtimes that confuse the estimator.

## 6. Sizing workers — the back-of-the-envelope

| Workload type | Characterization | `memory` | `timeout` | `maxJobs` | `maxTime` |
|---|---|---|---|---|---|
| Email / notification | 100ms each, lots of `Mail::send` | 128 | 30 | 5000 | 3600 |
| Image processing | 2-30s, Imagick / FFmpeg | 512 | 600 | 200 | 1800 |
| Payment / webhook | 200-2000ms, external HTTP | 256 | 60 | 1000 | 3600 |
| Reports / exports | 30-300s, large queries | 512 | 600 | 100 | 7200 |
| Bulk imports | 5-60s, repeated DB writes | 384 | 300 | 200 | 3600 |

**Rules of thumb:**
- `timeout` < `maxTime` — `timeout` kills mid-job; `maxTime` recycles between jobs.
- `memory` slightly above peak observed via `htop`/`pidstat` — too tight = thrashing.
- `maxJobs` low (100-500) for memory-leak-prone work (image, PDF), high (5000+) for trivial work.
- Calibrate by watching the dashboard's "Per Worker Runtime" and "Memory" charts for a day.

## 7. Tags — finding jobs in the dashboard

```php
final class ProcessOrder implements ShouldQueue
{
    use Queueable;

    public function __construct(public Order $order) {}

    public function tags(): array
    {
        return [
            "order:{$this->order->id}",
            "tenant:{$this->order->tenant_id}",
            "country:{$this->order->shipping_country}",
        ];
    }
}
```

In the dashboard: `Recent Jobs → Search "tenant:42"` filters every job for tenant 42.

**Rules:**
- Tag with **identifiers**, not values that change. `tenant:42` good; `status:paid` bad (status changes after dispatch).
- Tag granularity should match how you debug. If you fight fires by tenant, tag tenants.
- Don't put PII in tags — they show in the dashboard and persist for the metric retention window.

## 8. Dashboard authentication — mandatory

```php
// app/Providers/HorizonServiceProvider.php
protected function gate(): void
{
    Gate::define('viewHorizon', function ($user = null) {
        return $user && in_array($user->email, [
            'ops@example.com',
            'on-call@example.com',
        ]);
    });
}
```

For role-based gating with `spatie/laravel-permission`:

```php
Gate::define('viewHorizon', fn ($user = null) =>
    $user?->hasPermissionTo('manage-queues')
);
```

⚠️ **Anti-pattern:** `Gate::define('viewHorizon', fn () => true)` "for now". Dashboard exposes job payloads — possibly tokens, PII, internal URLs.

For extra safety, also restrict at the web server:

```nginx
location /horizon {
    allow 10.0.0.0/8;          # internal only
    deny all;
    proxy_pass http://app;
}
```

## 9. Failed-job alerting

The `failed_jobs` table fills silently. Wire alerts so you find out within minutes, not weeks.

```php
// app/Providers/AppServiceProvider.php
public function boot(): void
{
    Queue::failing(function (JobFailed $event) {
        Sentry::captureException($event->exception, [
            'extra' => [
                'connection' => $event->connectionName,
                'queue'      => $event->job->getQueue(),
                'job'        => $event->job->resolveName(),
                'attempts'   => $event->job->attempts(),
                'payload'    => $event->job->payload(),       // ⚠️ scrub if it contains PII
            ],
        ]);

        // Slack for high-priority queues
        if (in_array($event->job->getQueue(), ['payments', 'high'])) {
            Notification::route('slack', config('alerts.queues_webhook'))
                ->notify(new QueueJobFailedNotification($event));
        }
    });
}
```

**For pager-grade alerts** (PagerDuty / Opsgenie):
- Threshold by rate, not count: "3+ failures in `payments` per 5 min" → page.
- Suppress during maintenance windows (Horizon `pause` doesn't auto-suppress alerts).

⚠️ **Anti-pattern:** alerting on every single failed job. Noise → muted channel → real alert missed.

## 10. Operational commands

```bash
# Lifecycle
php artisan horizon                           # start (run under supervisor in prod)
php artisan horizon:terminate                 # graceful shutdown — finishes current jobs, exits
php artisan horizon:pause                      # stop processing new jobs (workers stay alive)
php artisan horizon:continue                   # resume after pause
php artisan horizon:pause-supervisor <name>    # pause one supervisor only
php artisan horizon:continue-supervisor <name>

# Status
php artisan horizon:status                     # is master process running?
php artisan horizon:list                       # deployed machines running Horizon
php artisan horizon:supervisors                # all supervisors and process counts
php artisan horizon:supervisor-status <name>   # status of one supervisor

# Maintenance
php artisan horizon:purge                      # clean up stale workers
php artisan horizon:clear                      # delete all jobs from all queues (DESTRUCTIVE)
php artisan horizon:forget <id>                # delete a specific failed job
```

**Deploy hook:**

```bash
# After new code is deployed
php artisan horizon:terminate
# supervisor restarts horizon → loads new code
```

⚠️ Don't `kill -9` the master. Always `horizon:terminate` — Horizon waits up to `terminate_timeout` (default 60s) for in-flight jobs to finish.

## 11. Supervisord template

```ini
# /etc/supervisor/conf.d/horizon.conf
[program:horizon]
process_name=%(program_name)s
command=php /var/www/html/artisan horizon
autostart=true
autorestart=true
user=www-data
redirect_stderr=true
stdout_logfile=/var/log/horizon.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
stopwaitsecs=3600
environment=APP_ENV="production"
```

```bash
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl start horizon
sudo supervisorctl status horizon
```

**Critical detail:** `stopwaitsecs=3600` is high on purpose — supervisord must wait for `horizon:terminate` to finish in-flight jobs before forcing kill. Default 10s will cause data corruption on long-running jobs.

## 12. systemd template

```ini
# /etc/systemd/system/horizon.service
[Unit]
Description=Laravel Horizon
After=network.target redis-server.service mysql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/html
ExecStart=/usr/bin/php /var/www/html/artisan horizon
ExecStop=/usr/bin/php /var/www/html/artisan horizon:terminate
Restart=always
RestartSec=5
TimeoutStopSec=3600
StandardOutput=journal
StandardError=journal
Environment=APP_ENV=production

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now horizon
sudo systemctl status horizon
sudo journalctl -fu horizon                                  # follow logs
sudo systemctl restart horizon                                # graceful via ExecStop
```

## 13. Deploy hooks — Forge / Envoyer / shipped script

```bash
# After new code is deployed AND symlink swapped
cd /var/www/current

php artisan migrate --force
php artisan optimize
php artisan horizon:terminate
# supervisord/systemd auto-restarts horizon → it loads new code
```

**Order matters:**
1. Migrate first (so new code finds the schema it expects).
2. `optimize` (config + route + view caches).
3. `horizon:terminate` last (workers re-load with everything in place).

⚠️ **Anti-pattern:** running migrations after `horizon:terminate` and during the restart window. Workers may pick up jobs against the old schema.

## 14. Metrics — what to watch

| Metric | Where | Threshold to alert |
|---|---|---|
| Queue wait time (P95) | Dashboard → Metrics | > 30s for `high`, > 5min for `default` |
| Failed jobs / hour | Dashboard → Failed | > 10 (project-dependent) |
| Workers at `maxProcesses` | Dashboard → Metrics | sustained for 5+ min — bump cap |
| Workers at `minProcesses` constantly | Dashboard | over-provisioned — lower min |
| Job runtime (P95) outliers | Dashboard → Per Job | jobs > 5× their average → investigate |
| Memory per worker | `htop` / dashboard | trending up → check for leaks |

**External monitoring options:**

```php
// Send Horizon metrics to StatsD / Datadog / Prometheus
use Laravel\Horizon\Events\JobReleased;

Event::listen(JobReleased::class, function ($event) {
    StatsD::increment('horizon.jobs.released', 1, [
        'queue' => $event->payload['queue'] ?? 'unknown',
    ]);
});
```

## 15. Troubleshooting

| Symptom | Diagnosis | Fix |
|---|---|---|
| Dashboard shows "no data" | Wrong env in `horizon.php#environments`; or `HORIZON_PREFIX` mismatches across servers | Check `config('horizon.environments')` vs `app()->environment()`; align `HORIZON_PREFIX` |
| Jobs queue but never run | Master process not running, or all supervisors paused | `horizon:status`, `horizon:list`, `horizon:continue` |
| Master starts then dies | Redis unreachable; missing `horizon` table; PHP error in service provider | `journalctl -u horizon` or `tail -f /var/log/horizon.log` |
| "Reserved" jobs stuck after a crash | Stale visibility timeout / lock | `horizon:purge` (or for raw Redis, tune `block_for`) |
| Workers OOM-killed | `memory` value too tight or genuine leak | Bump `memory`; lower `maxJobs` to recycle sooner; profile with `php-meminfo` |
| Same job runs twice | Ack failure + idempotency missing | Add idempotency guard (see SKILL.md §12); reduce `tries` if duplicate is worse than retry |
| Failed jobs missing from dashboard | `failed_jobs` table not migrated; or different connection | `php artisan queue:failed-table && migrate`; verify `config('queue.failed.driver')` |
| `Failed to authenticate using AUTH password` | Redis ACL misconfigured | Check `REDIS_USERNAME` / `REDIS_PASSWORD`; align with Redis 6+ ACL rules |
| Dashboard 404s | `php artisan horizon:install` not run, or assets not published after upgrade | Re-run; `php artisan horizon:publish` |
| Job throughput suddenly drops | `balance: auto` swung workers away; or Redis slow log spiking | Dashboard "Recent Workload" + Redis `SLOWLOG GET 10` |

## 16. Multi-environment — staging vs prod

```php
'environments' => [
    'production' => [
        'supervisor-default' => [/* tuned for prod */ 'maxProcesses' => 20],
    ],
    'staging' => [
        'supervisor-default' => [/* lower limits */ 'maxProcesses' => 4],
    ],
    'local' => [
        'supervisor-default' => [/* one worker, all queues */ 'maxProcesses' => 1],
    ],
],
```

`APP_ENV` selects the block. Keep staging close to prod in shape (same supervisor names, same balance strategy) so you spot config issues before prod deploy.

## 17. Multi-server clusters

| Concern | Approach |
|---|---|
| Many app servers, one Redis | Each server runs its own `horizon` master; they share the queue. Workers compete fairly. |
| `HORIZON_PREFIX` | Same across servers — they appear as one cluster in the dashboard. |
| Dashboard | Run on **one** server (gate the others' `/horizon` route at nginx) — avoids confusing the user with N "Horizon — production" entries. |
| Tags / metrics | Aggregated across all servers automatically (Redis is the single source of truth). |
| Deploy | `horizon:terminate` on all servers in parallel after symlink swap. Brief throughput dip is expected. |

⚠️ **Anti-pattern:** running Horizon dashboards on multiple servers behind a load balancer without sticky sessions. Users see different states on each refresh.

## 18. Cross-references

- `laravel-queues` SKILL.md §9 — summary that links here
- `laravel-queues` §3 — dispatch options (`afterCommit`, `delay`, `onQueue`, `onConnection`)
- `laravel-queues` §5 — job middleware (rate limit, overlap, exception throttle)
- `laravel-queues` §7 — failed-job hooks (`Queue::failing`)
- `laravel-queues` §12 — idempotency contract
- (devops agent) — supervisord/systemd unit deployment, env management
