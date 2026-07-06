# Vite advanced — chunking, containers, Wayfinder builds, performance

Deep-dive companion to `laravel-frontend` SKILL.md. Loaded on demand for manual chunking,
Docker/HTTPS dev-server setups, Wayfinder build integration, and slow-build diagnosis.
Baseline config lives in `references/vite_boilerplate.md` — this file only covers what
goes beyond it.

## 1. Manual chunking

### 1.1 What you already get for free

Before adding any `manualChunks` config, know what the default setup already does:

- **Per-page splitting.** `resolvePageComponent` + a lazy `import.meta.glob` (the default
  entry, `vite_boilerplate.md` §2) makes every Inertia page its own chunk. Visiting
  `/posts` downloads `Posts/Index-[hash].js`, nothing else.
- **Shared-module hoisting.** Rollup/Rolldown automatically extracts modules imported by
  two or more page chunks into shared chunks, so a component used by five pages is not
  duplicated five times.
- **Preload tags.** `laravel-vite-plugin` emits `<link rel="modulepreload">` for the entry
  and its static imports — no manual `<link>` tags in Blade.

If page navigation feels fine and no chunk is disproportionately large, stop here.

### 1.2 When manual chunks earn their keep

The one high-value case for an Inertia app: **a stable vendor/framework chunk**. The
framework (React or Vue, Inertia, axios) changes only when you bump dependencies, while
app code changes every deploy. Splitting them means returning users keep the framework
chunk in HTTP cache across deploys:

```js
// vite.config.js
export default defineConfig({
    // ...plugins
    build: {
        rollupOptions: {
            output: {
                manualChunks: {
                    framework: ['react', 'react-dom', '@inertiajs/react'],
                    // Vue variant: ['vue', '@inertiajs/vue3']
                },
            },
        },
    },
});
```

A second legitimate case: pinning one **heavy library used by several pages** (a chart
lib, an editor) into its own named chunk so its cache lifetime is decoupled from page code.
Prefer component-level `lazy()` / `defineAsyncComponent` first (SKILL.md §8) — reach for
`manualChunks` only when the library is shared across enough pages that lazy imports
would duplicate it or produce awkward loading states.

### 1.3 When manual chunks hurt

- **Over-splitting creates request waterfalls.** A page chunk that imports from three
  hand-carved vendor chunks can't execute until all of them arrive; each extra chunk is
  another request, another cache entry, another point of failure. Dozens of 2–10 KB chunks
  are strictly worse than a few 50–150 KB ones.
- **A function-form `manualChunks` that routes "everything from node_modules" into one
  `vendor` chunk** couples every dependency's cache lifetime together and can pull
  lazy-only dependencies into the eager path — the opposite of what page splitting bought
  you. Enumerate explicit package lists (object form) instead.
- **Circular chunk imports.** Aggressive function-form splitting can produce chunks that
  import each other, which surfaces as "Cannot access X before initialization" at runtime.
  If you see this, delete the manualChunks config and re-add groups one at a time.

Rule of thumb: measure first (§4.3), add one group, measure again. `manualChunks` with no
measurement attached is cargo cult.

## 2. Dev server in containers and VMs

The failure mode is always the same: the dev server binds inside the container/VM, but the
**browser** — which runs on the host — must be able to reach it, and the URLs printed into
the page must be resolvable *from the host*.

### 2.1 Bind + advertise

```js
// vite.config.js
export default defineConfig({
    // ...plugins
    server: {
        host: true,          // bind 0.0.0.0 so traffic from outside the container arrives
        hmr: {
            host: 'localhost',   // what the BROWSER should connect to for the WS
        },
    },
});
```

- `server.host: true` — listen on all interfaces. Without it, Vite binds `localhost`
  *inside* the container and the host's port mapping forwards to nothing.
- `server.hmr.host` — hostname baked into the HMR websocket URL the client uses. For
  Docker with `-p 5173:5173` (and Sail on WSL2) this is `localhost`.
- `server.hmr.clientPort` — only needed when the **outside** port differs from the inside
  one (e.g. `-p 3000:5173`, or a reverse proxy terminating on 443): set `clientPort` to the
  port the browser sees, leave `port` as what Vite binds.
- Expose the port in `docker-compose.yml` / Sail (`VITE_PORT` for Sail) and remember the
  `public/hot` file the plugin writes contains the dev-server URL — if pages load but
  scripts 404, read `public/hot` and check that URL works *from the host browser*.

### 2.2 HTTPS local dev

If the app is served over HTTPS (Valet `secure`, Herd secured site), the browser refuses
mixed-content requests to an `http://` dev server.

- **Valet / Herd:** `laravel-vite-plugin` auto-detects the TLS certificate generated for
  the site — zero config when the host matches the project directory name. If it doesn't,
  point the plugin at the right host: `laravel({ detectTls: 'my-app.test' })`.
- **Any other server:** provide the cert yourself:

  ```js
  server: {
      host: 'my-app.test',
      hmr: { host: 'my-app.test' },
      https: {
          key: fs.readFileSync('/path/to/my-app.test.key'),
          cert: fs.readFileSync('/path/to/my-app.test.crt'),
      },
  },
  ```

- **No trusted cert available:** `@vitejs/plugin-basic-ssl` generates a self-signed one;
  you must visit the dev-server URL once and accept the browser warning or the HMR
  websocket silently fails.

There is no bare `--https` flag doing this for you in a Laravel app — TLS comes either
from `detectTls` (Valet/Herd certs) or an explicit `server.https` block.

### 2.3 CORS pitfalls

The dev server serves modules cross-origin (app on `https://my-app.test`, assets from
`http://localhost:5173`), so CORS applies. The Laravel plugin pre-allows `localhost`,
`127.0.0.1`, `::1`, `*.test`, `*.localhost`, and the project's `APP_URL`. Requests break
when:

- The browsing origin isn't any of those — e.g. a `.local` domain, a LAN IP
  (`http://192.168.x.x`), or an ngrok/Expose tunnel. Fix with explicit origins:

  ```js
  server: {
      cors: {
          origin: ['https://my-app.local', /^https?:\/\/192\.168\.\d+\.\d+(:\d+)?$/],
      },
  },
  ```

- `APP_URL` doesn't match the URL actually in the address bar — the plugin allowlists
  what `.env` says, not what you typed. Align them before reaching for `server.cors`.
- ⚠️ **Never ship `server.cors: true`** (allow any origin) as a "fix" — any website the
  developer visits can then read source modules from the dev server. Enumerate origins.

## 3. Wayfinder build integration

Usage of the generated functions and sync gotchas live in SKILL.md §6. This section is the
build-pipeline side.

### 3.1 Dev: the Vite plugin

```js
import { wayfinder } from '@laravel/vite-plugin-wayfinder';

plugins: [laravel({ /* ... */ }), wayfinder()],
```

`@laravel/vite-plugin-wayfinder` (still 0.x — pin it) runs `php artisan wayfinder:generate`
when watched PHP files (routes, controllers) change, so `resources/js/{actions,routes}/`
never drifts during dev. Options when the defaults don't fit:

```js
wayfinder({
    command: 'herd php artisan wayfinder:generate',  // custom artisan invocation (Sail: 'vendor/bin/sail artisan ...')
    patterns: ['app/**/*.php', 'routes/**/*.php'],   // what to watch
    routes: true, actions: true, formVariants: true, // toggle output groups
    path: 'resources/js',                            // where generated files live
})
```

In containers, `command` must be runnable *where Vite runs* — if Vite runs on the host but
PHP lives in the container, point `command` at `sail artisan` / `docker compose exec`.

### 3.2 CI/deploy: ordering rule

The generated files are imports of the bundle, so generation is a **build dependency**:

```bash
composer install --no-dev ...
php artisan wayfinder:generate    # 1. BEFORE the bundle builds
npm ci && npm run build           # 2. bundle now resolves @/actions and @/routes
php artisan optimize              # 3. after assets exist
```

Inverting 1 and 2 fails the build on missing imports (good case) or bundles stale URLs
from a committed copy (bad case). The Vite plugin does **not** replace this step — it only
watches during `dev`; `npm run build` does not regenerate anything.

### 3.3 Caching the generated output

The output is a pure function of routes + controller signatures, so it caches cleanly:

- **Gitignored output (recommended):** regenerate in every environment; in CI, key a cache
  on a hash of `routes/**` + `app/Http/Controllers/**` if generation time ever matters
  (it's usually seconds — don't cache prematurely).
- **Committed output:** CI should run `wayfinder:generate` and fail on a dirty diff —
  that's the guard against "forgot to regenerate" PRs:

  ```bash
  php artisan wayfinder:generate
  git diff --exit-code resources/js/actions resources/js/routes
  ```

Whichever mode, `tsc --noEmit` / `vue-tsc --noEmit` after generation is what actually
catches stale imports (SKILL.md Wayfinder sync workflow).

## 4. Build performance

### 4.1 Dev-server warmup

Vite transforms files on demand, so the first hit on a deep import chain is slow. Pre-warm
the hot paths:

```js
server: {
    warmup: {
        clientFiles: ['resources/js/app.tsx', 'resources/js/Layouts/**/*'],
    },
},
```

Only list genuinely hot files (entry, persistent layout, ubiquitous components). Warming
everything just moves the cost to startup.

### 4.2 Dependency pre-bundling (`optimizeDeps`)

Vite pre-bundles bare imports from `node_modules` at dev-server start. Two interventions
are worth knowing:

- **`optimizeDeps.include`** — dependencies only reachable through dynamic imports (lazy
  pages, conditional imports) are discovered late, causing mid-session "new dependencies
  optimized, reloading" full reloads. Add the offenders to `include` so they're
  pre-bundled up front.
- **`optimizeDeps.exclude`** — for linked local packages you're editing (monorepo,
  `npm link`), exclude them so changes aren't served from the stale pre-bundle cache.

When the pre-bundle cache itself seems corrupted (imports resolving to old versions),
`rm -rf node_modules/.vite` and restart — don't chase ghosts.

### 4.3 Diagnosing a slow or bloated build

- `vite build --profile` starts an inspector session; `Ctrl/Cmd+P` in Chrome DevTools →
  record → find which plugin or transform dominates. Typical culprits: a misconfigured
  plugin transforming `node_modules`, or type-checking wired into the build (keep
  `tsc --noEmit` a separate CI step, never a Vite plugin in the build).
- `npx vite-bundle-visualizer` renders a treemap of the production bundle — this is the
  measurement step §1 requires before and after any `manualChunks` change. Look for one
  library appearing inside multiple page chunks (candidate for a manual group) or a giant
  eager chunk (candidate for lazy import).
- Rolldown-powered Vite (v8, §5) makes the *bundling* fast; if builds are still slow
  there, the time is in plugins — profile, don't guess.

## 5. Version notes — Vite 5 → 6 → 7 → 8

Verified against vite.dev and npm as of mid-2026. The pairing that matters in a Laravel
app is the plugin major, since it pins the Vite major:

| `laravel-vite-plugin` | Vite | Node | Notes for Laravel apps |
|---|---|---|---|
| 1.x | 5 / 6 | 18+ | Laravel 11/12 default for a long stretch |
| 2.x | 7 | 20.19+ / 22.12+ | ESM-only Vite; Node 18 dropped |
| 3.x | 8 | 20.19+ / 22.12+ | Rolldown bundler |

What each major actually changed for a Laravel app:

- **Vite 6 (Nov 2024):** introduced the experimental Environment API — plumbing for
  frameworks/plugin authors, **not something an app's `vite.config.js` should touch**.
  App-level migration from 5 was near zero.
- **Vite 7 (Jun 2025):** ESM-only distribution; Node 18 support dropped; default browser
  target moved to `'baseline-widely-available'`; removed the long-deprecated
  `splitVendorChunkPlugin` (if an old config imports it, delete it — §1.2 is the
  replacement) and Sass legacy API. Requires `laravel-vite-plugin` 2.x.
- **Vite 8 (Mar 2026):** Rolldown (Rust) replaces esbuild+Rollup as the single bundler —
  headline is build speed, with a compatibility layer for Rollup-based plugin options
  (`build.rollupOptions.output.manualChunks` from §1 keeps working). `@vitejs/plugin-react`
  v6 swaps Babel for Oxc. Environment API still not stable. Requires
  `laravel-vite-plugin` 3.x.

Upgrade rule: bump `laravel-vite-plugin` and `vite` **together** to the paired majors,
run the "After changing vite.config" workflow from SKILL.md, and read the official
migration guide for the Vite major — don't trust a model's memory (including this file)
over `vite.dev/guide/migration` for anything newer.

## 6. SSR-specific Vite config

The runtime side (SSR server, `inertia:start-ssr`, hydration) belongs to the
`laravel-inertia` skill's SSR reference. The Vite side is small:

```js
laravel({
    input: ['resources/css/app.css', 'resources/js/app.tsx'],
    ssr: 'resources/js/ssr.tsx',       // separate SSR entry (vite_boilerplate.md §1)
    refresh: true,
}),
```

```jsonc
// package.json — build both bundles
"build": "vite build && vite build --ssr"
```

- `vite build --ssr` emits a Node bundle to `bootstrap/ssr/` — deploy it alongside the
  app; it is as much a build artifact as `public/build/`.
- **`ssr.noExternal`**: by default the SSR build leaves `node_modules` packages external
  (loaded by Node at runtime). Packages that ship untranspiled ESM, raw `.vue`/`.svelte`
  files, or CSS imports crash Node with `ERR_UNKNOWN_FILE_EXTENSION` / `Unknown file
  extension ".css"` / `Cannot use import statement outside a module`. Force those through
  the bundle:

  ```js
  ssr: {
      noExternal: ['some-ui-kit', /^@fancy-scope\//],
  },
  ```

  Add packages one at a time as errors name them — `noExternal: true` (bundle everything)
  is a last resort that slows the SSR build and hides which dependency was broken.
- Guard browser globals: code reached by the SSR entry must not touch `window`/`document`
  at module scope. Fix the module or lazy-import it client-side; `noExternal` won't save
  you from that one.

## 7. Anti-patterns

| Anti-pattern | Why it's wrong | Rule |
|---|---|---|
| Hand-editing `public/build/manifest.json` | Regenerated on every build; hand edits vanish and desync hashes → 404s | Fix `vite.config.js#input` / `@vite` instead (SKILL.md §2, §10) |
| Committing `public/hot` | Every environment then thinks a dev server is running — prod loads assets from `localhost:5173` | Gitignore it; delete stale copies (SKILL.md Workflows) |
| Setting Vite `base` manually behind a CDN | Fights the plugin's manifest-driven URLs; half the URLs get the prefix, half don't | Use `ASSET_URL` in `.env` — the plugin derives the base (SKILL.md §10) |
| Secrets in `VITE_*` vars | Baked into the public bundle, readable by anyone | Server-only vars stay unprefixed (SKILL.md §7) |
| `manualChunks` routing all of `node_modules` into one `vendor` chunk | Couples all dependency cache lifetimes; drags lazy-only deps into the eager path | Explicit package lists, measured (§1) |
| `server.cors: true` to silence a CORS error | Any website can read your source through the dev server | Enumerate origins (§2.3) |
| Type-checking inside the Vite build | Multiplies build time on every run | `tsc --noEmit` / `vue-tsc` as a separate CI step (§4.3, `laravel-static-analysis`) |
