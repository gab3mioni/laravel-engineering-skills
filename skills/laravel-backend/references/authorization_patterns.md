# Authorization — Advanced Patterns

Beyond Policy and Gate basics. Loaded when working with multi-tenant authorization, super-admin escape hatches, Spatie Permission integration, or authorization in jobs and console commands.

## 1. Policy composition

Policies become repetitive when multiple methods share the same check. Extract a private helper:

```php
class PostPolicy
{
    public function update(User $user, Post $post): bool { return $this->isAuthor($user, $post); }
    public function delete(User $user, Post $post): bool { return $this->isAuthor($user, $post); }

    public function publish(User $user, Post $post): bool
    {
        return $this->isAuthor($user, $post) && $user->is_verified;
    }

    private function isAuthor(User $user, Post $post): bool
    {
        return $user->id === $post->user_id;
    }
}
```

For checks shared across multiple Policies, extract to a trait or a small domain service:

```php
trait HasOwnership
{
    protected function ownsResource(User $user, Model $model, string $foreignKey = 'user_id'): bool
    {
        return $user->id === $model->{$foreignKey};
    }
}
```

## 2. Gate `before` and `after`

```php
// AuthServiceProvider::boot()

// Before — runs before every Policy/Gate check
Gate::before(function (User $user, string $ability) {
    return $user->is_super_admin ? true : null;   // null = continue checking
});

// After — runs after every check; rarely should mutate result
Gate::after(function (User $user, string $ability, ?bool $result) {
    AuditLog::record($user->id, $ability, $result);
    return null;   // do not mutate
});
```

⚠️ Returning `true` in `before` bypasses **every** policy method — even ones a super-admin shouldn't bypass (PII, financial data). Tighten `before` when those exist:

```php
Gate::before(function (User $user, string $ability) {
    if (! $user->is_super_admin) {
        return null;
    }
    if (in_array($ability, ['view-pii', 'access-billing', 'export-data'])) {
        return null;   // require explicit Policy approval even for super-admin
    }
    return true;
});
```

## 3. Custom Policy methods

The default seven (`viewAny`, `view`, `create`, `update`, `delete`, `restore`, `forceDelete`) cover CRUD. Add domain-specific methods for richer operations:

```php
class PostPolicy
{
    public function publish(User $user, Post $post): bool   { /* ... */ }
    public function archive(User $user, Post $post): bool   { /* ... */ }
    public function transfer(User $user, Post $post, User $newOwner): bool { /* ... */ }
}
```

Invoke:

```php
$this->authorize('publish', $post);
$this->authorize('transfer', [$post, $newOwner]);   // multiple args via array
```

## 4. Authorize without a model

When the resource isn't a model — feature flags, regions, billing tiers — use a Gate:

```php
// AuthServiceProvider::boot()
Gate::define('access-region', function (User $user, string $regionCode) {
    return $user->permittedRegions->contains($regionCode);
});

// Anywhere
Gate::authorize('access-region', 'sa-east-1');
```

Or a "model-less" Policy method (Policy registered against a class but the method takes only `$user`):

```php
class BillingPolicy
{
    public function viewInvoice(User $user): bool
    {
        return $user->is_active;
    }
}
```

## 5. Multi-tenant authorization

Defense in depth — apply at two layers.

### 5.1 Layer 1: global scope (data isolation)

```php
class TenantScope implements Scope
{
    public function apply(Builder $b, Model $m): void
    {
        if ($tenantId = auth()->user()?->tenant_id) {
            $b->where("{$m->getTable()}.tenant_id", $tenantId);
        }
    }
}

class Post extends Model
{
    protected static function booted(): void
    {
        static::addGlobalScope(new TenantScope);
    }
}
```

### 5.2 Layer 2: Policy (explicit allow)

```php
class PostPolicy
{
    public function view(User $user, Post $post): bool
    {
        return $user->tenant_id === $post->tenant_id;
    }
}
```

Why both? The global scope prevents accidentally querying across tenants. The Policy enforces the rule even if the scope is bypassed (`withoutGlobalScope`, raw `DB::table` query, observer accessing the model directly).

⚠️ Anti-pattern: a Policy that trusts the global scope (`return true` in `view` because "the scope handles it"). The scope is a safety net, not the gate.

## 6. Row-level security via global scope — operational concerns

Global scopes use `auth()->user()`. Two contexts where that returns null:

### 6.1 Queue workers / jobs

Jobs run without an authenticated user. Either re-authenticate or pass the tenant explicitly:

```php
class ProcessPostJob implements ShouldQueue
{
    public function __construct(public int $postId, public int $tenantId) {}

    public function handle(): void
    {
        $post = Post::withoutGlobalScope(TenantScope::class)
            ->where('tenant_id', $this->tenantId)
            ->findOrFail($this->postId);

        // ... operate on $post ...
    }
}
```

### 6.2 Schedule / console commands

```php
// app/Console/Kernel.php (or routes/console.php in Laravel 11+)
Schedule::call(function () {
    Tenant::cursor()->each(function ($tenant) {
        Post::withoutGlobalScope(TenantScope::class)
            ->where('tenant_id', $tenant->id)
            ->where('archived_at', null)
            ->each(/* ... */);
    });
})->daily();
```

## 7. Spatie Permission integration

When `composer show spatie/laravel-permission` returns success, the project stores roles + permissions in DB.

Use Policies that delegate to permission checks rather than scattering role checks across the codebase:

```php
class PostPolicy
{
    public function update(User $user, Post $post): bool
    {
        return $user->can('posts.update') && $user->id === $post->user_id;
    }

    public function publishAny(User $user): bool
    {
        return $user->hasRole('editor');
    }
}
```

⚠️ Anti-pattern: `$user->hasRole('admin')` scattered through controllers and Blade templates. Wrap role/permission checks inside Policies and Gates so the abstraction layer remains stable when the role model evolves (e.g., adding a `pending-editor` intermediate role).

## 8. Sanctum token abilities — combining with Policies

Policies authorize the **user**. Token abilities authorize the **token**. For API endpoints, both must pass:

```php
public function update(UpdatePostRequest $r, Post $post): PostResource
{
    abort_unless($r->user()->tokenCan('posts:write'), 403);
    $this->authorize('update', $post);
    // ...
}
```

Token-only check (no Policy) via middleware:

```php
Route::put('/api/posts/{post}', [...])->middleware('abilities:posts:write');
```

For deeper Sanctum patterns — token creation, abilities design, machine-to-machine — see `laravel-auth`.

## 9. Inertia / forms — UX layer reflects authorization

The frontend hides controls the user can't use. **The server is source of truth** — never rely on the client for authorization.

```php
// HandleInertiaRequests::share()
public function share(Request $request): array
{
    $user = $request->user();
    return array_merge(parent::share($request), [
        'auth' => $user ? [
            'user' => $user->only('id', 'name'),
            'can'  => [
                'create_post' => $user->can('create', Post::class),
            ],
        ] : null,
    ]);
}
```

Frontend reads `auth.can.create_post` to show or hide a button. Submitting without permission still hits `$this->authorize()` server-side and returns 403.

## 10. Anti-patterns

| Smell | Why |
|---|---|
| `if ($user->role === 'admin')` scattered in controllers/Blade | Roles change; abstraction broken |
| `Gate::before` returning `true` unconditionally for super-admin | Bypasses every policy, even ones you'd want to audit |
| Policy returning `true` (placeholder forgotten) | Silent allow-all |
| Policy that calls `$user->can()` in a loop | N+1 of permission lookups |
| Authorize via `can:` middleware AND `$this->authorize()` for the same op | Duplicated; prefer `$this->authorize()` for visibility in tests |
| Bypass via `withoutGlobalScope` outside admin code, no audit trail | Tenant leakage |
| Global scope as the only gate | Bypassed by raw queries or observers; pair with Policy |
| Permission check on the frontend without server enforcement | Trivially defeated |
| Policy method assuming `$user` is non-null | Crashes for guests; check `$user` or use middleware |
