import { useState } from 'react'

import { API_BASE_URL, PROVIDER_OPTIONS } from '../config'

function EvaluateTranscriptTab({ savedRubrics, history, loadingHistory, onRefresh, llmProvider }) {
  const [transcript, setTranscript] = useState('')
  const [selectedRubricId, setSelectedRubricId] = useState('')
  const [shareWithStudent, setShareWithStudent] = useState(false)
  const [status, setStatus] = useState({ type: 'idle', message: '' })
  const [result, setResult] = useState(null)

  const providerMeta =
    PROVIDER_OPTIONS.find((option) => option.value === llmProvider) ?? PROVIDER_OPTIONS[0]

  const setError = (message) => setStatus({ type: 'error', message })

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!transcript.trim()) {
      setError('Transcript text is required.')
      return
    }
    if (!selectedRubricId) {
      setError('Please select a rubric.')
      return
    }

    const formData = new FormData()
    formData.append('transcript_text', transcript)
    formData.append('rubric_id', selectedRubricId)
    formData.append('share_with_student', shareWithStudent ? 'true' : 'false')
    formData.append('llm_provider', llmProvider)

    setStatus({ type: 'processing', message: 'Evaluating transcript…' })

    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/with-rubric`, {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to create evaluation.')
      }

      setResult(payload.evaluation)
      setStatus({ type: 'success', message: payload.message })
      setTranscript('')
      setSelectedRubricId('')
      event.target.reset()
      onRefresh()
    } catch (error) {
      setError(error.message)
    }
  }

  return (
    <>
      <section className="card">
        <h2>Evaluate Transcript</h2>
        <p className="provider-note">
          Scoring powered by <strong>{providerMeta.label}</strong>
        </p>
        <form className="form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="rubric-select">Select Rubric</label>
            <select
              id="rubric-select"
              value={selectedRubricId}
              onChange={(e) => setSelectedRubricId(e.target.value)}
              required
            >
              <option value="">Choose a rubric...</option>
              {savedRubrics.map((rubric) => (
                <option key={rubric.id} value={rubric.id}>
                  {rubric.title} ({rubric.items_count} criteria)
                </option>
              ))}
            </select>
          </div>

          <label htmlFor="transcript">Transcript</label>
          <textarea
            id="transcript"
            placeholder="Paste the dialogue between the learner and patient…"
            value={transcript}
            onChange={(event) => setTranscript(event.target.value)}
            rows={10}
          />

          <label className="checkbox">
            <input
              type="checkbox"
              checked={shareWithStudent}
              onChange={(event) => setShareWithStudent(event.target.checked)}
            />
            Share this with the learner
          </label>

          {status.message && (
            <p className={`status ${status.type}`}>{status.message}</p>
          )}

          <button type="submit" className="primary">
            {status.type === 'processing' ? 'Evaluating…' : 'Evaluate'}
          </button>
        </form>
      </section>

      <section className="card">
        <ResultPanel result={result} />
        <HistoryPanel
          history={history}
          loading={loadingHistory}
          onRefresh={onRefresh}
        />
      </section>
    </>
  )
}

function ResultPanel({ result }) {
  if (!result) {
    return (
      <div>
        <h2>Results</h2>
        <p>Submit a transcript to see automated scoring and feedback.</p>
      </div>
    )
  }

  return (
    <div className="results">
      <div className="result-header">
        <div>
          <p className="eyebrow">{result.rubric_title}</p>
          <h2>{result.performance_band}</h2>
        </div>
        <div>
          <span className="score">
            {result.total_score}/{result.max_total_score}
          </span>
        </div>
      </div>
      <p className="summary">{result.feedback_summary}</p>
      <p className="rubric-hint">
        Rubric excerpt: {result.rubric_summary?.slice(0, 180) ?? 'No rubric details stored.'}
      </p>
      <CriterionTable scores={result.criterion_scores} />
    </div>
  )
}

function CriterionTable({ scores }) {
  if (!scores?.length) {
    return null
  }

  return (
    <div className="table">
      {scores.map((criterion) => (
        <div key={criterion.id} className="row">
          <div>
            <p className="criterion-name">{criterion.name}</p>
            <p className="criterion-description">
              {criterion.description || 'Free-form criterion'}
            </p>
          </div>
          <div className="criterion-score">
            <span>
              {criterion.score}/{criterion.max_score}
            </span>
            <p>{criterion.feedback}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function HistoryPanel({ history, loading, onRefresh }) {
  return (
    <div className="history">
      <div className="history-header">
        <h3>Recent runs</h3>
        <button className="ghost small" type="button" onClick={onRefresh}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {history.length === 0 && <p>No history to display yet.</p>}
      {history.map((item) => (
        <article key={item.id} className="history-item">
          <div>
            <p className="history-title">{item.rubric_title}</p>
            <p className="history-meta">
              {new Date(item.created_at).toLocaleString()} ·{' '}
              {item.performance_band}
            </p>
          </div>
          <span className="history-score">
            {item.total_score}/{item.max_total_score}
          </span>
        </article>
      ))}
    </div>
  )
}

export default EvaluateTranscriptTab
