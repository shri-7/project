const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function validateInput(payload) {
  const res = await fetch(`${BASE_URL}/api/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to validate');
  return res.json();
}

export async function startGeneration(payload) {
  const res = await fetch(`${BASE_URL}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to start generation');
  return res.json();
}

export async function getGenerationStatus(jobId) {
  const res = await fetch(`${BASE_URL}/api/generate/status/${jobId}`);
  if (!res.ok) throw new Error('Failed to get status');
  return res.json();
}

export async function getGenerationResult(jobId) {
  const res = await fetch(`${BASE_URL}/api/generate/result/${jobId}`);
  if (!res.ok) throw new Error('Failed to get result');
  return res.json();
}

export async function downloadTimetablePdf(jobId) {
  const res = await fetch(`${BASE_URL}/api/timetable/${jobId}/download?format=pdf`);
  if (!res.ok) throw new Error('Failed to download PDF');
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `timetable_${jobId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
