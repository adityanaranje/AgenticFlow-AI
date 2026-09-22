# Applying the member-management migrations

Two new migrations ship the organization member management and in-app
join-request features:

| File | What it adds |
| ---- | ------------ |
| `database/migrations/015_member_management.sql` | The `organization_members_guard` trigger, the `organization_invitations` table + RLS, `leave_organization`, `accept_invitation`, `invitation_preview` |
| `database/migrations/016_invitation_requests.sql` | `declined` status, `my_pending_invitations`, `respond_to_invitation`, `search_invitable_users`, `resolve_invitable_email`, and a hardened guard trigger |
| `database/migrations/017_member_profiles_visibility.sql` | Lets members see each other's profiles — **required**, or the members list renders empty |
| `database/migrations/018_member_profile_relationship.sql` | Adds the `organization_members -> profiles` foreign key PostgREST needs to embed profiles — **required**, or the members list renders empty |

**Run 015, 016, 017, then 018.** All four are wrapped in a transaction and are
idempotent — re-running them is safe.

If this is a brand-new database, apply `001` … `014` first, in filename
order, as described in the README.

---

## Option A — Supabase SQL editor (most common)

1. Open your project → **SQL Editor** → **New query**.
2. Paste the entire contents of `database/migrations/015_member_management.sql`
   and click **Run**. Wait for "Success".
3. Repeat with `database/migrations/016_invitation_requests.sql`.
4. Repeat with `database/migrations/017_member_profiles_visibility.sql`.
5. Repeat with `database/migrations/018_member_profile_relationship.sql`.

> **Members list showing "No members yet"?** You need **both** 017 and
> 018 — they fix two separate causes of the same symptom:
>
> * **018** adds the foreign key `organization_members.user_id ->
>   profiles.id`. PostgREST resolves the embedded `profiles(...)` through
>   a foreign key, and there was none (only one to `auth.users`), so the
>   request failed outright and the roster looked empty *even to the
>   owner*.
> * **017** relaxes `profiles` RLS, which previously exposed only your
>   own row — so once the embed worked, every *other* member still
>   dropped out.

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

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/017_member_profiles_visibility.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/018_member_profile_relationship.sql
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
    'resolve_invitable_email',
    'shares_organization_with'
)
order by proname;
-- expect 9 rows

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

-- 4. Members can see each other (fixes the empty roster).
select polname
from pg_policy
where polrelid = 'public.profiles'::regclass
order by polname;
-- expect profiles_select_co_member among them

-- 5. PostgREST can embed a member's profile (fixes the empty roster).
select con.conname
from pg_constraint con
join pg_class src on src.oid = con.conrelid
join pg_class tgt on tgt.oid = con.confrelid
where con.contype = 'f'
  and src.relname = 'organization_members'
  and tgt.relname = 'profiles';
-- expect organization_members_user_id_profile_fkey

-- 6. The invariant really holds (this MUST fail):
update public.organization_members
set role = 'admin'
where role = 'owner';
-- expect ERROR: An organization must always have at least one owner.
```

Step 6 is the important one — it proves the guard trigger is live.

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
