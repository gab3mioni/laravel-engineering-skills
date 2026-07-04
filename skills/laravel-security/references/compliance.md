# Compliance — LGPD, GDPR, SOC 2, PCI, HIPAA

Regulatory requirements mapped to Laravel implementation. Loaded when implementing data subject rights, designing audit logs, or preparing for compliance review.

## 1. LGPD (Brazil) & GDPR (EU) — overlap

Both regulate personal data of individuals. ~80% overlap; differences mostly in penalty structure and authority.

### 1.1 Lawful basis

Every collection/processing of personal data requires a lawful basis. Common bases:
- **Consent** (explicit, granular, revocable)
- **Contract** (necessary to perform contract with the data subject)
- **Legitimate interest** (subject to balancing test against subject's rights)
- **Legal obligation**
- **Vital interests**
- **Public interest**

In Laravel, document the basis per data category:

```php
// config/privacy.php
return [
    'data_categories' => [
        'email' => ['basis' => 'contract', 'retention_days' => 1825],
        'phone' => ['basis' => 'consent', 'retention_days' => 365],
        'analytics' => ['basis' => 'legitimate_interest', 'retention_days' => 90],
    ],
];
```

### 1.2 Data subject rights

| Right | LGPD | GDPR | Implementation |
|---|---|---|---|
| Access | Art. 18 II | Art. 15 | Endpoint exporting all personal data |
| Rectification | Art. 18 III | Art. 16 | Standard update flow + audit |
| Deletion | Art. 18 VI | Art. 17 | Hard delete + cascade scrub |
| Portability | Art. 18 V | Art. 20 | Export in machine-readable format (JSON/CSV) |
| Restriction | Art. 18 IV | Art. 18 | Flag account read-only |
| Objection | Art. 18 § 2 | Art. 21 | Opt-out flow |
| Automated decision | Art. 20 | Art. 22 | Disclose logic; allow human review |

### 1.3 Implementing access (data export) in Laravel

```php
// Job that compiles user's personal data
class ExportUserDataJob implements ShouldQueue
{
    public function __construct(public int $userId) {}

    public function handle(): void
    {
        $user = User::with(['posts', 'comments', 'sessions'])->findOrFail($this->userId);

        $data = [
            'profile'    => $user->only(['name', 'email', 'phone', 'created_at']),
            'posts'      => $user->posts->map->toArray(),
            'comments'   => $user->comments->map->toArray(),
            'audit_log'  => ActivityLog::where('user_id', $user->id)->get(),
            'exported_at' => now()->toIso8601String(),
        ];

        $path = "exports/{$user->id}/" . Str::ulid() . '.json';
        Storage::disk('private')->put($path, json_encode($data, JSON_PRETTY_PRINT));

        $user->notify(new DataExportReady($path));
    }
}
```

### 1.4 Implementing deletion

True erasure means hard delete + scrub of cascading data:

```php
class DeleteUserDataJob implements ShouldQueue
{
    public function __construct(public int $userId) {}

    public function handle(): void
    {
        DB::transaction(function () {
            $user = User::findOrFail($this->userId);

            // 1. Anonymize references that must remain (e.g., for legal/financial integrity)
            $user->orders()->update([
                'email' => "deleted-{$user->id}@example.invalid",
                'name'  => '[deleted user]',
            ]);

            // 2. Hard delete content
            $user->posts()->forceDelete();
            $user->comments()->forceDelete();

            // 3. Scrub PII from audit log (keep the event, remove identifying fields)
            ActivityLog::where('user_id', $user->id)->update([
                'subject_id'   => null,
                'description'  => '[user deleted]',
                'properties'   => null,
            ]);

            // 4. Hard delete the user
            $user->forceDelete();
        });

        // 5. Trigger external scrubs
        SearchIndexService::deleteUser($this->userId);
        EmailServiceProvider::removeContact($this->userId);
        AnalyticsProvider::deleteUser($this->userId);
    }
}
```

⚠️ **Anti-pattern:** soft-delete only. The data persists; `withTrashed()` reads it. Soft delete is *not* erasure.

### 1.5 Retention

Define retention per data category. Run a scheduled job to enforce:

```php
// routes/console.php — Laravel 11+ has no Console Kernel
Schedule::command('privacy:enforce-retention')->daily();

class EnforceRetentionCommand extends Command
{
    protected $signature = 'privacy:enforce-retention';

    public function handle(): int
    {
        $config = config('privacy.data_categories');

        // Example: delete inactive users after 5 years
        User::where('last_login_at', '<', now()->subDays($config['email']['retention_days']))
            ->whereDoesntHave('orders', fn ($q) => $q->where('created_at', '>', now()->subYears(5)))
            ->cursor()
            ->each(fn ($u) => DeleteUserDataJob::dispatch($u->id));

        return self::SUCCESS;
    }
}
```

### 1.6 Breach notification

| Regulation | Window | Notify |
|---|---|---|
| LGPD | "Reasonable time" (commonly interpreted as 72h) | ANPD + affected subjects |
| GDPR | 72h | DPA + affected subjects (when high risk) |

Have the runbook ready. Document:
- What was breached (data categories, records affected)
- Timeline
- Containment actions taken
- User-facing communication

---

## 2. SOC 2

Audit framework for service organizations, organized into Trust Services Criteria (TSC):

| Criterion | Focus |
|---|---|
| Security | Common Criteria — required |
| Availability | Uptime, DR |
| Processing Integrity | Data is processed completely, accurately, timely |
| Confidentiality | Sensitive data protected |
| Privacy | PII handled per privacy notice |

### 2.1 Common Criteria controls (mapped to Laravel)

| Control area | Laravel mechanisms |
|---|---|
| Logical access | Auth (Sanctum/Fortify), Policies, Gates, role/permission |
| Change management | Git + PR review + CI; Pint/Larastan/tests as gates |
| Vulnerability management | `composer audit`, `npm audit`, Dependabot, scheduled pen tests |
| Audit logging | `LogsActivity` (Spatie) or custom audit log table; immutable |
| Incident response | Documented runbook; postmortems; alerting on auth failures |
| Backups | DB backups; tested restores; offsite |
| Encryption | `encrypt()`, encrypted casts, TLS, encrypted backups |

### 2.2 Type 1 vs. Type 2

- **Type 1**: design of controls at a point in time
- **Type 2**: controls operating effectively over a period (typically 6-12 months)

Type 2 requires *evidence* that controls ran consistently — logs, audit trails, ticket records.

---

## 3. PCI-DSS — payment card data

When the app handles credit card data:

### 3.1 Scope reduction (preferred)

Don't handle cards. Use a tokenizing provider (Stripe, Adyen, Pagar.me, Cielo). The card never touches your servers.

```javascript
// Frontend posts to Stripe directly; gets a token
stripe.createPaymentMethod({ type: 'card', card: cardElement })
    .then(({ paymentMethod }) => {
        // Send token (paymentMethod.id) to your server, NOT the card
        fetch('/api/charges', { body: JSON.stringify({ token: paymentMethod.id }) });
    });
```

In Laravel:

```php
// Receive token, never card
public function charge(Request $request)
{
    $token = $request->input('token');           // safe
    Stripe\Charge::create([
        'amount' => 1000,
        'currency' => 'brl',
        'source' => $token,
    ]);
}
```

### 3.2 If you must handle PAN

Full PCI-DSS scope kicks in. Common requirements:
- Network segmentation (cardholder data environment isolated)
- Strong cryptography (FIPS 140-2 modules)
- Quarterly external scans (ASV)
- Annual pen test
- 12 control areas, 250+ requirements

Realistically: don't. Use tokenization.

---

## 4. HIPAA — US health data

When the app handles Protected Health Information (PHI):

### 4.1 Required mechanisms

| Requirement | Implementation |
|---|---|
| Access control | Auth + Policies; unique user IDs; auto-logoff |
| Audit log | Every PHI access logged with user, timestamp, action |
| Integrity | Tamper detection on audit log (hash chain) |
| Encryption | At rest + in transit |
| Backup + DR | Tested; offsite; encrypted |

### 4.2 BAA (Business Associate Agreement)

Every subprocessor handling PHI signs a BAA. AWS, GCP, Azure offer HIPAA-eligible services with BAA. Free email (SendGrid free tier, Mailgun free tier) typically does NOT cover HIPAA.

### 4.3 Minimum necessary

Access PHI only to the extent necessary. Implement field-level Policies (PHI fields hidden unless caller has explicit authorization).

---

## 5. Audit log — design for compliance

Required by all of LGPD, GDPR, SOC 2, PCI-DSS, HIPAA. Design once, satisfy multiple regulations.

### 5.1 Schema

```php
Schema::create('audit_log', function (Blueprint $t) {
    $t->ulid('id')->primary();
    $t->timestampTz('happened_at')->index();
    $t->foreignId('actor_id')->nullable()->constrained('users')->nullOnDelete();
    $t->string('actor_type')->nullable();         // 'user', 'system', 'api_token'
    $t->string('event');                           // 'user.login', 'post.published'
    $t->string('subject_type')->nullable();
    $t->ulid('subject_id')->nullable();
    $t->json('properties')->nullable();
    $t->ipAddress('ip');
    $t->string('user_agent', 512)->nullable();
    $t->string('hash', 64);                        // for chain integrity
});
```

### 5.2 Immutability

Audit table should be append-only:

```sql
-- DB-level: revoke UPDATE/DELETE from app user
REVOKE UPDATE, DELETE ON audit_log FROM app_user;
```

Or in Laravel via observer (defense in depth):

```php
class AuditLogObserver
{
    public function updating(AuditLog $log): bool { return false; }
    public function deleting(AuditLog $log): bool { return false; }
}
```

### 5.3 Hash chain (tamper-evident)

```php
$previousHash = AuditLog::latest('happened_at')->value('hash') ?? str_repeat('0', 64);
$currentHash  = hash('sha256', $previousHash . json_encode($payload));

AuditLog::create([
    'id'           => Str::ulid(),
    'happened_at'  => now(),
    /* ... */
    'hash'         => $currentHash,
]);
```

Verification job: walk the chain, recompute each hash, alert on mismatch.

### 5.4 Retention

| Regulation | Audit retention |
|---|---|
| LGPD | Often 5 years for sensitive operations; varies by category |
| GDPR | "As long as necessary"; commonly 6 years |
| SOC 2 | 1 year minimum; 3 years common for evidence |
| PCI-DSS | 1 year minimum, 3 months immediately accessible |
| HIPAA | 6 years |

Use the longest applicable. Move older logs to cheaper storage (S3 Glacier).

---

## 6. Encryption strategy

### 6.1 At rest

| Layer | Mechanism |
|---|---|
| Disk (whole-DB) | RDS encryption, GCP Cloud SQL encryption |
| Column-level | Laravel `encrypted` cast for sensitive columns (SSN, MRN) |
| File storage | S3 SSE-S3 / SSE-KMS |
| Backups | Encrypted destination |

### 6.2 In transit

| Path | Mechanism |
|---|---|
| Client → app | TLS 1.2+ enforced; HSTS |
| App → DB | TLS to RDS / Cloud SQL |
| App → external API | HTTPS only |
| App → queue/cache | TLS where supported (Redis 6+) |

### 6.3 Key management

- **Application keys** (`APP_KEY`): rotate quarterly; re-encrypt data on rotation
- **DB encryption keys**: managed by cloud provider (AWS KMS, GCP Cloud KMS)
- **TLS certificates**: auto-renew via ACME (Let's Encrypt) or managed cert service

---

## 7. Compliance anti-patterns

| Smell | Why |
|---|---|
| Soft delete used as "erasure" | Data still readable; LGPD/GDPR violation |
| Audit log mutable (UPDATE/DELETE allowed) | Attacker erases tracks; compliance fail |
| PII in application logs | Violates privacy notice; expands breach scope |
| `APP_KEY` shared across environments | Dev leak compromises prod-encrypted data |
| BAA-required subprocessor without BAA | HIPAA violation |
| No retention enforcement | Data accumulates beyond stated retention; legal risk |
| Card data on your servers | Massive PCI scope; tokenize instead |
| Privacy policy promises X, code does Y | Regulatory + reputational risk |
| Audit log retained < legal minimum | Compliance fail at audit |
| No breach notification runbook | First breach = panicked, slow, non-compliant response |
