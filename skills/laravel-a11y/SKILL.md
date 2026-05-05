---
name: laravel-a11y
description: Accessibility (WCAG 2.2 AA) for Laravel frontend components — semantic HTML, landmark regions, heading hierarchy, ARIA (when to use, when not), keyboard navigation, focus management for SPAs (modals, route changes, Inertia visits), accessible forms (labels, errors, required, fieldset), color contrast, images and alt text, live regions, route-change announcements, media captions, automated testing with axe-core / jest-axe / cypress-axe / pa11y, lint plugins (jsx-a11y, vuejs-accessibility). Stack-neutral, consumed by the laravel-react, laravel-vue, and code-review agents.
---

# Laravel A11y — Accessibility for the frontend

WCAG 2.2 conformance for Laravel apps that render through React / Vue / Inertia / Blade. Stack-neutral guidance — examples flag React- or Vue-specific deviations only when they materially differ. Targets **WCAG 2.2 Level AA** (the legal floor in the EU and the practical floor everywhere else).

## When to use this skill

- Building or reviewing any UI component (form field, modal, dropdown, table, toast)
- Designing keyboard interaction or focus flow
- Adding `aria-*` attributes (or, more often, removing them)
- Auditing color contrast and visible focus indicators
- Wiring screen-reader announcements for SPA route changes / dynamic updates
- Configuring axe-core / jest-axe / cypress-axe / pa11y in tests and CI
- Adding `eslint-plugin-jsx-a11y` (React) or `eslint-plugin-vuejs-accessibility` (Vue)

## When NOT to use

| Topic | Use instead |
|---|---|
| React component anatomy, hooks, `useForm` | `laravel-react` |
| Vue component anatomy, composables, `useForm` | `laravel-vue` |
| Inertia route mechanics (`router.visit`, partials) | `laravel-inertia` |
| Vite/Tailwind/asset wiring | `laravel-frontend` |
| Pest backend tests | `laravel-qa` |
| Server-side validation rules feeding `props.errors` | `laravel-backend` |

## Stack assumptions

- WCAG 2.2 Level AA as the target
- React 19 (`.tsx`) or Vue 3.5 (`.vue`) on Inertia 2
- Tailwind for styles (relevant for color contrast and `:focus-visible` patterns)
- Tests in Pest (backend) + Vitest/Cypress (frontend) — automated a11y plugs into both

---

## 1. The mental model

> **Accessibility is structural, not cosmetic.** Most a11y bugs are fixed by using the right HTML element. ARIA is the patch when no semantic element exists — never the first move.

Two operating principles:

1. **Semantic HTML first.** A `<button>` is keyboard-accessible, focusable, announced, and clickable for free. A `<div onClick>` is none of those things.
2. **No ARIA is better than bad ARIA.** Wrong `role` or stale `aria-expanded` actively misinforms screen-reader users. If in doubt, leave it off.

---

## 2. Document & landmark structure

### 2.1 Page skeleton

```html
<html lang="pt-BR">              <!-- always set, matches @lang in Blade -->
  <head>
    <title>Page-specific title — App Name</title>   <!-- unique per page -->
  </head>
  <body>
    <a href="#main" class="skip-link">Skip to content</a>
    <header>...</header>          <!-- exactly one banner -->
    <nav aria-label="Primary">...</nav>
    <main id="main">...</main>    <!-- exactly one main -->
    <aside>...</aside>
    <footer>...</footer>          <!-- exactly one contentinfo -->
  </body>
</html>
```

**Rules:**
- `<html lang>` is **mandatory**. Without it, screen readers use the OS default voice — wrong language. Set in the Blade shell (see `laravel-frontend` §5).
- One `<main>` per page. Inertia: the layout owns it; pages render inside it.
- One `<header>` and one `<footer>` at the body level (others nested inside `<article>`/`<section>` are fine).
- The skip-link is the **first focusable element**. Hidden visually until focused (Tailwind: `sr-only focus:not-sr-only`).

### 2.2 Heading hierarchy

```html
<h1>Page title</h1>                 <!-- exactly one per page -->
  <h2>Section</h2>
    <h3>Subsection</h3>
  <h2>Another section</h2>
```

⚠️ **Anti-pattern:** skipping levels (`<h1>` → `<h3>`). Screen reader users navigate by heading; gaps imply missing structure.

⚠️ **Anti-pattern:** styling a `<div>` with large text instead of using `<h2>`. Visual hierarchy ≠ semantic hierarchy.

---

## 3. ARIA — the "when not" guide

| Symptom | Use ARIA? | Real fix |
|---|---|---|
| You reached for `role="button"` | No | Use `<button>` |
| You reached for `role="link"` | No | Use `<a href>` |
| You reached for `role="checkbox"` | No | Use `<input type="checkbox">` |
| You're hiding a presentational image | Maybe | `alt=""` on `<img>`; CSS background-image needs no ARIA |
| You're announcing a status update | Yes | `aria-live` (§7) |
| You're toggling a disclosure | Yes | `aria-expanded` on the trigger |
| You're labeling a custom widget | Yes | `aria-label` / `aria-labelledby` |
| The control's purpose is the visible text | No | The text is the label — no extra `aria-label` needed |

### 3.1 The five ARIA tools that earn their keep

| Attribute | Purpose | Example |
|---|---|---|
| `aria-label` | Provide an accessible name when no visible text exists | `<button aria-label="Close dialog">×</button>` |
| `aria-labelledby` | Reference visible text as the name | `<section aria-labelledby="settings-h"><h2 id="settings-h">Settings</h2>...` |
| `aria-describedby` | Reference supplementary text (hint, error) | `<input aria-describedby="email-help email-error">` |
| `aria-live` | Announce dynamic content | `<div aria-live="polite">{toast.message}</div>` |
| `aria-expanded` | State of disclosure / dropdown / menu | `<button aria-expanded={open}>Menu</button>` |

⚠️ **Anti-pattern:** `aria-label` that duplicates visible text (`<button>Save<span aria-label="Save">…</span>`). Screen readers read both; users hear "Save Save".

⚠️ **Anti-pattern:** `aria-hidden="true"` on a focusable element. Hidden from AT but still in the tab order — confusion guaranteed.

---

## 4. Keyboard navigation

### 4.1 The promise

Every interactive element is reachable and operable with a keyboard. **No mouse traps.**

| Action | Keys |
|---|---|
| Move focus | `Tab` / `Shift+Tab` |
| Activate buttons / submit | `Enter` or `Space` |
| Activate links | `Enter` |
| Open menus | `Enter` / `Space` / `↓` |
| Close popovers, modals | `Esc` |
| Move within radio groups, tabs, menus | `↑` / `↓` / `←` / `→` |
| Move within text inputs | native |

### 4.2 Visible focus

```css
/* Tailwind: keep the default. Adding `focus:outline-none` without a replacement is the #1 cause of keyboard inaccessibility. */
.btn:focus-visible {
  @apply outline outline-2 outline-offset-2 outline-indigo-600;
}
```

⚠️ **Anti-pattern:** `outline: none` (or `focus:outline-none` without `:focus-visible` replacement). Removes the keyboard user's only positional cue.

### 4.3 Tab order

- DOM order **is** tab order. If the visual order differs from the DOM, fix the DOM (or use CSS Grid/Flex `order` sparingly with awareness).
- ⚠️ **Anti-pattern:** `tabindex="5"` (or any positive integer). Creates global ordering that breaks with every new element. The only valid `tabindex` values are `0` (focusable in DOM order) and `-1` (programmatically focusable, not in tab order).

---

## 5. Focus management for SPAs

The single biggest a11y gap in Inertia / React / Vue apps. The browser doesn't reset focus on a client-side route change.

### 5.1 On route change

```ts
// React + Inertia
import { router } from '@inertiajs/react';
import { useEffect, useRef } from 'react';

export function PageWrapper({ children }) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const off = router.on('navigate', () => {
      headingRef.current?.focus();
    });
    return () => off();
  }, []);

  return (
    <main id="main">
      <h1 ref={headingRef} tabIndex={-1} className="focus:outline-none">{title}</h1>
      {children}
    </main>
  );
}
```

**Rules:**
- After an Inertia visit (`navigate` event), move focus to either the page `<h1>` or the `<main>` element.
- Make the target programmatically focusable: `tabIndex={-1}` (or `tabindex="-1"` in Vue) — keeps it out of tab order but allows `.focus()`.
- Pair with a polite live-region announcement of the new page title (§7).

### 5.2 Modals / dialogs

The hardest pattern. Use `<dialog>` (native) where possible — it gives focus trap, focus return, and `Esc`-to-close for free.

```html
<dialog ref={dialogRef}>
  <h2>Confirm delete</h2>
  <button onClick={() => dialogRef.current.close()}>Cancel</button>
  <button onClick={confirm}>Delete</button>
</dialog>
```

```ts
dialogRef.current.showModal();   // opens, traps focus, dims background
dialogRef.current.close();        // closes, restores focus to opener
```

If you can't use `<dialog>` (older browser support requirements):
- **On open:** save the currently-focused element; move focus to the first focusable element inside the modal.
- **While open:** trap focus (`Tab` cycles within the modal; `Esc` closes).
- **On close:** restore focus to the saved element.

⚠️ **Anti-pattern:** rolling a modal from scratch when `<dialog>` works. `<dialog>` is now baseline; reach for libraries (Radix, Headless UI) only if you need styling/animation control they provide.

### 5.3 Disclosed content (accordions, dropdowns)

```html
<button aria-expanded="false" aria-controls="panel-1" id="trigger-1">Section 1</button>
<div id="panel-1" hidden>...</div>
```

`aria-expanded` toggles with state. `aria-controls` references the panel id.

---

## 6. Forms

### 6.1 The labeling contract

Every form control has a visible label, either implicit (wrapped) or explicit (`for`/`id`):

```html
<!-- Explicit (preferred — works with disabled controls and screen readers consistently) -->
<label for="email">Email</label>
<input id="email" name="email" type="email" required>

<!-- Implicit -->
<label>Email <input name="email" type="email" required></label>
```

⚠️ **Anti-pattern:** placeholder as label. Disappears on focus, low contrast, lost on autofill.

⚠️ **Anti-pattern:** `aria-label` on a visually-labeled input (duplicates the name; screen reader hears it twice).

### 6.2 Errors

```html
<label for="email">Email</label>
<input
  id="email"
  name="email"
  type="email"
  required
  aria-invalid={!!errors.email}
  aria-describedby="email-error email-help"
>
<p id="email-help">We'll never share your email.</p>
<p id="email-error" role="alert">{errors.email}</p>
```

**Rules:**
- `aria-invalid={true}` whenever the field has an error.
- Error message is **referenced** via `aria-describedby` (so the screen reader reads it after the field name).
- `role="alert"` on the error container makes it announce immediately when it appears.
- ⚠️ **Anti-pattern:** showing errors only with red color. ~8% of men can't reliably distinguish red from green. Always combine color + icon + text + `aria-invalid`.

### 6.3 Required, optional, autocomplete

```html
<input required>                 <!-- native required attribute -->
<input autocomplete="email">     <!-- enables browser autofill, AT hint -->
```

`autocomplete` values worth knowing: `name`, `email`, `tel`, `street-address`, `postal-code`, `country`, `cc-number`, `current-password`, `new-password`, `one-time-code`.

### 6.4 Grouping

```html
<fieldset>
  <legend>Shipping method</legend>
  <label><input type="radio" name="shipping" value="standard"> Standard</label>
  <label><input type="radio" name="shipping" value="express"> Express</label>
</fieldset>
```

`<fieldset>` + `<legend>` is required for radio groups and checkbox groups — gives the **group** a name in the accessibility tree.

---

## 7. Live regions & dynamic announcements

```html
<!-- Polite: queues, doesn't interrupt -->
<div aria-live="polite" aria-atomic="true">
  {toast.message}
</div>

<!-- Assertive: interrupts current speech. Use sparingly — errors, alerts. -->
<div role="alert" aria-live="assertive">
  {errorMessage}
</div>
```

**Rules:**
- The live-region container must exist on initial render. AT only announces **changes** to existing live regions; creating one and immediately filling it = silent.
- `aria-atomic="true"` re-reads the whole region on change (otherwise only the changed text). For toasts: yes; for streaming logs: no.
- ⚠️ **Anti-pattern:** every notification as `assertive`. Fatigue → users mute the screen reader.

### 7.1 Inertia route announcements

Pair §5.1 (focus to heading) with a live region announcing the page title:

```tsx
const [routeMessage, setRouteMessage] = useState('');

useEffect(() => {
  return router.on('navigate', (event) => {
    setRouteMessage(`Loaded ${event.detail.page.props.title || event.detail.page.url}`);
  });
}, []);

return <div aria-live="polite" className="sr-only">{routeMessage}</div>;
```

---

## 8. Color contrast

WCAG 2.2 AA minima:

| Content | Ratio |
|---|---|
| Body text (< 18pt regular, < 14pt bold) | **4.5:1** |
| Large text (≥ 18pt, ≥ 14pt bold) | **3:1** |
| UI components, focus indicators, graphics | **3:1** |

Tools: browser devtools (Inspect → Accessibility tab); `axe` (§9); `pa11y`.

⚠️ **Anti-pattern:** gray-on-gray placeholder text at `#999` on `#fff` (2.85:1 — fails). Tailwind's `placeholder-gray-500` on `bg-white` is 3.36:1 — also fails. Use `placeholder-gray-600` (5.74:1) at minimum.

---

## 9. Images & media

### 9.1 `alt` text decision tree

```
Is the image purely decorative (carries no information)?
  ├─ YES → alt=""           (or role="presentation"; do NOT omit the alt attribute)
  └─ NO  → does the surrounding text already convey the same meaning?
      ├─ YES → alt=""
      └─ NO  → alt="concise description (no 'image of', no 'picture of')"
```

For complex images (charts, diagrams): short `alt` + long description nearby (`<figure>` + `<figcaption>` or `aria-describedby` to a paragraph).

### 9.2 Media

- Video: captions (open or closed). For prerecorded: also a transcript.
- Audio: transcript.
- Auto-playing video: `muted` attribute, controls visible, `prefers-reduced-motion` respected.

```css
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

---

## 10. Testing

### 10.1 Lint (catches ~30% of issues)

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

### 10.2 Component tests with axe-core

```ts
// React + Vitest
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

it('SignupForm has no a11y violations', async () => {
  const { container } = render(<SignupForm />);
  expect(await axe(container)).toHaveNoViolations();
});
```

```ts
// Vue + Vitest
import { mount } from '@vue/test-utils';
import { axe } from 'vitest-axe';

it('SignupForm has no a11y violations', async () => {
  const wrapper = mount(SignupForm);
  expect(await axe(wrapper.element)).toHaveNoViolations();
});
```

### 10.3 End-to-end with cypress-axe / pa11y

```ts
// Cypress
import 'cypress-axe';
it('home page', () => {
  cy.visit('/');
  cy.injectAxe();
  cy.checkA11y();
});
```

```bash
# pa11y standalone
npx pa11y http://localhost:8000/dashboard
npx pa11y-ci --sitemap http://localhost:8000/sitemap.xml
```

### 10.4 The 80/20 of automated testing

Automated tools catch roughly **30–40% of WCAG issues** (color contrast, missing alt, missing labels, ARIA misuse). The remaining 60% requires:

- **Keyboard-only smoke test:** unplug your mouse, run the critical path.
- **Screen-reader smoke test:** VoiceOver (macOS, free) on Safari, NVDA (Windows, free) on Firefox.
- **Zoom to 200%:** layout must remain functional with no horizontal scroll.

⚠️ **Anti-pattern:** "axe passes, ship it." A page can be axe-clean and totally unusable with a screen reader.

---

## 11. CI wiring

Run accessibility checks alongside the rest of the static-analysis pipeline (`laravel-static-analysis` §8):

```yaml
# .github/workflows/ci.yml — sketch
- run: npm run lint                      # eslint-plugin-jsx-a11y / vuejs-accessibility
- run: npm run test                       # jest-axe / vitest-axe
- run: npx pa11y-ci --sitemap http://localhost:8000/sitemap.xml
```

For PR review, surface results inline (most a11y reporters support `--reporter=github` or JUnit XML).

---

## 12. Anti-patterns — consolidated

| Smell | Section | Detection |
|---|---|---|
| `<div onClick>` for an action | §1, §3 | grep `<div[^>]*onClick` (React) / `@click` on `<div>` (Vue) |
| `<html>` without `lang` | §2.1 | Blade view inspection |
| Skipped heading levels | §2.2 | axe / manual outline |
| `outline: none` without `:focus-visible` replacement | §4.2 | grep `outline-none` / `outline:0` |
| Positive `tabindex` values | §4.3 | grep `tabindex="[1-9]` |
| SPA route change without focus management | §5.1 | review of layout / Inertia `navigate` listener |
| Custom modal not using `<dialog>` (no focus trap or restore) | §5.2 | review modal components |
| Placeholder-as-label | §6.1 | grep `placeholder=` on inputs without sibling `<label>` |
| Errors shown only by red color (no `aria-invalid`, no text) | §6.2 | review error rendering |
| Live region created **and** populated in the same render | §7 | review `aria-live` usage |
| Every notification as `assertive` | §7 | grep `aria-live="assertive"` density |
| Gray-on-white placeholder (< 4.5:1) | §8 | axe / contrast checker |
| `alt` attribute omitted (vs `alt=""`) | §9.1 | axe / lint |
| `aria-hidden="true"` on focusable element | §3 | axe / lint |
| Automated tests pass; no keyboard or screen-reader smoke ever run | §10.4 | code review heuristic |

---

## 13. Cross-references

| Topic | Skill |
|---|---|
| React component anatomy, hooks, `useForm`, error rendering | `laravel-react` |
| Vue component anatomy, composables, `useForm`, error rendering | `laravel-vue` |
| Inertia `router.on('navigate', ...)` event hookup | `laravel-inertia` |
| `<html lang>` in the Blade shell, Vite config | `laravel-frontend` |
| Server-side validation messages feeding `props.errors` | `laravel-backend` (FormRequests) |
| Pest backend test integration (axe via Dusk feasible but rare) | `laravel-qa` |
| Pa11y / axe-core in CI alongside Pint, PHPStan, Rector | `laravel-static-analysis` §8 |
