import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { startGeneration, getGenerationStatus, getGenerationResult } from '../api'
import Loader from '../components/Loader'

export default function GenerationStatus() {
  const location = useLocation()
  const navigate = useNavigate()
  const payload = location.state?.payload

  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (!payload) return
    let cancelled = false

    async function start() {
      try {
        const resp = await startGeneration(payload)
        if (resp.status === 'failed') {
          setError(resp.reason)
          return
        }
        setJobId(resp.job_id)
        setStatus({ status: 'running', progress: 0, best_fitness: null })
      } catch (e) {
        setError(e.message || 'Failed to start generation')
      }
    }

    start()

    return () => {
      cancelled = true
    }
  }, [payload])

  useEffect(() => {
    if (!jobId) return
    let timerId
    let finished = false

    async function poll() {
      try {
        const st = await getGenerationStatus(jobId)
        setStatus(st)
        if (st.status === 'completed') {
          const res = await getGenerationResult(jobId)
          setResult(res)
          finished = true
        }
      } catch (e) {
        setError(e.message || 'Failed to get status')
        finished = true
      }

      if (!finished) {
        timerId = setTimeout(poll, 1000)
      }
    }

    poll()

    return () => {
      if (timerId) clearTimeout(timerId)
    }
  }, [jobId])

  const onViewTimetable = () => {
    if (result && result.status === 'completed') {
      navigate('/timetable', { state: { result, jobId } })
    }
  }

  const onViewMetrics = () => {
    if (result && result.status === 'completed') {
      navigate('/metrics', { state: { result, jobId } })
    }
  }

  if (!payload) {
    return <div className="page"><p>No input found. Go back to Input page.</p></div>
  }

  return (
    <div className="page">
      <h2>Generation Status</h2>
      {error && <div className="error">{error}</div>}
      {!error && !result && <p>Starting genetic algorithm job...</p>}
      {status && (
        <div className="mt">
          <div>Status: {status.status}</div>
          {status.progress != null && (
            <div>Progress: {(status.progress * 100).toFixed(1)}%</div>
          )}
          {status.best_fitness != null && (
            <div>Best Fitness: {status.best_fitness.toFixed(2)}</div>
          )}
        </div>
      )}
      {!result && <Loader />}
      {result && result.status === 'completed' && (
        <div className="buttons mt">
          <button onClick={onViewTimetable}>View Timetable</button>
          <button onClick={onViewMetrics}>View Metrics</button>
        </div>
      )}
    </div>
  )
}
