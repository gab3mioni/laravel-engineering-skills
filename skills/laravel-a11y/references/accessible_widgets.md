# Accessible widget recipes (APG-conformant)

Full recipes for the five widgets most often built (and most often broken) in Inertia SPAs. Every keyboard map follows the W3C ARIA Authoring Practices Guide (APG). Markup sketches are framework-neutral plain HTML — translate attribute toggling to React/Vue state as needed.

Read `SKILL.md` first for the general rules (ARIA when-not-to, focus management, live regions). This file adds the per-widget contracts: roles, keyboard maps, focus behavior.

**The prime directive holds here more than anywhere:** a widget with ARIA roles but no keyboard support is *worse* than plain markup. The role promises behavior; screen-reader users switch interaction modes based on it. Ship the keyboard handling with the role or ship neither.

---

## 1. Modal dialog

APG pattern: `patterns/dialog-modal/`

**Prefer native `<dialog>` + `showModal()`.** It provides the focus trap, `Esc`-to-close, top-layer rendering, and `aria-modal` semantics for free. Hand-roll only when a real design constraint forbids it — then follow the full contract below.

### Role / attribute contract

| Attribute | Where | Value |
|---|---|---|
| `role="dialog"` | container | required (implicit on `<dialog>`) |
| `aria-modal="true"` | container | required — only if content behind is truly inert AND visually obscured |
| `aria-labelledby` | container | id of the visible title (or `aria-label` if no visible title) |
| `aria-describedby` | container | optional — id of a short description; omit for complex content |

### Keyboard map

| Key | Behavior |
|---|---|
| `Tab` | Next tabbable element inside the dialog; wraps from last to first |
| `Shift+Tab` | Previous tabbable element; wraps from first to last |
| `Escape` | Closes the dialog |

### Focus behavior

- **On open:** focus moves inside the dialog. Default: the first focusable element. APG refinements: for long/scrollable content, focus a static element (title) with `tabindex="-1"` so the top isn't scrolled away; for destructive confirmations, focus the **least destructive** action (Cancel, not Delete).
- **While open:** focus is trapped — `Tab` never reaches the page behind. Content behind is inert (`inert` attribute, or `aria-hidden="true"` + removed from tab order).
- **On close:** focus returns to the element that opened the dialog (unless it no longer exists — then the nearest logical target).

### Markup sketch

```html
<button type="button" data-opens="confirm-dlg">Delete account</button>

<dialog id="confirm-dlg" aria-labelledby="confirm-title">
  <!-- open with dlg.showModal(), never dlg.show() — show() gives no trap, no Esc, no top layer -->
  <h2 id="confirm-title">Delete account?</h2>
  <p>This cannot be undone.</p>
  <button type="button" autofocus>Cancel</button>   <!-- least destructive gets initial focus -->
  <button type="button">Delete</button>
</dialog>
```

Hand-rolled fallback (design constraint forbids `<dialog>`): same structure with `<div role="dialog" aria-modal="true" aria-labelledby="confirm-title">`, plus JS for the trap, `Esc`, and focus return — all three, not a subset.

---

## 2. Disclosure / accordion

APG patterns: `patterns/disclosure/`, `patterns/accordion/`

**Prefer native `<details>/<summary>`** for simple show/hide with no styling constraints on the marker or animation. Script the pattern only when design demands it.

### Role / attribute contract

| Attribute | Where | Value |
|---|---|---|
| (role) | trigger | a real `<button>` — no `role="button"` on a div |
| `aria-expanded` | trigger | `"true"` / `"false"`, toggled with state |
| `aria-controls` | trigger | id of the content panel (optional per APG, recommended) |
| heading wrapper | accordion headers | button nested inside `<h2>`–`<h6>` at the correct outline level |
| `role="region"` + `aria-labelledby` | accordion panel | optional; skip when the accordion has ~6+ panels (landmark noise) |
| `aria-disabled="true"` | trigger | when an open panel cannot be collapsed (one-must-stay-open accordions) |

### Keyboard map

| Key | Behavior |
|---|---|
| `Enter` / `Space` | Toggles the panel (free with a real `<button>`) |
| `Tab` / `Shift+Tab` | Standard document tab order through all headers and visible content |

No arrow-key handling is required by the APG for disclosures or accordions — `Tab` is the navigation. (Optional arrow-key header navigation exists in older APG examples but is not part of the contract.)

### Focus behavior

Nothing special: focus stays on the trigger after toggling. Never move focus into the panel on expand.

### Markup sketch

```html
<h3><!-- heading level fits the page outline, not styling -->
  <button type="button" aria-expanded="false" aria-controls="sect1">
    Shipping details
  </button>
</h3>
<div id="sect1" hidden>...</div>   <!-- hidden attr toggled with aria-expanded -->
```

### When NOT to make it a full accordion

- One collapsible section → plain disclosure (or `<details>`). Accordion machinery adds nothing.
- Content users need to compare side-by-side or Ctrl+F across → don't collapse it at all; hidden content is unfindable.
- "Exclusive open" (opening one closes another) is an APG option, not a requirement — it discards user context; use only when panels are truly alternatives.

---

## 3. Tabs

APG pattern: `patterns/tabs/`

### Role / attribute contract

| Attribute | Where | Value |
|---|---|---|
| `role="tablist"` | container of tabs | required; `aria-label` when purpose isn't obvious |
| `role="tab"` | each tab | required; must be a child of the tablist |
| `aria-selected` | each tab | `"true"` on the active tab, `"false"` on the rest |
| `aria-controls` | each tab | id of its tabpanel |
| `role="tabpanel"` | each panel | required; `aria-labelledby` → its tab's id |
| `aria-orientation="vertical"` | tablist | only for vertical tab stacks (swaps the arrow axis) |
| `tabindex="0"` | tabpanel | when the panel has no focusable content, so keyboard users can reach it |

### Keyboard map (horizontal tablist)

| Key | Behavior |
|---|---|
| `Tab` | Into the tablist: lands on the **active** tab only. Again: leaves the tablist to the panel / next element |
| `←` / `→` | Previous / next tab, wrapping at the ends (vertical tablist: `↑` / `↓`) |
| `Home` / `End` | First / last tab (optional but cheap — implement it) |
| `Enter` / `Space` | Activates the focused tab (manual activation only) |

### Roving tabindex

Only the active tab has `tabindex="0"`; every other tab has `tabindex="-1"`. Arrow keys move DOM focus **and** the roving `tabindex`. This is what makes the tablist one tab stop instead of five — without it, keyboard users wade through every tab to pass the component.

### Automatic vs manual activation

| Mode | Behavior | Use when |
|---|---|---|
| **Automatic** | Arrow focus = activation; the panel switches as focus moves | Panel content is already in memory and renders instantly. APG's recommended default |
| **Manual** | Arrows only move focus; `Enter`/`Space` activates | Switching is expensive — Inertia partial reload, network fetch, heavy render. Prevents firing N requests while arrowing across tabs |

In Inertia apps, tabs that trigger `router.visit`/partial reloads should be **manual** — or should be real links styled as tabs (then they're navigation, not a tabs widget: use `<a>` + `aria-current="page"`, no `tablist` roles).

### Markup sketch

```html
<div role="tablist" aria-label="Billing sections">
  <button role="tab" id="tab-1" aria-selected="true"  aria-controls="panel-1" tabindex="0">Invoices</button>
  <button role="tab" id="tab-2" aria-selected="false" aria-controls="panel-2" tabindex="-1">Payment methods</button>
</div>
<div role="tabpanel" id="panel-1" aria-labelledby="tab-1" tabindex="0">...</div>
<div role="tabpanel" id="panel-2" aria-labelledby="tab-2" tabindex="0" hidden>...</div>
```

---

## 4. Combobox / autocomplete

APG pattern: `patterns/combobox/` (editable input + listbox popup)

**Honest warning: this is the hardest widget in the APG.** Virtual focus, filtering races, `aria-activedescendant` scroll sync, touch + screen-reader combinations — hand-rolled versions are nearly always broken somewhere. **Prefer a proven headless library** (Headless UI Combobox, Radix, Ark UI) and style it. This recipe exists so you can *audit and fix* markup — not to encourage from-scratch builds.

### Role / attribute contract

| Attribute | Where | Value |
|---|---|---|
| `role="combobox"` | the `<input>` itself | the modern (ARIA 1.2) pattern — not on a wrapper div (that's the deprecated 1.1 shape) |
| `aria-expanded` | input | `"true"` while the listbox is visible, else `"false"` |
| `aria-controls` | input | id of the listbox |
| `aria-autocomplete` | input | `"list"` (suggestions only) or `"both"` (also inline-completes) |
| `aria-activedescendant` | input | id of the visually highlighted option; empty/absent when none |
| `role="listbox"` | popup | with `aria-label` |
| `role="option"` | each suggestion | `aria-selected="true"` on the highlighted one |

**Virtual focus:** DOM focus **stays on the input** the whole time — the user keeps typing. `aria-activedescendant` tells AT which option is "focused". The highlighted option must be scrolled into view manually (no DOM focus means no automatic scrolling).

### Keyboard map

| Key | Behavior |
|---|---|
| Typing | Filters/loads suggestions; opens the listbox |
| `↓` | Opens listbox if closed; moves active option down (wraps optional) |
| `↑` | Moves active option up (optionally opens landing on the last option) |
| `Enter` | Accepts the active option into the input; closes the listbox |
| `Escape` | Closes the listbox; a second `Escape` optionally clears the input |
| `Alt+↓` / `Alt+↑` | Optional: open without moving the active option / close |
| `←` / `→` `Home` `End` | Edit the input text normally — must NOT be hijacked for list navigation |
| `Tab` | Leaves the combobox (commonly accepting the active option first); closes the listbox |

### Markup sketch

```html
<label for="city">City</label>
<input id="city" type="text"
       role="combobox"
       aria-autocomplete="list"
       aria-expanded="true"
       aria-controls="city-listbox"
       aria-activedescendant="city-opt-2">   <!-- DOM focus stays here; this points at the highlight -->

<ul id="city-listbox" role="listbox" aria-label="City suggestions">
  <li id="city-opt-1" role="option">São Paulo</li>
  <li id="city-opt-2" role="option" aria-selected="true">São Carlos</li>
  <li id="city-opt-3" role="option">São Luís</li>
</ul>
```

### Audit checklist (the usual breakages)

- `role="combobox"` on a wrapper `<div>` instead of the input → ARIA 1.1 leftover, mis-announced.
- `aria-expanded` never flips, or `aria-activedescendant` points at a stale/removed id after filtering.
- Arrow keys move a highlight visually but nothing updates `aria-activedescendant` → screen reader hears nothing.
- Options are `<div>`s without `role="option"`, or the popup lacks `role="listbox"`.
- Highlighted option scrolls out of view (virtual focus doesn't auto-scroll).

---

## 5. Menu (dropdown of actions)

APG patterns: `patterns/menu-button/` + `patterns/menubar/`

### The critical distinction first

**Navigation links are NOT a menu.** `role="menu"` means a desktop-application-style menu of **actions/commands** (Edit → Copy, row actions: Duplicate / Archive / Delete). A dropdown of links ("Products", "Pricing", user-account page links) is a **disclosure containing a plain list of `<a>`** — pattern §2, no menu roles anywhere. Misusing `role="menu"` on nav promises arrow-key + typeahead behavior that isn't there and turns each link into a "menu item" announcement. This is the single most common ARIA error in generated navbars.

### Role / attribute contract

| Attribute | Where | Value |
|---|---|---|
| (role) | trigger | real `<button>` |
| `aria-haspopup="menu"` | trigger | required |
| `aria-expanded` | trigger | `"true"` / `"false"` |
| `aria-controls` | trigger | id of the menu (optional) |
| `role="menu"` | popup container | required; `aria-labelledby` → the trigger |
| `role="menuitem"` | each action | (`menuitemcheckbox` / `menuitemradio` for toggles, with `aria-checked`) |
| `tabindex` | items | roving: all items `tabindex="-1"`, focus moved programmatically with real DOM focus |
| `aria-disabled="true"` | item | disabled but still perceivable (vs `disabled`, which removes it from focus) |

### Keyboard map

| Key | Where | Behavior |
|---|---|---|
| `Enter` / `Space` / `↓` | trigger | Opens the menu, focus on the **first** item |
| `↑` | trigger | Opens the menu, focus on the **last** item (optional but standard) |
| `↓` / `↑` | in menu | Next / previous item, wrapping |
| `Home` / `End` | in menu | First / last item |
| `Enter` | in menu | Activates the item and closes the menu |
| `Escape` | in menu | Closes the menu, focus returns to the trigger |
| `Tab` / `Shift+Tab` | in menu | Closes the menu, focus moves on in the page tab order |
| Printable char | in menu | Typeahead: focus next item starting with that character (optional) |

### Focus behavior

The menu is **one tab stop** (the trigger). Real DOM focus moves between items via arrows — unlike the combobox, there is no virtual focus here. On close, focus always lands back on the trigger (except `Tab`, which moves past it).

### Markup sketch

```html
<button type="button" id="row-actions" aria-haspopup="menu" aria-expanded="false">
  Actions
</button>
<ul role="menu" aria-labelledby="row-actions" hidden>
  <li role="none"><button role="menuitem" tabindex="-1">Duplicate</button></li>
  <li role="none"><button role="menuitem" tabindex="-1">Archive</button></li>
  <li role="none"><button role="menuitem" tabindex="-1" aria-disabled="true">Delete</button></li>
</ul>
<!-- role="none" strips the <li> semantics so items are direct children of the menu tree -->
```

---

## Native element vs ARIA widget — decision table

| You're about to build | Native answer | ARIA widget only when |
|---|---|---|
| Clickable action | `<button>` | never — `div role="button"` also needs `tabindex="0"` + Enter + Space handlers and still loses form/AT integration |
| Modal | `<dialog>` + `showModal()` | a hard design/animation constraint blocks `<dialog>` — then full trap + Esc + return, no subset |
| Simple show/hide | `<details>/<summary>` | you need `aria-expanded` reporting on a styled button, animation control, or exclusive-open accordion |
| Dropdown of links | disclosure `<button aria-expanded>` + `<ul>` of `<a>` | never use `role="menu"` for navigation |
| Dropdown of actions | — | `role="menu"` + full keyboard map (§5) |
| Select-one-value | `<select>` | custom option rendering is a real requirement — then a headless library, not from scratch |
| Autocomplete | `<datalist>` covers surprisingly many cases | rich options/async search → headless library; hand-rolled combobox is a last resort |
| Tabs that navigate to routes | `<a>` links + `aria-current="page"` | true in-page panel switching → `tablist` (§3) |

The native row wins whenever it's viable: built-in keyboard support, focus behavior, AT mapping, and zero JS to keep in sync.

---

## Widget anti-patterns

| Anti-pattern | Why it breaks | Fix |
|---|---|---|
| ARIA roles without the keyboard map | Role promises behavior; AT users switch modes and hit a dead widget. **Worse than no ARIA** | Ship keys + roles together, or strip the roles |
| `role="menu"` on navigation links | Announces app-menu semantics; users expect arrows/typeahead and get links | Disclosure + plain list of `<a>` |
| `aria-hidden="true"` on/over focused or focusable content | Element stays tabbable but vanishes from AT — focus lands on "nothing" | `inert` on backgrounds; never `aria-hidden` on anything reachable |
| `tabindex` > 0 | Creates a parallel global tab order that breaks with every new element | Only `0` and `-1`; fix DOM order instead |
| Every tab/menuitem in the tab order (`tabindex="0"` on all) | Composite widget becomes N tab stops instead of 1 | Roving tabindex |
| `aria-selected` / `aria-expanded` set once, never toggled | Static ARIA lies about state — misinforms instead of informing | Bind to state; verify with a screen reader or axe |
| Focus not returned on dialog/menu close | Keyboard user dumped at document top; loses their place | Save opener on open, restore on close (`<dialog>` does it free) |
| `dialog.show()` instead of `showModal()` | No trap, no top layer, no Esc — looks modal, isn't | `showModal()` |
| Combobox roles on a wrapper div (ARIA 1.1 shape) | Announced wrong by current AT | `role="combobox"` on the `<input>` itself |
| Hand-rolled combobox "to save a dependency" | Hardest pattern in the APG; subtle breakage guaranteed | Headless UI / Radix / Ark; recipe §4 is for auditing |

---

## 60-second keyboard smoke test per widget

Automated scanners validate attributes, not behavior — these checks are manual by necessity (see `SKILL.md`, audit workflow). Run the row for the widget you just touched:

| Widget | Drive it | Pass condition |
|---|---|---|
| Dialog | Open → `Tab` ×N → `Escape` | `Tab` never leaves the dialog; `Escape` closes; focus is back on the opener |
| Disclosure / accordion | `Tab` to header → `Enter` → `Tab` | Panel toggles; focus stayed on the header; next `Tab` enters the open panel |
| Tabs | `Tab` into list → `→` `→` → `Tab` | Landed on the *active* tab; arrows moved (and activated, if automatic); one more `Tab` exits the whole tablist |
| Combobox | Type → `↓` `↓` → `Enter` → `Escape` | Highlight visibly moves and stays in view; `Enter` fills the input and closes; typing never loses the cursor |
| Menu | `Enter` on trigger → `↓` → `Escape` | Focus jumped to the first item; arrows cycle; `Escape` returns focus to the trigger |

If any row fails, the widget is broken for keyboard and screen-reader users regardless of what axe says.
