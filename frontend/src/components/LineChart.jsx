import React from 'react';

const fmt = (value) => new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }).format(value);

function makePath(rows, key, x, y) {
  let path = '';
  let drawing = false;
  rows.forEach((row, index) => {
    const value = row[key];
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      drawing = false;
      return;
    }
    path += `${drawing ? ' L' : ' M'} ${x(index).toFixed(2)} ${y(Number(value)).toFixed(2)}`;
    drawing = true;
  });
  return path;
}

export default function LineChart({ rows }) {
  const width = 960;
  const height = 284;
  const margin = { top: 18, right: 18, bottom: 35, left: 58 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const values = rows.flatMap((row) => [row.actual_mw, row.forecast_mw]).filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);
  if (!values.length) {
    return <div className="chart-empty">No matched data is available for this selection.</div>;
  }
  const min = Math.min(0, ...values);
  const max = Math.max(...values) * 1.08 || 1;
  const y = (value) => margin.top + (max - value) / (max - min || 1) * plotH;
  const x = (index) => margin.left + index / Math.max(rows.length - 1, 1) * plotW;
  const ticks = [0, 1, 2, 3, 4].map((n) => min + (max - min) * (n / 4));
  const labels = [0, Math.floor((rows.length - 1) / 3), Math.floor(2 * (rows.length - 1) / 3), rows.length - 1].filter((n, i, all) => all.indexOf(n) === i);

  return (
    <div className="line-chart-wrap">
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Actual and day-ahead forecast wind generation in megawatts over time">
        {ticks.map((tick, index) => (
          <g key={index}>
            <line x1={margin.left} x2={width - margin.right} y1={y(tick)} y2={y(tick)} className="chart-grid-line" />
            <text x={margin.left - 12} y={y(tick) + 4} textAnchor="end" className="chart-axis-label">{fmt(tick)}</text>
          </g>
        ))}
        <path d={makePath(rows, 'actual_mw', x, y)} className="chart-line chart-line-actual" />
        <path d={makePath(rows, 'forecast_mw', x, y)} className="chart-line chart-line-forecast" />
        {labels.map((index) => {
          const dateValue = rows[index]?.date;
          const label = dateValue ? new Date(`${dateValue}T12:00:00Z`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' }) : '';
          return <text key={index} x={x(index)} y={height - 9} textAnchor={index === 0 ? 'start' : index === rows.length - 1 ? 'end' : 'middle'} className="chart-axis-label">{label}</text>;
        })}
      </svg>
      <div className="chart-legend">
        <span><i className="legend-dot actual-dot" /> Actual generation</span>
        <span><i className="legend-dot forecast-dot" /> Selected day-ahead forecast</span>
      </div>
    </div>
  );
}
