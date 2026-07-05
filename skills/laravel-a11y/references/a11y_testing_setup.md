# A11y testing setup — axe-core, jest-axe, vitest-axe, cypress-axe, pa11y

Install, config, and CI wiring for automated accessibility testing in Laravel + React/Vue/Inertia apps.

> ⚠️ **Automated tools catch only 30–40% of WCAG issues** (contrast, missing alt, missing labels, ARIA misuse). A page can be axe-clean and totally unusable with a screen reader. Automated scans are the floor, not the ceiling — always pair with the keyboard-only and screen-reader passes described in the SKILL.md audit workflow.

## Which tool when

| Level | Tool | Runs against | Best for |
|---|---|---|---|
| Lint (static) | `eslint-plugin-jsx-a11y` / `eslint-plugin-vuejs-accessibility` | JSX / SFC source | Catching ~30% of issues at write time |
| Unit / component | `jest-axe` (React) / `vitest-axe` (Vue) | Rendered DOM in jsdom | Per-component regression gates |
| E2E | `cypress-axe` | Real browser pages | Full-page scans on critical flows |
| URL sweep | `pa11y` / `pa11y-ci` | Any reachable URL | Sitemap-wide CI sweeps, no test code |

All four wrap the same engine: **axe-core**. Running more than one at the same level adds noise, not coverage.

---

## 1. Lint plugins

**React:**

```bash
npm i -D eslint-plugin-jsx-a11y
```

```jsonc
// .eslintrc
{ "extends": ["plugin:jsx-a11y/recommended"] }
```

**Vue:**

```bash
npm i -D eslint-plugin-vuejs-accessibility
```

```jsonc
{ "extends": ["plugin:vuejs-accessibility/recommended"] }
```

Flat config (ESLint 9): import the plugin and spread its `flatConfigs.recommended` (jsx-a11y) or `configs["flat/recommended"]` (vuejs-accessibility) into the config array.

---

## 2. Component tests — jest-axe / vitest-axe

### React + Vitest

```bash
npm i -D jest-axe @types/jest-axe
```

```ts
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

it('SignupForm has no a11y violations', async () => {
  const { container } = render(<SignupForm />);
  expect(await axe(container)).toHaveNoViolations();
});
```

### Vue + Vitest

```bash
npm i -D vitest-axe
```

```ts
// vitest.setup.ts
import * as matchers from 'vitest-axe/matchers';
import { expect } from 'vitest';
expect.extend(matchers);
```

```ts
import { mount } from '@vue/test-utils';
import { axe } from 'vitest-axe';

it('SignupForm has no a11y violations', async () => {
  const wrapper = mount(SignupForm);
  expect(await axe(wrapper.element)).toHaveNoViolations();
});
```

**Notes:**

- jsdom has no layout engine — axe's color-contrast rule is skipped in component tests. Contrast is covered only by browser-level tools (cypress-axe, pa11y) or devtools.
- Scope rules per test when needed: `axe(container, { rules: { region: { enabled: false } } })` — components rendered outside a landmark legitimately fail `region`.

---

## 3. E2E — cypress-axe

```bash
npm i -D cypress-axe axe-core
```

```ts
// cypress/support/e2e.ts
import 'cypress-axe';
```

```ts
it('dashboard is axe-clean', () => {
  cy.visit('/dashboard');
  cy.injectAxe();
  cy.checkA11y();
});

// Scan only after dynamic content settles, scoped + filtered:
cy.checkA11y('main', {
  includedImpacts: ['critical', 'serious'],
});
```

**Notes:**

- `cy.injectAxe()` must run after `cy.visit()` — the script injects into the current page and dies on navigation.
- Re-run `checkA11y()` after opening modals/dropdowns; the initial scan only sees the initial DOM state.

---

## 4. URL sweep — pa11y / pa11y-ci

```bash
npm i -D pa11y pa11y-ci
```

```bash
# One-off, local
npx pa11y http://localhost:8000/dashboard

# CI sweep from sitemap
npx pa11y-ci --sitemap http://localhost:8000/sitemap.xml
```

```jsonc
// .pa11yci — config for authenticated pages and thresholds
{
  "defaults": {
    "standard": "WCAG2AA",
    "timeout": 30000,
    "headers": { "Cookie": "laravel_session=..." }
  },
  "urls": [
    "http://localhost:8000/",
    "http://localhost:8000/login",
    { "url": "http://localhost:8000/dashboard", "actions": [
      "set field #email to test@example.com",
      "set field #password to password",
      "click element button[type=submit]",
      "wait for path to be /dashboard"
    ] }
  ]
}
```

**Notes:**

- pa11y runs headless Chromium via Puppeteer — the Laravel app must be serving (`php artisan serve` or the CI service container) before the sweep starts.
- Default runner is HTML_CodeSniffer; add `"runners": ["axe"]` to use axe-core and keep findings consistent with the other tools.

---

## 5. CI wiring

Job sketch — the a11y steps slot into the existing quality pipeline:

```yaml
# .github/workflows/ci.yml — a11y steps
- run: npm run lint                       # jsx-a11y / vuejs-accessibility
- run: npm run test                       # jest-axe / vitest-axe suites
- run: php artisan serve --no-reload &    # app must be up for URL sweeps
- run: npx wait-on http://localhost:8000
- run: npx pa11y-ci --sitemap http://localhost:8000/sitemap.xml
```

For PR review, surface results inline — most reporters support `--reporter=github` or JUnit XML.

**Pipeline placement** (job ordering, caching, how a11y steps sit alongside Pint / PHPStan / Rector) is owned by the `laravel-static-analysis` skill, §8.
