# ShopAssist: Milestone 3 Spec (Admin Role)

## Goal
Users have a role: customer or admin. Admins (the store owner and staff)
can see all conversations, users, and the knowledge base through admin only
endpoints. Customers can never reach them. This protects the upload
endpoints that come in Milestone 4.

## In scope
- A role on every user
- A require_admin dependency built on get_current_user
- A command to promote or demote a user
- Read only admin endpoints
- A log line for every admin request
- Tests, README, deployment

## Out of scope
Uploads (Milestone 4), the admin dashboard interface (Milestone 6),
email verification, multiple stores, audit logs (a stored history of admin
actions), editing or deleting customer data.

## Data model
users gains:
- role: "customer" or "admin", not null, default "customer",
  enforced by a CHECK constraint named ck_users_role_valid (the same naming
  as the existing ck_messages_role_valid)
The migration must set existing users to "customer".

## Rules
- Registration always creates a customer. Any role sent in the register
  request is ignored.
- The role is NOT stored in the JWT. get_current_user already loads the
  user from the database on every request, so require_admin checks the
  role there. Promoting or demoting someone takes effect on their next
  request, without logging in again.
- No token: 401 (with the WWW-Authenticate: Bearer header, as now). Valid
  token but not an admin: 403 "Admin access required", with no
  WWW-Authenticate header (that header only means "not logged in").
- /auth/me also returns the user's role.
- Admins are still users: they can use the normal conversation and chat
  endpoints for themselves.

## Promoting an admin
A command: python -m app.cli.users promote <email>, and demote <email>.
- It only changes users who already exist; it never creates accounts.
  An unknown email is reported clearly and changes nothing.
- Before changing anything, it prints which database it is connected to
  (host and database name, never the password) and asks for confirmation,
  so a user is never promoted on the wrong database by accident. A --yes
  flag skips the question, for scripts and tests.
- It prints the result clearly, including when nothing needed changing
  (already an admin, already a customer).
- Demoting the last admin is allowed (an admin can always be promoted again
  from the command line), but it prints a warning that no admins are left.
- Known limitation: there is no email verification yet, so anyone could
  register with any email. The admin must register their own account
  before promoting it.

### Running it against production (Neon)
The command runs on the store owner's machine against the Neon database,
with DATABASE_URL passed for that one command only. It must never be saved
in a file, and that includes the shell history: typing the URL into a
command line would save the password in the history file. The README
explains this pattern:

    read -rs NEON_URL      # paste the Neon connection string; not shown, not saved
    docker compose run --rm --no-deps -e DATABASE_URL="$NEON_URL" api \
        python -m app.cli.users promote owner@example.com
    unset NEON_URL

The command shows the Neon host before asking for confirmation, so it is
clear which database is about to change.

## Admin endpoints (all require admin)
- GET /admin/users: list users (id, email, role, created_at), with
  pagination
- GET /admin/conversations: list all conversations, newest first, with
  owner email and message count; optional filter by user id; pagination.
  Filtering by a user id that does not exist returns an empty list, not
  404 (it is a filter, not a lookup).
- GET /admin/conversations/{id}/messages: any conversation's messages,
  oldest first (404 if it does not exist)
- GET /admin/knowledge/documents: knowledge documents with title, source,
  chunk count, the embedding model(s) used by its chunks (a list, since a
  document can be part way through a re-embed), a stale flag when any of
  them differs from EMBEDDING_MODEL, and updated time
- GET /admin/stats: totals for users, conversations, messages, documents,
  and chunks

Pagination: limit (default 20, maximum 100) and offset. A limit over 100
is rejected with 422 (FastAPI's normal validation), not silently capped.
List endpoints return:

    {"items": [...], "total": N, "limit": 20, "offset": 0}

so an admin knows how many pages there are. Never return an unbounded
list.

## Logging
Every admin request writes one log line with the admin's user id, the
method, and the path. Never request bodies, message content, or customer
data. This is a log line, not a stored audit log (which stays out of
scope).

## Privacy
Admins can read customers' conversations. That's expected for a store's
support team, and the README says so plainly. Password hashes are never
returned by any endpoint, admin or not.

## Tests (minimum)
- A customer gets 403 on every admin endpoint; no token gets 401
- An admin gets 200 on every admin endpoint
- Register ignores a role sent in the request
- Promoting a user gives admin access on the next request without a new
  token; demoting removes it
- Pagination: a limit over 100 is rejected with 422; total, limit and
  offset are returned
- Admin responses never include password hashes

## Build order
1. Role column and migration, require_admin (with the admin request log
   line), role in /auth/me, the promote and demote command (with the
   database host check, confirmation and last admin warning)
2. Admin endpoints
3. Tests, README (including the production promote pattern and fixing the
   roadmap's milestone numbering: uploads are Milestone 4, the dashboard
   Milestone 6), deploy, and promoting my account on Neon
