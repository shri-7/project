import { useLocation } from 'react-router-dom'
import TableRenderer from '../components/TableRenderer'

export default function Timetable() {
  const location = useLocation()
  const result = location.state?.result || null

  return (
    <div className="page">
      <h2>Generated Timetable</h2>
      {!result && <p>Generate a timetable first from the Input page.</p>}
      {result && result.status === 'completed' && result.timetable && result.timetable.sections && (
        <div>
          {Object.entries(result.timetable.sections).map(([sectionId, data]) => (
            <div key={sectionId} className="section-timetable">
              <h3>Section: {sectionId}</h3>
              <TableRenderer
                days={data.matrix.length}
                slots={data.matrix[0]?.length || 0}
                data={data.matrix}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
