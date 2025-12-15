import { useEffect, useState } from 'react'

import { API_BASE_URL, PROVIDER_OPTIONS } from '../config'

function ManageRubricsTab({ savedRubrics, onRubricSaved, llmProvider }) {
  const [rubricFile, setRubricFile] = useState(null)
  const [status, setStatus] = useState({ type: 'idle', message: '' })
  const [editingRubric, setEditingRubric] = useState(null)
  const [parsingInfo, setParsingInfo] = useState(null)
  const [editingRubricId, setEditingRubricId] = useState(null)
  const [loadingRubricId, setLoadingRubricId] = useState(null)
  const [showModificationScreen, setShowModificationScreen] = useState(false)

  const providerMeta =
    PROVIDER_OPTIONS.find((option) => option.value === llmProvider) ?? PROVIDER_OPTIONS[0]

  const setError = (message) => setStatus({ type: 'error', message })
  const isParsingUpload =
    status.type === 'processing' && (status.message || '').toLowerCase().includes('parsing')

  const buildParsingInfoFromRubric = (rubricPayload) => {
    if (!rubricPayload) return null
    const criteria = rubricPayload.criteria ?? []
    return {
      items_extracted: criteria.length,
      rubric_title: rubricPayload.title || 'Untitled Rubric',
      rubric_type: rubricPayload.rubric_type || 'analytic',
      max_total_score: rubricPayload.max_total_score ?? 0,
      criteria_names: criteria.map((criterion) => criterion.name || 'Criterion'),
      criteria: criteria.map((criterion) => ({
        name: criterion.name || '',
        description: criterion.description || '',
        item_type: criterion.item_type || 'criterion',
        max_score: criterion.max_score ?? 0,
        weight: criterion.weight,
        metadata: criterion.metadata || {},
      })),
      generated_prompts: [],
    }
  }

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
    formData.append('llm_provider', llmProvider)

    setStatus({ type: 'processing', message: 'Parsing rubric…' })

    try {
      // Add timeout to prevent infinite waiting
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 120000) // 120 second timeout (allow for retries)

      const response = await fetch(`${API_BASE_URL}/api/rubrics/parse`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      })
      clearTimeout(timeoutId)

      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to parse rubric.')
      }

      if (!payload?.rubric || !payload?.parsing_info) {
        throw new Error('Parser returned an invalid payload.')
      }
      setEditingRubric(payload.rubric)
      setParsingInfo(payload.parsing_info)
      setEditingRubricId(null)
      setShowModificationScreen(true)
      setStatus({ type: 'success', message: 'Rubric parsed successfully!' })
    } catch (error) {
      if (error.name === 'AbortError') {
        setError('Parsing timed out after 60 seconds. The LLM may be rate-limited. Please wait a minute and try again.')
      } else {
        setError(error.message)
      }
    }
  }

  const handleSaveRubric = async (modifiedRubric) => {
    const isUpdate = Boolean(editingRubricId)
    setStatus({ type: 'processing', message: isUpdate ? 'Updating rubric…' : 'Saving rubric…' })

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/rubrics${isUpdate ? `/${editingRubricId}` : ''}`,
        {
          method: isUpdate ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(modifiedRubric),
        }
      )
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to save rubric.')
      }

      setStatus({
        type: 'success',
        message: isUpdate ? 'Rubric updated successfully!' : 'Rubric saved successfully!',
      })
      setShowModificationScreen(false)
      setEditingRubric(null)
      setParsingInfo(null)
      setEditingRubricId(null)
      setRubricFile(null)
      onRubricSaved()
    } catch (error) {
      setError(error.message)
    }
  }

  const handleEditRubric = async (rubricId) => {
    setLoadingRubricId(rubricId)
    setStatus({ type: 'processing', message: 'Loading rubric…' })

    try {
      const response = await fetch(`${API_BASE_URL}/api/rubrics/${rubricId}`)
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to load rubric.')
      }

      const normalizedRubric = {
        id: payload.id,
        title: payload.title,
        summary: payload.summary || '',
        rubric_type: payload.rubric_type,
        max_total_score: payload.max_total_score,
        criteria: (payload.items || []).map((item) => ({
          rubric_item_id: item.id,
          name: item.name,
          description: item.description || '',
          item_type: item.item_type || 'criterion',
          max_score: item.max_score,
          weight: item.weight,
          metadata: item.metadata || item.metadata_dict || {},
        })),
      }

      setEditingRubric(normalizedRubric)
      setParsingInfo(buildParsingInfoFromRubric(normalizedRubric))
      setEditingRubricId(rubricId)
      setShowModificationScreen(true)
      setStatus({ type: 'idle', message: '' })
    } catch (error) {
      setError(error.message)
    } finally {
      setLoadingRubricId(null)
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

  if (showModificationScreen && editingRubric) {
    return (
      <div className="full-width">
        <RubricModificationScreen
          initialRubric={editingRubric}
          parsingInfo={parsingInfo}
          onSave={handleSaveRubric}
          onCancel={() => {
            setShowModificationScreen(false)
            setEditingRubric(null)
            setParsingInfo(null)
            setEditingRubricId(null)
            setStatus({ type: 'idle', message: '' })
          }}
        />
      </div>
    )
  }

  return (
    <>
      <section className="card">
        <h2>Upload Rubric</h2>
        <p className="provider-note">
          Parsing powered by <strong>{providerMeta.label}</strong>
        </p>
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
            {isParsingUpload ? 'Parsing…' : 'Parse Rubric'}
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
                <div className="rubric-actions">
                  <button
                    className="ghost small"
                    type="button"
                    onClick={() => handleEditRubric(rubric.id)}
                    disabled={loadingRubricId === rubric.id}
                  >
                    {loadingRubricId === rubric.id ? 'Opening…' : 'View / Edit'}
                  </button>
                  <button
                    className="ghost small delete-btn"
                    onClick={() => handleDeleteRubric(rubric.id)}
                    type="button"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

function RubricModificationScreen({ parsingInfo, initialRubric, onSave, onCancel }) {
  const buildDraft = (rubricSource) => {
    const criteriaSource =
      rubricSource?.criteria ??
      parsingInfo?.criteria ??
      parsingInfo?.criteria_names?.map((name, index) => ({
        name,
        description:
          parsingInfo?.generated_prompts?.[index]?.prompt_text || '',
        item_type: 'criterion',
        max_score:
          (parsingInfo?.max_total_score || 0) /
            Math.max(parsingInfo?.items_extracted || 1, 1) || 1,
        metadata: {},
      })) ??
      []

    return {
      title: rubricSource?.title || parsingInfo?.rubric_title || 'Untitled Rubric',
      summary: rubricSource?.summary || '',
      rubric_type: rubricSource?.rubric_type || parsingInfo?.rubric_type || 'analytic',
      max_total_score:
        rubricSource?.max_total_score ??
        parsingInfo?.max_total_score ??
        0,
      criteria: criteriaSource.map((criterion, index) => ({
        name: criterion.name || `Criterion ${index + 1}`,
        description: criterion.description || '',
        item_type: criterion.item_type || 'criterion',
        max_score:
          criterion.max_score !== undefined && criterion.max_score !== null
            ? criterion.max_score
            : 1,
        weight:
          criterion.weight !== undefined ? criterion.weight : null,
        metadata: criterion.metadata || {},
      })),
    }
  }

  const [rubricData, setRubricData] = useState(() => buildDraft(initialRubric))
  const isEditingExisting = Boolean(initialRubric?.id)

  useEffect(() => {
    setRubricData(buildDraft(initialRubric))
  }, [initialRubric, parsingInfo])

  const handleCriterionChange = (index, field, value) => {
    const updated = [...rubricData.criteria]
    updated[index] = { ...updated[index], [field]: value }
    setRubricData({ ...rubricData, criteria: updated })
  }

  const handleAddCriterion = () => {
    setRubricData((current) => ({
      ...current,
      criteria: [
        ...current.criteria,
        {
          name: 'New Criterion',
          description: '',
          item_type: 'criterion',
          max_score: 1,
          weight: null,
          metadata: {},
        },
      ],
    }))
  }

  const handleDeleteCriterion = (index) => {
    const updated = rubricData.criteria.filter((_, i) => i !== index)
    setRubricData({ ...rubricData, criteria: updated })
  }

  return (
    <div className="modification-screen">
      <div className="modification-header">
        <h2>{isEditingExisting ? 'Edit Rubric' : 'Modify Rubric'}</h2>
        <div className="button-group">
          <button className="ghost" type="button" onClick={onCancel}>
            Cancel
          </button>
          <button className="primary" type="button" onClick={() => onSave(rubricData)}>
            {isEditingExisting ? 'Update Rubric' : 'Save Rubric'}
          </button>
        </div>
      </div>

      {parsingInfo && <RubricParsingPreview parsingInfo={parsingInfo} />}

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
          <label>Rubric Summary</label>
          <textarea
            rows={3}
            value={rubricData.summary}
            onChange={(e) =>
              setRubricData({ ...rubricData, summary: e.target.value })
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
                max_total_score:
                  e.target.value === '' ? 0 : parseFloat(e.target.value),
              })
            }
          />
        </div>
      </div>

      <div className="criteria-section">
        <div className="section-header">
          <h3>Criteria ({rubricData.criteria.length})</h3>
          <button className="ghost small" type="button" onClick={handleAddCriterion}>
            + Add Criterion
          </button>
        </div>

        {rubricData.criteria.map((criterion, index) => (
          <div key={`${criterion.name}-${index}`} className="criterion-editor">
            <div className="criterion-header">
              <h4>Criterion {index + 1}</h4>
              <button
                className="ghost small delete-btn"
                type="button"
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
                    e.target.value === '' ? null : parseFloat(e.target.value)
                  )
                }
              />
            </div>

            <div className="form-group">
              <label>Item Type</label>
              <select
                value={criterion.item_type}
                onChange={(e) =>
                  handleCriterionChange(index, 'item_type', e.target.value)
                }
              >
                <option value="criterion">Criterion</option>
                <option value="checklist">Checklist</option>
                <option value="single_point">Single-point</option>
                <option value="holistic">Holistic</option>
              </select>
            </div>

            <div className="form-group">
              <label>Weight (optional)</label>
              <input
                type="number"
                value={criterion.weight ?? ''}
                onChange={(e) =>
                  handleCriterionChange(
                    index,
                    'weight',
                    e.target.value === '' ? null : parseFloat(e.target.value)
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

function RubricParsingPreview({ parsingInfo }) {
  if (!parsingInfo) {
    return null
  }

  const isChecklist = parsingInfo.rubric_type === 'checklist'

  // Group criteria by main group (items with IDs like "1", "2") and subgroups (items like "1.1", "1.2")
  const groupCriteria = (criteria) => {
    const groups = []
    const criteriaWithPrompts = criteria.map((criterion, index) => ({
      ...criterion,
      prompt: parsingInfo.generated_prompts?.[index]?.prompt_text || '',
    }))

    criteriaWithPrompts.forEach((criterion) => {
      const id = criterion.metadata?.id || criterion.name
      const idStr = String(id)

      // Check if this is a main group (no dot in ID or ID is a single digit/letter)
      if (!idStr.includes('.') || idStr.match(/^[A-Z0-9]$/i)) {
        groups.push({
          main: criterion,
          subgroups: [],
        })
      } else {
        // This is a subgroup, find its parent
        const parentId = idStr.split('.')[0]
        const parentGroup = groups.find(
          (g) => String(g.main.metadata?.id || g.main.name).startsWith(parentId)
        )
        if (parentGroup) {
          parentGroup.subgroups.push(criterion)
        } else {
          // No parent found, treat as main group
          groups.push({
            main: criterion,
            subgroups: [],
          })
        }
      }
    })

    return groups
  }

  const renderChecklistTable = () => {
    const groups = groupCriteria(parsingInfo.criteria)

    return (
      <div className="checklist-table-container">
        <h3>Detected Criteria & Prompts</h3>
        <table className="checklist-table">
          <thead>
            <tr>
              <th style={{ width: '40%' }}>Criterion</th>
              <th style={{ width: '60%' }}>Generated Prompt</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group, groupIndex) => (
              <>
                {/* Main group row */}
                <tr key={`main-${groupIndex}`} className="main-group-row">
                  <td>
                    <strong>{group.main.name}</strong>
                    <div className="criterion-meta">
                      {group.main.max_score} pts
                    </div>
                  </td>
                  <td>
                    <pre className="prompt-preview">{group.main.prompt}</pre>
                  </td>
                </tr>
                {/* Subgroup rows */}
                {group.subgroups.map((subgroup, subIndex) => (
                  <tr
                    key={`sub-${groupIndex}-${subIndex}`}
                    className="subgroup-row"
                  >
                    <td className="subgroup-cell">
                      <span className="subgroup-indent">↳</span>
                      {subgroup.name}
                      <div className="criterion-meta">
                        {subgroup.max_score} pts
                      </div>
                    </td>
                    <td>
                      <pre className="prompt-preview">{subgroup.prompt}</pre>
                    </td>
                  </tr>
                ))}
              </>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="parsing-info">
      <h3>Extraction Summary</h3>
      <div className="parsing-summary">
        <div className="summary-item">
          <span className="label">Criteria</span>
          <span className="value">{parsingInfo.items_extracted}</span>
        </div>
        <div className="summary-item">
          <span className="label">Rubric Type</span>
          <span className="value">{parsingInfo.rubric_type}</span>
        </div>
        <div className="summary-item">
          <span className="label">Max Score</span>
          <span className="value">{parsingInfo.max_total_score}</span>
        </div>
      </div>

      {isChecklist && parsingInfo.criteria?.length > 0 ? (
        renderChecklistTable()
      ) : (
        <>
          {parsingInfo.criteria?.length > 0 && (
            <div className="criteria-list">
              <h3>Detected Criteria</h3>
              <ul>
                {parsingInfo.criteria.map((criterion, index) => (
                  <li key={`${criterion.name}-${index}`}>
                    <strong>{criterion.name}</strong> — {criterion.max_score} pts
                  </li>
                ))}
              </ul>
            </div>
          )}

          {parsingInfo.generated_prompts?.length > 0 && (
            <div className="prompts-section">
              <h3>LLM Prompt Samples</h3>
              <p className="section-description">
                These prompts show how the scorer will frame each criterion. The
                transcript placeholder is substituted at runtime.
              </p>
              {parsingInfo.generated_prompts.slice(0, 3).map((prompt, index) => (
                <div
                  key={`${prompt.criterion_name}-${index}`}
                  className="prompt-item"
                >
                  <button type="button" className="prompt-header">
                    <span className="prompt-criterion">{prompt.criterion_name}</span>
                    <span className="expand-icon">Preview</span>
                  </button>
                  <pre className="prompt-text">{prompt.prompt_text}</pre>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default ManageRubricsTab
