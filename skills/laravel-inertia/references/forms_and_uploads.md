# Inertia Forms & File Uploads — useForm internals, PUT spoofing, Precognition

Deep mechanics of `useForm`, the file-upload protocol (including the PUT/PATCH multipart blind spot), the server side of uploads, and Laravel Precognition live validation. Loaded when the agent is building or reviewing any Inertia form beyond the basic submit-and-redirect flow covered in SKILL.md ("Forms & validation errors").

## 1. `useForm` — the parts that cause bugs

`useForm` (from `@inertiajs/react` or `@inertiajs/vue3`) wraps form data, submission, errors, and progress in one object. The API surface is identical across frameworks; only reactivity syntax differs.

```ts
const form = useForm({ title: '', body: '', tags: [] as string[] });
form.post('/posts', { preserveScroll: true });
```

### 1.1 State fields

| Field | Type | Semantics |
|---|---|---|
| `data` | object | current field values (in React, read via `form.data`, write via `form.setData`) |
| `isDirty` | bool | any field differs from the **defaults** (not from the initial props) |
| `processing` | bool | a submission is in flight — disable the submit button on it |
| `progress` | object \| null | upload progress; `progress.percentage` is the number to render |
| `errors` | object | validation errors keyed by field, dotted notation for nested fields |
| `hasErrors` | bool | `errors` is non-empty |
| `wasSuccessful` | bool | latest submission succeeded (stays true) |
| `recentlySuccessful` | bool | true for **2 seconds** after success — built for "Saved." flashes |

### 1.2 `transform()` — runs at submit, not at call time

`transform()` registers a callback that reshapes the payload **during request serialization**. It does not run when you chain it, and it never mutates `form.data`.

```ts
form
  .transform((data) => ({ ...data, remember: data.remember ? 'on' : '' }))
  .post('/login');
```

**Rules:**
- Treat the callback as pure: build and return a **new object**. Mutating `data` inside `transform` writes through to form state in some adapters — a classic source of "why did my checkbox value change after submit".
- After submit, `form.data` still holds the **untransformed** values. Anything that reads `form.data` (dirty checks, debug panels) never sees the transformed shape. Don't "fix" that by pre-transforming state — keep state in UI shape, wire format in `transform`.
- The transform stays registered for subsequent submits on the same form instance.

### 1.3 `reset()` and `defaults()`

```ts
form.reset();                    // all fields back to defaults
form.reset('title', 'body');     // only these fields

form.defaults();                                 // current values become the new defaults
form.defaults('email', 'new-default@example.com');
form.defaults({ name: 'Updated', email: 'x@y.z' });
```

- `reset()` restores to the **defaults**, which start as the values passed to `useForm` — not to whatever the server last sent.
- After a successful save on an edit form, call `form.defaults()` then rely on `isDirty` again; otherwise the just-saved values count as "unsaved changes".
- `form.resetAndClearErrors()` combines `reset()` + `clearErrors()` in one call (accepts field names too).

### 1.4 Error helpers

```ts
form.setError('email', 'Already taken');       // manual, client-side error
form.setError({ email: '...', name: '...' });  // several at once
form.clearErrors();                            // all
form.clearErrors('email');                     // one field
```

Server-driven errors overwrite these on the next submission — `setError` is for client-only checks (e.g. "passwords don't match" before hitting the server).

### 1.5 `errorBag` — multiple forms on one page

Laravel keys all validation errors under one session bag by default. Two forms with a `name` field on the same page will clobber each other's errors. Scope them:

```ts
form.post('/profile', { errorBag: 'updateProfile' });
// second form:
otherForm.post('/companies', { errorBag: 'createCompany' });
```

Server-side, throw into the same named bag (`$request->validateWithBag('updateProfile', [...])` or `FormRequest::$errorBag`). Errors then arrive under `page.props.errors.createCompany` instead of the root, and `useForm` with the matching `errorBag` picks up only its own.

## 2. File uploads — the PUT/PATCH blind spot

### 2.1 How Inertia ships files

When any value in the payload is a `File`/`Blob`, Inertia converts the whole payload to `FormData` and sends `multipart/form-data`. No manual `new FormData()` needed. If a file is nested where Inertia's detection misses it (e.g. inside a class instance), force it:

```ts
router.post('/users', data, { forceFormData: true });
```

### 2.2 ⚠️ The known failure: `PUT`/`PATCH` + files silently drops them

PHP only parses `multipart/form-data` bodies for **POST** requests. A `form.put('/users/1')` carrying a file reaches Laravel with `$request->file('avatar') === null` and, typically, a confusing "avatar is required" validation error — nothing crashes, the file just vanishes.

**The correct pattern — POST with method spoofing:**

```ts
// useForm
const form = useForm({
  _method: 'put',
  name: user.name,
  avatar: null as File | null,
});
form.post(`/users/${user.id}`);          // POST on the wire, PUT to the router

// or router directly
router.post(`/users/${user.id}`, {
  _method: 'put',
  avatar: file,
});
```

Laravel reads `_method` and dispatches to the `Route::put(...)` definition. The client sends POST; the framework treats it as PUT. Same trick for PATCH (`_method: 'patch'`).

### 2.3 Upload progress

`useForm` exposes progress automatically; render `form.progress.percentage` while `form.progress` is non-null.

```tsx
// React
{form.progress && <progress value={form.progress.percentage} max={100} />}
```

```vue
<!-- Vue -->
<progress v-if="form.progress" :value="form.progress.percentage" max="100" />
```

With the bare `router`, wire the visit callback instead:

```ts
router.post('/videos', data, {
  onProgress: (progress) => setPercent(progress?.percentage ?? 0),
});
```

### 2.4 FormData serialization limits (nested data + files)

Once a file forces `FormData`, **every** value is serialized to strings via bracketed keys (verified against `objectToFormData` in `@inertiajs/core`):

| JS value | Arrives in PHP as |
|---|---|
| nested object `{ user: { name } }` | `user[name]` |
| array `tags: ['a', 'b']` | `tags[0]`, `tags[1]` |
| `true` / `false` | `'1'` / `'0'` |
| `null` / `undefined` | `''` (empty string) |
| `Date` | ISO-8601 string |

Consequences: `boolean` validation rules still pass (`'1'`/`'0'` are accepted), but strict `null` checks fail — an optional field sent as `null` arrives as `''`. Use `nullable` + Laravel's `ConvertEmptyStringsToNull` middleware (on by default) and cast types server-side; don't expect JSON-typed values in a multipart request.

## 3. Server side of an upload

```php
// StoreAvatarRequest
use Illuminate\Validation\Rules\File;

public function rules(): array
{
    return [
        'avatar' => ['required', File::types(['jpg', 'png', 'webp'])->max('2mb')],
    ];
}
```

```php
public function update(StoreAvatarRequest $request, User $user)
{
    $path = $request->file('avatar')->store('avatars', 'private');

    $user->update(['avatar_path' => $path]);

    return to_route('profile.edit')->with('success', 'Avatar updated.');
}
```

**Rules:**
- Validate with `Illuminate\Validation\Rules\File` (`File::types()->max()`, `File::image()`), not string rules glued by hand — it validates MIME by content, not extension.
- Store on a **private disk** and serve through a signed or authorized route. Files under `public/` skip authorization entirely. Broader upload security (path traversal, SVG/XSS, content sniffing) → `laravel-security`.
- The response is a plain redirect. Because the spoofed request is a POST resolved as PUT, the adapter applies the same 303 upgrade described in SKILL.md § "Redirects, downloads, external URLs" — `to_route()` / `back()` handle it; hand-built responses must set 303 themselves.

## 4. Precognition — live validation before submit

Precognition sends the in-progress form to the server with a `Precognition` header; Laravel runs the route's middleware and **FormRequest validation only** — the controller method never executes.

### 4.1 Server setup (same for every client)

```php
use App\Http\Requests\StoreUserRequest;
use Illuminate\Foundation\Http\Middleware\HandlePrecognitiveRequests;

Route::post('/users', [UserController::class, 'store'])
    ->middleware([HandlePrecognitiveRequests::class]);
```

- Rules run; side effects don't — but **other middleware still runs**. Guard side-effecting middleware with `$request->isPrecognitive()`.
- Vary rules per mode inside the FormRequest: `$this->isPrecognitive() ? Password::min(8) : Password::min(8)->uncompromised()` keeps slow checks out of the live path.
- Files are **not uploaded** during precognitive validation by default (avoids re-uploading large files on every keystroke). Make file rules conditional: `...$this->isPrecognitive() ? [] : ['required']`. Opt in with `form.validateFiles()` only for small files.

### 4.2 Client — Inertia ≥ 2.3 (built-in)

Precognition support is built into `useForm` since Inertia 2.3. Chain `withPrecognition()`, or pass method + URL as the first arguments (the signature compatible with the standalone packages):

```ts
const form = useForm({ name: '', email: '' }).withPrecognition('post', '/users');
// equivalent:
const form = useForm('post', '/users', { name: '', email: '' });
```

```vue
<!-- Vue: validate on change -->
<input v-model="form.email" @change="form.validate('email')" />
<p v-if="form.invalid('email')">{{ form.errors.email }}</p>
```

```tsx
// React: setData on change, validate on blur
<input
  value={form.data.email}
  onChange={(e) => form.setData('email', e.target.value)}
  onBlur={() => form.validate('email')}
/>
{form.invalid('email') && <p>{form.errors.email}</p>}
```

Helpers: `form.validating` (request in flight), `form.valid('field')` / `form.invalid('field')` (only meaningful after the field changed and a response arrived), `form.touch()` / `form.touched()` for wizard flows, `form.validate({ only: ['name', 'email'], onSuccess, onValidationError })` for multi-field steps, `form.setValidationTimeout(3000)` to tune the debounce.

### 4.3 Client — Inertia < 2.3 (standalone packages)

Older Inertia versions need Laravel's adapter packages (verified on npm, latest 0.x):

```bash
npm install laravel-precognition-react-inertia   # React
npm install laravel-precognition-vue-inertia     # Vue
```

Import `useForm` from the package instead of the Inertia adapter; the API matches §4.2's compat signature. On upgrade to Inertia ≥ 2.3, drop the package and import from `@inertiajs/react` / `@inertiajs/vue3` — same call sites.

## 5. Error UX contract

Inertia never surfaces a 422 JSON body to the page. Validation failure = redirect back + errors flashed to the session + delivered as `props.errors` (see SKILL.md § "Forms & validation errors" for the full flow). UX consequences:

- **State survives failure.** Inertia preserves component state for `post`/`put`/`patch`/`delete` visits, so inputs keep their values — no `old()` repopulation.
- **Scroll does not survive by default.** A failed submit scrolls back to top; on long forms the user can't see which field failed. Default advice: submit with `preserveScroll: true` — or `preserveScroll: 'errors'` to keep scroll only on failure.
- **Scroll to the first error** instead of leaving the viewport wherever it was:

```ts
form.post('/register', {
  preserveScroll: true,
  onError: (errors) => {
    const first = Object.keys(errors)[0];
    document.querySelector(`[name="${first}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  },
});
```

  Move focus there too and wire `aria-describedby` on the input — a11y patterns in `laravel-a11y`.
- Need every message per field (not just the first)? Set `$withAllErrors = true` on `HandleInertiaRequests`; `errors.field` becomes an array.

## 6. Rules & anti-patterns

| Smell | Why it breaks | Detection |
|---|---|---|
| `form.put(...)` / `form.patch(...)` submitting a file | PHP drops multipart bodies on PUT/PATCH; file arrives null (§2.2) | grep `\.put\(`/`\.patch\(` in components that also match `File\|avatar\|upload\|type="file"` |
| Manual `axios.post` for a page form | Bypasses the Inertia protocol: no `props.errors`, no redirect handling, no progress | grep `axios\.(post\|put)` in `resources/js/Pages/` |
| `transform()` mutating its argument | Writes through to form state; UI values silently change after submit | grep `transform((data) =>` bodies assigning `data.` |
| `router.visit`/`router.post` for form submits with hand-rolled state | Reimplements `processing`/`errors`/`isDirty` badly; loses dirty tracking | review forms using `router.` + separate `useState`/`ref` for errors |
| Two forms on one page without `errorBag` | Same-named fields clobber each other's errors (§1.5) | grep pages with two `useForm` calls and no `errorBag` |
| File rules unconditional under Precognition | Live validation always fails `required` on the not-yet-sent file (§4.1) | review precognitive FormRequests for file rules without `isPrecognitive()` |
| Submit without `preserveScroll` on long forms | Validation failure jumps to top; error invisible (§5) | grep `form.post(` without `preserveScroll` in multi-section pages |

## 7. Cross-references

- `laravel-inertia` SKILL.md — § "Forms & validation errors" (protocol flow), § "Redirects, downloads, external URLs" (303 rules)
- `laravel-security` — upload hardening (MIME sniffing, private disks, signed URLs)
- `laravel-a11y` — accessible error announcement, focus management on failure
- `laravel-qa` — feature tests for uploads (`Storage::fake`, `UploadedFile::fake`)
- `laravel-react` / `laravel-vue` agents — component-level form composition around these primitives
