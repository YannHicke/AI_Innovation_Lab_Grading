# Frontend guide

React + Vite app located in `frontend/`.

## Configuration
- `src/config.js` exports `API_BASE_URL` (from `VITE_API_BASE_URL` with a Render default) and `PROVIDER_OPTIONS`.
- Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` (e.g., `http://localhost:8000` for local dev).

## Component map
- `src/App.jsx`: top-level layout (tabs, provider selector) and data loading (`/api/rubrics`, `/api/evaluations?limit=5`).
- `src/components/ManageRubricsTab.jsx`: upload + parse rubric PDFs, edit/save existing rubrics, list/delete saved rubrics.
  - Uses `RubricModificationScreen` for both newly parsed and persisted rubrics.
  - Calls POST `/api/rubrics`, PUT `/api/rubrics/{id}`, GET `/api/rubrics/{id}`, DELETE `/api/rubrics/{id}`, and POST `/api/rubrics/parse`.
- `src/components/EvaluateTranscriptTab.jsx`: evaluate a transcript against a saved rubric and view history.
  - Calls POST `/api/evaluations/with-rubric` and GET `/api/evaluations`.
  - Renders `ResultPanel`, `CriterionTable`, and `HistoryPanel`.

## Styling
- Global styles live in `src/App.css`. Component splits did not introduce CSS modules—classes remain shared across components.
- `.rubric-actions` groups edit/delete buttons in the saved rubric list.

## State flow
- `App` owns `llmProvider`, `activeTab`, `savedRubrics`, and `history`.
- Manage tab signals `onRubricSaved` to refresh the saved list; Evaluate tab signals `onRefresh` to reload history.
- Provider selection is passed down so both parsing and scoring use the same LLM provider value.

## Running locally
```bash
cd frontend
npm install
cp .env.example .env
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Building
```bash
npm run build
```
Outputs to `frontend/dist/` (used by GitHub Pages workflow).
