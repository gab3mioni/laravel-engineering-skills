# Laravel Claude Code Skills

Opinionated plugin for the **Laravel 12** ecosystem, compatible with both [Claude Code](https://claude.com/claude-code) and [Codex](https://developers.openai.com/codex/). It bundles reusable skills for idiomatic, type-safe, well-tested Laravel backend, frontend (Inertia + React/Vue), DevOps, code review, and security. Claude Code also receives the specialized subagents included in `agents/`.

## Installation

### Claude Code

In Claude Code:

```text
/plugin marketplace add gab3mioni/laravel-claude-code-skills
/plugin install laravel-claudecode-toolkit@laravel-claude-code-skills
```

The first command registers this repo as a marketplace; the second installs the plugin from it. The `@laravel-claude-code-skills` suffix is the marketplace identifier (matches the GitHub repo name).

### Codex

Register the GitHub repository as a marketplace, then install the plugin:

```bash
codex plugin marketplace add gab3mioni/laravel-claude-code-skills
codex plugin add laravel-claude-code-skills@laravel-claude-code-skills
```

Alternatively, run `codex`, enter `/plugins`, select the `laravel-claude-code-skills` marketplace, and install the plugin. Start a new Codex session after installation so the bundled skills are loaded.

For local development setup on either host, see [CONTRIBUTING.md](./CONTRIBUTING.md#local-testing).

## What's included

### Claude Code agents

- **`backend`** — Eloquent, controllers, FormRequests, services, jobs, migrations, API design.
- **`laravel-react`** — Inertia v2 + React 19 (hooks, `useForm`, partial reloads, deferred props, Wayfinder routes).
- **`laravel-vue`** — Inertia v2 + Vue 3.5 (composables, `useForm`, partial reloads, Pinia, Wayfinder routes).
- **`devops`** — Deploy, Docker, CI/CD, Octane, Horizon, scheduler, env management.
- **`code-review`** — Read-only PR/diff/branch review with a Laravel-aware checklist.
- **`security`** — OWASP Top 10:2025 audit and canonical fixes (CSRF, mass assignment, vulnerable deps).
- **`qa`** — Writes the tests other agents owe: Pest feature/unit tests, factories, fakes, Inertia assertions. Owns `tests/` and `database/factories/`.
- **`db-performance`** — Read-only diagnostician: hunts N+1s, audits indexes with EXPLAIN, picks chunk/cursor strategies; proposes fixes for `backend` to apply.

All agents inherit the Claude Code session model. Codex consumes the shared skills directly; Claude-specific agent definitions are not loaded by Codex.

### Skills

`laravel-backend` · `laravel-frontend` · `laravel-inertia` · `laravel-queues` · `laravel-auth` · `laravel-static-analysis` · `laravel-a11y` · `laravel-qa` · `laravel-security` · `laravel-deploy`

Skills are procedures and checklists agents follow — workflows with verification steps, decision tables, and anti-pattern greps, loaded on demand. `laravel-qa` is universal — every agent that touches code writes, runs, or audits tests against it.

**Scope:** the plugin targets the Inertia stack (React/Vue SPAs) with Laravel Wayfinder for client-side routes. Livewire and Filament are out of scope.

## Usage

Both hosts can select skills automatically from the task context. Claude Code can also activate its specialized agents proactively (editing a controller routes you to `backend`; reviewing a diff routes you to `code-review`).

To invoke a Claude Code agent explicitly:

```text
@backend create a FormRequest for the order checkout endpoint
@code-review audit the current branch
```

To invoke a skill explicitly in Codex, mention it with `$`:

```text
$laravel-backend create a FormRequest for the order checkout endpoint
$laravel-security audit the current branch
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the repo layout, how to add a skill or agent, and the project conventions.

## License

MIT — see [LICENSE](./LICENSE).
