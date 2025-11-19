# AI Innovation Lab Grading

A lightweight patient communication transcript grader. The React frontend (hosted on GitHub Pages) lets faculty upload a transcript plus a rubric PDF, and the FastAPI backend (hosted on Render) parses the rubric, scores the transcript against each criterion, and stores the results in PostgreSQL so that graders or students can review past runs.

## Tech stack

- **Frontend:** React + Vite, deployed via GitHub Pages (`frontend/`)
- **Backend:** FastAPI, SQLAlchemy, and pypdf for PDF parsing (`backend/`)
- **Database:** PostgreSQL on Render (falls back to local SQLite for development)
- **Automation:** GitHub Actions workflow that builds the frontend and publishes it to Pages on every push to `main`

The `evaluate_pdf_transcripts.py` script in the repo documents a multi-stage workflow that inspired the scoring pipeline implemented in the backend services.

## Repository layout

```
backend/
  app/
    config.py           # Pydantic settings pulled from environment variables
    database.py         # SQLAlchemy engine + session helpers
    main.py             # FastAPI app and API routes
    models.py           # Evaluation + CriterionScore ORM models
    schemas.py          # Pydantic response models
    services/
      rubric_parser.py  # Extract rubric text from PDF
      scoring.py        # Simple keyword-based scoring + summaries
  requirements.txt      # Backend dependencies
  .env.example          # Sample backend configuration
frontend/
  src/                  # React application
  vite.config.js        # Configured for GitHub Pages base path
  package.json
  .env.example          # Sample frontend configuration
.github/workflows/deploy-frontend.yml  # GitHub Pages workflow
```

## Local development

### Backend

```bash
# Make sure you're on Python 3.11 (see `.python-version`).
# If `python3` points at another version, run `pyenv local 3.11.9`
# in the repo root or install Homebrew's python@3.11 and call python3.11.
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # tweak APP_DATABASE_URL if needed
uvicorn app.main:app --reload --port 8000
```

Using Python 3.13+ will force `psycopg2-binary` to compile from source and
currently fails, which is why the repo pins 3.11.9. `uvicorn` is included in
`requirements.txt`, so you do not need to install it with Homebrew once the
virtualenv is active.

Key environment variables (defined in `.env`):

- `APP_DATABASE_URL`: Defaults to `sqlite:///./grader.db` for local dev. Point it to your PostgreSQL URL in production.
- `APP_ALLOWED_ORIGINS`: JSON list of URLs that may call the API (e.g. `["http://localhost:5173"]`).
- `APP_SHARE_RESULTS_DEFAULT`: Optional boolean default for the UI toggle.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
# Set VITE_API_BASE_URL to wherever FastAPI is running
npm run dev
```

`VITE_API_BASE_URL` should be `http://localhost:8000` for local dev and switched to your Render backend URL before building for production.

### Quick API overview

- `POST /api/evaluations`: multipart form (transcript text + rubric PDF + optional `share_with_student`). Returns stored evaluation with per-criterion scores and generated feedback.
- `GET /api/evaluations`: Paginated list of recent evaluations (defaults to 10, max 50).
- `GET /api/evaluations/{id}`: Full evaluation payload including criterion breakdown.
- `GET /api/health`: Liveness probe for Render.

## Render deployment guide

Render currently defaults new Python services to 3.13.x, which breaks the SQLAlchemy version in this repo. The `.python-version` file in the repo root pins deployments to 3.11.9. If you rename or remove it, set the `PYTHON_VERSION` env var on Render instead.

1. **Push the repository to GitHub** so Render can pull from `main`.
2. **Create a PostgreSQL instance on Render** (Free tier is fine to start). Copy the *External Database URL* and the *Internal Database URL*; you can use either, but the internal URL avoids public traffic when the backend is on Render too.
3. **Provision the backend web service:**
   - Service type: `Web Service`
   - Name: `ai-innovation-lab-grading` (or similar)
   - Branch: `main`
   - Region: keep `Oregon (US West)` to match the DB
   - Root Directory: `backend`
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Instance type: start with **Starter** for reduced cold starts; Free tier also works if occasional spin-downs are acceptable.
4. **Environment variables (Render dashboard → Environment):**
   - `APP_DATABASE_URL`: paste your Render PostgreSQL URL, but ensure it starts with `postgresql+psycopg2://` so SQLAlchemy loads the correct driver.
   - `APP_ALLOWED_ORIGINS`: `["https://yannhicke.github.io", "https://yannhicke.github.io/AI_Innovation_Lab_Grading"]` so the static site can call the API.
   - `APP_SHARE_RESULTS_DEFAULT`: `true` or `false` depending on whether sharing with students should be checked by default.
   - (Optional) `PORT`: Render sets this automatically, but defining it keeps local parity.
5. **Link the database to the service** (Render UI → *Add Environment Variable From Service* → choose the PostgreSQL instance) so that `APP_DATABASE_URL` always stays in sync when credentials rotate.
6. Click **Create Web Service**. Render will build the backend and expose a URL such as `https://ai-innovation-lab-grading.onrender.com`. Use that URL for your frontend `VITE_API_BASE_URL`.

## Frontend deployment (GitHub Pages)

The workflow in `.github/workflows/deploy-frontend.yml` handles building and publishing the site.

1. In the GitHub repository, go to **Settings → Pages** and set the source to **GitHub Actions**.
2. Add a repository secret named `VITE_API_BASE_URL` that points to your Render backend URL (e.g. `https://ai-innovation-lab-grading.onrender.com`). This is injected during the build so the static bundle calls the production API.
3. Push changes to `main`. The workflow will:
   - Install frontend dependencies
   - Run `npm run build` with the GitHub Pages base path
   - Upload `frontend/dist` as an artifact and deploy it to Pages (`https://yannhicke.github.io/AI_Innovation_Lab_Grading/`).

If you ever want to deploy manually, run `npm run build && npm run deploy` from `frontend/`. That command uses the `gh-pages` package to push the `dist/` folder to the `gh-pages` branch.

## Verification

- `python3 -m pip install -r backend/requirements.txt`
- `cd backend && python3 - <<'PY' ...` (see command history) to POST to `/api/evaluations`
- `cd frontend && npm run build`

All of the above complete without errors, confirming both stacks compile/build locally.

## Next steps

- Replace the keyword-based scorer in `backend/app/services/scoring.py` with the full multi-stage pipeline from `evaluate_pdf_transcripts.py` once model credentials and OCR helpers are ready.
- Expand the database schema with user accounts or assignment metadata if multiple cohorts will use the tool simultaneously.
- Harden file handling by uploading rubrics to S3 or Render Disks if you need to persist the original PDFs.
