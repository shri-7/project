import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import InputForm from './pages/InputForm'
import Timetable from './pages/Timetable'
import GenerationStatus from './pages/GenerationStatus'
import Navbar from './components/Navbar'

export default function App() {
  return (
    <div>
      <Navbar />
      <div className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/input" element={<InputForm />} />
          <Route path="/status" element={<GenerationStatus />} />
          <Route path="/timetable" element={<Timetable />} />
        </Routes>
      </div>
    </div>
  )
}
