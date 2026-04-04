# Railway Deployment Guide

This project is deployed as two Railway services:

1. `drilling-api` (backend, Dockerfile in `backend/`)
2. `drilling-frontend` (frontend, Dockerfile in `frontend/`)

The database is PostgreSQL and can be fully copied with data from local to Railway.

## 1) Create Railway project and services

From project root:

```bash
railway init
```

Then create:
- One PostgreSQL service (`Add Service` -> `Database` -> `PostgreSQL`)
- One backend service (deploy from `backend/`)
- One frontend service (deploy from `frontend/`)

## 2) Backend service config

- Root directory: `backend`
- Build: Dockerfile (already included)
- Start command: handled by Docker `CMD` (`railway-start.sh`)

Required env vars in backend service:

- `DATABASE_URL` -> connect to Railway PostgreSQL
- `ENVIRONMENT=production`
- `DEBUG=False`
- `SECRET_KEY=<secure-random-value>`
- `CORS_ORIGINS=["https://<your-frontend-domain>"]`

`railway-start.sh` will automatically run:

```bash
alembic upgrade head
```

before starting the API.

## 3) Frontend service config

- Root directory: `frontend`
- Build: Dockerfile (already included)
- Env var:
  - `VITE_API_BASE_URL=https://<your-backend-domain>/api/v1`

After changing `VITE_API_BASE_URL`, redeploy frontend.

## 4) Copy full local DB (all tables + all rows) to Railway

This project includes:

- `backend/scripts/copy_database.py`

It copies all public tables in batches from source PostgreSQL to target PostgreSQL.

Run from `backend/`:

```bash
set SOURCE_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/drilling_db
set TARGET_DATABASE_URL=postgresql://<railway-user>:<railway-pass>@<railway-host>:<railway-port>/<railway-db>?sslmode=require
venv\Scripts\python.exe scripts\copy_database.py
```

Notes:
- It truncates target tables before copying.
- It preserves IDs and resets sequences.
- It is intended for initial full migration to Railway.

## 5) Verify

1. Open backend URL: `/docs` should load.
2. Open frontend URL and validate:
   - Wells list loads
   - Processed datasets load
   - Outlier/Wells/Comparison pages read data correctly

