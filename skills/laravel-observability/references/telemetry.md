# Telemetry contract

Use stable event names such as `http.request.completed`, `queue.job.failed`, and `integration.request.completed`. Include duration, outcome, environment, release, and correlation IDs. Redact authorization headers, cookies, API keys, passwords, raw webhook bodies, and personal data unless an approved data-minimization policy says otherwise.

Propagate a request/trace ID through outbound HTTP headers and job payload metadata. Preserve the originating ID as a link, not as an unbounded metric label. Counters and histograms should use bounded labels such as route name, status class, queue name, and dependency name.

Use native logging and test doubles by default. Add provider adapters only after package detection. Pulse/Telescope are useful for local and application inspection; OpenTelemetry is appropriate for distributed traces; Sentry is appropriate for exception grouping and alerting. None is required by this skill.
