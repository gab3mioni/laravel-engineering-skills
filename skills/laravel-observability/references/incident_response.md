# Incident response

1. Declare the incident, assign an incident lead, and record start time and scope.
2. Stabilize with the smallest reversible action: rollback, disable a feature, drain a queue, or rate-limit a dependency.
3. Communicate customer impact and next update time.
4. Preserve correlation IDs, deploy version, logs, metrics, traces, failed jobs, and provider responses.
5. Recover, verify the SLO and critical path, then close with a timeline, root/contributing causes, and owned follow-ups.

Do not paste secrets or personal data into incident channels. Link to the canonical runbook and use the release identifier to compare before/after behavior.
