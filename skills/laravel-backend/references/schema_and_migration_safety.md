# Schema Design & Migration Safety

How to design schema and run migrations safely against a live app. Loaded when designing tables, choosing index strategy, or modifying schema in production.

## 1. Index strategy

| Index type | Use case | Example |
|---|---|---|
| Single column | Equality / range on one column | `index('email')` |
| Composite | Multi-column WHERE or WHERE + ORDER | `index(['user_id', 'created_at'])` |
| Unique | Enforce uniqueness | `unique(['email'])`, `unique(['user_id', 'role_id'])` |
| Partial / filtered (Postgres) | Subset of rows only | `WHERE status = 'active'` |
| Covering (`INCLUDE` in Postgres) | Avoid table lookup | Index covers all columns in SELECT |
| Functional / expression | On expression / JSON path | `(LOWER(email))`, `(settings->>'theme')` |

### Composite-index column order

Rule: **most-selective first**, then the column used for ORDER BY. For

```sql
SELECT * FROM posts WHERE user_id = ? AND status = 'published' ORDER BY created_at DESC
```

best index is `(user_id, status, created_at)` — `user_id` is most selective, `status` filters further, `created_at` enables index-backed ordering.

### Trade-offs

Indexes speed reads but slow writes (every INSERT/UPDATE updates each index). Don't index:
- Tables with very few rows (< ~1000)
- Write-dominated logging tables
- Columns rarely used in WHERE / JOIN / ORDER BY

## 2. Foreign key cascade choices

```php
$t->foreignId('user_id')->constrained()->cascadeOnDelete();   // delete posts when user deleted
$t->foreignId('user_id')->constrained()->restrictOnDelete();  // prevent user delete if posts exist
$t->foreignId('user_id')->constrained()->nullOnDelete();      // null out posts.user_id on user delete
```

| Cascade | When |
|---|---|
| `cascadeOnDelete` | Composition — child cannot exist without parent (PostMeta → Post) |
| `restrictOnDelete` | Default safe — parent deletion becomes an explicit decision |
| `nullOnDelete` | Optional reference — child survives parent (Comment.author_id where comments outlive author) |

### Cascade in large tables

`cascadeOnDelete` on a parent with millions of children locks all child rows for the duration of the delete. For high-volume parents:

1. Use `restrictOnDelete` or `nullOnDelete`
2. Build an explicit "delete parent + children" job that deletes children in chunks
3. Then delete the parent

## 3. JSON columns vs side tables

| Use JSON when | Use side table when |
|---|---|
| Schema is sparse (rows have different keys) | Schema is consistent across rows |
| Queries by these fields are rare | Queries by these fields are frequent |
| Field set evolves frequently | Field set is stable |
| You need atomic updates of partial keys | You need foreign keys, indexes, joins |

A common hybrid: store everything in JSON, then **promote** hot fields to real columns when query patterns stabilize. (See `eloquent_advanced.md` §4 for JSON indexing.)

## 4. Soft deletes

```php
class Post extends Model
{
    use SoftDeletes;
}

// Migration
$t->softDeletes();   // adds nullable deleted_at
```

Trade-offs:
- Every query implicitly filters `WHERE deleted_at IS NULL` (global scope)
- "Deleted" data still occupies storage; queryable via `withTrashed()`
- Index every column that joins/filters along with `deleted_at` (composite)

⚠️ Soft delete is **not** a security feature. Sensitive data should be removed (or anonymized) on real deletion, not soft-deleted.

When **hard delete + audit log** wins:
- Compliance requires actual erasure (LGPD/GDPR right-to-be-forgotten)
- Storage cost matters at scale
- The "undo" use case is rare in practice

## 5. Zero-downtime migrations

Production migrations run while traffic flows. Three patterns cover most needs.

### 5.1 Adding a NOT NULL column

Three deploys:

1. **Migration A** — add column nullable, with default if applicable
2. **Backfill** — populate existing rows in batches
3. **Migration B** — alter to NOT NULL

```php
// Migration A
Schema::table('users', fn ($t) => $t->string('country', 2)->nullable());

// Backfill (artisan command — see §6)
User::whereNull('country')->chunkById(1000, function ($users) {
    $users->each->update(['country' => 'BR']);
});

// Migration B
Schema::table('users', fn ($t) => $t->string('country', 2)->nullable(false)->change());
```

### 5.2 Renaming a column

Three deploys:

1. **Add new column** — migration adds `email_address`; code writes to both
2. **Backfill** — copy values; code reads from new
3. **Drop old column** — migration drops `email`

### 5.3 Changing column type

1. Add shadow column (e.g., `amount_v2 DECIMAL(10,2)`)
2. Backfill from old
3. Cut over reads to new column
4. Drop old column in next release

### 5.4 Adding an index on a large table

| DB | Approach |
|---|---|
| Postgres | `CREATE INDEX CONCURRENTLY` — non-blocking, slower |
| MySQL 5.6+ | `ALTER TABLE ... ALGORITHM=INPLACE, LOCK=NONE` |
| MySQL with pt-online-schema-change | External tool, copies table |

Do not run `Schema::table` with a plain `index()` on a multi-million-row table during traffic — it locks writes.

## 6. Backfilling in batches

```php
class BackfillCountryCommand extends Command
{
    protected $signature = 'backfill:country {--batch=1000} {--sleep=100}';

    public function handle(): int
    {
        User::whereNull('country')->chunkById(
            (int) $this->option('batch'),
            function ($users) {
                $users->each(fn ($u) => $u->update(['country' => $this->infer($u)]));
                usleep((int) $this->option('sleep') * 1000);   // throttle
            }
        );
        return self::SUCCESS;
    }
}
```

- **Idempotent** — `whereNull('country')` skips already-backfilled rows
- **Throttled** — `usleep` between batches prevents read-replica lag
- **Resumable** — `chunkById` continues from the last seen ID after a crash

## 7. Naming conventions

| Element | Convention | Example |
|---|---|---|
| Table | plural snake_case | `blog_posts` |
| Primary key | `id` | |
| Foreign key | `<singular>_id` | `user_id`, `blog_post_id` |
| Pivot table | alphabetical singulars | `post_tag`, `role_user` |
| Polymorphic | `<name>_type`, `<name>_id` | `commentable_type`, `commentable_id` |
| Boolean | `is_*`, `has_*`, `can_*` | `is_active`, `has_avatar` |
| Timestamp | `<verb>_at` | `published_at`, `archived_at` |
| Counter | `<noun>_count` | `comments_count` (`withCount` writes here) |

## 8. Multi-DB compatibility

When the project may run on MySQL, Postgres, and SQLite (CI test):

| Feature | Cross-DB safe? |
|---|---|
| `json` column type | Yes (SQLite has JSON1) |
| `jsonb` (Postgres) | No — Postgres only |
| `ulid` | Yes (Laravel emulates) |
| `uuid` | Yes |
| `geography` | No — extension-specific |
| Generated columns | Yes (newer versions) |
| Functional indexes | Mostly yes |
| `LATERAL` joins | Postgres only |
| `RETURNING` clause | Postgres only |

Stick to the lowest common subset unless the app is committed to a single DB.

## 9. Anti-patterns

| Smell | Why |
|---|---|
| `down()` deleting data via `delete()`/`truncate()` | Loses data on rollback |
| Migration that mutates business data | Should be a job/command, not a migration |
| `DROP COLUMN` in one deploy | Code still reading it crashes |
| Plain `Schema::table` to add index on multi-million-row table | Locks writes |
| `foreignId('x')` without `->constrained()` | FK not enforced — orphans accumulate |
| `cascadeOnDelete` on a parent with millions of children | Lock contention |
| `softDeletes` as a security mechanism | Data still readable via `withTrashed()` |
| Renaming column in one migration | Crashes inflight requests |
| Using `string()` without explicit length | DB-specific default; surprises in migrations across environments |
| Backfill without throttle | Saturates replicas, induces lag |
