# Idempotency and retries

An idempotency key needs a durable uniqueness constraint scoped to the operation and tenant/account, a request fingerprint, status, response/result reference, and an expiry policy. Concurrent requests must serialize through a database constraint or lock. A key reused with a different fingerprint is a client error.

Retries require an operation that is safe to repeat. Prefer provider idempotency keys for charges and writes. Keep attempt deadlines shorter than the caller's timeout budget, and stop at a bounded deadline. Queue-level retries and `afterCommit` are mechanics owned by `laravel-queues`.
