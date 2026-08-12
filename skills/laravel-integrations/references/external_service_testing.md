# External service testing

Use `Http::fake()` and assert request method, URL, headers, body, and call count. Cover successful responses, malformed payloads, timeouts, 429/5xx, auth failures, and exhaustion. Use Pest feature or integration tests around the application boundary; do not contact a vendor from the test suite.

For webhook tests, send the exact raw JSON used to compute the signature and cover invalid, stale, and duplicate events. Assert durable state and queued work with `Queue::fake()` where the job itself is not under test.
