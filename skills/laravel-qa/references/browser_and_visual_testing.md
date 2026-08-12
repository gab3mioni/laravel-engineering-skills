# Browser and visual testing with optional Playwright MCP

Playwright MCP is optional. Detect availability by checking whether the MCP tools are exposed in the current session. Do not install a package or fail QA when they are absent.

## Procedure

1. Select one critical user flow affected by the change.
2. Exercise it with behavioral assertions: navigation, form submission, visible result, API error handling, focus target, keyboard operation, and route state.
3. Capture screenshots at desktop and mobile viewports when appearance or responsiveness matters. Screenshots are evidence, not a versioned baseline.
4. Check loading, empty, error, and success states, plus focus indicators and keyboard navigation for interactive changes.
5. If MCP is unavailable, run the existing Pest/Vitest/Cypress/Dusk checks and report browser smoke testing as skipped with the reason.

Visual testing answers “does this render as intended?” E2E testing answers “does the user behavior complete correctly?” Keep both assertions when both risks exist. Prefer stable roles, labels, and user-visible text over CSS selectors.

## Routing

- `laravel-qa` owns this procedure and the fallback.
- `laravel-a11y` owns WCAG criteria, focus, keyboard, and semantics.
- `laravel-frontend` routes UI changes here after build/type checks.
- `laravel-role-react` and `laravel-role-vue` execute it conditionally.
