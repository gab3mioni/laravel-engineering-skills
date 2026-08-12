# Health checks and SLOs

Separate liveness from readiness. Liveness should answer whether the process can serve; readiness may verify the database, cache, queue, or other mandatory dependency with a bounded timeout. Do not expose credentials, SQL errors, hostnames, or stack traces in the response.

Define each SLO as a target, time window, eligible requests/jobs, owner, and alert policy. Examples include successful HTTP requests, queue completion latency, and integration delivery success. Verify a deploy by checking readiness, a critical smoke path, error rate, latency, queue depth, and worker freshness before increasing traffic.
