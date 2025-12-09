import { useNavigate } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()
  return (
    <div className="page">
      <h1>Timetable Generator</h1>
      <p>Enter your parameters on the Input page, validate, then generate a timetable using the Genetic Algorithm.</p>
      <div className="buttons">
        <button onClick={() => navigate('/input')}>Start</button>
      </div>
    </div>
  )
}
