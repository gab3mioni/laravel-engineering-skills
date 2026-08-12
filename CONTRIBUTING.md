# Contributing

Thanks for your interest in `laravel-engineering-skills`. This document covers the repo layout, how to add an agent or skill, and the conventions the project follows across Claude Code and Codex.

## Language

All committed content is **English** — README, this file, `SKILL.md`, agent prompts, references, code comments, and commit messages. Issues and PRs may be opened in any language.

## Repo layout

```
.claude-plugin/
  plugin.json                  # Claude Code plugin manifest
  marketplace.json             # Claude Code marketplace
.codex-plugin/
  plugin.json                  # Codex plugin manifest
.agents/plugins/
  marketplace.json             # Codex repository marketplace
agents/
  backend.md                   # one file per agent: frontmatter + system prompt
  laravel-react.md
  laravel-vue.md
  devops.md
  code-review.md
  security.md
  qa.md
  db-performance.md
scripts/
  detect-stack.sh              # shared stack detection (HAS_* flags) used by every agent
skills/
  <skill>/
    SKILL.md                   # active procedures + decision tables (idiomatic Laravel 12)
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

1. Create `skills/<skill-name>/SKILL.md` with frontmatter shared by Claude Code and Codex:

   ```markdown
   ---
   name: <skill-name>
   description: One-paragraph description listing concrete topics and trigger conditions. Used by Claude Code and Codex to decide when to load it.
   ---

   # Skill title

   Body in Markdown.
   ```

2. Follow the **active template** — sections in this order: When to use / When NOT to use → Stack assumptions → **Workflows** (numbered procedures, each step with a verification command) → **Decision tables** → knowledge sections (corrective/opinionated content only — no API catalogs the model already knows) → **Rules & anti-patterns** (every row with a detection grep) → **Troubleshooting** (symptom → cause → fix) → **Reference routing** (task/symptom → which reference to load) → Cross-references. When a section grows past ~150 lines, extract it to `references/<topic>.md` and route to it.

   Two hard rules: never point to another skill's file by path (point by skill name — relative paths only resolve inside the skill's own folder), and label `laravel-react`/`laravel-vue`/`devops` and other agents as **agents** in routing tables (they are not loadable skills).

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

## Shared roles and skill dependency map

The `laravel-role-*` directories are the canonical procedures consumed directly by Codex and loaded by the compatibility wrappers in `agents/`. Agents must not duplicate role instructions.

| Skill | Consumed by |
|---|---|
| `laravel-backend` | `backend`, `security`, `code-review`, `db-performance`, `qa` |
| `laravel-frontend` | `laravel-react`, `laravel-vue`, `code-review` |
| `laravel-inertia` | `laravel-react`, `laravel-vue`, `code-review`, `qa` |
| `laravel-queues` | `backend`, `devops`, `code-review`, `db-performance` |
| `laravel-auth` | `security`, `backend`, `code-review`, `qa` |
| `laravel-static-analysis` | `backend`, `code-review` |
| `laravel-a11y` | `laravel-react`, `laravel-vue`, `code-review` |
| `laravel-qa` | every agent; `qa` follows its workflows as procedure |
| `laravel-security` | `security`, `code-review`, `backend` |
| `laravel-deploy` | `devops` |
| `laravel-observability` | `laravel-role-devops`, `laravel-role-backend`, `laravel-role-security`, `laravel-role-code-review` |
| `laravel-integrations` | `laravel-role-backend`, `laravel-role-security`, `laravel-role-code-review`, `laravel-role-qa` |
| `laravel-qa/references/browser_and_visual_testing.md` | `laravel-role-react`, `laravel-role-vue`, `laravel-role-qa`, `laravel-a11y`, `laravel-frontend` |

| Shared role | Claude wrapper |
|---|---|
| `laravel-role-backend` | `agents/backend.md` |
| `laravel-role-code-review` | `agents/code-review.md` |
| `laravel-role-db-performance` | `agents/db-performance.md` |
| `laravel-role-devops` | `agents/devops.md` |
| `laravel-role-react` | `agents/laravel-react.md` |
| `laravel-role-vue` | `agents/laravel-vue.md` |
| `laravel-role-qa` | `agents/qa.md` |
| `laravel-role-security` | `agents/security.md` |

`code-review` is universal and consumes every skill — review crosses every code domain. `laravel-qa` is universal in the other direction — every agent that writes, runs, or audits code touches it.

## Local testing

### Claude Code

After cloning, register the local checkout as a marketplace and install the plugin:

```text
/plugin marketplace add /absolute/path/to/laravel-engineering-skills
/plugin install laravel-engineering-skills@laravel-engineering-skills
```

The marketplace identifier (`laravel-engineering-skills`) is defined in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json). The plugin identifier (`laravel-engineering-skills`) is defined in [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json).

Validate the manifests before committing:

```bash
claude plugin validate .
```

Reload after edits with `/reload-plugins` (or restart the Claude Code session).

### Codex

Register this checkout as a local marketplace, install the plugin, and start a new session:

```bash
codex plugin marketplace add /absolute/path/to/laravel-engineering-skills
codex plugin add laravel-engineering-skills@laravel-engineering-skills
```

Validate the Codex manifest and every shared skill before committing:

```bash
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
for skill in skills/*; do
  python3 /path/to/skill-creator/scripts/quick_validate.py "$skill"
done

# Repository-level deterministic validation (stdlib only)
python3 scripts/validate_skills.py .
python3 scripts/validate_manifests.py .
```

Codex discovers the plugin skills in a new session. The files under `agents/` are Claude Code subagent definitions and are intentionally ignored by Codex.

## Roadmap

- Evaluate additional framework/domain skills only when requested.
- Improve provider adapters while keeping observability and integrations provider-neutral.

## Status

| Component | State |
|---|---|
| Plugin scaffolding (manifest, dirs) | done |
| Codex plugin and repository marketplace | done |
| Shared roles, 12 core skills, and provider-neutral integrations/observability | done |
| 8 agent prompts (`backend`, `code-review`, `devops`, `laravel-react`, `laravel-vue`, `security`, `qa`, `db-performance`) | done |
| Shared stack detection (`scripts/detect-stack.sh`) | done |

## License

By contributing you agree your contributions are licensed under the [MIT License](./LICENSE).
