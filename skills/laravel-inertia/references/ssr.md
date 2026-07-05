# Inertia SSR — Setup, supervision, debugging

Server-side rendering for Inertia 2 with Laravel 12. Loaded when the agent is enabling SSR, debugging hydration mismatches, supervising the SSR process under Octane / FrankenPHP, or wiring SSR into the deploy pipeline.

## 1. When SSR earns its keep

| Reason | SSR helps? |
|---|---|
| SEO for crawler-indexed marketing pages | yes |
| First Contentful Paint on slow networks | yes |
| Social-share preview cards (OG / Twitter) | yes — hydrate before social bots fetch |
| Authenticated dashboard performance | rarely — bot indexing is irrelevant; FCP gain is marginal vs Inertia's normal SPA flow |
| Client devices with no JS | partial — SSR delivers HTML, but Inertia still needs JS for navigation |

⚠️ **Anti-pattern:** enabling SSR for an authenticated-only app to "make it faster". The SSR Node process adds ops surface area (supervisor, memory budget, restart on deploy) without real user-facing payoff.

## 2. The architecture

```
Browser  ──HTTP──▶  Laravel (Octane / FPM)
                      │
                      ├─ first request? ──▶  HTTP POST  ──▶  Node SSR server (:13714)
                      │                                          │
                      │                                          ▼
                      │                                   Renders page component to HTML
                      │                                   Returns { head, body }
                      │                  ◀──────────────────────┘
                      │
                      ▼
                  Blade shell rendered with SSR'd HTML inside @inertia
                      │
Browser  ◀── HTML ────┘
        │
        ▼
   JS bundle loads, Inertia hydrates the existing DOM, takes over
```

**Two processes in production:**
1. **Laravel** (Octane / FrankenPHP / FPM) — receives the request, calls the SSR server over loopback HTTP, renders the Blade shell with the SSR output, returns full HTML.
2. **Node SSR** — long-running process listening on `127.0.0.1:13714` that imports the same page components and renders them to HTML strings.

Both must be running for SSR to work. If the Node process is down, Inertia's PHP adapter falls back to client-only rendering — pages still work but ship blank shells with `data-page` payloads.

## 3. Vite SSR build

The client and SSR builds share the same page components but emit different bundles.

### 3.1 Entry files

```
resources/js/
  app.tsx              # client entry (boots in browser)
  ssr.tsx              # SSR entry (runs in Node)
  Pages/...            # shared by both
```

**`resources/js/ssr.tsx` (React):**
```tsx
import { createInertiaApp } from '@inertiajs/react';
import createServer from '@inertiajs/react/server';
import ReactDOMServer from 'react-dom/server';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';

const port = 13714;

createServer((page) =>
  createInertiaApp({
    page,
    render: ReactDOMServer.renderToString,
    title: (title) => `${title} · MyApp`,
    resolve: (name) =>
      resolvePageComponent(`./Pages/${name}.tsx`, import.meta.glob('./Pages/**/*.tsx')),
    setup: ({ App, props }) => <App {...props} />,
  }),
  port,
);
```

**`resources/js/ssr.ts` (Vue):**
```ts
import { createInertiaApp } from '@inertiajs/vue3';
import createServer from '@inertiajs/vue3/server';
import { renderToString } from 'vue/server-renderer';
import { createSSRApp, h } from 'vue';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';

const port = 13714;

createServer((page) =>
  createInertiaApp({
    page,
    render: renderToString,
    title: (title) => `${title} · MyApp`,
    resolve: (name) =>
      resolvePageComponent(`./Pages/${name}.vue`, import.meta.glob('./Pages/**/*.vue')),
    setup({ App, props, plugin }) {
      return createSSRApp({ render: () => h(App, props) }).use(plugin);
    },
  }),
  port,
);
```

Route helpers need no SSR wiring: Wayfinder-generated functions are plain module imports and render identically in Node and the browser (they emit relative URLs, so no location context is required).

### 3.2 `vite.config.js`

```js
export default defineConfig({
    plugins: [
        laravel({
            input: ['resources/css/app.css', 'resources/js/app.tsx'],
            ssr: 'resources/js/ssr.tsx',          // ← the SSR entry
            refresh: true,
        }),
        react(),
    ],
});
```

The `ssr:` key triggers a separate build target. `npm run build` produces both:

```
public/build/
  manifest.json
  assets/app-<hash>.js          # client bundle
  assets/app-<hash>.css
bootstrap/ssr/
  ssr.mjs                       # SSR bundle (Node entry)
```

**Build commands:**
```bash
npm run build                   # builds both client AND ssr targets
npx vite build --ssr            # SSR build only (rare; usually together)
```

## 4. Laravel adapter config

**`config/inertia.php`:**
```php
return [
    'ssr' => [
        'enabled' => true,
        'url'     => env('INERTIA_SSR_URL', 'http://127.0.0.1:13714'),
        'bundle'  => base_path('bootstrap/ssr/ssr.mjs'),
    ],

    'testing' => [
        'ensure_pages_exist' => true,
        'page_paths'         => [resource_path('js/Pages')],
        'page_extensions'    => ['js', 'jsx', 'ts', 'tsx', 'vue'],
    ],
];
```

**`.env`:**
```env
INERTIA_SSR_ENABLED=true
INERTIA_SSR_URL=http://127.0.0.1:13714
```

When `enabled=true`, every Inertia response is rendered SSR-first. The PHP adapter POSTs the page payload to `INERTIA_SSR_URL`, receives `{ head, body }`, and injects them into the Blade shell.

## 5. Running the SSR process

### 5.1 Local dev

```bash
php artisan inertia:start-ssr
# or directly:
node bootstrap/ssr/ssr.mjs
```

`inertia:start-ssr` is the artisan wrapper — it reads `config/inertia.php#ssr.bundle` and spawns Node. Convenient for dev (`Ctrl+C` to stop), inadequate for prod (no auto-restart, no log management).

### 5.2 Supervisord (classic)

**`/etc/supervisor/conf.d/inertia-ssr.conf`:**
```ini
[program:inertia-ssr]
process_name=%(program_name)s
command=node /var/www/html/bootstrap/ssr/ssr.mjs
autostart=true
autorestart=true
user=www-data
redirect_stderr=true
stdout_logfile=/var/log/inertia-ssr.log
stdout_logfile_maxbytes=10MB
stopwaitsecs=10
environment=NODE_ENV=production
```

```bash
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl start inertia-ssr
```

### 5.3 systemd

**`/etc/systemd/system/inertia-ssr.service`:**
```ini
[Unit]
Description=Inertia SSR Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/html
ExecStart=/usr/bin/node bootstrap/ssr/ssr.mjs
Restart=always
RestartSec=5
Environment=NODE_ENV=production
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now inertia-ssr
sudo journalctl -fu inertia-ssr
```

### 5.4 Docker / Compose

Run SSR as a sibling service:

```yaml
services:
  app:
    build: .
    environment:
      INERTIA_SSR_URL: http://ssr:13714
    depends_on:
      ssr:
        condition: service_healthy

  ssr:
    image: node:20-alpine
    working_dir: /app
    volumes:
      - ./:/app:ro
    command: node bootstrap/ssr/ssr.mjs
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:13714/health"]
      interval: 5s
      timeout: 2s
      retries: 5
```

**Rules:**
- Exactly **one** SSR process per app instance is enough — it's CPU-bound only during the render call.
- For multi-server clusters, run one SSR per app server (loopback) — don't share a single SSR across servers (latency, single point of failure).
- Health endpoint: Inertia's SSR server exposes one at `/health` returning 200 when ready.

## 6. Octane / FrankenPHP interplay

Octane and the SSR process are independent. Both must be running.

| Component | Reload trigger |
|---|---|
| Octane (PHP) | `php artisan octane:reload` — required after PHP changes |
| Node SSR | restart the Node process — required after JS bundle changes |

**Deploy order matters:**
1. `npm run build` (writes new `public/build/` and `bootstrap/ssr/ssr.mjs`).
2. Restart the SSR Node process so it loads the new bundle.
3. `php artisan octane:reload` so PHP picks up new code.
4. `php artisan queue:restart` for workers.

⚠️ **Anti-pattern:** reloading Octane before restarting SSR. Octane sends new page payloads to a stale SSR bundle → component-not-found errors or hydration mismatches.

## 7. Hydration mismatches — the #1 SSR bug

**Symptom:** browser console shows `Warning: Text content did not match. Server: "..." Client: "..."` (React) or `Hydration node mismatch` (Vue). The page renders, then Inertia replaces the DOM and visible content "flickers".

**Root causes (in order of frequency):**

| Cause | Diagnostic | Fix |
|---|---|---|
| `Date.now()` / `Math.random()` / `new Date()` in render | grep components for these calls | Pass server-computed values via props; use `useEffect` for client-only computations |
| `window` / `document` accessed at module top level | grep `typeof window` / `document.` outside hooks | Wrap in `useEffect` (React) / `onMounted` (Vue), or guard `if (typeof window !== 'undefined')` |
| Locale / timezone differences | server is UTC, browser is local | Format server-side or pass ISO strings + format in `useEffect` |
| Browser extensions injecting DOM | hydrate fails only on some users | Not your bug; document for support |
| Stale SSR bundle vs new client bundle | recent deploy | Ensure SSR restart preceded Octane reload (§6) |
| Conditional rendering based on `localStorage` | grep `localStorage.getItem` in render | Move to `useEffect`; render placeholder during SSR |

**Debugging workflow:**
```bash
# 1. Confirm SSR is actually running
curl -s http://127.0.0.1:13714/health

# 2. Inspect what the SSR is producing for a page
curl -s -X POST http://127.0.0.1:13714/render \
  -H 'Content-Type: application/json' \
  -d '{"component":"Posts/Index","props":{},"url":"/posts","version":"abc"}'

# 3. Compare with the client console error — find the divergent text/attribute

# 4. View source (NOT inspect) on the page in the browser; SSR'd HTML lives there
```

## 8. What does NOT work in SSR (or breaks it)

| Pattern | Why | Workaround |
|---|---|---|
| Direct DOM access at render time | No DOM in Node | Move to lifecycle hooks |
| `window.matchMedia()` for responsive rendering at SSR | No `window` | Render desktop default, swap on mount |
| Lazy components without `ssr: true` (or async resolvers that never settle in time) | SSR awaits resolution | Use `Suspense` (React) / `<Suspense>` (Vue) with a fallback |
| Components that call `fetch()` during render | Network in SSR is fragile | Pass data as props from controller |
| TanStack Query without SSR hydration support | Cache is empty server-side | Use `<Hydrate>` boundary or skip the lib for SSR |
| Animations triggered on first render | No `requestAnimationFrame` | Trigger in `useEffect` / `onMounted` |
| `Image` width/height inferred from network | Can't fetch | Always declare `width`/`height` attributes |

## 9. Memory & restarts

The Node process accumulates memory over time (V8 heap, module caches, possible component-level leaks). Like PHP workers, recycle it.

**With supervisord:**
```ini
[program:inertia-ssr]
command=node --max-old-space-size=512 /var/www/html/bootstrap/ssr/ssr.mjs
# Add a restart cron, e.g. at 04:00
```

**With systemd:**
```ini
[Service]
MemoryMax=512M
Restart=always
RuntimeMaxSec=86400        # restart daily
```

**With FrankenPHP + Caddyfile-managed worker:** if you're already managing workers via Caddy, run SSR as a separate service — don't try to colocate Node inside the FrankenPHP process.

## 10. Production deploy checklist

1. CI builds artifact: `npm run build` (produces `public/build/` and `bootstrap/ssr/ssr.mjs`).
2. Atomic release swap (Forge / Envoyer / shipped script).
3. **Restart SSR first:** `sudo systemctl restart inertia-ssr` (or supervisorctl).
4. **Then Octane:** `php artisan octane:reload`.
5. Workers: `php artisan queue:restart`.
6. Verify SSR is up: `curl http://127.0.0.1:13714/health` returns 200.
7. Smoke test: load any public page, **View Source** (not Inspect) — `<div id="app">` should contain rendered HTML, not just `data-page`.
8. Check browser console on the same page — no hydration warnings.

## 11. Disabling SSR temporarily

If the SSR process is unhealthy and you need to ship without fixing:

```env
INERTIA_SSR_ENABLED=false
```

Then `php artisan config:clear`. The PHP adapter skips the SSR call; pages render client-only. Acceptable as an incident workaround; not as a long-term posture (you lose the SEO benefit).

## 12. Common errors

| Error | Cause | Fix |
|---|---|---|
| `cURL error 7: Failed to connect to 127.0.0.1 port 13714` | SSR process down | Start it; confirm `INERTIA_SSR_URL` matches |
| `Cannot find module 'bootstrap/ssr/ssr.mjs'` | Build never ran or Vite SSR target not configured | Add `ssr:` to `vite.config.js`; `npm run build` |
| `ReferenceError: window is not defined` in SSR logs | Component touches `window` at render | Move to lifecycle hook (§7) |
| Pages render blank in source but appear in browser | SSR call timed out or returned 500 | Check SSR logs; check Vite SSR build for errors |
| Different content in source vs after hydration | Hydration mismatch (§7) | Diagnose root cause; don't suppress with `suppressHydrationWarning` unless 100% benign |
| `route is not defined` in SSR logs | Leftover global-helper usage (pre-Wayfinder code) | Replace with Wayfinder imports — no SSR wiring needed (§3.1) |
| Memory grows linearly | Component-level leak or no recycling | Cap memory + recycle (§9) |

## 13. Cross-references

- `laravel-inertia` SKILL.md §13 — summary that links here
- `laravel-frontend` §2 — `vite.config.js` baseline (the `ssr:` key extends it)
- `laravel-frontend` §11 — build & deploy contract
- (devops agent) — supervisord/systemd/Docker setup, deploy scripting
