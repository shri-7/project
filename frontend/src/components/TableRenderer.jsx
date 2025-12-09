export default function TableRenderer({ days, slots, data }) {
  const dayLabels = Array.from({ length: days }, (_, i) => `Day ${i + 1}`)
  const slotLabels = Array.from({ length: slots }, (_, i) => `S${i + 1}`)

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Day / Slot</th>
            {slotLabels.map((s, i) => <th key={i}>{s}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map((row, d) => (
            <tr key={d}>
              <td className="row-header">{dayLabels[d]}</td>
              {row.map((cell, s) => {
                let text = '';
                if (cell == null) {
                  text = '';
                } else if (typeof cell === 'string') {
                  text = cell;
                } else if (typeof cell === 'object') {
                  const subj = cell.subject || '';
                  const fac = cell.faculty || '';
                  const typ = cell.type || '';
                  text = `${subj}${fac ? ` (${fac})` : ''}${typ ? ` [${typ}]` : ''}`;
                }
                return <td key={s}>{text}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
