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
  const handleDownloadPDF = async (evaluationId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/${evaluationId}/pdf`)
      if (!response.ok) {
        throw new Error('Failed to generate PDF')
      }

      // Create blob from response
      const blob = await response.blob()

      // Create download link
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `evaluation_${evaluationId}.pdf`
      document.body.appendChild(a)
      a.click()

      // Cleanup
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error downloading PDF:', error)
      alert('Failed to download PDF. Please try again.')
    }
  }

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
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span className="score">
            {result.total_score}/{result.max_total_score}
          </span>
          <button
            className="ghost small"
            type="button"
            onClick={() => handleDownloadPDF(result.id)}
            title="Download PDF Report"
          >
            Download PDF
          </button>
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
  const [selectedEvalId, setSelectedEvalId] = useState(null)
  const [selectedEval, setSelectedEval] = useState(null)
  const [loadingEval, setLoadingEval] = useState(false)

  const handleViewEvaluation = async (evaluationId) => {
    if (selectedEvalId === evaluationId) {
      // Clicking the same item collapses it
      setSelectedEvalId(null)
      setSelectedEval(null)
      return
    }

    setSelectedEvalId(evaluationId)
    setLoadingEval(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/${evaluationId}`)
      if (!response.ok) {
        throw new Error('Failed to load evaluation details')
      }
      const data = await response.json()
      setSelectedEval(data)
    } catch (error) {
      console.error('Error loading evaluation:', error)
      setSelectedEval(null)
    } finally {
      setLoadingEval(false)
    }
  }

  const handleDownloadPDF = async (evaluationId, event) => {
    event.stopPropagation() // Prevent triggering the expand/collapse

    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/${evaluationId}/pdf`)
      if (!response.ok) {
        throw new Error('Failed to generate PDF')
      }

      // Create blob from response
      const blob = await response.blob()

      // Create download link
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `evaluation_${evaluationId}.pdf`
      document.body.appendChild(a)
      a.click()

      // Cleanup
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error downloading PDF:', error)
      alert('Failed to download PDF. Please try again.')
    }
  }

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
        <div key={item.id}>
          <article
            className={`history-item ${selectedEvalId === item.id ? 'active' : ''}`}
            onClick={() => handleViewEvaluation(item.id)}
            style={{ cursor: 'pointer' }}
          >
            <div>
              <p className="history-title">{item.rubric_title}</p>
              <p className="history-meta">
                {new Date(item.created_at).toLocaleString()} ·{' '}
                {item.performance_band}
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span className="history-score">
                {item.total_score}/{item.max_total_score}
              </span>
              <button
                className="ghost small"
                type="button"
                onClick={(e) => handleDownloadPDF(item.id, e)}
                title="Download PDF"
                style={{ fontSize: '0.85rem', padding: '0.25rem 0.5rem' }}
              >
                PDF
              </button>
            </div>
          </article>
          {selectedEvalId === item.id && (
            <div className="history-detail">
              {loadingEval ? (
                <p>Loading details...</p>
              ) : selectedEval ? (
                <div className="history-detail-content">
                  <p className="summary">{selectedEval.feedback_summary}</p>
                  {selectedEval.rubric_summary && (
                    <p className="rubric-hint" style={{ marginTop: '0.5rem' }}>
                      Rubric: {selectedEval.rubric_summary.slice(0, 180)}...
                    </p>
                  )}
                  <CriterionTable scores={selectedEval.criterion_scores} />
                </div>
              ) : (
                <p>Failed to load evaluation details.</p>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default EvaluateTranscriptTab
