export async function getAnalysis({ startDate, endDate, cutoffHour }) {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    cutoff_hour: String(cutoffHour),
  });
  const response = await fetch(`/api/analysis?${params.toString()}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || `Request failed (HTTP ${response.status})`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return payload;
}

export function getCsvUrl({ startDate, endDate, cutoffHour }) {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    cutoff_hour: String(cutoffHour),
  });
  return `/api/records.csv?${params.toString()}`;
}
