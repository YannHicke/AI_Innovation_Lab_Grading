# Dev notes

## Commands
- Backend dev server: `cd backend && uvicorn app.main:app --reload --port 8000`
- Backend deps: `pip install -r requirements.txt`
- Frontend dev: `cd frontend && npm install && npm run dev`
- Frontend build check: `cd frontend && npm run build`

## Code organization
- FastAPI app lives in `app/main.py`; API routes are split into `app/routers/rubrics.py` and `app/routers/evaluations.py`.
- Rubric/user/assignment helpers are in `app/services/rubric_ops.py`; rubric normalization and prompt utilities stay in `app/services/rubric_manager.py`.
- React is split into `ManageRubricsTab` and `EvaluateTranscriptTab` under `src/components/`. Shared config is in `src/config.js`.

## Conventions
- Prefer `rg` for search and `apply_patch` for edits.
- Keep ASCII in source files and avoid removing user changes.
- Keep backend response models in `app/schemas.py`; add new endpoints via routers and import them in `main.py`.
- Frontend: keep API URLs centralized in `src/config.js` and avoid duplicating the provider list.

## Testing / verification
- Backend: run the FastAPI app and hit `/api/health`; exercise `/api/rubrics/parse` with a small PDF when changing parser code.
- Frontend: `npm run build` should stay green; spot-check rubric upload/edit and evaluation flows in the UI.
