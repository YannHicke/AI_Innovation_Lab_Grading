import { useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://ai-innovation-lab-grading.onrender.com'

function App() {
  const [transcript, setTranscript] = useState('')
  const [rubricFile, setRubricFile] = useState(null)
  const [shareWithStudent, setShareWithStudent] = useState(false)
  const [status, setStatus] = useState({ type: 'idle', message: '' })
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const fetchHistory = async () => {
    setLoadingHistory(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations?limit=5`)
      if (!response.ok) {
        throw new Error('Unable to load latest evaluations.')
      }
      const items = await response.json()
      setHistory(items)
    } catch (error) {
      console.error(error)
    } finally {
      setLoadingHistory(false)
    }
  }

  useEffect(() => {
    fetchHistory()
  }, [])

  const setError = (message) => setStatus({ type: 'error', message })

  const handleRubricChange = (event) => {
    const file = event.target.files?.[0]
    if (file && file.type !== 'application/pdf') {
      setError('Please upload a PDF rubric.')
      return
    }
    setStatus({ type: 'idle', message: '' })
    setRubricFile(file ?? null)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!transcript.trim()) {
      setError('Transcript text is required.')
      return
    }
    if (!rubricFile) {
      setError('Upload a rubric PDF to continue.')
      return
    }

    const formData = new FormData()
    formData.append('transcript_text', transcript)
    formData.append('rubric_pdf', rubricFile)
    formData.append('share_with_student', shareWithStudent ? 'true' : 'false')

    setStatus({ type: 'processing', message: 'Scoring transcript…' })

    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations`, {
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
      setRubricFile(null)
      event.target.reset()
      fetchHistory()
    } catch (error) {
      setError(error.message)
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">AI Innovation Lab</p>
          <h1>Transcript Grading Assistant</h1>
          <p>
            Upload a conversation transcript and the PDF rubric used for your
            OSCE or client interview. We&apos;ll extract the criteria,
            generate scores, and surface quick feedback for either faculty or
            learners.
          </p>
          <button className="ghost" type="button" onClick={fetchHistory}>
            {loadingHistory ? 'Refreshing…' : 'Load latest results'}
          </button>
        </div>
        <div className="metrics">
          <div>
            <p className="label">Backend</p>
            <p className="value">FastAPI</p>
          </div>
          <div>
            <p className="label">Hosting</p>
            <p className="value">Render + GH Pages</p>
          </div>
          <div>
            <p className="label">Storage</p>
            <p className="value">PostgreSQL</p>
          </div>
        </div>
      </header>

      <main className="content-grid">
        <section className="card">
          <h2>Grade a new transcript</h2>
          <form className="form" onSubmit={handleSubmit}>
            <label htmlFor="transcript">Transcript</label>
            <textarea
              id="transcript"
              placeholder="Paste the dialogue between the learner and patient…"
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              rows={10}
            />

            <label className="file-label" htmlFor="rubric">
              Rubric PDF
              <input
                id="rubric"
                type="file"
                accept="application/pdf"
                onChange={handleRubricChange}
              />
            </label>

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
              {status.type === 'processing' ? 'Scoring…' : 'Submit for scoring'}
            </button>
          </form>
        </section>

        <section className="card">
          <ResultPanel result={result} />
          <HistoryPanel
            history={history}
            loading={loadingHistory}
            onRefresh={fetchHistory}
          />
        </section>
      </main>
    </div>
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

export default App
