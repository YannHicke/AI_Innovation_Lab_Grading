import { useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://ai-innovation-lab-grading.onrender.com'

function App() {
  const [activeTab, setActiveTab] = useState('manage-rubrics')
  const [savedRubrics, setSavedRubrics] = useState([])
  const [history, setHistory] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const fetchSavedRubrics = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics`)
      if (response.ok) {
        const rubrics = await response.json()
        setSavedRubrics(rubrics)
      }
    } catch (error) {
      console.error('Failed to fetch rubrics:', error)
    }
  }

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
    fetchSavedRubrics()
    fetchHistory()
  }, [])

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">AI Innovation Lab</p>
          <h1>Transcript Grading Assistant</h1>
          <p>
            Manage rubrics and evaluate transcripts with AI-powered scoring.
          </p>
        </div>
      </header>

      <div className="tabs">
        <button
          className={`tab ${activeTab === 'manage-rubrics' ? 'active' : ''}`}
          onClick={() => setActiveTab('manage-rubrics')}
        >
          Manage Rubrics
        </button>
        <button
          className={`tab ${activeTab === 'evaluate-transcript' ? 'active' : ''}`}
          onClick={() => setActiveTab('evaluate-transcript')}
        >
          Evaluate Transcript
        </button>
      </div>

      <main className="content-grid">
        {activeTab === 'manage-rubrics' ? (
          <ManageRubricsTab
            savedRubrics={savedRubrics}
            onRubricSaved={fetchSavedRubrics}
          />
        ) : (
          <EvaluateTranscriptTab
            savedRubrics={savedRubrics}
            history={history}
            loadingHistory={loadingHistory}
            onRefresh={fetchHistory}
          />
        )}
      </main>
    </div>
  )
}

function ManageRubricsTab({ savedRubrics, onRubricSaved }) {
  const [rubricFile, setRubricFile] = useState(null)
  const [status, setStatus] = useState({ type: 'idle', message: '' })
  const [parsingInfo, setParsingInfo] = useState(null)
  const [showModificationScreen, setShowModificationScreen] = useState(false)

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

  const handleUploadRubric = async (event) => {
    event.preventDefault()
    if (!rubricFile) {
      setError('Upload a rubric PDF to continue.')
      return
    }

    const formData = new FormData()
    formData.append('rubric_pdf', rubricFile)

    setStatus({ type: 'processing', message: 'Parsing rubric…' })

    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics/parse`, {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to parse rubric.')
      }

      setParsingInfo(payload)
      setShowModificationScreen(true)
      setStatus({ type: 'success', message: 'Rubric parsed successfully!' })
    } catch (error) {
      setError(error.message)
    }
  }

  const handleSaveRubric = async (modifiedRubric) => {
    setStatus({ type: 'processing', message: 'Saving rubric…' })

    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(modifiedRubric),
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to save rubric.')
      }

      setStatus({ type: 'success', message: 'Rubric saved successfully!' })
      setShowModificationScreen(false)
      setParsingInfo(null)
      setRubricFile(null)
      onRubricSaved()
    } catch (error) {
      setError(error.message)
    }
  }

  const handleDeleteRubric = async (rubricId) => {
    if (!confirm('Are you sure you want to delete this rubric?')) {
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics/${rubricId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Unable to delete rubric.')
      }
      onRubricSaved()
    } catch (error) {
      setError(error.message)
    }
  }

  if (showModificationScreen && parsingInfo) {
    return (
      <div className="full-width">
        <RubricModificationScreen
          parsingInfo={parsingInfo}
          onSave={handleSaveRubric}
          onCancel={() => {
            setShowModificationScreen(false)
            setParsingInfo(null)
          }}
        />
      </div>
    )
  }

  return (
    <>
      <section className="card">
        <h2>Upload Rubric</h2>
        <form className="form" onSubmit={handleUploadRubric}>
          <label className="file-label" htmlFor="rubric">
            Rubric PDF
            <input
              id="rubric"
              type="file"
              accept="application/pdf"
              onChange={handleRubricChange}
            />
          </label>

          {status.message && (
            <p className={`status ${status.type}`}>{status.message}</p>
          )}

          <button type="submit" className="primary">
            {status.type === 'processing' ? 'Parsing…' : 'Parse Rubric'}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Saved Rubrics</h2>
        {savedRubrics.length === 0 ? (
          <p>No rubrics saved yet. Upload a rubric to get started.</p>
        ) : (
          <div className="rubrics-list">
            {savedRubrics.map((rubric) => (
              <div key={rubric.id} className="rubric-item">
                <div>
                  <p className="rubric-title">{rubric.title}</p>
                  <p className="rubric-meta">
                    {rubric.items_count} criteria · Max score: {rubric.max_total_score}
                  </p>
                </div>
                <button
                  className="ghost small delete-btn"
                  onClick={() => handleDeleteRubric(rubric.id)}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

function RubricModificationScreen({ parsingInfo, onSave, onCancel }) {
  const [rubricData, setRubricData] = useState({
    title: parsingInfo.rubric_title,
    rubric_type: parsingInfo.rubric_type,
    max_total_score: parsingInfo.max_total_score,
    criteria: parsingInfo.criteria_names.map((name, index) => ({
      name,
      description: parsingInfo.generated_prompts[index]?.prompt_text || '',
      max_score: parsingInfo.max_total_score / parsingInfo.items_extracted,
    })),
  })

  const handleCriterionChange = (index, field, value) => {
    const updated = [...rubricData.criteria]
    updated[index][field] = value
    setRubricData({ ...rubricData, criteria: updated })
  }

  const handleAddCriterion = () => {
    setRubricData({
      ...rubricData,
      criteria: [
        ...rubricData.criteria,
        { name: 'New Criterion', description: '', max_score: 10 },
      ],
    })
  }

  const handleDeleteCriterion = (index) => {
    const updated = rubricData.criteria.filter((_, i) => i !== index)
    setRubricData({ ...rubricData, criteria: updated })
  }

  return (
    <div className="modification-screen">
      <div className="modification-header">
        <h2>Modify Rubric</h2>
        <div className="button-group">
          <button className="ghost" onClick={onCancel}>
            Cancel
          </button>
          <button className="primary" onClick={() => onSave(rubricData)}>
            Save Rubric
          </button>
        </div>
      </div>

      <div className="rubric-details">
        <div className="form-group">
          <label>Rubric Title</label>
          <input
            type="text"
            value={rubricData.title}
            onChange={(e) =>
              setRubricData({ ...rubricData, title: e.target.value })
            }
          />
        </div>

        <div className="form-group">
          <label>Rubric Type</label>
          <input
            type="text"
            value={rubricData.rubric_type}
            onChange={(e) =>
              setRubricData({ ...rubricData, rubric_type: e.target.value })
            }
          />
        </div>

        <div className="form-group">
          <label>Max Total Score</label>
          <input
            type="number"
            value={rubricData.max_total_score}
            onChange={(e) =>
              setRubricData({
                ...rubricData,
                max_total_score: parseFloat(e.target.value),
              })
            }
          />
        </div>
      </div>

      <div className="criteria-section">
        <div className="section-header">
          <h3>Criteria ({rubricData.criteria.length})</h3>
          <button className="ghost small" onClick={handleAddCriterion}>
            + Add Criterion
          </button>
        </div>

        {rubricData.criteria.map((criterion, index) => (
          <div key={index} className="criterion-editor">
            <div className="criterion-header">
              <h4>Criterion {index + 1}</h4>
              <button
                className="ghost small delete-btn"
                onClick={() => handleDeleteCriterion(index)}
              >
                Delete
              </button>
            </div>

            <div className="form-group">
              <label>Name</label>
              <input
                type="text"
                value={criterion.name}
                onChange={(e) =>
                  handleCriterionChange(index, 'name', e.target.value)
                }
              />
            </div>

            <div className="form-group">
              <label>Max Score</label>
              <input
                type="number"
                value={criterion.max_score}
                onChange={(e) =>
                  handleCriterionChange(
                    index,
                    'max_score',
                    parseFloat(e.target.value)
                  )
                }
              />
            </div>

            <div className="form-group">
              <label>Prompt / Description</label>
              <textarea
                rows={8}
                value={criterion.description}
                onChange={(e) =>
                  handleCriterionChange(index, 'description', e.target.value)
                }
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function EvaluateTranscriptTab({ savedRubrics, history, loadingHistory, onRefresh }) {
  const [transcript, setTranscript] = useState('')
  const [selectedRubricId, setSelectedRubricId] = useState('')
  const [shareWithStudent, setShareWithStudent] = useState(false)
  const [status, setStatus] = useState({ type: 'idle', message: '' })
  const [result, setResult] = useState(null)

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

export default App
