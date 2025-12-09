import { Link } from 'react-router-dom'

export default function Navbar() {
  return (
    <nav className="navbar">
      <div className="brand">Timetable GA</div>
      <div className="links">
        <Link to="/">Home</Link>
        <Link to="/input">Input</Link>
        <Link to="/timetable">Timetable</Link>
      </div>
    </nav>
  )
}
