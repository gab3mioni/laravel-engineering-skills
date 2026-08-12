# Laravel Engineering Skills

Opinionated plugin for the **Laravel 12** ecosystem, compatible with both [Claude Code](https://claude.com/claude-code) and [Codex](https://developers.openai.com/codex/). It bundles reusable skills for idiomatic, type-safe, well-tested Laravel backend, frontend (Inertia + React/Vue), DevOps, code review, and security. Claude Code also receives the specialized subagents included in `agents/`.

## Installation

Install the plugin in the host you use. Claude Code and Codex have separate plugin registries, so installing it in one host does not install it in the other.

### Claude Code

1. Open Claude Code.
2. Add this repository as a marketplace:

```text
/plugin marketplace add gab3mioni/laravel-engineering-skills
```

3. Install the Claude Code plugin:

```text
/plugin install laravel-engineering-skills@laravel-engineering-skills
```

The `@laravel-engineering-skills` suffix is the marketplace identifier. After installation, start a new session or reload plugins if Claude Code asks for it. The eight Claude agents remain available, and each one loads its corresponding shared `laravel-role-*` skill.

You can also install through the interactive interface:

1. Run `/plugins`.
2. Add or select the `laravel-engineering-skills` marketplace.
3. Install `laravel-engineering-skills`.

For a local checkout, use the absolute path instead of the GitHub repository:

```text
/plugin marketplace add /absolute/path/to/laravel-engineering-skills
/plugin install laravel-engineering-skills@laravel-engineering-skills
```

### Codex

#### CLI

1. Register the GitHub repository as a marketplace:

```bash
codex plugin marketplace add gab3mioni/laravel-engineering-skills
```

2. Install the Codex plugin:

```bash
codex plugin add laravel-engineering-skills@laravel-engineering-skills
```

3. Start a new Codex session so the bundled skills are loaded.

#### Interactive interface

1. Run `codex`.
2. Open `/plugins`.
3. Select the `laravel-engineering-skills` marketplace.
4. Install `laravel-engineering-skills`.

Codex loads the shared skills and roles directly. The files under `agents/` are Claude Code wrappers and are not loaded by Codex.

#### Use a local checkout

Replace the GitHub path with the absolute path to your checkout:

```bash
codex plugin marketplace add /absolute/path/to/laravel-engineering-skills
codex plugin add laravel-engineering-skills@laravel-engineering-skills
```

Start a new session after changing a skill. For repository validation commands, see [CONTRIBUTING.md](./CONTRIBUTING.md#local-testing).


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

### Shared roles

Codex loads the eight shared `laravel-role-*` skills directly. Claude Code agents with the same names are compatibility wrappers that load those roles, so ownership, handoffs, and Definition of Done stay in one place.

### Skills

`laravel-backend` · `laravel-frontend` · `laravel-inertia` · `laravel-queues` · `laravel-auth` · `laravel-static-analysis` · `laravel-a11y` · `laravel-qa` · `laravel-security` · `laravel-deploy` · `laravel-observability` · `laravel-integrations`

Skills are procedures and checklists agents follow — workflows with verification steps, decision tables, and anti-pattern greps, loaded on demand. `laravel-qa` is universal — every agent that touches code writes, runs, or audits tests against it.

**Scope:** the plugin targets the Inertia stack (React/Vue SPAs) with Laravel Wayfinder for client-side routes. Livewire and Filament are out of scope.

Playwright MCP support is optional. When its tools are exposed, QA and frontend roles may run behavioral browser smoke checks and desktop/mobile screenshots. Without it, the normal test and accessibility workflows remain complete and report browser checks as skipped.

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
