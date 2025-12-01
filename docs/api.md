# API reference

Base URL: `http://localhost:8000` in development (or your Render URL in production). All responses are JSON unless noted.

## Health
- `GET /api/health` → `{"status": "ok"}` used for liveness checks.

## Rubrics
- `POST /api/rubrics/parse`  
  Multipart form with `rubric_pdf` (file) and optional `llm_provider`. Returns `{rubric, parsing_info}` without saving.
- `POST /api/rubrics`  
  JSON body matching `RubricSaveRequest`:  
  ```json
  { "title": "Counseling Skills", "summary": "4-point analytic", "rubric_type": "analytic", "max_total_score": 16, "criteria": [ { "name": "Empathy", "description": "Shows empathy", "item_type": "criterion", "max_score": 4, "weight": null, "metadata": {} } ] }
  ```  
  Returns `{"id": <rubric_id>, "message": "Rubric saved successfully"}`.
- `PUT /api/rubrics/{id}`  
  Same body as create; replaces all criteria/levels for that rubric.
- `GET /api/rubrics`  
  List rubrics with metadata: `[{id, title, rubric_type, max_total_score, items_count, created_at}]`.
- `GET /api/rubrics/{id}`  
  Full rubric with criteria and levels; response model: `RubricResponse` (includes `items[]` and `levels[]`).
- `DELETE /api/rubrics/{id}`  
  Deletes rubric and its items/levels. Returns `{"message": "Rubric deleted successfully"}`.

## Evaluations
- `POST /api/evaluations`  
  Multipart form with fields: `transcript_text` (string), `rubric_pdf` (file), optional `share_with_student`, assignment metadata (`assignment_name`, `assignment_cohort`, `assignment_description`, `assignment_due_date` ISO string), grader metadata (`grader_email`, `grader_name`, `grader_role`), and optional `llm_provider`. Stores rubric, scores transcript, and returns `EvaluationCreateResponse` with `evaluation` and `parsing_info`.
- `POST /api/evaluations/with-rubric`  
  Multipart form: `transcript_text`, `rubric_id`, optional `share_with_student`, `llm_provider`. Uses a saved rubric instead of uploading a PDF. Returns `{"evaluation": {...}, "message": "Evaluation created successfully"}`.
- `GET /api/evaluations?limit=10`  
  List recent evaluations (limit capped at 50). Response model: `EvaluationListItem[]`.
- `GET /api/evaluations/{id}`  
  Full evaluation including rubric, assignment, grader, and `criterion_scores[]`. Response model: `EvaluationResponse`.

## Notes on rubric shapes
- `rubric_type` defaults to `"analytic"` if absent.
- Each criterion (`item`) supports `name`, `description`, `item_type`, `max_score`, `weight`, and `metadata` (free-form JSON). `metadata.performance_levels` is preserved and emitted on fetch.
- `max_total_score` is used for aggregate scoring and prompt hints; when missing, the backend will fall back to distributing evenly across criteria during scoring.
