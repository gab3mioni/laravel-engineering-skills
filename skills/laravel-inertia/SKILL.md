---
name: laravel-inertia
description: Inertia.js v2 protocol and Laravel 12 server adapter — prop strategies (closure, defer, optional, merge, always), shared data, partial reloads, polling, prefetching, WhenVisible, history encryption, asset versioning, redirects, SSR. Use when writing or reviewing any controller that returns Inertia::render, choosing how a prop ships, wiring shared data, or debugging symptoms like "page props stale after partial reload", "back button shows encrypted history error", "deferred prop never resolves", hydration mismatches after a deploy, or an infinite version-reload loop. Stack-neutral protocol skill consumed by the laravel-react, laravel-vue, and code-review agents.
---

# Laravel Inertia — Protocol & server adapter

The Inertia.js v2 protocol with the Laravel adapter (`inertiajs/inertia-laravel`). Stack-neutral — covers the **server-side contract** and the **router API** used identically by React and Vue clients. Component-flavored details live in the `laravel-react` / `laravel-vue` agents; the wiring (Vite, Wayfinder route generation, layout) in the `laravel-frontend` skill. Client-side route/URL generation uses **Laravel Wayfinder**-generated functions or plain URLs.

## When to use / When NOT to use

Use this skill when:

- Choosing how to ship props (eager / closure / deferred / optional / merge / always)
- Designing partial reloads, polling endpoints, or prefetched routes
- Wiring shared data (auth, flash, errors)
- Returning redirects, validation errors, file downloads, or external redirects
- Configuring SSR or asset versioning
- Writing or reviewing any controller that returns `Inertia::render`

When NOT to use:

| Topic | Use instead | Kind |
|---|---|---|
| React 19 components, hooks, `useForm` (React) | `laravel-react` | agent |
| Vue 3.5 components, composables, `useForm` (Vue) | `laravel-vue` | agent |
| Vite, `resources/js` layout, Wayfinder generation | `laravel-frontend` | skill |
| Pest assertions beyond the `assertInertia` template here | `laravel-qa` | skill |
| Eloquent queries fed into props | `laravel-backend` | skill |
| WCAG / ARIA on rendered components | `laravel-a11y` | skill |
| Supervising the SSR process in production | `devops` | agent |

## Stack assumptions

- Laravel 12 with `inertiajs/inertia-laravel` v2.x
- `@inertiajs/react` v2.x or `@inertiajs/vue3` v2.x on the client
- Vite 6 + Wayfinder for client-side routes (wiring covered in `laravel-frontend`)
- SPA mode by default; SSR opt-in via `inertia:start-ssr`

---

## Workflows

### Add or modify an Inertia page

1. **Choose a strategy for every prop.** Walk the four questions above the prop-strategy table (next section) for each prop. Never default everything to plain values.
2. **Write the controller.** `Inertia::render('Pages/Name', [...])` with the chosen wrappers — `fn () =>`, `Inertia::defer()`, `Inertia::optional()`, `Inertia::merge()`, `Inertia::always()`.
3. **Verify with a Pest `assertInertia` test.** Assert the component name, the props that must ship on first paint, and `missing()` for every `optional`/`defer` prop:

   ```php
   use function Pest\Laravel\actingAs;
   use Inertia\Testing\AssertableInertia as Assert;

   it('renders the posts index with eager-loaded posts', function () {
       actingAs(User::factory()->create())
           ->get('/posts')
           ->assertInertia(fn (Assert $page) => $page
               ->component('Posts/Index')
               ->has('posts.data', 10)
               ->where('filters.q', null)
               ->missing('audit')              // optional prop must not ship on first paint
           );
   });
   ```

   Broader Pest patterns (datasets, fakes, factories) → `laravel-qa`.
4. **Run the greps.** Apply the detection column of the anti-pattern table (below) to the diff.

### Review an Inertia controller diff

- [ ] Every shared-data key in `HandleInertiaRequests::share()` wrapped in a closure?
- [ ] User serialization slimmed to a Resource — no raw `$request->user()` shipped?
- [ ] Expensive props wrapped (closure / `defer`) instead of computed as plain values?
- [ ] Polling and reload calls pass `only:` / `except` — never the whole page on a tick?
- [ ] Redirects after PUT/PATCH/DELETE resolve to 303 (automatic via `back()` / `to_route()`; hand-built responses must set it)?
- [ ] `version()` still tied to the build manifest — no hardcoded return?
- [ ] Pages rendering PII call `encryptHistory()`; logout clears history?

---

## Decision table — prop evaluation strategies

The single most important thing to internalize about Inertia. For **each prop**, answer four questions:

1. **Needed on first paint?** No → `defer` (auto-loaded after render) or `optional` (only when explicitly requested).
2. **Expensive to compute?** Yes → at minimum a **closure**, so unrelated partial reloads skip it.
3. **Target of a partial reload / poll?** Yes → closure (or `defer`/`optional`) so it actually re-runs when named in `only:`.
4. **Appendable list (infinite scroll, "load more")?** Yes → `merge`.

| Strategy | Evaluated on full request | Evaluated on partial that asks for it | Evaluated on partial that does NOT ask for it | Use when |
|---|---|---|---|---|
| Plain value `'count' => 5` | yes | yes | yes | trivial constants |
| **Closure** `fn () => Stats::compute()` | yes | yes | **no** | expensive prop you want to skip on unrelated partials |
| **`Inertia::defer(fn ())`** | **no** (sent in a follow-up request after first render) | yes | no | slow data you don't want to block first paint |
| **`Inertia::optional(fn ())`** (was `Inertia::lazy()` pre-v2) | **no** | yes (only when explicitly requested) | no | data only some flows need (e.g. drawer, modal) |
| **`Inertia::merge(fn ())`** | yes | yes — **appended** to existing array on the client | no | append-style pagination, infinite scroll |
| **`Inertia::always(fn ())`** | yes | yes | **yes** | flash messages, CSRF token — always shipped |

```php
return Inertia::render('Dashboard', [
    'user'       => $request->user(),                                   // plain
    'recent'     => fn () => $request->user()->posts()->latest()->take(5)->get(),
    'stats'      => Inertia::defer(fn () => Stats::expensive()),        // load after first paint
    'audit'      => Inertia::optional(fn () => AuditLog::for($request->user())),
    'feed'       => Inertia::merge(fn () => Post::feed()->paginate()),  // appendable
    'flash'      => Inertia::always(fn () => $request->session()->get('flash')),
]);
```

**Rules:**
- A closure is the default for any non-trivial prop. ⚠️ **Anti-pattern:** computing all props as plain values — every partial reload re-runs the work even when the prop isn't requested.
- `defer` requires no client change to fetch — Inertia issues an automatic follow-up. Group multiple deferred props with `->group('chart')` to load them in a single request.
- `optional` props **never run** unless the client names them in `only:` — perfect for drawer/modal contents.
- `merge` is the v2 building block for "Load more" buttons; the client appends instead of replacing.

---

## The protocol in one paragraph

Inertia turns a classic server-rendered app into a SPA without an API layer. The first request returns a regular HTML page that boots the JS app; every subsequent navigation is an XHR that returns a JSON payload `{ component, props, url, version }`. The client swaps the page component without a full reload. Validation errors, redirects, flash, and auth state all flow through the same response shape — there is no separate REST contract to design.

**Key consequence:** the controller still returns `Inertia::render('Page', [...props])`. There is **no client-side data fetching** for page-level data — props are the contract. Avoid pulling page data with `fetch()` from the client; use props + partial reloads.

---

## Server response — `Inertia::render`

```php
use Inertia\Inertia;

class PostController extends Controller
{
    public function index(Request $request): \Inertia\Response
    {
        return Inertia::render('Posts/Index', [
            'posts'   => Post::with('author')->latest()->paginate(),
            'filters' => $request->only(['q', 'tag']),
        ]);
    }
}
```

- The first arg is the **component name** — must match a file under `resources/js/Pages/` (e.g. `Posts/Index` → `Pages/Posts/Index.tsx` or `.vue`).
- The second arg is the **props array**. Anything `Arrayable` / `JsonSerializable` is serialized.

### Helper variants

```php
Inertia::location($url);                  // hard, full-page redirect (external or cross-domain)
return back();                            // Laravel redirect — Inertia turns it into 303
return to_route('posts.show', $post);     // ditto
```

⚠️ **Anti-pattern:** returning `response()->json(...)` from an Inertia route — the client can't distinguish it from a real Inertia response. Use `Inertia::render(...)` or a redirect.

---

## Shared data — `HandleInertiaRequests`

Global props every page receives. Generated middleware lives at `app/Http/Middleware/HandleInertiaRequests.php` and is registered in `bootstrap/app.php`.

```php
class HandleInertiaRequests extends Middleware
{
    public function version(Request $request): ?string
    {
        return parent::version();   // tied to the Vite manifest hash
    }

    public function share(Request $request): array
    {
        return [
            ...parent::share(),
            'auth' => [
                'user' => fn () => $request->user()
                    ? UserResource::make($request->user())->resolve()
                    : null,
            ],
            'flash' => [
                'success' => fn () => $request->session()->get('success'),
                'error'   => fn () => $request->session()->get('error'),
            ],
        ];
    }
}
```

**Rules:**
- Wrap every shared key in a closure. Inertia evaluates closures lazily; plain values run on every request.
- Keep shared data **small**. It ships on every page. Heavy globals belong in dedicated endpoints. Client-side route generation needs no shared prop — Wayfinder emits typed functions at build time.
- ⚠️ **Anti-pattern:** sharing the entire `User` model. Use a slim Resource (`id`, `name`, abilities). Leaks PII and bloats payload.

---

## Partial reloads

Re-render the same page but only re-resolve a subset of props. The Inertia adapter detects partials via the `X-Inertia-Partial-Component` and `X-Inertia-Partial-Data` headers.

```ts
// Client (stack-neutral pseudocode)
router.reload({ only: ['posts'] });          // re-render with only `posts` re-resolved
router.reload({ except: ['stats'] });        // everything except `stats`
router.visit('/dashboard', { only: ['feed'] });
```

Server-side: nothing to do. The closures whose keys are in `only:` run; everything else (plain values run, closures skip, defers skip, optionals skip).

**Use cases:**
- Filtering a table without losing scroll
- Re-fetching a single widget after a mutation
- Pairing with **polling** or **WhenVisible** (below)

---

## Polling (v2)

Re-issues a partial reload on an interval.

```ts
import { usePoll } from '@inertiajs/react';   // or '@inertiajs/vue3'
usePoll(2000, { only: ['unread_count'] });
```

**Rules:**
- Always pair polling with `only:` — never re-resolve the whole page on a tick.
- Stop the poll when the user backgrounds the tab — Inertia handles `visibilitychange` automatically; verify in `keepAlive`/`autoStart` options.
- Server-side: the polled prop must be a **closure** (or `defer`/`optional`) so it actually re-runs.

⚠️ **Anti-pattern:** polling endpoints that re-execute heavy queries in plain values — see the prop-strategy table.

---

## Prefetching & WhenVisible (v2)

### Prefetch on hover / mount

```ts
// React/Vue — same prop
<Link href="/posts/123" prefetch>...</Link>             // on hover (default)
<Link href="/posts/123" prefetch="mount">...</Link>     // on mount
<Link href="/posts/123" prefetch cacheFor="1m">...</Link> // cache the fetched response
```

`router.prefetch(url, options, { cacheFor })` is the imperative form.

### WhenVisible — load when the element scrolls into view

```ts
// React
<WhenVisible data="comments" fallback={<Skeleton />}>
  <Comments />
</WhenVisible>

// Vue
<WhenVisible data="comments">
  <template #fallback><Skeleton /></template>
  <Comments />
</WhenVisible>
```

Triggers a partial reload requesting `data: 'comments'` the first time the element enters the viewport. Pair with `Inertia::optional()` server-side so the prop is skipped on initial render.

---

## Router API — the non-obvious parts

`router` (from `@inertiajs/react` or `@inertiajs/vue3`, identical surface) exposes the expected `visit` / `get` / `post` / `put` / `patch` / `delete` / `reload` methods — no surprises there. What actually causes bugs:

| Option | Effect | Gotcha |
|---|---|---|
| `preserveScroll` | skip scroll-to-top on visit | without it, filter/sort visits jump the table back to the top |
| `preserveState` | keep local component state across the visit | omitting it remounts the page component and wipes local state (open accordions, unsaved inputs) |
| `replace` | replace instead of push the history entry | use for filter/search visits, or every keystroke becomes a back-button entry |
| `router.remember(state, 'key')` | persist state into `history.state` | the only way local state survives back/forward |

### Request cancellation

```ts
let cancelToken: { cancel: () => void };
router.visit('/search', {
  data: { q },
  onCancelToken: (t) => (cancelToken = t),
});
// later:
cancelToken.cancel();
```

⚠️ **Anti-pattern:** firing a visit per keystroke without cancellation — pile-ups race; later-typed terms can lose to earlier ones.

---

## Forms & validation errors

Inertia turns a Laravel `ValidationException` (HTTP 422) into a `props.errors` object on the **same page** (no redirect needed). The flow:

1. Client posts to a route protected by a `FormRequest`.
2. FormRequest fails → 302 redirect back (or 422 for XHR; Inertia accepts both).
3. Inertia merges the session's `errors` bag into `props.errors`.
4. Component renders inline errors.

```php
public function store(StorePostRequest $request)
{
    Post::create($request->validated());
    return to_route('posts.index')->with('success', 'Post created.');
}
```

```ts
// Client (stack-neutral)
router.post('/posts', { title }, {
  onError: (errors) => { /* errors === props.errors */ },
  onSuccess: () => { /* page swapped to /posts */ },
});
```

For richer form ergonomics (dirty tracking, `useForm` API, file uploads, optimistic UI), see the `laravel-react` / `laravel-vue` agents.

⚠️ **Anti-pattern:** `try/catch` around `validate()` to render custom error UI. Let the FormRequest throw; Inertia delivers it.

---

## Redirects, downloads, external URLs

| Goal | Server | Result on client |
|---|---|---|
| Internal navigation | `to_route(...)`, `back()`, `redirect(...)` | Inertia visit, page swap |
| Redirect after PUT/PATCH/DELETE | same helpers — adapter upgrades 302 → **303** | browser re-requests with GET instead of replaying the verb |
| External URL | `Inertia::location($url)` | `window.location = $url` (full reload) |
| File download | `response()->download($path)` — but route must be **outside** the Inertia link | browser download dialog |
| 419 (CSRF expired) | Laravel auto-handles via XSRF cookie | Inertia retries once after refreshing token |

⚠️ **Anti-pattern:** triggering downloads from an Inertia link (`<Link href="/exports/report.pdf">`). Use a plain `<a href>` or `window.location` — Inertia will try to parse the response as JSON.

---

## History encryption & `clearHistory` (v2)

Inertia caches page props in `history.state` so back/forward is instant. For pages with sensitive data, encrypt the cached state and clear it on logout.

```ts
// Component-level — encrypt this page's history entry
import { encryptHistory } from '@inertiajs/react';
encryptHistory();

// On logout
import { router } from '@inertiajs/react';
router.flushAll();           // drop entire visit cache
// or
router.clearHistory();       // clear encrypted history entries
```

**Rule:** call `encryptHistory()` in any page that renders PII, financial data, or auth tokens. The browser still caches the page; encryption ensures back-button doesn't expose the data after logout.

---

## Asset versioning

Inertia ships a `version` field with every response. When the client's cached version doesn't match the server's, the next visit triggers a **hard reload** — guaranteeing users on stale JS bundles get the new HTML shell.

`HandleInertiaRequests::version()` defaults to `parent::version()`, which hashes the Vite manifest. Override only when not using Vite.

```php
public function version(Request $request): ?string
{
    return md5_file(public_path('build/manifest.json'));
}
```

⚠️ **Anti-pattern:** returning a constant version string. Defeats the bust-on-deploy mechanism. The inverse is worse: a version that changes per request (timestamp, random) forces a hard reload on **every** visit.

---

## SSR

Optional. Boots a Node server (`bootstrap/ssr/ssr.mjs`) that renders the initial component to HTML. Trades infra complexity (one extra long-running process per app server) for first-paint latency and crawler-indexable HTML.

```php
// config/inertia.php
'ssr' => [
    'enabled' => true,
    'url'     => env('INERTIA_SSR_URL', 'http://127.0.0.1:13714'),
    'bundle'  => base_path('bootstrap/ssr/ssr.mjs'),
],
```

```bash
php artisan inertia:start-ssr        # dev only — supervise via systemd/supervisord/Docker in prod
```

**The deploy ordering rule:** restart the SSR Node process **before** reloading Octane — otherwise PHP sends new payloads to a stale SSR bundle and you get hydration mismatches.

---

## Rules & anti-patterns

| Smell | Section | Detection |
|---|---|---|
| `response()->json(...)` from Inertia route | Server response | grep controllers returning `Inertia::render` mixed with `->json` |
| All props as plain values (no closures) | Decision table | review of large prop arrays |
| Heavy work in shared data | Shared data | review `HandleInertiaRequests::share` for non-closure or expensive closures |
| Sharing full `User` model | Shared data | grep `'user' => $request->user()` (no Resource) |
| Polling whole page (no `only:`) | Polling | grep `usePoll` without `only:` |
| Visit per keystroke without cancellation | Router API | review search inputs |
| `try/catch` around validation in controller | Forms | grep `try.*validate` |
| Inertia link to a download endpoint | Redirects | grep `<Link href=".*\.(pdf\|csv\|xlsx)"` |
| Sensitive page without `encryptHistory()` | History encryption | review pages with PII / tokens |
| Constant `version()` override | Asset versioning | grep `HandleInertiaRequests` for hardcoded return |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Prop stale after partial reload | prop is a plain value, or its key isn't in `only:` | wrap in a closure; name the key in `only:` |
| Deferred prop never resolves | key/group mismatch between `Inertia::defer()` and the client `<Deferred data="...">` | align key names; check the follow-up XHR in devtools |
| Back button shows blank page / decryption error after logout | `encryptHistory()` without clearing on logout | call `router.clearHistory()` (or `flushAll()`) in the logout flow |
| Hard reload on every navigation (409 loop) | `version()` changes per request (timestamp, random) | make version stable per deploy (manifest hash) |
| Hydration mismatch after deploy | stale SSR bundle — Octane reloaded before the SSR process | restart SSR first; full workflow in `references/ssr.md` |
| Download link renders garbage / JSON error | download served through an Inertia `<Link>` | plain `<a href>` or `window.location` |

---

## Reference routing

| Need | Read |
|---|---|
| SSR setup, Vite SSR build config, hydration-mismatch debugging, deploy ordering, supervisor templates (systemd / supervisord / Docker) for the SSR server | [`references/ssr.md`](references/ssr.md) |

---

## Cross-references

| Topic | Where | Kind |
|---|---|---|
| React components, hooks, `useForm` ergonomics (React) | `laravel-react` | agent |
| Vue components, composables, `useForm` ergonomics (Vue) | `laravel-vue` | agent |
| Vite, `resources/js` layout, Wayfinder route generation | `laravel-frontend` | skill |
| `assertInertia` beyond the template here, Pest fakes/datasets | `laravel-qa` | skill |
| Eloquent queries feeding props | `laravel-backend` | skill |
| WCAG / ARIA in rendered components | `laravel-a11y` | skill |
| Auth state in shared data (Sanctum cookies, abilities) | `laravel-auth` | skill |
