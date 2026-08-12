---
name: laravel-frontend
description: Client-side wiring for Laravel 12 — Vite (laravel-vite-plugin, dev server, HMR, manifest), resources/js layout, Laravel Wayfinder (typed named routes/actions on the client), public env vars (VITE_*), code splitting, TypeScript posture, build artifacts, CSP-friendly bundling. Use when editing vite.config, wiring or regenerating Wayfinder routes, laying out resources/js, or debugging symptoms like "HMR not reloading", "manifest not found", "Vite dev server 404", or "asset 404 after deploy". Used by shared React, Vue, and review roles.
---

# Laravel Frontend — Vite, Wayfinder, asset wiring

The plumbing between Laravel and the client bundle. Stack-neutral — covers Vite config, asset pipeline, typed route helpers (Wayfinder), and `resources/js` conventions used identically by React and Vue projects. Component/framework specifics live in the `laravel-react` and `laravel-vue` agents; the Inertia protocol lives in `laravel-inertia`.

## When to use this skill

- Configuring Vite (`vite.config.js`, plugins, aliases, code splitting)
- Laying out `resources/js/` (Pages, Components, Layouts, entry file)
- Wiring **Wayfinder** so the client imports typed route/action functions instead of hardcoding URLs
- Exposing env vars to the client (`VITE_*`)
- Debugging dev-server / HMR issues, manifest mismatches, missing `@vite` directives
- Build/deploy concerns (`npm run build`, hashed assets, `public/build/manifest.json`)
- Reviewing `package.json`, `tsconfig.json`, `vite.config.js` in PRs

## When NOT to use

| Topic | Use instead |
|---|---|
| React 19 components, hooks, `useForm` | `laravel-role-react` |
| Vue 3.5 components, composables, `useForm` | `laravel-role-vue` |
| Inertia protocol (props, partials, defer) | `laravel-inertia` skill |
| WCAG / ARIA in components | `laravel-a11y` skill |
| Pest assertions on rendered HTML | `laravel-qa` skill |
| Octane/FrankenPHP runtime concerns | `laravel-role-devops` |

After UI changes, route relevant browser smoke, responsive, loading/error-state, focus, and keyboard checks to `laravel-qa`'s optional `browser_and_visual_testing.md` reference. Playwright MCP is conditional.

## Stack assumptions

- Laravel 12 with `laravel-vite-plugin` 2.x (Vite 7) or 3.x (Vite 8) — version pairing table in `references/vite_advanced.md`
- Node 20+ (LTS); npm or pnpm
- TypeScript by default in greenfield (`.tsx` / `.ts`); plain JS still supported
- `laravel/wayfinder` for typed named routes/actions on the client (the default in the Laravel 12 starter kits)
- Inertia 2 (most apps) — the layout below assumes Inertia. SPA-without-Inertia and pure Blade are noted where they diverge.

---

## Workflows

### After changing `vite.config.js` or entry files

1. `npm run build` — must exit 0.
2. Open `public/build/manifest.json` — confirm every entry listed in `vite.config.js#input` appears as a top-level key.
3. Confirm the `@vite([...])` call in the Blade shell lists the **same** entries as `input`.
4. `npm run dev`, load a page, edit a component — confirm HMR applies the change without a full reload.

### Dev-server checklist

When `@vite` shows the "running in dev mode" banner but assets 404:

1. Is `npm run dev` running on the same host you're browsing from?
2. Is `APP_URL` correct? The Vite plugin uses it to compute the dev server URL.
3. Custom `VITE_DEV_SERVER_URL` set? Useful for Docker / VM setups.
4. Stale `public/hot` file? It signals "use dev server"; delete after stopping `npm run dev`.

When prod assets 404:

1. Did `npm run build` actually run?
2. Is `public/build/manifest.json` present and readable?
3. Did the deploy script clear `bootstrap/cache/` before `optimize`?
4. CSP blocking `<script type="module">`? Check `script-src` allows `'self'` (§11).

### Wayfinder sync

After adding, renaming, or removing a route or controller method:

1. `php artisan wayfinder:generate` — refreshes `resources/js/actions/` and `resources/js/routes/`.
2. `tsc --noEmit` (React) or `vue-tsc --noEmit` (Vue) — stale imports of renamed/deleted routes now fail the type check instead of 404ing at runtime.
3. If `composer dev` or the Wayfinder Vite plugin is wired in, step 1 happens automatically during dev — still run it explicitly before committing generated files or when the watcher wasn't running.

---

## Decision table — code splitting, lazy vs eager

| Situation | Choice |
|---|---|
| Inertia pages (default resolver) | Already split per file — do nothing |
| Heavy, rarely-visited component (chart lib, rich-text editor, admin screen) | Lazy (`lazy()` / `defineAsyncComponent`) |
| Small component on the critical path | Eager — a lazy chunk adds a request for nothing |
| Tiny app (< ~10 pages, small bundle) | Consider `import.meta.glob(..., { eager: true })` for pages |

---

## 1. The wiring in one paragraph

The `@vite` Blade directive points at the Vite dev server in dev (HMR, on-the-fly transforms) and reads `public/build/manifest.json` in prod to emit hashed `<script>` / `<link>` tags. Page components live under `resources/js/Pages/`, mounted by the entry file. **Wayfinder** generates typed TypeScript functions from Laravel's routes and controllers so the client imports `show(post.id)` instead of hardcoding URLs.

---

## 2. `vite.config.js` rules

Full React and Vue boilerplate: `references/vite_boilerplate.md` §1.

- `input` is the list of entries — `app.css` separately so Vite emits a CSS chunk, not just JS.
- `refresh: true` watches `routes/**`, `app/Http/{Controllers,Middleware}/**`, `app/View/Components/**`, and Blade files; full reload on change. Pass an array to override paths.
- Use `@/...` aliases instead of long `../../../` import paths.
- Add the Wayfinder Vite plugin (or a `composer dev` watcher) so generated route functions stay in sync during dev (§6).

⚠️ **Anti-pattern:** importing CSS only from JS (`import './app.css'` inside `app.tsx`) **without** also listing it as a Vite input. The CSS still ships, but `manifest.json` won't list it as a top-level entry — breaks SSR and preload links.

---

## 3. `resources/js/` layout

The conventional structure for an Inertia app:

```
resources/
  css/
    app.css                       # Tailwind / global styles
  js/
    app.tsx (or app.ts)           # Entry — boots Inertia
    ssr.tsx (or ssr.ts)           # Optional SSR entry
    bootstrap.ts                  # Axios defaults, Echo, etc.
    actions/                      # Wayfinder-generated controller actions (build artifact)
    routes/                       # Wayfinder-generated named routes (build artifact)
    Pages/                        # Inertia page components — match Inertia::render names
      Posts/Index.tsx, Posts/Show.tsx
    Components/                   # Reusable UI
    Layouts/                      # Persistent layouts
    Composables/ or hooks/        # useXxx() — Vue composables / React hooks
    types/                        # TS types (User, Post, shared shapes)
    lib/                          # framework-agnostic helpers (formatDate, ...)
```

**Rules:**
- One file per page component; folder structure mirrors route prefixes (`/posts` → `Pages/Posts/`).
- `Components/` = stack-pure UI; pages compose them.
- `Layouts/` = persistent layouts (header/sidebar). React: render in the page; Vue: assign via `defineOptions({ layout: AppLayout })`.
- Never hand-edit `actions/` or `routes/` — they're regenerated output (§6).
- ⚠️ **Anti-pattern:** putting page-level data fetching in `Components/`. Page components own props; child components receive them.

---

## 4. The entry file

Full React and Vue entries: `references/vite_boilerplate.md` §2.

**Rules:**
- `import.meta.glob` is lazy by default — pages are code-split per file. Don't pass `{ eager: true }` unless the app is tiny.
- `progress` enables the top-of-page progress bar; remove if you ship your own loader.
- Wayfinder needs no app-level plugin registration — generated functions are plain imports.
- ⚠️ **Anti-pattern:** registering globals (axios interceptors, error handlers) in `app.tsx`/`.ts`. Put them in `bootstrap.ts` so SSR and tests share them.

---

## 5. The Blade shell

A single Blade file (`resources/views/app.blade.php`) hosts the SPA. Full boilerplate: `references/vite_boilerplate.md` §3.

**Rules:**
- One `@vite([...])` call lists the same entries as `vite.config.js#input`.
- `<title inertia>` lets Inertia rewrite the title per page; `@inertiaHead` in `<head>`, `@inertia` in `<body>`.
- No route-injection directive: Wayfinder routes travel inside the bundle as modules, not as an inline `<script>` block.

⚠️ **Anti-pattern:** multiple `@vite` calls on the same page. Each adds its own preload/links — emit one combined call.

---

## 6. Wayfinder — typed routes and actions on the client

```bash
composer require laravel/wayfinder
php artisan wayfinder:generate        # writes resources/js/actions/ and resources/js/routes/
```

Wayfinder is the official first-party package used by the Laravel 12 starter kits. It generates TypeScript functions from your controllers and named routes — TypeScript-first and tree-shakeable: only the routes a component imports end up in the bundle.

### Usage in a component

```ts
// Controller action — mirrors the PHP namespace
import { show } from '@/actions/App/Http/Controllers/PostController';
show(post.id);          // { url: '/posts/1', method: 'get' }
show.url(post.id);      // '/posts/1'

// Named route — mirrors the route name
import { show } from '@/routes/posts';
router.visit(show(post.id).url);
```

### Keeping it in sync

The generated files go stale the moment a route or controller signature changes. Dev: the Wayfinder Vite plugin (`@laravel/vite-plugin-wayfinder`) or a `composer dev` watcher re-runs generation on PHP changes. CI/deploy: run `php artisan wayfinder:generate` **before** `npm run build`. Manual fallback: the Wayfinder sync workflow above.

**Gotchas:**
- ⚠️ The generated dir is a **build artifact**. Either gitignore it and regenerate in every environment, or commit it and regenerate on every route change — mixing the two produces "works on my machine" 404s.
- ⚠️ Forgetting to regenerate in CI before `npm run build` fails the build (missing imports) or, worse, ships stale URLs.
- ⚠️ After a route **rename**, old imports keep compiling against the stale generated file until you regenerate — regenerate first, then let `tsc --noEmit` / `vue-tsc --noEmit` surface every dead import.

Route generation is stable. Wayfinder's broader type-generation surface is newer — stick to route/action generation in reviews and don't build on APIs the package still marks experimental.

⚠️ **Anti-pattern:** hardcoding URL strings in JS (`'/posts/' + id`). Wayfinder exists exactly to avoid this — hardcoded paths break silently on route changes; typed imports break the type check instead.

---

## 7. Public env vars

Vite exposes only env vars prefixed with `VITE_`. Anything else stays server-side.

```bash
# .env
APP_URL=https://app.example.com
VITE_APP_URL="${APP_URL}"
```

Read on the client via `import.meta.env.VITE_APP_URL`.

**Rules:**
- ⚠️ **Anti-pattern:** secrets in `VITE_*`. They ship to every browser. API keys for client-side services (Stripe pk_, Pusher key, GA ID) are fine; server tokens never.
- `VITE_*` from `.env` are baked into the bundle at build time. Changing them requires a rebuild.

---

## 8. Code splitting & preloading

Inertia's page resolver already splits per page (§4). For component-level splitting:

```ts
const Heavy = lazy(() => import('@/Components/Heavy'));                       // React
const Heavy = defineAsyncComponent(() => import('@/Components/Heavy.vue'));  // Vue
```

- Code-split only what's actually heavy or rarely visited — see the decision table above.
- ⚠️ **Anti-pattern:** lazy-loading every component "to be safe" — small chunks add HTTP overhead and worsen cold load. Profile before splitting.

**Preloading:** `laravel-vite-plugin` automatically inserts `<link rel="modulepreload">` for entry chunks. For extra chunk grouping use `build.rollupOptions.output.manualChunks` — no manual `<link rel="preload">` in Blade. Route-level prefetch (Inertia v2) → `laravel-inertia` skill.

---

## 9. TypeScript posture

Greenfield default: **TypeScript on**. `.tsx` for React, `.ts` + `<script setup lang="ts">` for Vue. Full `tsconfig.json`: `references/vite_boilerplate.md` §4.

**Rules:**
- Type **shared shapes** under `resources/js/types/` (`User`, `Post`, `PageProps`).
- For Inertia page props, declare the shared global once:

  ```ts
  // resources/js/types/inertia.d.ts
  import type { PageProps as InertiaPageProps } from '@inertiajs/core';
  declare module '@inertiajs/core' {
    interface PageProps extends InertiaPageProps {
      auth: { user: { id: number; name: string } | null };
      flash: { success?: string; error?: string };
    }
  }
  ```

- Vue: run `vue-tsc --noEmit` in CI. React: `tsc --noEmit`. Wire into the static-analysis flow (`laravel-static-analysis`). The same check is what catches stale Wayfinder imports (§6).

⚠️ **Anti-pattern:** `any` for Inertia page props. Defeats the entire reason for TS in an SPA.

---

## 10. Build & deploy

```bash
php artisan wayfinder:generate   # generated files must exist before the bundle builds
npm run build                    # writes public/build/{assets,manifest.json,ssr/}
```

**The contract with Laravel:**
- Production must serve `public/build/manifest.json` for `@vite` to resolve hashed paths.
- `npm run build` must run **before** `php artisan optimize` / `config:cache`.
- Rolling deploys: write `public/build/` atomically (build to a temp dir then `mv`), or accept a brief window of mismatched manifest vs assets.

⚠️ **Anti-pattern:** committing `public/build/` to git. Build artifacts are CI/deploy output.

---

## 11. CSP & inline scripts

Inertia's page payload lives in the `data-page` attribute of the mount `<div>` — no inline `<script>`, no CSP impact. Wayfinder routes are module imports inside the bundle — also no inline script, so no route-injection exception is needed in `script-src`.

For strict CSP:

- Vite: `<script type="module">` requires `script-src 'self'` plus the dev server origin (dev only). Use a nonce in prod for any inline JS you add yourself.
- For the broader CSP/headers picture (X-Frame-Options, HSTS, frame-ancestors), see the `laravel-security` skill.

---

## Rules & anti-patterns — consolidated

| Smell | Section | Detection |
|---|---|---|
| CSS imported from JS but missing from `vite.config.js#input` | §2 | review `vite.config.js` |
| Page-level data fetching inside `Components/` | §3 | review `Components/**` for `router.visit` / page-level loads |
| Hand-edited files under `resources/js/{actions,routes}/` | §3 | diff against fresh `wayfinder:generate` output |
| Globals registered in entry file instead of `bootstrap.ts` | §4 | review `app.tsx` / `app.ts` |
| Multiple `@vite([...])` calls on the same page | §5 | grep `@vite\(` in views |
| Hardcoded URL strings (`'/posts/' + id`) in JS | §6 | grep `["']/api\|["']/[a-z]+/` in `resources/js/` |
| Stale Wayfinder output after a route rename | §6 | run `wayfinder:generate` + `tsc --noEmit`; CI missing the generate step before `npm run build` |
| Secrets in `VITE_*` env vars | §7 | grep `VITE_.*SECRET\|VITE_.*KEY` |
| Lazy-loading every component | §8 | review `lazy(`/`defineAsyncComponent` density |
| `any` for Inertia page props | §9 | grep `: any` in pages and shared types |
| `public/build/` committed to git | §10 | check `.gitignore` |
| Stale `public/hot` after stopping `npm run dev` | Workflows | check `public/hot` exists in dev FS |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| HMR not reloading | Dev server not reachable from the browser host; wrong `APP_URL` | Dev-server checklist (Workflows) |
| "Unable to locate file in Vite manifest" | Entry in `@vite([...])` not listed in `vite.config.js#input`, or build never ran | Align entries; `npm run build` |
| Asset 404 after deploy | `manifest.json` missing/stale; `optimize` ran before build | Build before optimize; atomic `mv` of `public/build/` |
| Dev banner shows but assets 404 | Stale `public/hot` file | Delete `public/hot` |
| TS errors on `@/actions/...` or `@/routes/...` imports | Wayfinder output missing or stale | `php artisan wayfinder:generate`, then re-run type check |
| Blank page, console shows blocked module script | CSP `script-src` missing `'self'` or dev origin | §11 |

---

## Reference routing

| Need | Load |
|---|---|
| Full `vite.config.js` (React and Vue variants), app entry files, Blade shell, `tsconfig.json` | `references/vite_boilerplate.md` |
| Manual chunking, Docker/HTTPS dev server, Wayfinder build integration, slow builds, Vite version notes, SSR build config | `references/vite_advanced.md` |

---

## Cross-references

| Topic | Where |
|---|---|
| Inertia protocol (props, partials, defer, polling, prefetching) | `laravel-inertia` skill |
| React 19 components, hooks, `useForm` | `laravel-role-react` |
| Vue 3.5 components, composables, `useForm` | `laravel-role-vue` |
| `tsc --noEmit` / `vue-tsc` in CI flow | `laravel-static-analysis` skill |
| WCAG / ARIA in components | `laravel-a11y` skill |
| Auth state propagated via shared data | `laravel-auth` skill + `laravel-inertia` §4 |
| CSP, X-Frame-Options, HSTS | `laravel-security` skill |
| Octane interaction with Vite dev server | `laravel-role-devops` |
