# Drilling Data Visualization

Full-stack app for drilling data exploration:

- Wells dashboard
- Well logs
- Crossplots
- Comparison
- Quality report
- Outlier detection pipeline (scaling + PCA + anomaly labeling)

## Structure

- `backend/`: FastAPI + SQLAlchemy + Alembic
- `frontend/`: React + Vite + Recharts

## Local run

Backend:

```bash
cd backend
venv\Scripts\python.exe run.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Railway

Deployment steps and full database migration are documented in:

- [RAILWAY_DEPLOY.md](./RAILWAY_DEPLOY.md)

