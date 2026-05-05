# Eloquent — Advanced Patterns

Depth on patterns that go beyond CRUD. Loaded by the agent when working with polymorphic relations, pivot models, recursive structures, JSON columns, or custom collections.

## 1. Polymorphic relationships

### 1.1 One-to-many polymorphic

A `Comment` belongs to either a `Post` or a `Video`. The `comments` table has `commentable_type` and `commentable_id`:

```php
// Migration
Schema::create('comments', function (Blueprint $t) {
    $t->id();
    $t->morphs('commentable');         // adds commentable_type + commentable_id + composite index
    $t->foreignId('user_id')->constrained()->cascadeOnDelete();
    $t->text('body');
    $t->timestamps();
});

// Comment
public function commentable(): MorphTo
{
    return $this->morphTo();
}

// Post
public function comments(): MorphMany
{
    return $this->morphMany(Comment::class, 'commentable');
}
```

### 1.2 Many-to-many polymorphic

A `Tag` may attach to `Post` or `Video`. Pivot table is named `taggables`:

```php
Schema::create('taggables', function (Blueprint $t) {
    $t->foreignId('tag_id')->constrained()->cascadeOnDelete();
    $t->morphs('taggable');
    $t->primary(['tag_id', 'taggable_id', 'taggable_type']);
});

// Post
public function tags(): MorphToMany
{
    return $this->morphToMany(Tag::class, 'taggable');
}

// Tag (reverse)
public function posts(): MorphToMany
{
    return $this->morphedByMany(Post::class, 'taggable');
}
```

### 1.3 Eager-loading polymorphic

```php
$comments = Comment::with('commentable')->get();

// Per-type eager load
$comments = Comment::with(['commentable' => function (MorphTo $morph) {
    $morph->morphWith([
        Post::class  => ['author'],
        Video::class => ['channel'],
    ]);
}])->get();
```

### 1.4 Morph map — decouple from class names

By default, `commentable_type` stores `App\Models\Post`. Renaming or moving the class breaks every existing row. Register a morph map in `AppServiceProvider::boot()`:

```php
Relation::enforceMorphMap([
    'post'  => Post::class,
    'video' => Video::class,
]);
```

The column now stores `post` / `video`. Refactors are safe; the database is independent of PHP class paths.

⚠️ Anti-pattern: deploying polymorphic relations without a morph map. Adding it later requires a data migration to rewrite every `*_type` value.

## 2. Pivot models

When the pivot table needs more than `withPivot()` and `withTimestamps()` — methods, casts, events — extract a pivot model.

```php
class Membership extends Pivot
{
    public $incrementing = true;          // when the pivot has its own id
    protected $casts = [
        'joined_at' => 'datetime',
        'role'      => MembershipRole::class,
    ];

    public function isOwner(): bool
    {
        return $this->role === MembershipRole::Owner;
    }
}

// User
public function organizations(): BelongsToMany
{
    return $this->belongsToMany(Organization::class)
        ->using(Membership::class)
        ->withPivot(['role', 'joined_at'])
        ->withTimestamps();
}
```

Access: `$user->organizations->first()->pivot->isOwner()`.

For polymorphic pivots, extend `MorphPivot` instead of `Pivot`.

## 3. Recursive / self-referential

Self-referencing tables (categories with parents, threaded comments) are easy to model but hard to query at depth.

```php
class Category extends Model
{
    public function parent(): BelongsTo
    {
        return $this->belongsTo(self::class, 'parent_id');
    }

    public function children(): HasMany
    {
        return $this->hasMany(self::class, 'parent_id');
    }
}
```

This handles a single level. For arbitrary depth without N+1, three approaches:

| Approach | Trade-off |
|---|---|
| Adjacency list + recursive CTE | Native (MySQL 8 / Postgres); deep traversals are expensive |
| Materialized path (`path = "1/4/12/"`) | Cheap reads; expensive moves |
| Nested set (`lft`, `rgt`) | Cheap reads; very expensive writes |

When the project already has `staudenmeir/laravel-adjacency-list` (`composer show staudenmeir/laravel-adjacency-list`), prefer it — it adds CTE-based recursive scopes (`->withRecursiveDescendants()`).

⚠️ Anti-pattern: recursive `with()` without depth guard — `Category::with('children.children.children...')` blows up. Cap depth or use a recursive package.

## 4. JSON columns

```php
// Migration
$t->json('settings')->nullable();

// Model
protected $casts = ['settings' => 'array'];

// Reading
$user->settings['theme'];

// Writing — replaces whole JSON
$user->settings = ['theme' => 'dark', 'tz' => 'America/Sao_Paulo'];
$user->save();

// Update single key (atomic at SQL level)
User::where('id', $id)->update(['settings->theme' => 'dark']);

// Querying
User::where('settings->theme', 'dark')->get();
User::whereJsonContains('settings->roles', 'admin')->get();
User::whereJsonLength('settings->tags', '>', 5)->get();
```

### Indexing JSON

- **Postgres** — functional index: `CREATE INDEX idx_users_theme ON users ((settings->>'theme'))`.
- **MySQL** — generated stored column then index it:
  ```sql
  ALTER TABLE users
    ADD theme VARCHAR(50) GENERATED ALWAYS AS (settings->>'$.theme') STORED,
    ADD INDEX idx_users_theme (theme);
  ```

⚠️ Anti-pattern: storing data in JSON that you query frequently. If `settings->theme` appears in every WHERE clause, promote it to a real column.

## 5. Custom collections

When operations on a result set repeat across the codebase, return a domain-specific collection instead of repeating helper methods.

```php
class PostCollection extends Collection
{
    public function totalReadingMinutes(): int
    {
        return (int) $this->sum(fn (Post $p) => str_word_count($p->body) / 200);
    }

    public function published(): self
    {
        return $this->filter->isPublished();
    }
}

// Post
public function newCollection(array $models = []): PostCollection
{
    return new PostCollection($models);
}

// Usage
Post::all()->published()->totalReadingMinutes();
```

## 6. Builder customizations

### 6.1 Macros

For one-off helpers shared across all builders:

```php
// AppServiceProvider::boot()
Builder::macro('whereLike', function (string $column, string $value) {
    return $this->where($column, 'like', "%{$value}%");
});

// Usage
Post::whereLike('title', 'laravel')->get();
```

### 6.2 Custom builder class

When you want first-class IDE support and discoverable model-specific methods:

```php
class PostBuilder extends Builder
{
    public function published(): self    { return $this->whereNotNull('published_at'); }
    public function popular(int $t = 100): self { return $this->where('views', '>', $t); }
}

class Post extends Model
{
    public function newEloquentBuilder($query): PostBuilder
    {
        return new PostBuilder($query);
    }
}
```

## 7. Batch operations

```php
// Insert without events (no created_at via Eloquent — set timestamps manually)
Post::insert([
    ['title' => 'A', 'body' => '...', 'created_at' => now(), 'updated_at' => now()],
    ['title' => 'B', 'body' => '...', 'created_at' => now(), 'updated_at' => now()],
]);

// Upsert — insert or update on unique key
Post::upsert(
    [['slug' => 'a', 'title' => 'A'], ['slug' => 'b', 'title' => 'B']],
    uniqueBy: ['slug'],
    update:   ['title'],
);

// Skip events for a block
Post::withoutEvents(function () use ($posts) {
    $posts->each->save();
});
```

⚠️ Anti-pattern: `insert()` for models that depend on observers/events (audit trail, cache invalidation) — they will not fire. Use `create()` in a loop or accept the loss of side effects.

## 8. Anti-patterns

| Smell | Why |
|---|---|
| Polymorphic relations without `enforceMorphMap` | Class rename breaks data |
| Recursive `with()` without depth cap | OOM / DB exhaustion |
| JSON column for fields used in every WHERE | Slow queries, awkward indexes |
| Mass assignment via JSON without internal validation | Same risk as `$request->all()` but harder to spot |
| `insert()` on a model with observers | Side effects silently skipped |
| Self-referential without recursion guard | Infinite parent traversal |
| Pivot model without `using()` declared on the relation | Pivot methods unreachable |
| Querying `whereJsonContains` on un-indexed JSON | Full table scan |
