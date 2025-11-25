import { useEffect, useState } from 'react'

import './App.css'
import EvaluateTranscriptTab from './components/EvaluateTranscriptTab'
import ManageRubricsTab from './components/ManageRubricsTab'
import { API_BASE_URL, PROVIDER_OPTIONS } from './config'

function App() {
  const [activeTab, setActiveTab] = useState('manage-rubrics')
  const [savedRubrics, setSavedRubrics] = useState([])
  const [history, setHistory] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [llmProvider, setLlmProvider] = useState('openai')

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

      <div className="provider-controls">
        <label htmlFor="provider-select">LLM Provider</label>
        <select
          id="provider-select"
          value={llmProvider}
          onChange={(event) => setLlmProvider(event.target.value)}
        >
          {PROVIDER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <p className="provider-hint">
          Controls which LLM handles rubric parsing and scoring.
        </p>
      </div>

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
            llmProvider={llmProvider}
          />
        ) : (
          <EvaluateTranscriptTab
            savedRubrics={savedRubrics}
            history={history}
            loadingHistory={loadingHistory}
            onRefresh={fetchHistory}
            llmProvider={llmProvider}
          />
        )}
      </main>
    </div>
  )
}

export default App
