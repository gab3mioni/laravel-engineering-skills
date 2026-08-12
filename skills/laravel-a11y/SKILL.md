---
name: laravel-a11y
description: Use when building or reviewing ANY UI component, form, modal, or navigation in a Laravel frontend — WCAG 2.2 AA conformance covering semantic HTML, landmark regions, heading hierarchy, ARIA (when to use, when not), keyboard navigation, focus management for SPAs (modals, route changes, Inertia visits), accessible forms (labels, errors, required, fieldset), color contrast, images and alt text, live regions, route-change announcements, media captions, automated testing with axe-core / jest-axe / cypress-axe / pa11y, lint plugins (jsx-a11y, vuejs-accessibility). Stack-neutral, consumed by the laravel-react, laravel-vue, and code-review agents.
---

# Laravel A11y — Accessibility for the frontend

WCAG 2.2 conformance for Laravel apps that render through React / Vue / Inertia / Blade. Stack-neutral guidance — examples flag React- or Vue-specific deviations only when they materially differ. Targets **WCAG 2.2 Level AA** (the legal floor in the EU and the practical floor everywhere else).

Two operating principles:

1. **Semantic HTML first.** A `<button>` is keyboard-accessible, focusable, announced, and clickable for free. A `<div onClick>` is none of those things. ARIA is the patch when no semantic element exists — never the first move.
2. **No ARIA is better than bad ARIA.** Wrong `role` or stale `aria-expanded` actively misinforms screen-reader users. If in doubt, leave it off.

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
| React component anatomy, hooks, `useForm` | `laravel-role-react` |
| Vue component anatomy, composables, `useForm` | `laravel-role-vue` |
| Inertia route mechanics (`router.visit`, partials) | `laravel-inertia` skill |
| Vite/Tailwind/asset wiring | `laravel-frontend` skill |
| Pest backend tests | `laravel-qa` skill |
| Server-side validation rules feeding `props.errors` | `laravel-backend` skill |

For optional browser verification of focus, keyboard, and responsive behavior, use `laravel-qa`'s `browser_and_visual_testing.md` reference. The MCP is never required.

## Stack assumptions

- WCAG 2.2 Level AA as the target
- React 19 (`.tsx`) or Vue 3.5 (`.vue`) on Inertia 2
- Tailwind for styles (relevant for color contrast and `:focus-visible` patterns)
- Tests in Pest (backend) + Vitest/Cypress (frontend) — automated a11y plugs into both

---

## Workflows

### Component a11y checklist

Run before shipping any component:

- [ ] **Semantic element?** `<button>` for actions, `<a href>` for navigation, native inputs for form controls — no `<div onClick>`.
- [ ] **Label wired?** Every control has a visible `<label for>`/`id` pair (or `aria-label` when no visible text exists — icon buttons).
- [ ] **Focus visible and order logical?** `:focus-visible` styling present; DOM order matches visual order; no positive `tabindex`.
- [ ] **Disclosure state exposed?** `aria-expanded` toggles with state and `aria-controls` references the panel on dropdowns/accordions/menus.
- [ ] **Errors referenced?** `aria-invalid` on the field + error text wired via `aria-describedby` (not color alone).
- [ ] **Contrast passes?** Text ≥ 4.5:1 (3:1 for large text); UI components and focus indicators ≥ 3:1.
- [ ] **Works keyboard-only?** Reachable, operable (`Enter`/`Space`), escapable (`Esc` closes popovers) — no mouse traps.
- [ ] **Modal focus handled?** Focus trapped while open, returned to the opener on close (`<dialog>` gives this free).
- [ ] **Route change announced?** (Inertia) focus moved to `<h1>`/`<main>` + polite live-region announcement of the new title.
- [ ] **Reduced motion respected?** Animations gated behind `prefers-reduced-motion`.

### A11y audit workflow

1. **Grep battery** — run the detection greps from the anti-patterns table below across the component tree.
2. **Automated scan** — `npx pa11y <url>` on the affected pages, or run the jest-axe/vitest-axe suite (setup: `references/a11y_testing_setup.md`).
3. **Keyboard-only pass** on the critical path — tab order sane, `Esc` closes overlays, `Enter`/`Space` activate, focus never lost or trapped outside a modal.
4. **Report each finding with its WCAG 2.2 criterion number** (e.g. "focus not visible — 2.4.7 Focus Visible (AA)").

Steps 3–4 are not optional: **automated tools catch only 30–40% of WCAG issues** (contrast, missing alt, missing labels, ARIA misuse). The remaining 60% — broken keyboard flows, meaningless announcements, focus loss — only shows up when you drive the page yourself. A page can be axe-clean and totally unusable with a screen reader.

---

## Decision tables

### ARIA — the "when not" guide

| Symptom | Use ARIA? | Real fix |
|---|---|---|
| You reached for `role="button"` | No | Use `<button>` |
| You reached for `role="link"` | No | Use `<a href>` |
| You reached for `role="checkbox"` | No | Use `<input type="checkbox">` |
| You're hiding a presentational image | Maybe | `alt=""` on `<img>`; CSS background-image needs no ARIA |
| You're announcing a status update | Yes | `aria-live` (see Live regions) |
| You're toggling a disclosure | Yes | `aria-expanded` on the trigger |
| You're labeling a custom widget | Yes | `aria-label` / `aria-labelledby` |
| The control's purpose is the visible text | No | The text is the label — no extra `aria-label` needed |

The five ARIA tools that earn their keep:

| Attribute | Purpose | Example |
|---|---|---|
| `aria-label` | Accessible name when no visible text exists | `<button aria-label="Close dialog">×</button>` |
| `aria-labelledby` | Reference visible text as the name | `<section aria-labelledby="settings-h">` |
| `aria-describedby` | Reference supplementary text (hint, error) | `<input aria-describedby="email-help email-error">` |
| `aria-live` | Announce dynamic content | `<div aria-live="polite">{toast.message}</div>` |
| `aria-expanded` | State of disclosure / dropdown / menu | `<button aria-expanded={open}>Menu</button>` |

⚠️ `aria-label` that duplicates visible text → screen readers read both ("Save Save").
⚠️ `aria-hidden="true"` on a focusable element → hidden from AT but still in the tab order.

### Alt text decision tree

```
Is the image purely decorative (carries no information)?
  ├─ YES → alt=""           (or role="presentation"; do NOT omit the alt attribute)
  └─ NO  → does the surrounding text already convey the same meaning?
      ├─ YES → alt=""
      └─ NO  → alt="concise description (no 'image of', no 'picture of')"
```

Complex images (charts, diagrams): short `alt` + long description nearby (`<figure>` + `<figcaption>` or `aria-describedby` to a paragraph).

---

## Structure & keyboard rules

### Page skeleton

- `<html lang>` is **mandatory** — set in the Blade shell (see `laravel-frontend` §5). Without it, screen readers pick the OS default voice.
- Exactly one `<main>`, one body-level `<header>`, one body-level `<footer>`. Inertia: the layout owns `<main>`; pages render inside it.
- `<nav aria-label="Primary">` when more than one nav exists.
- Skip-link is the **first focusable element**, hidden until focused (Tailwind: `sr-only focus:not-sr-only`).
- Exactly one `<h1>` per page; never skip heading levels (`h1` → `h3`). Visual hierarchy ≠ semantic hierarchy — a big-text `<div>` is not a heading.
- Unique `<title>` per page.

### Keyboard

- Every interactive element reachable and operable via keyboard: `Tab`/`Shift+Tab` to move, `Enter`/`Space` to activate, `Esc` to close overlays, arrow keys within composite widgets (radio groups, tabs, menus).
- **Visible focus:** keep or replace the outline — `focus:outline-none` without a `:focus-visible` replacement is the #1 cause of keyboard inaccessibility.

```css
.btn:focus-visible {
  @apply outline outline-2 outline-offset-2 outline-indigo-600;
}
```

- **Tab order:** DOM order is tab order. If visual order differs, fix the DOM. The only valid `tabindex` values are `0` (in DOM order) and `-1` (programmatic focus only) — positive integers create global ordering that breaks with every new element.

---

## Focus management for SPAs

The single biggest a11y gap in Inertia / React / Vue apps. The browser doesn't reset focus on a client-side route change.

### On route change

Listen for Inertia's `navigate` event and move focus to the page `<h1>` (or `<main>`), made programmatically focusable with `tabindex="-1"`:

```tsx
useEffect(() => router.on('navigate', () => headingRef.current?.focus()), []);
// <h1 ref={headingRef} tabIndex={-1} className="focus:outline-none">{title}</h1>
```

Pair with a polite live-region announcement of the new page title (see Live regions). Event API and protocol details are owned by the `laravel-inertia` skill.

### Modals / dialogs

Use native `<dialog>` where possible — `showModal()` gives focus trap, `Esc`-to-close, and focus return to the opener for free.

If `<dialog>` is off the table:

- **On open:** save the currently-focused element; move focus to the first focusable element inside.
- **While open:** trap focus (`Tab` cycles inside; `Esc` closes).
- **On close:** restore focus to the saved element.

⚠️ Don't roll a modal from scratch when `<dialog>` works. Reach for Radix / Headless UI only for styling/animation control they provide.

### Disclosed content (accordions, dropdowns)

```html
<button aria-expanded="false" aria-controls="panel-1">Section 1</button>
<div id="panel-1" hidden>...</div>
```

`aria-expanded` toggles with state; `aria-controls` references the panel id.

---

## Forms

- Every control has a visible label — explicit `<label for>`/`id` preferred (works with disabled controls consistently).
- ⚠️ Placeholder is not a label: disappears on focus, low contrast, lost on autofill.
- ⚠️ No `aria-label` on a visually-labeled input — the screen reader hears the name twice.
- Errors: `aria-invalid={true}` on the field, error text referenced via `aria-describedby`, `role="alert"` on the error container so it announces on appearance.
- ⚠️ Never errors by red color alone (~8% of men can't reliably distinguish red/green) — combine color + icon + text + `aria-invalid`.
- Use native `required` and `autocomplete` (`email`, `tel`, `street-address`, `current-password`, `new-password`, `one-time-code`, …).
- Radio and checkbox groups need `<fieldset>` + `<legend>` — gives the **group** a name in the accessibility tree.

---

## Live regions & dynamic announcements

```html
<!-- Polite: queues, doesn't interrupt -->
<div aria-live="polite" aria-atomic="true">{toast.message}</div>

<!-- Assertive: interrupts. Use sparingly — errors, alerts. -->
<div role="alert" aria-live="assertive">{errorMessage}</div>
```

**Rules:**

- The live-region container must exist on initial render. AT only announces **changes** to existing live regions; creating one and filling it in the same render = silent.
- `aria-atomic="true"` re-reads the whole region on change. Toasts: yes; streaming logs: no.
- ⚠️ Every notification as `assertive` → fatigue → users mute the screen reader.
- Route announcements: on Inertia `navigate`, set the new page title into a `sr-only` polite region, paired with the focus move above.

---

## Color contrast

WCAG 2.2 AA minima:

| Content | Ratio |
|---|---|
| Body text (< 18pt regular, < 14pt bold) | **4.5:1** |
| Large text (≥ 18pt, ≥ 14pt bold) | **3:1** |
| UI components, focus indicators, graphics | **3:1** |

Tools: browser devtools (Inspect → Accessibility tab); axe; pa11y.

⚠️ Gray-on-gray placeholder at `#999` on `#fff` is 2.85:1 — fails. Tailwind's `placeholder-gray-500` on `bg-white` is 3.36:1 — **also fails**. Use `placeholder-gray-600` (5.74:1) at minimum.

---

## Media

- Video: captions (open or closed); prerecorded video also gets a transcript.
- Audio: transcript.
- Auto-playing video: `muted`, visible controls, and `prefers-reduced-motion` respected:

```css
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

---

## Rules & anti-patterns

| Smell | Topic | Detection |
|---|---|---|
| `<div onClick>` for an action | Semantics | grep `<div[^>]*onClick` (React) / `@click` on `<div>` (Vue) |
| `<html>` without `lang` | Skeleton | Blade view inspection |
| Skipped heading levels | Skeleton | axe / manual outline |
| `outline: none` without `:focus-visible` replacement | Keyboard | grep `outline-none` / `outline:0` |
| Positive `tabindex` values | Keyboard | grep `tabindex="[1-9]` |
| SPA route change without focus management | SPA focus | review layout / Inertia `navigate` listener |
| Custom modal not using `<dialog>` (no focus trap or restore) | SPA focus | review modal components |
| Placeholder-as-label | Forms | grep `placeholder=` on inputs without sibling `<label>` |
| Errors shown only by red color (no `aria-invalid`, no text) | Forms | review error rendering |
| Live region created **and** populated in the same render | Live regions | review `aria-live` usage |
| Every notification as `assertive` | Live regions | grep `aria-live="assertive"` density |
| Gray-on-white placeholder (< 4.5:1) | Contrast | axe / contrast checker |
| `alt` attribute omitted (vs `alt=""`) | Images | axe / lint |
| `aria-hidden="true"` on focusable element | ARIA | axe / lint |
| `aria-label` duplicating visible text | ARIA | review icon/text buttons |
| Automated tests pass; no keyboard or screen-reader smoke ever run | Testing | code review heuristic |

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Screen reader silent on Inertia route change | No live region for the title, or region created and filled in the same render |
| Live region never announces | Container not present on initial render, or `display: none` on it |
| `Tab` escapes an open modal | No focus trap — use `<dialog>.showModal()` or trap manually |
| Focus lost after closing a modal / deleting a row | Focus not restored to the opener / nearest surviving element |
| Keyboard user can't see where they are | `outline-none` without a `:focus-visible` replacement |
| axe contrast rule passes in Vitest but page fails in browser | jsdom has no layout — contrast only runs in browser-level tools |

---

## Reference routing

| Need | Reference |
|---|---|
| axe-core / jest-axe / vitest-axe / cypress-axe / pa11y install + config, lint plugins, CI wiring | `references/a11y_testing_setup.md` |
| Building or auditing a modal, tabs, accordion, combobox, or action menu — APG role contracts, full keyboard maps, focus behavior | `references/accessible_widgets.md` |

---

## Cross-references

| Topic | Owner |
|---|---|
| React component anatomy, hooks, `useForm`, error rendering | `laravel-role-react` |
| Vue component anatomy, composables, `useForm`, error rendering | `laravel-role-vue` |
| Inertia `router.on('navigate', ...)` event hookup | `laravel-inertia` skill |
| `<html lang>` in the Blade shell, Vite config | `laravel-frontend` skill |
| Server-side validation messages feeding `props.errors` | `laravel-backend` skill (FormRequests) |
| Pest backend test integration (axe via Dusk feasible but rare) | `laravel-qa` skill |
| CI pipeline placement (a11y steps alongside Pint, PHPStan, Rector) | `laravel-static-analysis` skill §8 |
