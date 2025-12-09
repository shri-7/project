import { useState } from 'react'

export default function InputList({ label, values, onChange, placeholder }) {
  const [input, setInput] = useState('')

  const add = () => {
    const v = input.trim()
    if (!v) return
    onChange([...values, v])
    setInput('')
  }

  const remove = (idx) => {
    const next = values.filter((_, i) => i !== idx)
    onChange(next)
  }

  return (
    <div className="input-list">
      <label>{label}</label>
      <div className="row">
        <input value={input} onChange={e => setInput(e.target.value)} placeholder={placeholder} />
        <button type="button" onClick={add}>Add</button>
      </div>
      <ul>
        {values.map((v, i) => (
          <li key={i}>
            <span>{v}</span>
            <button type="button" onClick={() => remove(i)}>Remove</button>
          </li>
        ))}
      </ul>
    </div>
  )
}
