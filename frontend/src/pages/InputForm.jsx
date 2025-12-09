import { useState } from 'react'
import { validateInput } from '../api'
import Loader from '../components/Loader'
import InputList from '../components/InputList'
import { useNavigate } from 'react-router-dom'

export default function InputForm() {
  const [daysPerWeek, setDaysPerWeek] = useState(5)
  const [periodsPerDay, setPeriodsPerDay] = useState(7)
  const [lunchEnabled, setLunchEnabled] = useState(true)
  const [lunchPeriod, setLunchPeriod] = useState(4)

  const [sections, setSections] = useState(['A'])
  const [subjects, setSubjects] = useState([
    { id: 'MATH', section_id: 'A', type: 'theory', hours_per_week: 5 },
  ])
  const [faculty, setFaculty] = useState([
    { id: 'F1', specializations: ['MATH'] },
  ])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [validationResult, setValidationResult] = useState(null)
  const navigate = useNavigate()

  const onAddSubject = () => {
    setSubjects(prev => [...prev, { id: '', section_id: sections[0] || 'A', type: 'theory', hours_per_week: 1 }])
  }

  const onChangeSubject = (idx, patch) => {
    setSubjects(prev => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)))
  }

  const onAddFaculty = () => {
    setFaculty(prev => [...prev, { id: '', specializations: [] }])
  }

  const onChangeFaculty = (idx, patch) => {
    setFaculty(prev => prev.map((f, i) => (i === idx ? { ...f, ...patch } : f)))
  }

  const buildPayload = () => {
    return {
      days_per_week: Number(daysPerWeek),
      periods_per_day: Number(periodsPerDay),
      lunch_break: {
        enabled: Boolean(lunchEnabled),
        day: 'all',
        period: Number(lunchPeriod),
      },
      sections: sections.map(id => ({ id })),
      subjects: subjects.map(s => ({
        id: s.id,
        section_id: s.section_id,
        type: s.type,
        hours_per_week: Number(s.hours_per_week),
      })),
      faculty: faculty.map(f => ({
        id: f.id,
        specializations: Array.isArray(f.specializations)
          ? f.specializations
          : String(f.specializations || '')
              .split(',')
              .map(x => x.trim())
              .filter(Boolean),
      })),
      constraints: {
        one_faculty_per_section_subject: true,
        faculty_cannot_teach_two_sections_at_same_time: true,
        lab_block_length: 2,
      },
      generation_settings: {
        population_size: 200,
        max_generations: 500,
        time_limit_seconds: 30,
      },
    }
  }

  const onValidate = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setValidationResult(null)
    const payload = buildPayload()
    try {
      const res = await validateInput(payload)
      setValidationResult(res)
      if (res.status === 'ok') {
        navigate('/status', { state: { payload } })
      }
    } catch (err) {
      setError(err.message || 'Failed to validate')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <h2>Input Parameters</h2>
      <form onSubmit={onValidate} className="form">
        <div className="grid">
          <label>Days per Week
            <input type="number" min="1" value={daysPerWeek} onChange={e => setDaysPerWeek(e.target.value)} />
          </label>
          <label>Periods per Day
            <input type="number" min="1" value={periodsPerDay} onChange={e => setPeriodsPerDay(e.target.value)} />
          </label>
        </div>
        <div className="input-list">
          <label>
            Lunch Break
            <div className="grid">
              <label>
                <input
                  type="checkbox"
                  checked={lunchEnabled}
                  onChange={e => setLunchEnabled(e.target.checked)}
                /> Enable
              </label>
              <label>
                Period Index
                <input
                  type="number"
                  min="0"
                  value={lunchPeriod}
                  onChange={e => setLunchPeriod(e.target.value)}
                />
              </label>
            </div>
          </label>
        </div>

        <InputList label="Sections" values={sections} onChange={setSections} placeholder="Add section" />

        <div className="input-list">
          <label>Subjects</label>
          {subjects.map((s, idx) => (
            <div key={idx} className="grid">
              <input
                placeholder="ID (e.g. MATH)"
                value={s.id}
                onChange={e => onChangeSubject(idx, { id: e.target.value })}
              />
              <input
                placeholder="Section ID"
                value={s.section_id}
                onChange={e => onChangeSubject(idx, { section_id: e.target.value })}
              />
              <select
                value={s.type}
                onChange={e => onChangeSubject(idx, { type: e.target.value })}
              >
                <option value="theory">theory</option>
                <option value="lab">lab</option>
              </select>
              <input
                type="number"
                min="1"
                value={s.hours_per_week}
                onChange={e => onChangeSubject(idx, { hours_per_week: Number(e.target.value) })}
              />
            </div>
          ))}
          <div className="buttons mt">
            <button type="button" onClick={onAddSubject}>Add Subject</button>
          </div>
        </div>

        <div className="input-list">
          <label>Faculty</label>
          {faculty.map((f, idx) => (
            <div key={idx} className="grid">
              <input
                placeholder="Faculty ID (e.g. F1)"
                value={f.id}
                onChange={e => onChangeFaculty(idx, { id: e.target.value })}
              />
              <input
                placeholder="Specializations (comma-separated subject IDs)"
                value={Array.isArray(f.specializations) ? f.specializations.join(',') : f.specializations}
                onChange={e => onChangeFaculty(idx, { specializations: e.target.value })}
              />
            </div>
          ))}
          <div className="buttons mt">
            <button type="button" onClick={onAddFaculty}>Add Faculty</button>
          </div>
        </div>

        {error && <div className="error">{error}</div>}
        {validationResult && validationResult.status === 'failed' && (
          <div className="error">
            {validationResult.reason}
          </div>
        )}
        <div className="buttons">
          <button type="submit" disabled={loading}>Validate &amp; Generate</button>
        </div>
      </form>
      {loading && <Loader />}
    </div>
  )
}
