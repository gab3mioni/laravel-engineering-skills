# Vite boilerplate — Laravel 12 frontend

Starter boilerplate — copy and adapt; loaded on demand from `laravel-frontend` SKILL.md.

## 1. `vite.config.js`

### 1.1 React project

```js
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import react from '@vitejs/plugin-react';
import { wayfinder } from '@laravel/vite-plugin-wayfinder';
import path from 'node:path';

export default defineConfig({
    plugins: [
        laravel({
            input: ['resources/css/app.css', 'resources/js/app.tsx'],
            ssr: 'resources/js/ssr.tsx',
            refresh: true,                          // full reload on Blade/route changes during dev
        }),
        react(),
        wayfinder(),                                // regenerates route/action functions on PHP changes
    ],
    resolve: {
        alias: { '@': path.resolve(__dirname, 'resources/js') },
    },
});
```

### 1.2 Vue project

```js
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import vue from '@vitejs/plugin-vue';
import { wayfinder } from '@laravel/vite-plugin-wayfinder';
import path from 'node:path';

export default defineConfig({
    plugins: [
        laravel({
            input: ['resources/css/app.css', 'resources/js/app.ts'],
            ssr: 'resources/js/ssr.ts',
            refresh: true,
        }),
        vue({ template: { transformAssetUrls: { base: null, includeAbsolute: false } } }),
        wayfinder(),
    ],
    resolve: {
        alias: { '@': path.resolve(__dirname, 'resources/js') },
    },
});
```

Drop the `wayfinder()` plugin line if the project regenerates via `composer dev` / a watcher instead.

## 2. App entry files

### 2.1 React (`resources/js/app.tsx`)

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

### 2.2 Vue (`resources/js/app.ts`)

```ts
import './bootstrap';
import '../css/app.css';

import { createInertiaApp } from '@inertiajs/vue3';
import { createApp, h } from 'vue';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';

createInertiaApp({
    title: (title) => `${title} · MyApp`,
    resolve: (name) =>
        resolvePageComponent(`./Pages/${name}.vue`, import.meta.glob('./Pages/**/*.vue')),
    setup: ({ el, App, props, plugin }) => {
        createApp({ render: () => h(App, props) })
            .use(plugin)
            .mount(el);
    },
    progress: { color: '#4F46E5' },
});
```

Wayfinder needs no app-level plugin — generated route/action functions are plain module imports (e.g. `import { show } from '@/routes/posts'`).

## 3. Blade shell (`resources/views/app.blade.php`)

```blade
<!doctype html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title inertia>{{ config('app.name') }}</title>

    @vite(['resources/css/app.css', 'resources/js/app.tsx'])
    @inertiaHead                                         {{-- title, head meta from page components --}}
</head>
<body>
    @inertia                                             {{-- mount target — <div id="app" data-page="..."> --}}
</body>
</html>
```

- One `@vite([...])` call listing the same entries as `vite.config.js#input`.
- `<title inertia>` lets Inertia rewrite the title per page.
- No route-injection directive needed — Wayfinder routes are imported as modules, not inlined as a script.

## 4. `tsconfig.json`

```jsonc
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
    "types": ["vite/client"]
  },
  "include": ["resources/js/**/*", "resources/js/**/*.vue"]
}
```

`include` already covers the Wayfinder output (`resources/js/actions`, `resources/js/routes`, `resources/js/wayfinder`) — no extra `types` entry needed.
