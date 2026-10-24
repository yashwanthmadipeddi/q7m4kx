import React from 'react';

export default function DailyBars({ rows }) {
  const points = rows.filter((row) => row.mae_mw !== null && row.mae_mw !== undefined);
  if (!points.length) return <div className="chart-empty">Daily error metrics will appear when forecast and actual records match.</div>;
  const max = Math.max(...points.map((row) => Number(row.mae_mw) || 0), 1);
  return (
    <div className="daily-bars" role="img" aria-label="Daily mean absolute forecast error in megawatts">
      {points.map((row) => {
        const value = Number(row.mae_mw) || 0;
        const height = Math.max(3, value / max * 100);
        const label = new Date(`${row.date}T12:00:00Z`).toLocaleDateString('en-GB', { day: '2-digit', timeZone: 'UTC' });
        return (
          <div className="bar-column" key={row.date} title={`${row.date}: ${value.toLocaleString('en-GB')} MW MAE`}>
            <div className="bar-value">{value.toFixed(0)}</div>
            <div className="bar-track"><div className="bar-fill" style={{ height: `${height}%` }} /></div>
            <div className="bar-label">{label}</div>
          </div>
        );
      })}
    </div>
  );
}
