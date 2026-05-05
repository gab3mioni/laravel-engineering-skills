# Contributing

Thanks for your interest in `laravel-claudecode-toolkit`. This document covers the repo layout, how to add an agent or skill, and the conventions the project follows.

## Language

All committed content is **English** — README, this file, `SKILL.md`, agent prompts, references, code comments, and commit messages. Issues and PRs may be opened in any language.

## Repo layout

```
.claude-plugin/
  plugin.json                  # plugin manifest (name, version, author)
agents/
  backend.md                   # one file per agent: frontmatter + system prompt
  laravel-react.md
  laravel-vue.md
  devops.md
  code-review.md
  security.md
skills/
  <skill>/
    SKILL.md                   # stack-neutral cheat-sheet (idiomatic Laravel 12)
    references/                # deep-dives loaded on demand
    scripts/                   # Python helpers (stdlib only, ≥ 3.11)
LICENSE
README.md
CONTRIBUTING.md
```

## Stack constraints

- **Laravel 12** and **PHP 8.3+** for any server-side example.
- **Pest 3** for tests (no PHPUnit examples).
- **Inertia 2** for the React 19 / Vue 3.5 frontends.
- **Python ≥ 3.11, stdlib only** for skill helper scripts. No `pip install`, no `uv`. Static analysis of PHP is shelled out (`pint`, `larastan`, `phpstan`, `rector`).

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with frontmatter:

   ```markdown
   ---
   name: <skill-name>
   description: One-paragraph description that lists the concrete topics covered and which agents consume the skill. Used by Claude Code to decide when to load it.
   ---

   # Skill title

   Body in Markdown.
   ```

2. Keep `SKILL.md` as a **stack-neutral cheat-sheet**. When a section grows past ~150 lines, extract it to `references/<topic>.md` and link to it from `SKILL.md`.

3. Helper scripts go under `scripts/` and must use Python stdlib only.

4. Update the dependency map below if the skill is consumed by additional agents.

## Adding an agent

1. Create `agents/<agent-name>.md` with frontmatter:

   ```markdown
   ---
   name: <agent-name>
   description: Use PROACTIVELY when ... (one paragraph; the trigger conditions matter — they drive automatic invocation)
   tools: Read, Glob, Grep, Edit, Write, Bash, WebFetch
   ---

   System prompt for the agent.
   ```

2. Agents inherit the session model — never pin a model in the agent file.

3. Read-only agents (e.g. `code-review`) must omit `Edit` and `Write` from `tools`.

4. The system prompt should reference the skills the agent consumes by name so Claude loads them when activated.

## Skill / agent dependency map

| Skill | Consumed by |
|---|---|
| `laravel-backend` | `backend`, `security`, `code-review` |
| `laravel-frontend` | `laravel-react`, `laravel-vue`, `code-review` |
| `laravel-inertia` | `laravel-react`, `laravel-vue`, `code-review` |
| `laravel-queues` | `backend`, `devops`, `code-review` |
| `laravel-auth` | `security`, `backend`, `code-review` |
| `laravel-static-analysis` | `backend`, `code-review` |
| `laravel-a11y` | `laravel-react`, `laravel-vue`, `code-review` |
| `laravel-qa` | every agent |
| `laravel-security` | `security`, `code-review`, `backend` |

`code-review` is universal and consumes every skill — review crosses every code domain. `laravel-qa` is universal in the other direction — every agent that writes, runs, or audits code touches it.

## Local testing

After cloning, register the local checkout as a marketplace and install the plugin:

```text
/plugin marketplace add /absolute/path/to/laravel-claude-code-skills
/plugin install laravel-claudecode-toolkit
```

Reload after edits with `/plugin reload laravel-claudecode-toolkit` (or restart the Claude Code session).

## Roadmap

- Livewire skill and agent
- Filament skill
- Dedicated `secops` agent (operational security, beyond the current `security` agent's per-PR scope)

## Status

| Component | State |
|---|---|
| Plugin scaffolding (manifest, dirs) | done |
| `laravel-backend` skill + 7 references | done |
| `laravel-qa` skill + 3 references | done |
| `laravel-security` skill + 3 references | done |
| `laravel-inertia`, `laravel-frontend`, `laravel-auth`, `laravel-queues`, `laravel-static-analysis`, `laravel-a11y` skills | done (no references yet — extract from `SKILL.md` when sections grow past ~150 lines) |
| All 6 agent prompts (`backend`, `code-review`, `devops`, `laravel-react`, `laravel-vue`, `security`) | done |

## License

By contributing you agree your contributions are licensed under the [MIT License](./LICENSE).
