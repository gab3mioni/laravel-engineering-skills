# Webhooks

Verify the signature against `$request->getContent()` using a secret from configuration and `hash_equals`. If the provider supplies a timestamp, enforce a bounded freshness window. Store event ID/provider/received-at and reject or no-op duplicates before side effects. Persist the event before dispatching processing with `afterCommit()`.

For outgoing webhooks, serialize once, sign that exact body, persist delivery state, send from a queue, and record a bounded response summary. Never log the body or signing secret.
