# Russian Market

Flask website with:

- Login and account creation page matching the supplied Russian Market image.
- One login page for user login, account creation, and admin login.
- Profile name during account creation; the dashboard shows the profile name after login.
- Mobile-first card shop based on the supplied video.
- User balance, history, deposit history, transaction ID submission, purchases, and approved card details.
- Admin panel for product/card uploads/details, payment method adding, deposit approvals, order approvals, and user list.
- Admin panel can change the admin username and password; after a change, the old credentials no longer work.
- Card upload images are stored in the database, so Render redeploys do not remove uploaded product images when `DATABASE_URL` is set.
- Neon Postgres support through `DATABASE_URL`, with SQLite fallback for local testing.

## Run

```powershell
cd "C:\Users\IBRAHIM PRODHAN\Documents\New project\russian-market-site"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

Admin panel: `http://127.0.0.1:5000/admin/login`

Default admin credentials in `.env.example`:

- Username: `admin`
- Password: `admin123`

For Neon, set `DATABASE_URL` in `.env` to your Neon pooled Postgres connection string.

## Render

Render settings:

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Python Version: `3.13`

Environment variables to set in Render:

- `SECRET_KEY`
- `PYTHON_VERSION=3.13`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `DATABASE_URL`

Use a Neon pooled Postgres URL for `DATABASE_URL`; Render's filesystem is not meant for permanent SQLite data.
