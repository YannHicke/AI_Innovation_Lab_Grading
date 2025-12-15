import { useEffect, useState } from 'react'

import './App.css'
import { API_BASE_URL, PROVIDER_OPTIONS } from './config'

function App() {
  const [currentStep, setCurrentStep] = useState(1)
  const [rubricText, setRubricText] = useState('')
  const [rubricFile, setRubricFile] = useState(null)
  const [transcriptText, setTranscriptText] = useState('')
  const [parsedRubric, setParsedRubric] = useState(null)
  const [savedRubricId, setSavedRubricId] = useState(null)
  const [savedRubrics, setSavedRubrics] = useState([])
  const [evaluation, setEvaluation] = useState(null)
  const [history, setHistory] = useState([])
  const [llmProvider, setLlmProvider] = useState('anthropic')
  const [status, setStatus] = useState({ type: 'idle', message: '' })
  const [editingRubric, setEditingRubric] = useState(null)
  const [editingEvaluation, setEditingEvaluation] = useState(null)
  const [validationComparisons, setValidationComparisons] = useState([])
  const [selectedComparison, setSelectedComparison] = useState(null)
  const [generateLearnerReport, setGenerateLearnerReport] = useState(false)
  const [learnerReport, setLearnerReport] = useState(null)

  const providerMeta =
    PROVIDER_OPTIONS.find((option) => option.value === llmProvider) ?? PROVIDER_OPTIONS[0]

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations?limit=10`)
      if (!response.ok) {
        throw new Error('Unable to load latest evaluations.')
      }
      const items = await response.json()
      setHistory(items)
    } catch (error) {
      console.error(error)
    }
  }

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

  const fetchValidationComparisons = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/validations`)
      if (response.ok) {
        const comparisons = await response.json()
        setValidationComparisons(comparisons)
      }
    } catch (error) {
      console.error('Failed to fetch validation comparisons:', error)
    }
  }

  useEffect(() => {
    // Fetch saved rubrics when we reach step 3 or 6
    if (currentStep === 3 || currentStep === 6) {
      fetchSavedRubrics()
    }
    // Fetch history when we reach step 5
    if (currentStep === 5) {
      fetchHistory()
    }
    // Fetch validation comparisons when we reach step 7
    if (currentStep === 7) {
      fetchValidationComparisons()
    }
  }, [currentStep])

  const handleEditRubric = (rubric) => {
    setEditingRubric(rubric)
    setCurrentStep(8)
  }

  const handleEditEvaluation = async (evaluationId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/${evaluationId}`)
      if (!response.ok) {
        throw new Error('Failed to load evaluation details')
      }
      const data = await response.json()
      setEditingEvaluation(data)
      setCurrentStep(9)
    } catch (error) {
      console.error('Error loading evaluation:', error)
      alert('Failed to load evaluation for editing. Please try again.')
    }
  }

  const handleSaveEditedRubric = async (updatedRubric) => {
    setStatus({ type: 'processing', message: 'Saving rubric changes...' })

    try {
      // Calculate max_total_score from items
      const maxTotalScore = updatedRubric.items.reduce((sum, item) => sum + (item.max_score || 0), 0)

      // Transform items to criteria format expected by backend
      const criteria = updatedRubric.items.map(item => ({
        name: item.name,
        description: item.description || '',
        item_type: item.item_type || 'criterion',
        max_score: item.max_score || 0,
        weight: item.weight || null,
        metadata: item.metadata || {}
      }))

      const response = await fetch(`${API_BASE_URL}/api/rubrics/${updatedRubric.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: updatedRubric.title,
          summary: updatedRubric.summary || '',
          rubric_type: updatedRubric.rubric_type,
          max_total_score: maxTotalScore,
          criteria: criteria,
        }),
      })

      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail || 'Unable to update rubric.')
      }

      setStatus({ type: 'success', message: 'Rubric updated successfully!' })
      setEditingRubric(null)
      setCurrentStep(6)
      fetchSavedRubrics()
    } catch (error) {
      setStatus({ type: 'error', message: error.message })
    }
  }

  const handleSaveEditedEvaluation = async (updatedEvaluation) => {
    setStatus({ type: 'processing', message: 'Saving evaluation changes...' })

    try {
      // Calculate new total score from criterion scores
      const totalScore = updatedEvaluation.criterion_scores.reduce((sum, cs) => sum + (cs.score || 0), 0)

      const response = await fetch(`${API_BASE_URL}/api/evaluations/${updatedEvaluation.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          total_score: totalScore,
          criterion_scores: updatedEvaluation.criterion_scores.map(cs => ({
            id: cs.id,
            score: cs.score,
            feedback: cs.feedback,
          })),
        }),
      })

      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail || 'Unable to update evaluation.')
      }

      setStatus({ type: 'success', message: 'Evaluation updated successfully!' })
      setEditingEvaluation(null)
      setCurrentStep(5)
      fetchHistory()
    } catch (error) {
      setStatus({ type: 'error', message: error.message })
    }
  }

  const handleUploadHumanGrading = async (evaluationId, file, notes) => {
    setStatus({ type: 'processing', message: 'Parsing human grading PDF...' })

    try {
      const formData = new FormData()
      formData.append('human_grading_file', file)
      formData.append('llm_provider', llmProvider)
      if (notes) formData.append('notes', notes)

      const response = await fetch(`${API_BASE_URL}/api/validations/${evaluationId}/upload-human-grading`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail || 'Failed to upload human grading.')
      }

      const result = await response.json()
      setStatus({
        type: 'success',
        message: `Human grading uploaded! Found ${result.parsed_data?.criterion_count || 0} criteria.`
      })
      fetchValidationComparisons()
    } catch (error) {
      setStatus({ type: 'error', message: error.message })
    }
  }

  const handleViewComparison = async (evaluationId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/validations/${evaluationId}/comparison`)
      if (!response.ok) {
        throw new Error('Failed to load comparison')
      }
      const data = await response.json()
      setSelectedComparison(data)
    } catch (error) {
      console.error('Error loading comparison:', error)
      alert('Failed to load comparison. Please try again.')
    }
  }

  const handleContinueStep1 = () => {
    if (!rubricText.trim() && !transcriptText.trim()) {
      setStatus({ type: 'error', message: 'Please provide both rubric and transcript.' })
      return
    }
    setStatus({ type: 'idle', message: '' })
    setCurrentStep(2)
  }

  const handleGenerateSkeleton = async () => {
    if (!rubricFile) {
      setStatus({ type: 'error', message: 'Please upload a rubric file first.' })
      return
    }

    setStatus({ type: 'processing', message: 'Parsing rubric...' })

    try {
      const formData = new FormData()
      formData.append('rubric_pdf', rubricFile)
      formData.append('llm_provider', llmProvider)

      const response = await fetch(`${API_BASE_URL}/api/rubrics/parse`, {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json()
      console.log('Parse response payload:', payload)

      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to parse rubric.')
      }

      // Extract the rubric object from the response
      const rubricData = payload.rubric || payload
      console.log('Extracted rubric data:', rubricData)
      console.log('Rubric criteria:', rubricData.criteria || rubricData.items)

      setParsedRubric(rubricData)
      setStatus({ type: 'success', message: 'Rubric parsed successfully!' })
      setCurrentStep(2)
    } catch (error) {
      console.error('Parse error:', error)
      setStatus({ type: 'error', message: error.message })
    }
  }

  const handleConfirmRubric = async () => {
    if (!parsedRubric) {
      setStatus({ type: 'error', message: 'Please parse the rubric first.' })
      return
    }

    setStatus({ type: 'processing', message: 'Saving rubric...' })

    try {
      // Transform items to criteria format expected by backend
      const criteria = parsedRubric.criteria.map(item => ({
        name: item.name,
        description: item.description || '',
        item_type: item.item_type || 'criterion',
        max_score: item.max_score || 0,
        weight: item.weight || null,
        metadata: item.metadata || {}
      }))

      const response = await fetch(`${API_BASE_URL}/api/rubrics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: parsedRubric.title,
          summary: parsedRubric.summary || '',
          rubric_type: parsedRubric.rubric_type,
          max_total_score: parsedRubric.max_total_score,
          criteria: criteria,
        }),
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to save rubric.')
      }

      setSavedRubricId(payload.id)
      setStatus({ type: 'success', message: 'Rubric confirmed and saved!' })
      setParsedRubric(null)
      setRubricFile(null)
      setCurrentStep(6)
      fetchSavedRubrics()
    } catch (error) {
      setStatus({ type: 'error', message: error.message })
    }
  }

  const handleStartGrading = async () => {
    if (!savedRubricId) {
      setStatus({ type: 'error', message: 'Please confirm rubric first.' })
      return
    }
    if (!transcriptText.trim()) {
      setStatus({ type: 'error', message: 'Transcript is required.' })
      return
    }

    setStatus({ type: 'processing', message: 'AI is grading transcript...' })

    try {
      const formData = new FormData()
      formData.append('transcript_text', transcriptText)
      formData.append('rubric_id', savedRubricId)
      formData.append('share_with_student', 'true')
      formData.append('llm_provider', llmProvider)

      const response = await fetch(`${API_BASE_URL}/api/evaluations/with-rubric`, {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to create evaluation.')
      }

      setEvaluation(payload.evaluation)
      setStatus({ type: 'success', message: 'Grading completed!' })
      setCurrentStep(4)
      fetchHistory()
    } catch (error) {
      setStatus({ type: 'error', message: error.message })
    }
  }

  const handleGenerateLearnerReport = async () => {
    if (!evaluation) return

    setStatus({ type: 'processing', message: 'Generating student learner report...' })

    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/${evaluation.id}/learner-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm_provider: llmProvider }),
      })

      if (!response.ok) {
        throw new Error('Failed to generate learner report')
      }

      const data = await response.json()
      setLearnerReport(data)
      setStatus({ type: 'success', message: 'Learner report generated!' })
      setCurrentStep(10) // New step for learner report
    } catch (error) {
      console.error('Error generating learner report:', error)
      setStatus({ type: 'error', message: error.message })
    }
  }

  const handleDownloadPDF = async (evaluationId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/${evaluationId}/pdf`)
      if (!response.ok) {
        throw new Error('Failed to generate PDF')
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `evaluation_${evaluationId}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error downloading PDF:', error)
      alert('Failed to download PDF. Please try again.')
    }
  }

  return (
    <div className="wizard-container">
      <header className="wizard-header">
        <div className="wizard-title-section">
          <h1 className="wizard-title">Classroom Client Simulator</h1>
        </div>
      </header>

      <div className="progress-steps">
        <StepIndicator number={1} title="Upload Rubric" subtitle="PDF format" active={currentStep === 1} completed={currentStep > 1} onClick={() => setCurrentStep(1)} />
        <div className="step-connector"></div>
        <StepIndicator number={2} title="Parse Rubric" subtitle="Review and confirm criteria" active={currentStep === 2} completed={currentStep > 2} onClick={() => setCurrentStep(2)} />
        <div className="step-connector"></div>
        <StepIndicator number={3} title="AI Grading" subtitle="Select rubric & paste transcript" active={currentStep === 3} completed={currentStep > 3} onClick={() => setCurrentStep(3)} />
        <div className="step-connector"></div>
        <StepIndicator number={4} title="Generate Reports" subtitle="Teacher and student reports" active={currentStep === 4} completed={currentStep > 4} onClick={() => setCurrentStep(4)} />
        <div className="step-connector"></div>
        <StepIndicator number={5} title="History" subtitle="View past evaluations" active={currentStep === 5} completed={false} onClick={() => setCurrentStep(5)} />
        <div className="step-connector"></div>
        <StepIndicator number={6} title="Manage Rubrics" subtitle="Edit saved rubrics" active={currentStep === 6} completed={false} onClick={() => setCurrentStep(6)} />
        <div className="step-connector"></div>
        <StepIndicator number={7} title="Validation" subtitle="Compare AI vs Human grading" active={currentStep === 7} completed={false} onClick={() => setCurrentStep(7)} />
      </div>

      <main className="wizard-content">
        {currentStep === 1 && (
          <Step1UploadInputs
            rubricFile={rubricFile}
            setRubricFile={setRubricFile}
            onGenerateSkeleton={handleGenerateSkeleton}
            status={status}
          />
        )}

        {currentStep === 2 && (
          <Step2ParseRubric
            parsedRubric={parsedRubric}
            onConfirm={handleConfirmRubric}
            onBack={() => setCurrentStep(1)}
            status={status}
            providerMeta={providerMeta}
          />
        )}

        {currentStep === 3 && (
          <Step3AIGrading
            savedRubrics={savedRubrics}
            savedRubricId={savedRubricId}
            setSavedRubricId={setSavedRubricId}
            transcriptText={transcriptText}
            setTranscriptText={setTranscriptText}
            generateLearnerReport={generateLearnerReport}
            setGenerateLearnerReport={setGenerateLearnerReport}
            onStartGrading={handleStartGrading}
            onBack={() => setCurrentStep(2)}
            status={status}
            providerMeta={providerMeta}
          />
        )}

        {currentStep === 4 && (
          <Step4GenerateReports
            evaluation={evaluation}
            onDownloadPDF={handleDownloadPDF}
            onContinue={() => setCurrentStep(5)}
            generateLearnerReport={generateLearnerReport}
            onGenerateLearnerReport={handleGenerateLearnerReport}
            providerMeta={providerMeta}
          />
        )}

        {currentStep === 5 && (
          <Step5Validation
            history={history}
            onRefresh={fetchHistory}
            onDownloadPDF={handleDownloadPDF}
            onEditEvaluation={handleEditEvaluation}
          />
        )}

        {currentStep === 6 && (
          <Step6ManageRubrics
            savedRubrics={savedRubrics}
            onRefresh={fetchSavedRubrics}
            llmProvider={llmProvider}
            onEditRubric={handleEditRubric}
          />
        )}

        {currentStep === 7 && (
          <Step9ValidationComparison
            history={history}
            validationComparisons={validationComparisons}
            selectedComparison={selectedComparison}
            onUploadHumanGrading={handleUploadHumanGrading}
            onViewComparison={handleViewComparison}
            onRefresh={fetchValidationComparisons}
            status={status}
          />
        )}

        {currentStep === 8 && (
          <Step7EditRubric
            rubric={editingRubric}
            onSave={handleSaveEditedRubric}
            onCancel={() => setCurrentStep(6)}
            status={status}
          />
        )}

        {currentStep === 9 && (
          <Step8EditEvaluation
            evaluation={editingEvaluation}
            onSave={handleSaveEditedEvaluation}
            onCancel={() => setCurrentStep(5)}
            status={status}
          />
        )}

        {currentStep === 10 && (
          <Step10LearnerReport
            learnerReport={learnerReport}
            evaluation={evaluation}
            onBack={() => setCurrentStep(4)}
            status={status}
          />
        )}
      </main>
    </div>
  )
}

function StepIndicator({ number, title, subtitle, active, completed, onClick }) {
  return (
    <div className="step-indicator" onClick={onClick} style={{ cursor: 'pointer' }}>
      <div className={`step-circle ${active ? 'active' : ''} ${completed ? 'completed' : ''}`}>
        <span className="step-number">{number}</span>
      </div>
      <div className="step-info">
        <div className="step-title">{title}</div>
        <div className="step-subtitle">{subtitle}</div>
      </div>
    </div>
  )
}

function Step1UploadInputs({ rubricFile, setRubricFile, onGenerateSkeleton, status }) {
  const handleRubricFileChange = (event) => {
    const file = event.target.files[0]
    if (file) {
      setRubricFile(file)
    }
  }

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Upload Rubric</h2>
        <p className="step-description">Upload your grading rubric (PDF format)</p>

        <div className="form-section">
          <label htmlFor="rubric-file">Upload Rubric (PDF)</label>
          <div className="file-input-wrapper">
            <input
              type="file"
              id="rubric-file"
              accept=".pdf,.txt"
              onChange={handleRubricFileChange}
            />
            <label htmlFor="rubric-file" className="file-input-label">
              {rubricFile ? rubricFile.name : 'Choose rubric file...'}
            </label>
          </div>
        </div>

        {status.message && (
          <p className={`status ${status.type}`}>{status.message}</p>
        )}

        <button type="button" className="primary-button" onClick={onGenerateSkeleton} disabled={!rubricFile}>
          Parse Rubric
        </button>
      </div>
    </div>
  )
}

function Step2ParseRubric({ parsedRubric, onConfirm, onBack, status, providerMeta }) {
  const [expandedItems, setExpandedItems] = useState(new Set())
  const [editingItem, setEditingItem] = useState(null)
  const [editedRubric, setEditedRubric] = useState(parsedRubric)

  console.log('Step2ParseRubric - parsedRubric:', parsedRubric)
  console.log('Step2ParseRubric - providerMeta:', providerMeta)

  useEffect(() => {
    setEditedRubric(parsedRubric)
  }, [parsedRubric])

  if (!editedRubric) {
    return (
      <div className="step-content">
        <div className="step-card">
          <h2>Parse Rubric</h2>
          <p className="step-description">Review and confirm the extracted criteria</p>
          <p className="empty-state">No rubric parsed yet. Go back to Step 1 and click "Parse Rubric".</p>
          <button type="button" className="secondary-button" onClick={onBack}>
            Back to Step 1
          </button>
        </div>
      </div>
    )
  }

  const criteria = editedRubric.criteria || editedRubric.items || []

  const toggleExpand = (index) => {
    const newExpanded = new Set(expandedItems)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedItems(newExpanded)
  }

  const handleEdit = (index, subIndex = null) => {
    setEditingItem({ index, subIndex })
  }

  const handleSaveEdit = (index, subIndex, field, value) => {
    const newCriteria = [...criteria]
    if (subIndex !== null) {
      // Editing sub-criterion
      const subCriteria = newCriteria[index].metadata?.sub_criteria || []
      subCriteria[subIndex] = { ...subCriteria[subIndex], [field]: value }
      newCriteria[index] = {
        ...newCriteria[index],
        metadata: { ...newCriteria[index].metadata, sub_criteria: subCriteria }
      }
    } else {
      // Editing main criterion
      newCriteria[index] = { ...newCriteria[index], [field]: value }
    }
    setEditedRubric({ ...editedRubric, criteria: newCriteria })
  }

  const handleConfirmWithEdits = () => {
    onConfirm(editedRubric)
  }

  const getSubCriteria = (item) => {
    return item.metadata?.sub_criteria || []
  }

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Parse Rubric</h2>
        <p className="step-description">Review and confirm the extracted criteria</p>
        <p className="provider-note">
          Parsed using <strong>{providerMeta.label}</strong>
        </p>

        <div className="rubric-preview">
          <h3>{editedRubric.title || 'Untitled Rubric'}</h3>
          <p className="rubric-type">Type: {editedRubric.rubric_type || 'analytic'}</p>
          <p className="rubric-type">Total Criteria: {criteria.length}</p>
          <p className="rubric-type">Max Score: {editedRubric.max_total_score || 0}</p>

          {criteria.length === 0 ? (
            <p className="empty-state">No criteria found in rubric.</p>
          ) : (
            <div className="criteria-list">
              {criteria.map((item, index) => {
                const subCriteria = getSubCriteria(item)
                const hasSubCriteria = subCriteria.length > 0
                const isExpanded = expandedItems.has(index)
                const isEditing = editingItem?.index === index && editingItem?.subIndex === null

                return (
                  <div key={index} className="criterion-item collapsible">
                    <div className="criterion-header clickable" onClick={() => hasSubCriteria && toggleExpand(index)}>
                      {hasSubCriteria && (
                        <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                      )}
                      <span className="criterion-number">{index + 1}</span>
                      <span className="criterion-name">{item.name}</span>
                      <span className="criterion-score">0-{item.max_score}</span>
                      <button
                        className="edit-icon-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleEdit(index)
                        }}
                        title="Edit"
                      >
                        ✏️
                      </button>
                    </div>

                    {isEditing ? (
                      <div className="edit-section">
                        <textarea
                          className="criterion-description-input"
                          value={item.description || ''}
                          onChange={(e) => handleSaveEdit(index, null, 'description', e.target.value)}
                          placeholder="Description"
                          rows={2}
                        />
                        <input
                          type="number"
                          className="criterion-score-input"
                          value={item.max_score || 0}
                          onChange={(e) => handleSaveEdit(index, null, 'max_score', parseFloat(e.target.value))}
                          placeholder="Max score"
                          step="0.5"
                        />
                        <button className="secondary-button small" onClick={() => setEditingItem(null)}>
                          Done
                        </button>
                      </div>
                    ) : item.description && (
                      <p className="criterion-description">{item.description}</p>
                    )}

                    {hasSubCriteria && isExpanded && (
                      <div className="sub-criteria-list">
                        {subCriteria.map((subItem, subIndex) => {
                          const isSubEditing = editingItem?.index === index && editingItem?.subIndex === subIndex
                          return (
                            <div key={subIndex} className="criterion-item sub-item">
                              <div className="criterion-header">
                                <span className="criterion-number">{index + 1}.{subIndex + 1}</span>
                                <span className="criterion-name">{subItem.name}</span>
                                <span className="criterion-score">0-{subItem.max_score}</span>
                                <button
                                  className="edit-icon-btn"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    handleEdit(index, subIndex)
                                  }}
                                  title="Edit"
                                >
                                  ✏️
                                </button>
                              </div>

                              {isSubEditing ? (
                                <div className="edit-section">
                                  <textarea
                                    className="criterion-description-input"
                                    value={subItem.description || ''}
                                    onChange={(e) => handleSaveEdit(index, subIndex, 'description', e.target.value)}
                                    placeholder="Description"
                                    rows={2}
                                  />
                                  <input
                                    type="number"
                                    className="criterion-score-input"
                                    value={subItem.max_score || 0}
                                    onChange={(e) => handleSaveEdit(index, subIndex, 'max_score', parseFloat(e.target.value))}
                                    placeholder="Max score"
                                    step="0.5"
                                  />
                                  <button className="secondary-button small" onClick={() => setEditingItem(null)}>
                                    Done
                                  </button>
                                </div>
                              ) : subItem.description && (
                                <p className="criterion-description">{subItem.description}</p>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {status.message && (
          <p className={`status ${status.type}`}>{status.message}</p>
        )}

        <div className="button-group">
          <button type="button" className="secondary-button" onClick={onBack}>
            Back
          </button>
          <button type="button" className="primary-button" onClick={handleConfirmWithEdits} disabled={criteria.length === 0}>
            Confirm & Continue
          </button>
        </div>
      </div>
    </div>
  )
}

function Step3AIGrading({ savedRubrics, savedRubricId, setSavedRubricId, transcriptText, setTranscriptText, generateLearnerReport, setGenerateLearnerReport, onStartGrading, onBack, status, providerMeta }) {
  return (
    <div className="step-content">
      <div className="step-card">
        <h2>AI Grading</h2>
        <p className="step-description">Select a rubric and paste the transcript to evaluate</p>
        <p className="provider-note">
          Scoring powered by <strong>{providerMeta.label}</strong>
        </p>

        <div className="form-section">
          <label htmlFor="rubric-select">Select Saved Rubric</label>
          <select
            id="rubric-select"
            value={savedRubricId || ''}
            onChange={(e) => setSavedRubricId(e.target.value ? parseInt(e.target.value) : null)}
          >
            <option value="">-- Select a rubric --</option>
            {savedRubrics.map((rubric) => (
              <option key={rubric.id} value={rubric.id}>
                {rubric.title} ({rubric.items?.length || 0} criteria)
              </option>
            ))}
          </select>
        </div>

        <div className="form-section">
          <label htmlFor="transcript-text">Paste Transcript Text</label>
          <textarea
            id="transcript-text"
            placeholder="Paste the consultation transcript here..."
            value={transcriptText}
            onChange={(e) => setTranscriptText(e.target.value)}
            rows={12}
          />
          <p className="input-tip">Paste the dialogue between the learner and patient</p>
        </div>

        <div className="form-section">
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={generateLearnerReport}
              onChange={(e) => setGenerateLearnerReport(e.target.checked)}
              style={{ width: '18px', height: '18px', cursor: 'pointer' }}
            />
            <span>Generate Student Learner Report</span>
          </label>
          <p className="input-tip">Include personalized feedback with strengths, growth opportunities, and actionable suggestions</p>
        </div>

        {status.message && (
          <p className={`status ${status.type}`}>{status.message}</p>
        )}

        <div className="button-group">
          <button type="button" className="secondary-button" onClick={onBack}>
            Back
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={onStartGrading}
            disabled={status.type === 'processing'}
          >
            {status.type === 'processing' ? 'Grading...' : 'Start Grading'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Step4GenerateReports({ evaluation, onDownloadPDF, onContinue, generateLearnerReport, onGenerateLearnerReport, providerMeta }) {
  if (!evaluation) {
    return (
      <div className="step-content">
        <div className="step-card">
          <h2>Generate Reports</h2>
          <p className="empty-state">No evaluation results yet.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Evaluation Results</h2>
        <p className="step-description">Review the AI-generated scores and feedback</p>

        <div className="results-summary">
          <div className="result-header">
            <div>
              <p className="eyebrow">{evaluation.rubric_title}</p>
              <h3 className="performance-band">{evaluation.performance_band}</h3>
            </div>
            <div className="score-display">
              <span className="score-large">
                {evaluation.total_score}/{evaluation.max_total_score}
              </span>
              <button
                className="secondary-button small"
                type="button"
                onClick={() => onDownloadPDF(evaluation.id)}
                title="Download PDF Report"
              >
                Download PDF
              </button>
            </div>
          </div>

          <p className="feedback-summary">{evaluation.feedback_summary}</p>

          <div className="criteria-table">
            {evaluation.criterion_scores.map((criterion) => (
              <div key={criterion.id} className="criterion-row">
                <div className="criterion-info">
                  <p className="criterion-name">{criterion.name}</p>
                  <p className="criterion-description">
                    {criterion.description || 'Free-form criterion'}
                  </p>
                </div>
                <div className="criterion-result">
                  <span className="criterion-score-value">
                    {criterion.score}/{criterion.max_score}
                  </span>
                  <p className="criterion-feedback">{criterion.feedback}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="button-group" style={{ marginTop: '2rem' }}>
          {generateLearnerReport && (
            <button type="button" className="primary-button" onClick={onGenerateLearnerReport}>
              Generate Student Learner Report
            </button>
          )}
          <button type="button" className={generateLearnerReport ? "secondary-button" : "primary-button"} onClick={onContinue}>
            Continue to History
          </button>
        </div>
      </div>
    </div>
  )
}

function Step5Validation({ history, onRefresh, onDownloadPDF, onEditEvaluation }) {
  const [selectedEvalId, setSelectedEvalId] = useState(null)
  const [selectedEval, setSelectedEval] = useState(null)
  const [loadingEval, setLoadingEval] = useState(false)
  const [editingTitleId, setEditingTitleId] = useState(null)
  const [editingTitleValue, setEditingTitleValue] = useState('')

  const handleStartEditTitle = (item, e) => {
    e.stopPropagation()
    setEditingTitleId(item.id)
    setEditingTitleValue(item.rubric_title)
  }

  const handleSaveTitle = async (evaluationId, e) => {
    e.stopPropagation()
    try {
      const response = await fetch(`${API_BASE_URL}/api/evaluations/${evaluationId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rubric_title: editingTitleValue }),
      })

      if (!response.ok) {
        throw new Error('Failed to update title')
      }

      setEditingTitleId(null)
      setEditingTitleValue('')
      onRefresh()
    } catch (error) {
      console.error('Error updating title:', error)
      alert('Failed to update title. Please try again.')
    }
  }

  const handleCancelEditTitle = (e) => {
    e.stopPropagation()
    setEditingTitleId(null)
    setEditingTitleValue('')
  }

  const handleViewEvaluation = async (evaluationId) => {
    if (selectedEvalId === evaluationId) {
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

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Validation & History</h2>
        <p className="step-description">Compare AI evaluations with human scores and review past evaluations</p>

        <div className="history-section">
          <div className="history-header">
            <h3>Recent Evaluations</h3>
            <button className="secondary-button small" type="button" onClick={onRefresh}>
              Refresh
            </button>
          </div>

          {history.length === 0 && <p className="empty-state">No history to display yet.</p>}

          {history.map((item) => (
            <div key={item.id}>
              <div
                className={`history-item ${selectedEvalId === item.id ? 'active' : ''}`}
                onClick={() => handleViewEvaluation(item.id)}
              >
                <div>
                  {editingTitleId === item.id ? (
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }} onClick={(e) => e.stopPropagation()}>
                      <input
                        type="text"
                        value={editingTitleValue}
                        onChange={(e) => setEditingTitleValue(e.target.value)}
                        style={{
                          padding: '0.25rem 0.5rem',
                          fontSize: '1rem',
                          border: '2px solid #3b82f6',
                          borderRadius: '4px',
                          flex: 1
                        }}
                        autoFocus
                      />
                      <button
                        className="secondary-button small"
                        onClick={(e) => handleSaveTitle(item.id, e)}
                        title="Save"
                      >
                        Save
                      </button>
                      <button
                        className="secondary-button small"
                        onClick={handleCancelEditTitle}
                        title="Cancel"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <p className="history-title">{item.rubric_title}</p>
                      <button
                        className="edit-icon-btn"
                        onClick={(e) => handleStartEditTitle(item, e)}
                        title="Rename"
                        style={{ fontSize: '0.875rem', padding: '0.25rem' }}
                      >
                        ✏️
                      </button>
                    </div>
                  )}
                  <p className="history-meta">
                    {new Date(item.created_at).toLocaleString()} · {item.performance_band}
                  </p>
                </div>
                <div className="history-actions">
                  <span className="history-score">
                    {item.total_score}/{item.max_total_score}
                  </span>
                  <button
                    className="secondary-button small"
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onEditEvaluation(item.id)
                    }}
                    title="Edit Score"
                  >
                    Edit Score
                  </button>
                  <button
                    className="secondary-button small"
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDownloadPDF(item.id, e)
                    }}
                    title="Download PDF"
                  >
                    PDF
                  </button>
                </div>
              </div>
              {selectedEvalId === item.id && (
                <div className="history-detail">
                  {loadingEval ? (
                    <p>Loading details...</p>
                  ) : selectedEval ? (
                    <div className="history-detail-content">
                      <p className="feedback-summary">{selectedEval.feedback_summary}</p>
                      {selectedEval.rubric_summary && (
                        <p className="rubric-hint">
                          Rubric: {selectedEval.rubric_summary.slice(0, 180)}...
                        </p>
                      )}
                      <div className="criteria-table">
                        {selectedEval.criterion_scores?.map((criterion) => (
                          <div key={criterion.id} className="criterion-row">
                            <div className="criterion-info">
                              <p className="criterion-name">{criterion.name}</p>
                              <p className="criterion-description">
                                {criterion.description || 'Free-form criterion'}
                              </p>
                            </div>
                            <div className="criterion-result">
                              <span className="criterion-score-value">
                                {criterion.score}/{criterion.max_score}
                              </span>
                              <p className="criterion-feedback">{criterion.feedback}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p>Failed to load evaluation details.</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Step6ManageRubrics({ savedRubrics, onRefresh, llmProvider, onEditRubric }) {
  const [selectedRubricId, setSelectedRubricId] = useState(null)
  const [selectedRubric, setSelectedRubric] = useState(null)
  const [loadingRubric, setLoadingRubric] = useState(false)

  const handleViewRubric = async (rubricId) => {
    if (selectedRubricId === rubricId) {
      setSelectedRubricId(null)
      setSelectedRubric(null)
      return
    }

    setSelectedRubricId(rubricId)
    setLoadingRubric(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics/${rubricId}`)
      if (!response.ok) {
        throw new Error('Failed to load rubric details')
      }
      const data = await response.json()
      setSelectedRubric(data)
    } catch (error) {
      console.error('Error loading rubric:', error)
      setSelectedRubric(null)
    } finally {
      setLoadingRubric(false)
    }
  }

  const handleEditRubric = async (rubricId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics/${rubricId}`)
      if (!response.ok) {
        throw new Error('Failed to load rubric details')
      }
      const data = await response.json()
      onEditRubric(data)
    } catch (error) {
      console.error('Error loading rubric:', error)
      alert('Failed to load rubric for editing. Please try again.')
    }
  }

  const handleDeleteRubric = async (rubricId) => {
    if (!confirm('Are you sure you want to delete this rubric? This action cannot be undone.')) {
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics/${rubricId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Failed to delete rubric')
      }
      alert('Rubric deleted successfully')
      setSelectedRubricId(null)
      setSelectedRubric(null)
      onRefresh()
    } catch (error) {
      console.error('Error deleting rubric:', error)
      alert('Failed to delete rubric. Please try again.')
    }
  }

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Manage Saved Rubrics</h2>
        <p className="step-description">View, edit, and delete your saved rubrics</p>

        <div className="history-section">
          <div className="history-header">
            <h3>Saved Rubrics ({savedRubrics.length})</h3>
            <button className="secondary-button small" type="button" onClick={onRefresh}>
              Refresh
            </button>
          </div>

          {savedRubrics.length === 0 && <p className="empty-state">No saved rubrics yet. Upload and parse a rubric to get started.</p>}

          {savedRubrics.map((rubric) => (
            <div key={rubric.id}>
              <div
                className={`history-item ${selectedRubricId === rubric.id ? 'active' : ''}`}
                onClick={() => handleViewRubric(rubric.id)}
              >
                <div>
                  <p className="history-title">{rubric.title}</p>
                  <p className="history-meta">
                    {rubric.items?.length || 0} criteria · {rubric.rubric_type} · Created {new Date(rubric.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="history-actions">
                  <button
                    className="secondary-button small"
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleEditRubric(rubric.id)
                    }}
                    title="Edit Rubric"
                  >
                    Edit
                  </button>
                  <button
                    className="secondary-button small"
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDeleteRubric(rubric.id)
                    }}
                    title="Delete Rubric"
                  >
                    Delete
                  </button>
                </div>
              </div>
              {selectedRubricId === rubric.id && (
                <div className="history-detail">
                  {loadingRubric ? (
                    <p>Loading rubric details...</p>
                  ) : selectedRubric ? (
                    <div className="history-detail-content">
                      <p className="rubric-hint">Type: {selectedRubric.rubric_type}</p>
                      {selectedRubric.summary && (
                        <p className="feedback-summary">{selectedRubric.summary}</p>
                      )}
                      <h4 style={{ marginTop: '1rem', marginBottom: '0.5rem' }}>Criteria ({selectedRubric.items?.length || 0}):</h4>
                      <div className="criteria-list">
                        {selectedRubric.items?.map((item, index) => (
                          <div key={item.id} className="criterion-item">
                            <div className="criterion-header">
                              <span className="criterion-number">{index + 1}</span>
                              <span className="criterion-name">{item.name}</span>
                              {item.max_score && <span className="criterion-score">Max: {item.max_score}</span>}
                            </div>
                            {item.description && (
                              <p className="criterion-description">{item.description}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p>Failed to load rubric details.</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Step7EditRubric({ rubric, onSave, onCancel, status }) {
  const [editedRubric, setEditedRubric] = useState(rubric)

  useEffect(() => {
    setEditedRubric(rubric)
  }, [rubric])

  if (!editedRubric) {
    return (
      <div className="step-content">
        <div className="step-card">
          <h2>Edit Rubric</h2>
          <p className="empty-state">No rubric selected for editing.</p>
          <button type="button" className="secondary-button" onClick={onCancel}>
            Back to Manage Rubrics
          </button>
        </div>
      </div>
    )
  }

  const handleTitleChange = (e) => {
    setEditedRubric({ ...editedRubric, title: e.target.value })
  }

  const handleItemChange = (index, field, value) => {
    const updatedItems = [...editedRubric.items]
    updatedItems[index] = { ...updatedItems[index], [field]: value }
    setEditedRubric({ ...editedRubric, items: updatedItems })
  }

  const handleAddItem = () => {
    const newItem = {
      name: 'New Criterion',
      description: '',
      max_score: 10,
      item_type: 'criterion',
      order_index: editedRubric.items.length,
      metadata: {}
    }
    setEditedRubric({ ...editedRubric, items: [...editedRubric.items, newItem] })
  }

  const handleRemoveItem = (index) => {
    if (!confirm('Are you sure you want to remove this criterion?')) {
      return
    }
    const updatedItems = editedRubric.items.filter((_, i) => i !== index)
    setEditedRubric({ ...editedRubric, items: updatedItems })
  }

  const handleSave = () => {
    onSave(editedRubric)
  }

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Edit Rubric</h2>
        <p className="step-description">Modify rubric title, criteria, and scoring details</p>

        <div className="form-section">
          <label htmlFor="rubric-title">Rubric Title</label>
          <input
            type="text"
            id="rubric-title"
            value={editedRubric.title}
            onChange={handleTitleChange}
          />
        </div>

        <div className="form-section">
          <label>Rubric Type</label>
          <p className="input-tip">{editedRubric.rubric_type}</p>
        </div>

        <div className="form-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <label>Criteria ({editedRubric.items.length})</label>
            <button type="button" className="secondary-button small" onClick={handleAddItem}>
              Add Criterion
            </button>
          </div>

          <div className="criteria-list">
            {editedRubric.items.map((item, index) => (
              <div key={index} className="criterion-item editable">
                <div className="criterion-header">
                  <span className="criterion-number">{index + 1}</span>
                  <input
                    type="text"
                    className="criterion-name-input"
                    value={item.name}
                    onChange={(e) => handleItemChange(index, 'name', e.target.value)}
                    placeholder="Criterion name"
                  />
                  <input
                    type="number"
                    className="criterion-score-input"
                    value={item.max_score || 0}
                    onChange={(e) => handleItemChange(index, 'max_score', parseFloat(e.target.value))}
                    placeholder="Max score"
                    style={{ width: '80px' }}
                  />
                  <button
                    type="button"
                    className="secondary-button small"
                    onClick={() => handleRemoveItem(index)}
                    title="Remove criterion"
                  >
                    Remove
                  </button>
                </div>
                <textarea
                  className="criterion-description-input"
                  value={item.description || ''}
                  onChange={(e) => handleItemChange(index, 'description', e.target.value)}
                  placeholder="Criterion description"
                  rows={3}
                />
              </div>
            ))}
          </div>
        </div>

        {status.message && (
          <p className={`status ${status.type}`}>{status.message}</p>
        )}

        <div className="button-group">
          <button type="button" className="secondary-button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="primary-button" onClick={handleSave}>
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}

function Step8EditEvaluation({ evaluation, onSave, onCancel, status }) {
  const [editedEvaluation, setEditedEvaluation] = useState(evaluation)

  useEffect(() => {
    setEditedEvaluation(evaluation)
  }, [evaluation])

  if (!editedEvaluation) {
    return (
      <div className="step-content">
        <div className="step-card">
          <h2>Edit Evaluation</h2>
          <p className="empty-state">No evaluation selected for editing.</p>
          <button type="button" className="secondary-button" onClick={onCancel}>
            Back to History
          </button>
        </div>
      </div>
    )
  }

  const handleScoreChange = (index, field, value) => {
    const updatedScores = [...editedEvaluation.criterion_scores]
    updatedScores[index] = { ...updatedScores[index], [field]: value }
    setEditedEvaluation({ ...editedEvaluation, criterion_scores: updatedScores })
  }

  const calculateTotalScore = () => {
    return editedEvaluation.criterion_scores.reduce((sum, cs) => sum + (parseFloat(cs.score) || 0), 0)
  }

  const handleSave = () => {
    onSave(editedEvaluation)
  }

  const totalScore = calculateTotalScore()

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Edit Evaluation Scores</h2>
        <p className="step-description">Modify individual criterion scores and feedback</p>

        <div className="form-section">
          <h3>{editedEvaluation.rubric_title}</h3>
          <p className="rubric-type">
            Total Score: <strong>{totalScore.toFixed(1)}</strong> / {editedEvaluation.max_total_score}
          </p>
          {editedEvaluation.performance_band && (
            <p className="rubric-type">Performance Band: {editedEvaluation.performance_band}</p>
          )}
        </div>

        <div className="form-section">
          <label>Criterion Scores ({editedEvaluation.criterion_scores?.length || 0})</label>

          <div className="criteria-list">
            {editedEvaluation.criterion_scores?.map((criterion, index) => (
              <div key={criterion.id || index} className="criterion-item editable">
                <div className="criterion-header">
                  <span className="criterion-number">{index + 1}</span>
                  <span className="criterion-name">{criterion.name}</span>
                  <input
                    type="number"
                    className="criterion-score-input"
                    value={criterion.score || 0}
                    onChange={(e) => handleScoreChange(index, 'score', parseFloat(e.target.value) || 0)}
                    placeholder="Score"
                    step="0.1"
                    min="0"
                    max={criterion.max_score}
                    style={{ width: '80px' }}
                  />
                  <span className="criterion-score">/ {criterion.max_score}</span>
                </div>
                {criterion.description && (
                  <p className="criterion-description">{criterion.description}</p>
                )}
                <textarea
                  className="criterion-description-input"
                  value={criterion.feedback || ''}
                  onChange={(e) => handleScoreChange(index, 'feedback', e.target.value)}
                  placeholder="Feedback (optional)"
                  rows={2}
                />
              </div>
            ))}
          </div>
        </div>

        {status.message && (
          <p className={`status ${status.type}`}>{status.message}</p>
        )}

        <div className="button-group">
          <button type="button" className="secondary-button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="primary-button" onClick={handleSave}>
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}

function Step9ValidationComparison({ history, validationComparisons, selectedComparison, onUploadHumanGrading, onViewComparison, onRefresh, status }) {
  const [uploadEvalId, setUploadEvalId] = useState(null)
  const [humanGradingFile, setHumanGradingFile] = useState(null)
  const [notes, setNotes] = useState('')
  const [expandedCriterionIndex, setExpandedCriterionIndex] = useState(null)

  const handleFileChange = (event) => {
    const file = event.target.files[0]
    if (file) {
      setHumanGradingFile(file)
    }
  }

  const handleUpload = async () => {
    if (!humanGradingFile || !uploadEvalId) {
      alert('Please select an evaluation and upload a PDF file.')
      return
    }

    await onUploadHumanGrading(uploadEvalId, humanGradingFile, notes)

    // Reset form
    setHumanGradingFile(null)
    setNotes('')
    setUploadEvalId(null)
    onRefresh()
  }

  const handleViewDetails = (evaluationId) => {
    onViewComparison(evaluationId)
  }

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Validation: AI vs Human Grading Comparison</h2>
        <p className="step-description">Upload human grading PDFs to compare with AI evaluations</p>

        {/* Upload Section */}
        <div className="form-section" style={{ backgroundColor: '#f9fafb', padding: '1.5rem', borderRadius: '8px', marginBottom: '2rem' }}>
          <h3>Upload Human Grading PDF</h3>
          <p className="input-tip" style={{ marginBottom: '1.5rem' }}>
            Upload a PDF containing human-graded scores. The AI will automatically extract the grader name, scores, and feedback.
          </p>

          <div style={{ marginBottom: '1.5rem' }}>
            <label htmlFor="eval-select" style={{ fontWeight: '600', display: 'block', marginBottom: '0.5rem' }}>
              Select AI Evaluation to Compare Against
            </label>
            <select
              id="eval-select"
              value={uploadEvalId || ''}
              onChange={(e) => setUploadEvalId(e.target.value ? parseInt(e.target.value) : null)}
              style={{
                width: '100%',
                padding: '0.75rem',
                fontSize: '1rem',
                border: '2px solid #d1d5db',
                borderRadius: '6px',
                backgroundColor: 'white'
              }}
            >
              <option value="">-- Select an AI evaluation --</option>
              {history.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.rubric_title} - AI Score: {item.total_score}/{item.max_total_score} - {new Date(item.created_at).toLocaleDateString()}
                </option>
              ))}
            </select>
          </div>

          <div className="file-input-wrapper" style={{ marginBottom: '1.5rem' }}>
            <label htmlFor="human-grading-file" style={{ fontWeight: '600', display: 'block', marginBottom: '0.5rem' }}>
              Human Grading PDF
            </label>
            <input
              type="file"
              id="human-grading-file"
              accept=".pdf"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
            <label
              htmlFor="human-grading-file"
              className="file-input-label"
              style={{
                display: 'inline-block',
                padding: '0.75rem 1.5rem',
                backgroundColor: humanGradingFile ? '#10b981' : '#3b82f6',
                color: 'white',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: '500'
              }}
            >
              {humanGradingFile ? `✓ ${humanGradingFile.name}` : '📄 Choose PDF file'}
            </label>
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label htmlFor="notes" style={{ fontWeight: '600', display: 'block', marginBottom: '0.5rem' }}>
              Notes (optional)
            </label>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add any notes about the human grading session"
              rows={3}
              style={{
                width: '100%',
                padding: '0.75rem',
                border: '2px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '0.95rem'
              }}
            />
          </div>

          <button
            type="button"
            className="primary-button"
            onClick={handleUpload}
            disabled={!humanGradingFile || !uploadEvalId}
            style={{
              padding: '0.75rem 2rem',
              fontSize: '1rem',
              opacity: (!humanGradingFile || !uploadEvalId) ? 0.5 : 1
            }}
          >
            Upload & Parse Human Grading
          </button>
        </div>

        {status.message && (
          <p className={`status ${status.type}`}>{status.message}</p>
        )}

        {/* Comparisons List */}
        <div className="form-section" style={{ marginTop: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>Validation Comparisons</h3>
            <button type="button" className="secondary-button small" onClick={onRefresh}>
              Refresh
            </button>
          </div>

          {validationComparisons.length === 0 ? (
            <p className="empty-state">No validation comparisons yet. Upload human grading data to get started.</p>
          ) : (
            <div className="history-list">
              {validationComparisons.map((comparison) => (
                <div key={comparison.evaluation_id} className="history-item">
                  <div className="history-info">
                    <h4>{comparison.rubric_title}</h4>
                    <p className="history-meta">
                      AI: {comparison.ai_total_score} | Human: {comparison.human_total_score} |
                      Difference: <strong style={{ color: Math.abs(comparison.difference) > 5 ? '#ef4444' : '#10b981' }}>
                        {comparison.difference > 0 ? '+' : ''}{comparison.difference.toFixed(1)}
                      </strong>
                      {comparison.grader_name && ` | Grader: ${comparison.grader_name}`}
                    </p>
                  </div>
                  <div className="history-actions">
                    <button
                      className="secondary-button small"
                      type="button"
                      onClick={() => handleViewDetails(comparison.evaluation_id)}
                      title="View Detailed Comparison"
                    >
                      View Details
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Detailed Comparison View */}
        {selectedComparison && (
          <div className="form-section" style={{ marginTop: '2rem', border: '2px solid #3b82f6', padding: '1.5rem', borderRadius: '8px' }}>
            <h3>Detailed Comparison: {selectedComparison.rubric_title}</h3>

            {/* Summary Statistics */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ padding: '1rem', backgroundColor: '#f3f4f6', borderRadius: '6px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>AI Total Score</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                  {selectedComparison.ai_total_score}/{selectedComparison.ai_max_total_score}
                </div>
              </div>
              <div style={{ padding: '1rem', backgroundColor: '#f3f4f6', borderRadius: '6px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>Human Total Score</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                  {selectedComparison.human_total_score}/{selectedComparison.human_max_total_score}
                </div>
              </div>
              <div style={{ padding: '1rem', backgroundColor: '#f3f4f6', borderRadius: '6px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>Total Difference</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: Math.abs(selectedComparison.total_difference) > 5 ? '#ef4444' : '#10b981' }}>
                  {selectedComparison.total_difference > 0 ? '+' : ''}{selectedComparison.total_difference.toFixed(1)}
                </div>
              </div>
              <div style={{ padding: '1rem', backgroundColor: '#f3f4f6', borderRadius: '6px' }}>
                <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>Mean Absolute Difference</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                  {selectedComparison.mean_absolute_difference.toFixed(2)}
                </div>
              </div>
            </div>

            {/* Criterion-by-Criterion Comparison */}
            <h4>Criterion Comparison</h4>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f3f4f6' }}>
                    <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #d1d5db', width: '5%' }}></th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #d1d5db' }}>Criterion</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #d1d5db' }}>AI Score</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #d1d5db' }}>Human Score</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #d1d5db' }}>Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedComparison.criterion_comparisons.map((criterion, index) => {
                    const diffColor = !criterion.difference ? '#6b7280' :
                                     Math.abs(criterion.difference) > 2 ? '#ef4444' :
                                     Math.abs(criterion.difference) > 1 ? '#f59e0b' : '#10b981'
                    const hasDifference = criterion.difference !== null && Math.abs(criterion.difference) > 0
                    const isExpanded = expandedCriterionIndex === index

                    return (
                      <>
                        <tr
                          key={index}
                          style={{
                            borderBottom: '1px solid #e5e7eb',
                            cursor: hasDifference ? 'pointer' : 'default',
                            backgroundColor: isExpanded ? '#f9fafb' : 'transparent'
                          }}
                          onClick={() => hasDifference && setExpandedCriterionIndex(isExpanded ? null : index)}
                        >
                          <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                            {hasDifference && (
                              <span style={{ fontSize: '1.25rem', color: '#6b7280' }}>
                                {isExpanded ? '▼' : '▶'}
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '0.75rem' }}>{criterion.criterion_name}</td>
                          <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                            {criterion.ai_score !== null ? `${criterion.ai_score}/${criterion.ai_max_score}` : 'N/A'}
                          </td>
                          <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                            {criterion.human_score !== null ? `${criterion.human_score}/${criterion.human_max_score}` : 'N/A'}
                          </td>
                          <td style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 'bold', color: diffColor }}>
                            {criterion.difference !== null ?
                              (criterion.difference > 0 ? '+' : '') + criterion.difference.toFixed(1) :
                              'N/A'}
                          </td>
                        </tr>
                        {isExpanded && hasDifference && (
                          <tr key={`${index}-details`} style={{ backgroundColor: '#f9fafb' }}>
                            <td colSpan={5} style={{ padding: '1rem', borderBottom: '1px solid #e5e7eb' }}>
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                {/* AI Feedback */}
                                <div style={{
                                  padding: '1rem',
                                  backgroundColor: '#eff6ff',
                                  borderRadius: '6px',
                                  borderLeft: '4px solid #3b82f6'
                                }}>
                                  <h5 style={{ margin: '0 0 0.5rem 0', color: '#3b82f6', fontWeight: '600' }}>
                                    AI Feedback
                                  </h5>
                                  <p style={{ margin: 0, fontSize: '0.9rem', lineHeight: '1.5' }}>
                                    {criterion.ai_feedback || 'No feedback provided'}
                                  </p>
                                </div>
                                {/* Human Feedback */}
                                <div style={{
                                  padding: '1rem',
                                  backgroundColor: '#fef3c7',
                                  borderRadius: '6px',
                                  borderLeft: '4px solid #f59e0b'
                                }}>
                                  <h5 style={{ margin: '0 0 0.5rem 0', color: '#f59e0b', fontWeight: '600' }}>
                                    Human Feedback
                                  </h5>
                                  <p style={{ margin: 0, fontSize: '0.9rem', lineHeight: '1.5' }}>
                                    {criterion.human_feedback || 'No feedback provided'}
                                  </p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <button
              type="button"
              className="secondary-button"
              onClick={() => onViewComparison(null)}
              style={{ marginTop: '1rem' }}
            >
              Close Details
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function Step10LearnerReport({ learnerReport, evaluation, onBack, status }) {
  if (!learnerReport) {
    return (
      <div className="step-content">
        <div className="step-card">
          <h2>Student Learner Report</h2>
          <p className="empty-state">No learner report generated yet.</p>
          <button type="button" className="secondary-button" onClick={onBack}>
            Back
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="step-content">
      <div className="step-card">
        <h2>Student Learner Report</h2>
        <p className="step-description">Personalized feedback for {evaluation?.rubric_title || 'student'}</p>

        <div className="results-summary">
          <div className="result-header">
            <div>
              <p className="eyebrow">{evaluation?.rubric_title}</p>
              <h3 className="performance-band">{evaluation?.performance_band}</h3>
            </div>
            <div className="score-display">
              <span className="score-large">
                {evaluation?.total_score}/{evaluation?.max_total_score}
              </span>
            </div>
          </div>

          {/* Top Strengths */}
          <div style={{ marginTop: '2rem' }}>
            <h3 style={{ color: '#10b981', marginBottom: '1rem' }}>Top Strengths</h3>
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {learnerReport.top_strengths?.map((strength, index) => (
                <li key={index} style={{
                  padding: '1rem',
                  marginBottom: '0.5rem',
                  backgroundColor: '#f0fdf4',
                  borderLeft: '4px solid #10b981',
                  borderRadius: '4px'
                }}>
                  {strength}
                </li>
              ))}
            </ul>
          </div>

          {/* Opportunities for Growth */}
          <div style={{ marginTop: '2rem' }}>
            <h3 style={{ color: '#f59e0b', marginBottom: '1rem' }}>Opportunities for Growth</h3>
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {learnerReport.growth_opportunities?.map((opportunity, index) => (
                <li key={index} style={{
                  padding: '1rem',
                  marginBottom: '0.5rem',
                  backgroundColor: '#fffbeb',
                  borderLeft: '4px solid #f59e0b',
                  borderRadius: '4px'
                }}>
                  {opportunity}
                </li>
              ))}
            </ul>
          </div>

          {/* Actionable Suggestions */}
          <div style={{ marginTop: '2rem' }}>
            <h3 style={{ color: '#3b82f6', marginBottom: '1rem' }}>Actionable Suggestions</h3>
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {learnerReport.actionable_suggestions?.map((suggestion, index) => (
                <li key={index} style={{
                  padding: '1rem',
                  marginBottom: '0.5rem',
                  backgroundColor: '#eff6ff',
                  borderLeft: '4px solid #3b82f6',
                  borderRadius: '4px'
                }}>
                  {suggestion}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {status.message && (
          <p className={`status ${status.type}`} style={{ marginTop: '1rem' }}>{status.message}</p>
        )}

        <button type="button" className="secondary-button" onClick={onBack} style={{ marginTop: '2rem' }}>
          Back to Evaluation Results
        </button>
      </div>
    </div>
  )
}

export default App
