# Applying the member-management migrations

Two new migrations ship the organization member management and in-app
join-request features:

| File | What it adds |
| ---- | ------------ |
| `database/migrations/015_member_management.sql` | The `organization_members_guard` trigger, the `organization_invitations` table + RLS, `leave_organization`, `accept_invitation`, `invitation_preview` |
| `database/migrations/016_invitation_requests.sql` | `declined` status, `my_pending_invitations`, `respond_to_invitation`, `search_invitable_users`, `resolve_invitable_email`, and a hardened guard trigger |

**Run 015 first, then 016.** Both are wrapped in a transaction and are
idempotent — re-running them is safe.

If this is a brand-new database, apply `001` … `014` first, in filename
order, as described in the README.

---

## Option A — Supabase SQL editor (most common)

1. Open your project → **SQL Editor** → **New query**.
2. Paste the entire contents of `database/migrations/015_member_management.sql`
   and click **Run**. Wait for "Success".
3. Repeat with `database/migrations/016_invitation_requests.sql`.

## Option B — `psql`

Use the **connection string** from Supabase → Settings → Database
(the *session* pooler or direct connection, not the transaction pooler —
these migrations create functions and triggers).

```bash
export DATABASE_URL='postgresql://postgres:<password>@<host>:5432/postgres'

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/015_member_management.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/016_invitation_requests.sql
```

`ON_ERROR_STOP=1` matters: without it `psql` would keep going after a
failed statement and leave the schema half-applied.

## Option C — Supabase CLI

```bash
supabase db push
```

---

## Verifying it worked

```sql
-- 1. Both new functions exist.
select proname
from pg_proc
where proname in (
    'guard_organization_members',
    'leave_organization',
    'accept_invitation',
    'invitation_preview',
    'my_pending_invitations',
    'respond_to_invitation',
    'search_invitable_users',
    'resolve_invitable_email'
)
order by proname;
-- expect 8 rows

-- 2. The invitations table exists with the declined status allowed.
select conname, pg_get_constraintdef(oid)
from pg_constraint
where conname = 'organization_invitations_status_check';
-- expect: CHECK (status IN ('pending','accepted','revoked','declined'))

-- 3. The guard trigger is attached.
select tgname
from pg_trigger
where tgrelid = 'public.organization_members'::regclass
  and not tgisinternal;
-- expect organization_members_guard (and the updated_at trigger)

-- 4. The invariant really holds (this MUST fail):
update public.organization_members
set role = 'admin'
where role = 'owner';
-- expect ERROR: An organization must always have at least one owner.
```

Step 4 is the important one — it proves the guard trigger is live.

---

## Notes

* **No data migration is needed.** Existing organizations and members are
  untouched; 015 only adds constraints, a table and functions.
* **Existing owners keep working.** The "at least one owner" rule is
  enforced going forward; every organization created by
  `create_organization` already has exactly one.
* **Rollback**, should you need it:

  ```sql
  drop trigger if exists organization_members_guard
    on public.organization_members;
  ```

  That disables the new enforcement while leaving the invitations table in
  place. Dropping the table (`drop table public.organization_invitations
  cascade;`) removes the invitation feature entirely.
* Nothing needs to change in `.env` — these features use the Supabase
  credentials the app already has.
