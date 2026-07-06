# laravel-claudecode-toolkit

Opinionated [Claude Code](https://claude.com/claude-code) plugin for the **Laravel 12** ecosystem. Bundles specialized agents and skills so Claude writes idiomatic, type-safe, well-tested Laravel  backend, frontend (Inertia + React/Vue), DevOps, code review, and security, without you having to spell out conventions every session.

## Installation

In Claude Code:

```text
/plugin marketplace add gab3mioni/laravel-claude-code-skills
/plugin install laravel-claudecode-toolkit@laravel-claude-code-skills
```

The first command registers this repo as a marketplace; the second installs the plugin from it. The `@laravel-claude-code-skills` suffix is the marketplace identifier (matches the GitHub repo name).

For local development, clone the repo and point the marketplace at the local path:

```bash
git clone https://github.com/gab3mioni/laravel-claude-code-skills
```

```text
/plugin marketplace add /absolute/path/to/laravel-claude-code-skills
/plugin install laravel-claudecode-toolkit@laravel-claude-code-skills
```

## What's included

### Agents

- **`backend`** — Eloquent, controllers, FormRequests, services, jobs, migrations, API design.
- **`laravel-react`** — Inertia v2 + React 19 (hooks, `useForm`, partial reloads, deferred props, Wayfinder routes).
- **`laravel-vue`** — Inertia v2 + Vue 3.5 (composables, `useForm`, partial reloads, Pinia, Wayfinder routes).
- **`devops`** — Deploy, Docker, CI/CD, Octane, Horizon, scheduler, env management.
- **`code-review`** — Read-only PR/diff/branch review with a Laravel-aware checklist.
- **`security`** — OWASP Top 10:2025 audit and canonical fixes (CSRF, mass assignment, vulnerable deps).
- **`qa`** — Writes the tests other agents owe: Pest feature/unit tests, factories, fakes, Inertia assertions. Owns `tests/` and `database/factories/`.
- **`db-performance`** — Read-only diagnostician: hunts N+1s, audits indexes with EXPLAIN, picks chunk/cursor strategies; proposes fixes for `backend` to apply.

All agents inherit the session model — you control Opus/Sonnet/Haiku.

### Skills

`laravel-backend` · `laravel-frontend` · `laravel-inertia` · `laravel-queues` · `laravel-auth` · `laravel-static-analysis` · `laravel-a11y` · `laravel-qa` · `laravel-security` · `laravel-deploy`

Skills are procedures and checklists agents follow — workflows with verification steps, decision tables, and anti-pattern greps, loaded on demand. `laravel-qa` is universal — every agent that touches code writes, runs, or audits tests against it.

**Scope:** the plugin targets the Inertia stack (React/Vue SPAs) with Laravel Wayfinder for client-side routes. Livewire and Filament are out of scope.

## Usage

Most of the time you don't need to do anything — agents activate proactively based on context (editing a controller routes you to `backend`; reviewing a diff routes you to `code-review`).

To invoke explicitly:

```text
@backend create a FormRequest for the order checkout endpoint
@code-review audit the current branch
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the repo layout, how to add a skill or agent, and the project conventions.

## License

MIT — see [LICENSE](./LICENSE).
