# HTTP clients

Wrap each vendor in a focused client. Configure base URL from `config()`, explicit connect/total timeouts, accepted status codes, authentication headers, and a bounded retry policy. Validate response shape before using it. Do not pass arbitrary user-controlled URLs to the client; use an allowlist or a configured endpoint.

Classify errors into transport, rate limit, retryable server, contract, and authentication failures. Include vendor request IDs in structured telemetry, not secrets or full payloads.
