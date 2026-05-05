---
name: laravel-frontend
description: Client-side wiring for Laravel 12 — Vite 6 (laravel-vite-plugin, dev server, HMR, manifest), resources/js layout (Pages, Components, Layouts, app entry), Ziggy (named routes on the client), public env vars (VITE_*), code splitting and lazy chunks, asset preloading, TypeScript posture, build artifacts, and CSP-friendly bundling. Stack-neutral, consumed by the laravel-react, laravel-vue, and code-review agents.
---

# Laravel Frontend — Vite, Ziggy, asset wiring

The plumbing between Laravel and the client bundle. Stack-neutral — covers Vite config, asset pipeline, route helpers, and `resources/js` conventions used identically by React and Vue projects. Component/framework specifics live in `laravel-react` and `laravel-vue`; the Inertia protocol lives in `laravel-inertia`.

## When to use this skill

- Configuring Vite (`vite.config.js`, plugins, aliases, code splitting)
- Laying out `resources/js/` (Pages, Components, Layouts, Composables, entry file)
- Wiring **Ziggy** so the client can call `route('posts.show', id)`
- Exposing env vars to the client (`VITE_*`)
- Debugging dev-server / HMR issues, manifest mismatches, missing `@vite` directives
- Build/deploy concerns (`npm run build`, hashed assets, `public/build/manifest.json`)
- Reviewing `package.json`, `tsconfig.json`, `vite.config.js` in PRs

## When NOT to use

| Topic | Use instead |
|---|---|
| React 19 components, hooks, `useForm` | `laravel-react` |
| Vue 3.5 components, composables, `useForm` | `laravel-vue` |
| Inertia protocol (props, partials, defer) | `laravel-inertia` |
| WCAG / ARIA in components | `laravel-a11y` |
| Pest assertions on rendered HTML | `laravel-qa` |
| Octane/FrankenPHP runtime concerns | (devops agent) |

## Stack assumptions

- Laravel 12 with `laravel/vite-plugin` v1.x (Vite 6)
- Node 20+ (LTS); npm or pnpm
- TypeScript by default in greenfield (`.tsx` / `.ts`); plain JS still supported
- `tightenco/ziggy` v2.x for named routes on the client
- Inertia 2 (most apps) — the layout below assumes Inertia. SPA-without-Inertia and pure Blade are noted where they diverge.

---

## 1. The wiring in one paragraph

The Laravel side declares "include these JS/CSS entries" via the `@vite` Blade directive. In dev, the directive points at the Vite dev server (HMR + on-the-fly transforms); in prod, it reads `public/build/manifest.json` and emits hashed `<script>` / `<link>` tags. Routes/controllers stay PHP. Page components live under `resources/js/Pages/` and are mounted by the entry file (`resources/js/app.tsx` or `app.ts`). **Ziggy** publishes Laravel's named routes as a JS object so the client can call `route('posts.show', id)` instead of hardcoding URLs.

---

## 2. `vite.config.js`

### 2.1 React project

```js
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
    plugins: [
        laravel({
            input: ['resources/css/app.css', 'resources/js/app.tsx'],
            ssr: 'resources/js/ssr.tsx',
            refresh: true,                          // refresh Blade/route changes during dev
        }),
        react(),
    ],
    resolve: {
        alias: { '@': path.resolve(__dirname, 'resources/js') },
    },
});
```

### 2.2 Vue project

```js
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import vue from '@vitejs/plugin-vue';
import path from 'node:path';

export default defineConfig({
    plugins: [
        laravel({
            input: ['resources/css/app.css', 'resources/js/app.ts'],
            ssr: 'resources/js/ssr.ts',
            refresh: true,
        }),
        vue({ template: { transformAssetUrls: { base: null, includeAbsolute: false } } }),
    ],
    resolve: {
        alias: { '@': path.resolve(__dirname, 'resources/js') },
    },
});
```

**Rules:**
- `input` is the list of entries — `app.css` separately so Vite emits a CSS chunk, not just JS.
- `refresh: true` watches `routes/**`, `app/Http/{Controllers,Middleware}/**`, `app/View/Components/**`, and Blade files; full reload on change. Pass an array to override paths.
- Use `@/...` aliases instead of long `../../../` import paths.

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
    Pages/                        # Inertia page components — match Inertia::render names
      Posts/
        Index.tsx
        Show.tsx
    Components/                   # Reusable UI
      Button.tsx
      Modal.tsx
    Layouts/                      # Persistent layouts
      AppLayout.tsx
    Composables/                  # Vue only — useXxx() composables
    hooks/                        # React only — useXxx() hooks
    types/                        # TS types (User, Post, shared shapes)
    lib/                          # framework-agnostic helpers (formatDate, ...)
```

**Rules:**
- One file per page component; folder structure mirrors route prefixes (`/posts` → `Pages/Posts/`).
- `Components/` = stack-pure UI; pages compose them.
- `Layouts/` = persistent layouts (header/sidebar). React: render in the page; Vue: assign via `defineOptions({ layout: AppLayout })`.
- ⚠️ **Anti-pattern:** putting page-level data fetching in `Components/`. Page components own props; child components receive them.

---

## 4. The entry file

### 4.1 React (`resources/js/app.tsx`)

```tsx
import './bootstrap';
import '../css/app.css';

import { createInertiaApp } from '@inertiajs/react';
import { createRoot } from 'react-dom/client';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';

createInertiaApp({
    title: (title) => `${title} · MyApp`,
    resolve: (name) =>
        resolvePageComponent(`./Pages/${name}.tsx`, import.meta.glob('./Pages/**/*.tsx')),
    setup: ({ el, App, props }) => {
        createRoot(el).render(<App {...props} />);
    },
    progress: { color: '#4F46E5' },
});
```

### 4.2 Vue (`resources/js/app.ts`)

```ts
import './bootstrap';
import '../css/app.css';

import { createInertiaApp } from '@inertiajs/vue3';
import { createApp, h } from 'vue';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';
import { ZiggyVue } from 'ziggy-js/vue';

createInertiaApp({
    title: (title) => `${title} · MyApp`,
    resolve: (name) =>
        resolvePageComponent(`./Pages/${name}.vue`, import.meta.glob('./Pages/**/*.vue')),
    setup: ({ el, App, props, plugin }) => {
        createApp({ render: () => h(App, props) })
            .use(plugin)
            .use(ZiggyVue)
            .mount(el);
    },
    progress: { color: '#4F46E5' },
});
```

**Rules:**
- `import.meta.glob` is **eager-by-default false** — pages are code-split per file. Don't pass `{ eager: true }` unless the app is tiny.
- `progress` enables the top-of-page progress bar; remove if you ship your own loader.
- ⚠️ **Anti-pattern:** registering globals (axios interceptors, error handlers) in `app.tsx`/`.ts`. Put them in `bootstrap.ts` so SSR and tests share them.

---

## 5. The Blade shell

A single Blade file (`resources/views/app.blade.php`) hosts the SPA:

```blade
<!doctype html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title inertia>{{ config('app.name') }}</title>

    @routes                                              {{-- Ziggy: named routes as JS object --}}
    @vite(['resources/css/app.css', 'resources/js/app.tsx'])
    @inertiaHead                                         {{-- title, head meta from page components --}}
</head>
<body>
    @inertia                                             {{-- mount target — <div id="app" data-page="..."> --}}
</body>
</html>
```

**Rules:**
- One `@vite([...])` call lists the same entries as `vite.config.js#input`.
- `@routes` (Ziggy) and `@vite` order: `@routes` **before** `@vite` so the Ziggy global is defined before the JS bundle reads it.
- `<title inertia>` lets Inertia rewrite the title per page.

⚠️ **Anti-pattern:** multiple `@vite` calls on the same page. Each adds its own preload/links — emit one combined call.

---

## 6. Ziggy — named routes on the client

```bash
composer require tightenco/ziggy
```

Ziggy publishes Laravel's named routes as a JS function `route(name, params)`. Two delivery modes:

### 6.1 Inline via `@routes` (default)

The `@routes` Blade directive renders a `<script>` block that defines `window.Ziggy`. Smallest setup; routes are inlined on every request.

```blade
@routes                       {{-- all named routes for the current user --}}
@routes('admin')              {{-- only routes in the 'admin' route group/middleware --}}
@routes(nonce: 'abc123')      {{-- CSP nonce passthrough --}}
```

### 6.2 Generated file (better for SSR / CSP)

```bash
php artisan ziggy:generate              # writes resources/js/ziggy.js
```

```ts
// app.ts / app.tsx
import { Ziggy } from './ziggy';
window.Ziggy = Ziggy;
```

Run `ziggy:generate` in `package.json#scripts.build` so prod builds always have a fresh file.

### 6.3 Usage on the client

```ts
// React
import { route } from 'ziggy-js';
router.visit(route('posts.show', { post: 123 }));

// Vue (with ZiggyVue plugin)
router.visit(route('posts.show', { post: 123 }));
```

**Rules:**
- Filter Ziggy's route list — exposing internal/admin routes leaks attack surface. Use `'except'` / `'only'` in `config/ziggy.php` or the `@routes('group')` form.
- For CSP environments: use the generated file (no inline script) or pass a nonce.

⚠️ **Anti-pattern:** hardcoding URL strings in JS (`'/posts/' + id`). Ziggy exists exactly to avoid this — broken on route changes.

---

## 7. Public env vars

Vite exposes only env vars prefixed with `VITE_`. Anything else stays server-side.

```bash
# .env
APP_URL=https://app.example.com
VITE_APP_URL="${APP_URL}"
VITE_PUSHER_APP_KEY=
VITE_PUSHER_HOST=
```

```ts
const url = import.meta.env.VITE_APP_URL;
```

**Rules:**
- ⚠️ **Anti-pattern:** secrets in `VITE_*`. They ship to every browser. API keys for client-side services (Stripe pk_, Pusher key, GA ID) are fine; server tokens never.
- `VITE_*` from `.env` are baked into the bundle at build time. Changing them requires a rebuild.

---

## 8. Code splitting & dynamic imports

Inertia's page resolver already splits per-page (§4). For component-level splitting:

```ts
// React
const Heavy = lazy(() => import('@/Components/Heavy'));

// Vue
import { defineAsyncComponent } from 'vue';
const Heavy = defineAsyncComponent(() => import('@/Components/Heavy.vue'));
```

Vite emits a separate chunk and the framework loads it on demand.

**Rules:**
- Code-split only what's actually heavy or rarely visited (chart libs, rich-text editors, admin-only screens).
- ⚠️ **Anti-pattern:** lazy-loading every component "to be safe" — small chunks add HTTP overhead and worsen cold load. Profile before splitting.

---

## 9. Preloading & prefetching

The `laravel-vite-plugin` automatically inserts `<link rel="modulepreload">` for the entry chunks. For route-level prefetch (Inertia v2), see `laravel-inertia` §7.

For server-pushed preloads of additional chunks, configure Vite's `build.rollupOptions.output.manualChunks` and let the plugin handle the manifest — no manual `<link rel="preload">` needed in Blade.

---

## 10. TypeScript posture

Greenfield default: **TypeScript on**. `.tsx` for React, `.ts` + `<script setup lang="ts">` for Vue.

```jsonc
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "jsx": "react-jsx",                 // remove for Vue
    "baseUrl": ".",
    "paths": { "@/*": ["resources/js/*"] },
    "types": ["vite/client", "ziggy-js"]
  },
  "include": ["resources/js/**/*", "resources/js/**/*.vue"]
}
```

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

- Vue: run `vue-tsc --noEmit` in CI. React: `tsc --noEmit`. Wire into the static-analysis flow (`laravel-static-analysis`).

⚠️ **Anti-pattern:** `any` for Inertia page props. Defeats the entire reason for TS in an SPA.

---

## 11. Build & deploy

```bash
npm run build                  # writes public/build/{assets,manifest.json,ssr/}
php artisan ziggy:generate     # if using the generated file mode (§6.2)
```

**The contract with Laravel:**
- Production must serve `public/build/manifest.json` for `@vite` to resolve hashed paths.
- `npm run build` must run **before** `php artisan optimize` / `config:cache`.
- Rolling deploys: write `public/build/` atomically (build to a temp dir then `mv`), or accept a brief window of mismatched manifest vs assets.

⚠️ **Anti-pattern:** committing `public/build/` to git. Build artifacts are CI/deploy output.

---

## 12. Dev server checklist

When `@vite` shows the "running in dev mode" banner but assets 404:

1. Is `npm run dev` running on the same host you're browsing from?
2. Is `APP_URL` correct? The Vite plugin uses it to compute the dev server URL.
3. Custom `VITE_DEV_SERVER_URL` set? Useful for Docker / VM setups.
4. Stale `public/hot` file? It signals "use dev server"; delete after stopping `npm run dev`.

When prod assets 404:

1. Did `npm run build` actually run?
2. Is `public/build/manifest.json` present and readable?
3. Did the deploy script clear `bootstrap/cache/` before `optimize`?
4. CSP blocking `<script>`? Check the inline Ziggy block (§6) — switch to generated mode if so.

---

## 13. CSP & inline scripts

Inertia + Ziggy default setup uses **two** inline scripts: the `<div id="app" data-page="...">` payload and the `@routes` Ziggy block. Neither violates CSP because they're inline `data-*` attributes (not `<script>`) — except `@routes`, which is a real `<script>` tag.

For strict CSP:

- Ziggy: switch to `php artisan ziggy:generate` (§6.2), import as module.
- Inertia: the page payload is `data-page` (no script tag), so no CSP impact.
- Vite: `<script type="module">` requires `script-src 'self'` plus the dev server origin (dev only). Use a nonce in prod for any inline JS.

For the broader CSP/headers picture (X-Frame-Options, HSTS, frame-ancestors), see the `laravel-security` skill.

---

## 14. Anti-patterns — consolidated

| Smell | Section | Detection |
|---|---|---|
| CSS imported from JS but missing from `vite.config.js#input` | §2 | review `vite.config.js` |
| Page-level data fetching inside `Components/` | §3 | review `Components/**` for `router.visit` / page-level loads |
| Globals registered in entry file (axios, error handlers) instead of `bootstrap.ts` | §4 | review `app.tsx` / `app.ts` |
| Multiple `@vite([...])` calls on the same page | §5 | grep `@vite\(` in views |
| Hardcoded URL strings (`'/posts/' + id`) in JS | §6.3 | grep `["']/api\|["']/[a-z]+/` in `resources/js/` |
| Secrets in `VITE_*` env vars | §7 | grep `VITE_.*SECRET\|VITE_.*KEY` |
| Lazy-loading every component | §8 | review `lazy(`/`defineAsyncComponent` density |
| `any` for Inertia page props | §10 | grep `: any` in pages and shared types |
| `public/build/` committed to git | §11 | check `.gitignore` |
| Stale `public/hot` after stopping `npm run dev` | §12 | check `public/hot` exists in dev FS |

---

## 15. Cross-references

| Topic | Skill |
|---|---|
| Inertia protocol (props, partials, defer, polling) | `laravel-inertia` |
| React 19 components, hooks, `useForm` | `laravel-react` |
| Vue 3.5 components, composables, `useForm` | `laravel-vue` |
| `tsc --noEmit` / `vue-tsc` in CI flow | `laravel-static-analysis` |
| WCAG / ARIA in components | `laravel-a11y` |
| Auth state propagated via shared data | `laravel-auth` + `laravel-inertia` §4 |
| CSP, X-Frame-Options, HSTS | `laravel-security` |
| Octane interaction with Vite dev server | (devops agent) |
