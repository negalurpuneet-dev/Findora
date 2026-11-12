# Findora

Findora is a Django local service finder for discovering nearby professionals and managing service requests. The application uses PostgreSQL, Django's built-in authentication, server-rendered HTML, local CSS, and lightweight vanilla JavaScript.

The project prompt attachment mentions a separate project specification PDF, but no PDF was present in the project. The categories currently suggested by the prompt are starter catalog entries; update them in Django admin to match the approved specification.

## Features

- Customer and provider registration, login, and role-aware dashboards.
- Admin-managed service categories and verified provider profiles.
- Search by provider/service, category, locality, experience, availability, and rating.
- Listing details and booking requests with preferred date, time, and location.
- Provider accept/reject, start, and completion workflow; customer cancellation.
- Database notifications, completed-booking reviews, and support complaints.
- Private, responsive Findora administration panel with real PostgreSQL-backed metrics and role-scoped management pages.
- Provider verification, category and listing management, customer accounts, booking workflow, review moderation, complaints, employee permissions, and read-only admin audit history.
- Responsive pages with local styles and no required third-party APIs.
- Responsive navigation, accessible search controls, provider management, and real-data dashboard summaries.

The frontend lives in `templates/core/`, `static/core/site.css`, and `static/core/site.js`; the hero illustration is a locally bundled SVG. Django searches the project `static/` directory via `STATICFILES_DIRS`. This setting is necessary for `runserver` to find the stylesheet and script; without it, page templates still render but asset requests return 404.

## Requirements

- Python 3.12 or later.
- PostgreSQL (the default database is `findora_db`).
- Django and a PostgreSQL driver, available in the Python environment.

No external maps, AI, payment, email, or SMS credentials are needed for core functionality. Email uses Django's console backend by default. Maps and payments are not implemented.

## Local setup

1. Create and activate a virtual environment if needed.
2. Install the project dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, then set `DJANGO_SECRET_KEY` and `DB_PASSWORD` for your local PostgreSQL installation. The settings loader reads `.env` and `.env.local`; both are excluded from Git.
4. Confirm PostgreSQL is running and that the configured user can access the existing `findora_db`. The application does not create, drop, or reset that database.
5. From the project directory, run:

   ```powershell
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver
   ```

6. Open <http://127.0.0.1:8000/> for the public website. The private staff sign-in is <http://127.0.0.1:8000/staff/login/>; the advanced Django admin is at <http://127.0.0.1:8000/admin/>.

## Private administration and team access

The public website starts at `/` and renders the home page for both signed-in and signed-out visitors. The administration panel is a separate interface at `/staff/login/` and `/staff/dashboard/`; its links do not appear on customer/provider pages. Unauthenticated `/admin/` requests also redirect to the private staff login. Customers and providers receive a forbidden response if they try to open private administration routes directly.

Create the primary owner account securely with `python manage.py createsuperuser`. Django prompts for the username and password; do not put credentials in source code or a command line. Sign in at `/staff/login/` (or the protected `/admin/`). The owner can open `/staff/team/` to create employee accounts, set initial credentials, assign only the required Findora view/add/change permissions, inspect last-login status, reset passwords, or deactivate accounts. There is no public administrator or employee registration. Employees are not superusers, cannot manage User or Group records, and must change their initial/reset password before accessing the panel. Passwords are stored using Django's configured hashers and never appear in the management interface.

Grant the dashboard permission separately from model permissions: analytics display database aggregates, while pages containing identifiable customer/provider/booking/review/complaint records require their corresponding model view permissions. Editing actions require the matching change/add permission. Only the primary superuser can manage employee accounts and activate/deactivate customer/provider accounts. Use a unique temporary password and provide it privately. To revoke access immediately, deactivate the employee from `/staff/team/`.

The admin dashboard includes live account, provider verification, catalog, booking, review, complaint, and active employee counts; 14-day booking activity; booking-state distribution; popular categories; and permission-gated recent queues. Dedicated pages provide search, filters, pagination, and empty states for categories, listings, providers, customers, bookings, reviews, and complaints. Booking state changes follow the existing allowed workflow and create immutable status-history records; administrative changes are recorded in a read-only audit log that never stores passwords.

Migrations `0003`–`0006` add the team-account controls, category icon identifiers, complaint resolution notes, booking status history, and admin audit log. They preserve existing records. Apply them with `python manage.py migrate`; do not reset the database.

The initial migration adds the suggested starter categories. Provider profiles are not publicly discoverable until an administrator verifies them. Administrators can edit or deactivate categories to align them with the approved specification.

## Faculty demonstration data

After applying migrations, populate the existing database without resetting it:

```powershell
python manage.py migrate
python manage.py seed_demo_data
```

The command creates or updates 20 demo customers, 12 verified demo providers and profiles, up to 8 missing suggested categories, 12 service listings, 35 bookings, 25 reviews for completed demo bookings, 32 notifications, and 4 complaints. Existing categories with the suggested names are reused and not rewritten. All account passwords are set with Django's password hashing. Demo login usernames are `demo_customer01` through `demo_customer20` and `demo_provider01` through `demo_provider12`; their shared demo-only password is `Findora-Demo-2026!`. Change these credentials or remove the demo accounts before using a publicly accessible deployment. Demo customer/provider accounts are not staff.

Seeded records have an `is_demo` marker and demo accounts use reserved usernames and `example.com` addresses. Phone numbers use fictional 202-555-01xx numbers. Provider image uploads are not supported by the current `ProviderProfile` model. The current booking workflow has no distinct `Scheduled` status: upcoming accepted bookings are displayed as scheduled work, so the seeder uses the existing `Accepted` status for that workflow.

Remove seeded data safely with:

```powershell
python manage.py remove_demo_data
```

Cleanup deletes only records marked as demo, preserves shared/pre-existing categories and all unmarked accounts, and stops before deletion if it finds unmarked records attached to demo accounts, listings, or bookings. The demo marker migration adds nullable-in-practice Boolean ownership flags with a `False` default; existing records are preserved and remain unmarked.

## Testing and checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

The configured database engine is PostgreSQL. Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in `.env` or the deployment environment. Production uses `DB_SSLMODE=require` by default; set it explicitly for Neon. Do not switch to SQLite to work around a PostgreSQL connection or migration error.

## Deploying to Vercel with Neon

Vercel automatically detects this Django project from `manage.py`, uses `config.wsgi:application`, and collects static files because `STATIC_ROOT` is configured. No separate `vercel.json`, API wrapper, or custom build command is required. `requirements.txt` already includes Django, the psycopg PostgreSQL driver, Gunicorn, and WhiteNoise. WhiteNoise remains enabled for local/`vercel dev` use; Vercel serves collected static assets from its CDN.

In the Vercel project settings, add these environment variables for the deployment environments you use:

- `DJANGO_SECRET_KEY`: a unique, long random secret; do not commit it.
- `DJANGO_DEBUG`: `False`.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`: the connection values from Neon.
- `DB_SSLMODE`: `require`.
- `DJANGO_ALLOWED_HOSTS`: optional comma-separated hostnames for any custom domains. Vercel's `VERCEL_URL` and `VERCEL_PROJECT_PRODUCTION_URL` are added automatically, along with this project's current Vercel hostname.
- `CSRF_TRUSTED_ORIGINS`: optional comma-separated HTTPS origins for custom domains (for example, `https://findora.example.com`). HTTPS origins for the detected Vercel deployment hostnames are added automatically.

The settings default to development mode on a regular local run, but default to `DEBUG=False` on Vercel and reject an explicit `DJANGO_DEBUG=True` there. Production startup also fails clearly if the secret key or required PostgreSQL variables are missing. `.env.local` is supported for local commands that use environment values pulled from Vercel; keep that file private.

Apply the existing migrations to Neon after configuring the Neon variables, for example by pulling them to `.env.local` and running `python manage.py migrate` once from a trusted local machine. This preserves existing records and creates only the tables/changes represented by migrations `0001`–`0007`. Do not run migrations as part of every Vercel build or reset the database. A successful local migration requires valid Neon credentials and network access; Django's system checks alone do not prove database connectivity.

The current models do not define file/image upload fields, so no media storage setting is needed. Vercel's function filesystem is ephemeral; if uploads are added later, store them in durable object storage rather than the local `media/` directory.

## Deployment notes

For Render or another HTTPS host:

- Set `DJANGO_DEBUG=False`, a unique `DJANGO_SECRET_KEY`, and the production hostname in `DJANGO_ALLOWED_HOSTS`.
- Set `CSRF_TRUSTED_ORIGINS` to comma-separated HTTPS origins.
- Set all `DB_*` variables to the managed PostgreSQL connection details; use `DB_SSLMODE=require` if the host requires TLS.
- Use `pip install -r requirements.txt && python manage.py collectstatic --noinput` as the build command, `python manage.py migrate` as the release command, and `gunicorn config.wsgi:application` as the start command.
- WhiteNoise serves compressed static assets.
- Use HTTPS and verify the production security checklist before accepting real users.

No live payment processing, map/geocoding, AI provider, external identity verification, or SMS integration is configured. The recommendation ordering is deterministic local logic based on locality when known, actual public ratings, and reviews.
