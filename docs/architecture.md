# System Architecture

This document explains how the AI Innovation Lab Grading project is wired together so new contributors can navigate both stacks quickly.

## High-level overview

| Layer    | Purpose                                                                 | Entry points                                   |
|----------|-------------------------------------------------------------------------|------------------------------------------------|
| Frontend | React + Vite single page app with two workflows (manage rubrics, score transcripts). | `frontend/src/App.jsx`, `frontend/src/App.css` |
| Backend  | FastAPI service that parses rubric PDFs, persists rubrics/evaluations, and calls LLMs for scoring. | `backend/app/main.py` and `backend/app/services/*` |
| Data     | PostgreSQL in production (SQLite for local dev) tracked via SQLAlchemy models. | `backend/app/models.py`                        |

Clients interact with the backend in two ways:

1. **Upload & edit a rubric** – the frontend sends a PDF to `/api/rubrics/parse`. The backend extracts structure, generates placeholder scoring prompts, and returns both the normalized rubric object and preview metadata. The UI lets faculty tweak the extracted data and saves it via `/api/rubrics`.
2. **Evaluate a transcript** – graders either upload a brand-new rubric PDF in the same request (`POST /api/evaluations`) or reference a rubric that already lives in the database (`POST /api/evaluations/with-rubric`). In both cases the backend builds per-criterion prompts and calls the configured LLM to receive scores + narrative feedback.

## Backend modules

### `app/main.py`

Defines the FastAPI routes. The key endpoints are:

| Endpoint | Description |
|----------|-------------|
| `POST /api/rubrics/parse` | Accepts `rubric_pdf` (multipart). Returns `{ "rubric": <normalized payload>, "parsing_info": <RubricParsingInfo> }`. The payload mirrors what would eventually be saved in the DB, while `parsing_info` contains summaries, detected criteria, and sample prompts that use the transcript placeholder. |
| `POST /api/rubrics` | Accepts a JSON body that matches `RubricSaveRequest` (title, summary, rubric_type, max_total_score, and a `criteria` array with `name`, `description`, `item_type`, `max_score`, `weight`, `metadata`). Creates `Rubric` and `RubricItem` rows. |
| `GET /api/rubrics` / `DELETE /api/rubrics/{id}` | List and delete saved rubrics. |
| `POST /api/evaluations` | Multipart route for the “upload PDF + transcript” flow. Parses the rubric, persists it (along with performance levels), scores the transcript, stores an `Evaluation`, and returns an `EvaluationCreateResponse`. The response includes the evaluation payload and a `parsing_info` field for UI debugging. |
| `POST /api/evaluations/with-rubric` | Uses a previously saved rubric (`rubric_id`) for scoring. |
| `GET /api/evaluations` / `GET /api/evaluations/{id}` | Fetch recent runs or a single run with linked assignment, grader, and criterion scores. |

### `app/services/rubric_parser.py`

Wraps the LLM (OpenAI or Anthropic) that extracts a structured rubric from raw PDF text. The parser:

- Normalizes rubric type (`analytic`, `holistic`, etc.).
- Ensures every criterion has a numeric `max_score` (defaults to 1.0 if omitted for checklists).
- Preserves metadata, performance levels, and holistic levels when present.
- Returns a canonical dict with `title`, `summary`, `rubric_type`, `max_total_score`, `criteria`, and `levels`.

#### Structured outputs per provider

- **OpenAI** – Requests now include `response_format` with a strict JSON Schema so GPT-4o models stream schema-compliant JSON automatically (`backend/app/services/rubric_parser.py:20-120`, `backend/app/services/scoring.py:21-105`). This replaces the legacy `json_object` mode and removes the need for brittle post-processing.
- **Anthropic** – The client calls the beta Messages API with `betas=["structured-outputs-2025-11-13"]` plus `output_format={"type": "json_schema", ...}`. This unlocks Claude's structured decoding and keeps responses reliable. See `backend/app/services/llm_utils.py:8-33` for the helper that attaches the beta flag and routes to the correct SDK surface.

The same schemas (one for rubric extraction, one for per-criterion scoring) are shared between providers, which keeps downstream validation identical regardless of the configured `APP_LLM_PROVIDER`.

### `app/services/rubric_manager.py`

Utility helpers introduced in this refactor:

- `scoring_payload_from_payload` – converts parsed criteria into the format expected by the scorer.
- `scoring_payload_from_models` – serializes ORM `RubricItem` rows into the same structure, handling fallback max scores.
- `build_parsing_info` – builds the `RubricParsingInfo` object shared by `/api/rubrics/parse` and `/api/evaluations`. It always uses a transcript placeholder so the transcript never leaks in API responses.

### `app/services/scoring.py`

Provides `score_criteria`, which injects each criterion’s metadata into `build_item_prompt`, calls the configured LLM (`openai` or `anthropic`), clamps scores, and assembles totals plus narrative feedback.

### Models & schemas

- ORM models live in `app/models.py`. `Rubric`, `RubricItem`, `RubricLevel`, `Evaluation`, and `CriterionScore` map to the DB.
- Pydantic schemas in `app/schemas.py` define API shapes. Notable models:
  - `RubricSaveRequest`
  - `RubricCriterionInput` / `RubricCriterionPreview`
  - `RubricParsingInfo` (now includes the criteria list and generated prompts)
  - `EvaluationCreateResponse`

### Configuration & env vars

`app/config.py` pulls settings from env vars. Important flags:

- `APP_DATABASE_URL`
- `APP_ALLOWED_ORIGINS`
- `APP_SHARE_RESULTS_DEFAULT`
- `APP_LLM_PROVIDER` (`openai` or `anthropic`)
- `APP_OPENAI_API_KEY` / `APP_ANTHROPIC_API_KEY`
- `APP_LLM_MODEL`, `APP_LLM_TEMPERATURE`, `APP_LLM_MAX_OUTPUT_TOKENS`

## Frontend

`App.jsx` renders two tabs:

- **Manage Rubrics** – Handles PDF upload → preview → editing → save. After parsing succeeds it displays:
  - Extraction summary (`parsing_info`)
  - The editable rubric draft (title, summary, type, max score, and each criterion’s properties). Editing preserves metadata so saved rubrics remain faithful to the PDF.
  - Saved rubric list with delete actions.
- **Evaluate Transcript** – Allows graders to choose a saved rubric, paste a transcript, optionally share with the student, and submit. Results are shown next to the history panel.

Compiled styles live in `App.css`. It already contains utility classes used by the parsing preview (`parsing-info`, `parsing-summary`, `prompt-item`, etc.).

## Typical data flow

1. **Parse + save a rubric**
   1. UI uploads `rubric_pdf` to `/api/rubrics/parse`.
   2. Backend extracts text via `pdf_bytes_to_text`, normalizes via `parse_rubric`, and ships `{rubric, parsing_info}`.
   3. UI lets the user edit the returned JSON and issues `POST /api/rubrics` with the cleaned payload.

2. **Score a transcript with a saved rubric**
   1. UI posts `transcript_text`, `rubric_id`, and options to `/api/evaluations/with-rubric`.
   2. Backend loads the rubric + items, serializes them via `scoring_payload_from_models`, calls `score_criteria`, and persists an `Evaluation` with `CriterionScore` rows.
   3. The JSON response includes the evaluation plus a success message.

3. **One-off evaluation with a rubric PDF**
   1. UI posts to `/api/evaluations` with `transcript_text`, `rubric_pdf`, and optional assignment/grader metadata.
   2. Backend parses the rubric, persists it (for traceability), scores the transcript, and returns `EvaluationCreateResponse` (with `parsing_info` for debugging).

## Tips for contributors

- If you need to change how prompts look, edit `build_item_prompt` in `services/prompt_builder.py`. All scoring and preview prompts share this function.
- Any time you adjust rubric structure or metadata, update `RubricCriterionInput`, `RubricSaveRequest`, and `build_parsing_info` so the API stays consistent.
- Keep new files under `docs/` for additional runbooks or onboarding guides and link them from `README.md` if needed.
