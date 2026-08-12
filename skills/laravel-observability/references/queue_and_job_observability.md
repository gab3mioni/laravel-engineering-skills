# Queue and job observability

Track dispatch, start, completion, release, retry, failure, and duration with queue, job class, attempt, release, and correlation metadata. Monitor depth, oldest-job age, throughput, failure rate, retry rate, timeout rate, and worker restarts. Keep payloads out of telemetry.

Connect failed jobs to an operator-safe replay process. A replay must preserve idempotency and record who or what initiated it. Queue retry/backoff, uniqueness, and `afterCommit` mechanics remain owned by `laravel-queues`.
