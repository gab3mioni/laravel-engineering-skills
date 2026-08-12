# Laravel Engineering Skills

Opinionated skills for the **Laravel 12** ecosystem. The collection provides reusable procedures for idiomatic, type-safe, well-tested Laravel backend, frontend (Inertia + React/Vue), DevOps, code review, security, integrations, and observability. Optional agent wrappers are included for hosts that support them.

## Installation

Install the collection using the method supported by your AI coding agent. Plugin registries are host-specific, so installing the plugin in one host does not install it in another.

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

The `@laravel-engineering-skills` suffix is the marketplace identifier. After installation, start a new session or reload plugins if requested. The eight agent wrappers remain available, and each one loads its corresponding shared `laravel-role-*` skill.

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

This installation loads the shared skills and roles directly. The files under `agents/` are optional host-specific wrappers.

#### Use a local checkout

Replace the GitHub path with the absolute path to your checkout:

```bash
codex plugin marketplace add /absolute/path/to/laravel-engineering-skills
codex plugin add laravel-engineering-skills@laravel-engineering-skills
```

Start a new session after changing a skill. For repository validation commands, see [CONTRIBUTING.md](./CONTRIBUTING.md#local-testing).

### Install individual skills with `npx`

The repository is also compatible with the open agent skills CLI. No npm package publication is required: the CLI installs skills directly from this GitHub repository.

List the available skills:

```bash
npx skills@latest add gab3mioni/laravel-engineering-skills --list
```

Install one skill globally for a Codex-compatible host:

```bash
npx skills@latest add gab3mioni/laravel-engineering-skills \
  --skill laravel-backend \
  -a codex \
  -g \
  -y
```

Install one skill globally for a Claude-compatible host:

```bash
npx skills@latest add gab3mioni/laravel-engineering-skills \
  --skill laravel-backend \
  -a claude-code \
  -g \
  -y
```

Replace `laravel-backend` with any skill name, such as `laravel-integrations`, `laravel-observability`, `laravel-role-backend`, or `laravel-role-qa`. To install the complete collection:

```bash
npx skills@latest add gab3mioni/laravel-engineering-skills \
  --all \
  -g \
  -y
```

This method installs the `SKILL.md` directories. Use the host plugin installation above when you also need complete plugin manifests, agent wrappers, marketplace metadata, or other plugin capabilities.


## What's included

### Agent wrappers

- **`backend`** — Eloquent, controllers, FormRequests, services, jobs, migrations, API design.
- **`laravel-react`** — Inertia v2 + React 19 (hooks, `useForm`, partial reloads, deferred props, Wayfinder routes).
- **`laravel-vue`** — Inertia v2 + Vue 3.5 (composables, `useForm`, partial reloads, Pinia, Wayfinder routes).
- **`devops`** — Deploy, Docker, CI/CD, Octane, Horizon, scheduler, env management.
- **`code-review`** — Read-only PR/diff/branch review with a Laravel-aware checklist.
- **`security`** — OWASP Top 10:2025 audit and canonical fixes (CSRF, mass assignment, vulnerable deps).
- **`qa`** — Writes the tests other agents owe: Pest feature/unit tests, factories, fakes, Inertia assertions. Owns `tests/` and `database/factories/`.
- **`db-performance`** — Read-only diagnostician: hunts N+1s, audits indexes with EXPLAIN, picks chunk/cursor strategies; proposes fixes for `backend` to apply.

Agent wrappers inherit the host session model. The shared roles remain the canonical procedures, while wrappers provide host-specific tools and activation behavior.

### Shared roles

The eight shared `laravel-role-*` skills are the canonical roles. The wrappers with matching names load those roles, so ownership, handoffs, and Definition of Done stay in one place.

### Skills

`laravel-backend` · `laravel-frontend` · `laravel-inertia` · `laravel-queues` · `laravel-auth` · `laravel-static-analysis` · `laravel-a11y` · `laravel-qa` · `laravel-security` · `laravel-deploy` · `laravel-observability` · `laravel-integrations`

Skills are procedures and checklists AI coding agents follow — workflows with verification steps, decision tables, and anti-pattern greps, loaded on demand. `laravel-qa` is universal — every agent that touches code writes, runs, or audits tests against it.

**Scope:** the plugin targets the Inertia stack (React/Vue SPAs) with Laravel Wayfinder for client-side routes. Livewire and Filament are out of scope.

Playwright MCP support is optional. When its tools are exposed, QA and frontend roles may run behavioral browser smoke checks and desktop/mobile screenshots. Without it, the normal test and accessibility workflows remain complete and report browser checks as skipped.

## Usage

Compatible hosts can select skills automatically from task context. Hosts that support agent wrappers can also activate specialized agents proactively, such as `backend` for controller work or `code-review` for branch review.

To invoke an agent explicitly, use the syntax supported by your host. For example, Claude Code uses:

```text
@backend create a FormRequest for the order checkout endpoint
@code-review audit the current branch
```

Codex-style skill invocation uses `$`:

```text
$laravel-backend create a FormRequest for the order checkout endpoint
$laravel-security audit the current branch
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the repo layout, how to add a skill or agent, and the project conventions.

## License

MIT — see [LICENSE](./LICENSE).
