import React, { useEffect, useMemo, useState } from 'react';
import LineChart from './components/LineChart.jsx';
import DailyBars from './components/DailyBars.jsx';
import { getAnalysis, getCsvUrl } from './services/api.js';

const initialFilters = { startDate: '2026-01-01', endDate: '2026-01-31', cutoffHour: 11 };
const fmtNumber = (value, digits = 0) => value === null || value === undefined || !Number.isFinite(Number(value))
  ? '—'
  : new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value));
const fmtDateTime = (value) => value ? new Date(value).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' }) : 'Not available';

function Icon({ type }) {
  const paths = {
    wind: <><path d="M3 8h13a3 3 0 1 0-3-3"/><path d="M2 12h18a2.5 2.5 0 1 1-2.5 2.5"/><path d="M4 16h6a2 2 0 1 1-2 2"/></>,
    chart: <><path d="M4 19V5M4 19h17"/><path d="m7 15 4-4 3 2 5-7"/></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    download: <><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 20h16"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7h.01"/></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10"/></>,
  };
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[type] || paths.info}</svg>;
}

function MetricCard({ label, value, unit, note, accent = '' }) {
  return (
    <article className={`metric-card ${accent}`}>
      <div className="metric-card-head"><span>{label}</span><span className="metric-indicator" /></div>
      <div className="metric-value">{value}<small>{unit}</small></div>
      <div className="metric-note">{note}</div>
    </article>
  );
}

function EmptyState({ title, description }) {
  return <div className="empty-state"><div className="empty-icon"><Icon type="wind" /></div><h3>{title}</h3><p>{description}</p></div>;
}

export default function App() {
  const [filters, setFilters] = useState(initialFilters);
  const [draft, setDraft] = useState(initialFilters);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const [queryToken, setQueryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError('');
      setData(null);
      try {
        const result = await getAnalysis(filters);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [filters, queryToken]);

  const rows = useMemo(() => data?.records || [], [data]);
  const plottedRows = useMemo(() => {
    // Preserve chronological order while limiting SVG detail for very dense ranges.
    const step = Math.max(1, Math.ceil(rows.length / 720));
    const sampled = rows.filter((_, index) => index % step === 0 || index === rows.length - 1);
    return sampled;
  }, [rows]);

  function applyFilters(event) {
    event.preventDefault();
    if (draft.startDate > draft.endDate) {
      setError('The start date must be on or before the end date.');
      return;
    }
    setFilters({ ...draft, cutoffHour: Number(draft.cutoffHour) });
  }

  const metrics = data?.metrics;
  const coverage = data?.coverage;
  const hasMatches = (metrics?.matched_intervals || 0) > 0;
  const sourceDiagnostics = data?.source_diagnostics;
  const emptyDescription = sourceDiagnostics
    ? `Elexon returned ${fmtNumber(sourceDiagnostics.fuelhh_raw_records)} FUELHH rows and ${fmtNumber(sourceDiagnostics.windfor_raw_records)} WINDFOR rows. ${sourceDiagnostics.fuelhh_raw_records === 0 || sourceDiagnostics.windfor_raw_records === 0 ? 'At least one source query returned no rows; check the dataset query filters and source availability.' : 'Source rows were returned, but no actual/forecast pairs survived the target-time match and day-ahead cutoff. Check the publication-time window and cutoff assumption.'} No sample values are substituted.`
    : 'The Elexon API returned no forecast/actual pairs for this selection and cutoff. Retry the request or check the data source. No sample values are substituted.';
  const csvUrl = getCsvUrl(filters);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark"><Icon type="wind" /></div><div><div className="brand-name">windlens<span>.</span></div><div className="brand-subtitle">FORECAST INTELLIGENCE</div></div></div>
        <div className="nav-group-label">WORKSPACE</div>
        <button className={`nav-item ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => setActiveTab('overview')}><Icon type="grid" /> Overview</button>
        <button className={`nav-item ${activeTab === 'detail' ? 'active' : ''}`} onClick={() => setActiveTab('detail')}><Icon type="chart" /> Forecast detail</button>
        <button className={`nav-item ${activeTab === 'methodology' ? 'active' : ''}`} onClick={() => setActiveTab('methodology')}><Icon type="info" /> Methodology</button>
        <div className="sidebar-bottom">
          <div className="source-state"><span className="source-dot" /><div><strong>Elexon BMRS</strong><small>Live source · API-backed</small></div></div>
          <div className="sidebar-footnote">Pilot analytics for GB wind generation<br/>Historical delivery period: Jan 2026</div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb"><span>Analytics</span><span className="breadcrumb-sep">/</span><strong>{activeTab === 'overview' ? 'Overview' : activeTab === 'detail' ? 'Forecast detail' : 'Methodology'}</strong></div>
          <div className="topbar-right"><span className="live-chip"><i /> ELEXON DATA</span><div className="avatar">WL</div></div>
        </header>

        <section className="page-heading">
          <div><div className="eyebrow">UK POWER MARKETS <span>•</span> DAY-AHEAD</div><h1>Wind forecast intelligence</h1><p>Understand forecast performance before the day-ahead procurement decision.</p></div>
          <a className="export-button" href={csvUrl}><Icon type="download" /> Export CSV</a>
        </section>

        <section className="filter-panel">
          <div className="filter-intro"><div className="filter-icon"><Icon type="calendar" /></div><div><strong>Analysis window</strong><small>Delivery dates · January 2026</small></div></div>
          <form className="filter-form" onSubmit={applyFilters}>
            <label><span>FROM</span><input aria-label="Start date" type="date" min="2026-01-01" max="2026-01-31" value={draft.startDate} onChange={(e) => setDraft({ ...draft, startDate: e.target.value })} required /></label>
            <label><span>TO</span><input aria-label="End date" type="date" min={draft.startDate || '2026-01-01'} max="2026-01-31" value={draft.endDate} onChange={(e) => setDraft({ ...draft, endDate: e.target.value })} required /></label>
            <label className="cutoff-label"><span>DAY-AHEAD CUTOFF</span><select aria-label="Decision cutoff hour" value={draft.cutoffHour} onChange={(e) => setDraft({ ...draft, cutoffHour: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, hour) => <option value={hour} key={hour}>{String(hour).padStart(2, '0')}:00 UK time</option>)}</select></label>
            <button className="apply-button" type="submit" disabled={loading}><Icon type="arrow" /> {loading ? 'Loading…' : 'Apply filters'}</button>
          </form>
        </section>

        {error && <div className="error-banner" role="alert"><div className="error-title"><Icon type="info" /> Data could not be loaded</div><p>{error}</p><div className="error-actions"><button onClick={() => setQueryToken((n) => n + 1)}>Retry request</button><a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream" target="_blank" rel="noreferrer">Check Elexon API status ↗</a></div></div>}

        {loading && !data ? (
          <div className="loading-area"><div className="loading-spin" /><h3>Loading Elexon generation data</h3><p>Retrieving actuals and forecast publication history for the selected delivery dates.</p></div>
        ) : data ? (
          <>
            {activeTab === 'overview' && <>
              <section className="summary-strip"><div><span className="summary-label">SELECTED PERIOD</span><strong>{new Date(`${filters.startDate}T12:00:00Z`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' })} — {new Date(`${filters.endDate}T12:00:00Z`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })}</strong></div><div className="summary-vline"/><div><span className="summary-label">FORECAST VINTAGE</span><strong>As available by previous-day cutoff</strong></div><div className="summary-vline"/><div className="summary-right"><span className="summary-label">MATCHED INTERVALS</span><strong>{fmtNumber(metrics?.matched_intervals)} <small>of {fmtNumber(metrics?.candidate_actual_or_forecast_intervals)} expected</small></strong></div></section>

              {!hasMatches && !loading ? <EmptyState title="No matched intervals found" description={emptyDescription} /> : <>
                <section className="metrics-grid">
                  <MetricCard label="Mean absolute error" value={fmtNumber(metrics?.mae_mw, 1)} unit="MW" note="Average absolute miss per matched interval" accent="blue-accent" />
                  <MetricCard label="Root mean squared error" value={fmtNumber(metrics?.rmse_mw, 1)} unit="MW" note="Penalises larger forecast misses" accent="purple-accent" />
                  <MetricCard label="Forecast bias" value={metrics?.bias_mw === null || metrics?.bias_mw === undefined ? '—' : `${Number(metrics.bias_mw) > 0 ? '+' : ''}${fmtNumber(metrics.bias_mw, 1)}`} unit="MW" note={Number(metrics?.bias_mw) > 0 ? 'Net overforecasting' : Number(metrics?.bias_mw) < 0 ? 'Net underforecasting' : 'Forecast minus actual generation'} accent="green-accent" />
                  <MetricCard label="Weighted absolute error" value={fmtNumber(metrics?.wape_percent, 1)} unit="%" note="Absolute error ÷ total actual generation" accent="amber-accent" />
                </section>

                <section className="content-grid overview-charts">
                  <article className="panel trend-panel"><div className="panel-heading"><div><div className="panel-kicker">GENERATION PROFILE</div><h2>Actual vs. selected forecast</h2><p>National wind output · half-hourly target periods</p></div><span className="panel-tag">MW</span></div><LineChart rows={plottedRows} /></article>
                  <article className="panel coverage-panel"><div className="panel-heading"><div><div className="panel-kicker">DATA QUALITY</div><h2>Interval coverage</h2><p>Records available after vintage selection</p></div></div><div className="coverage-ring-wrap"><div className="coverage-ring" style={{ '--coverage': `${coverage?.matched_intervals && coverage?.expected_intervals ? Math.round(coverage.matched_intervals / coverage.expected_intervals * 100) : 0}%` }}><div><strong>{coverage?.expected_intervals ? Math.round(coverage.matched_intervals / coverage.expected_intervals * 100) : 0}%</strong><span>matched</span></div></div></div><div className="coverage-rows"><div><span><i className="coverage-dot actual-dot"/>Actual intervals</span><strong>{fmtNumber(coverage?.actual_intervals)}</strong></div><div><span><i className="coverage-dot forecast-dot"/>Forecast selected</span><strong>{fmtNumber(coverage?.forecast_intervals_selected)}</strong></div><div><span><i className="coverage-dot match-dot"/>Matched pairs</span><strong>{fmtNumber(coverage?.matched_intervals)} / {fmtNumber(coverage?.expected_intervals)}</strong></div></div><div className="coverage-footnote">Intervals without an eligible forecast are excluded from error metrics.</div></article>
                </section>

                <section className="content-grid lower-charts"><article className="panel daily-panel"><div className="panel-heading"><div><div className="panel-kicker">ERROR DISTRIBUTION</div><h2>Daily forecast error</h2><p>Mean absolute error for each delivery date</p></div><span className="panel-tag">MAE · MW</span></div><DailyBars rows={data.daily || []}/></article><article className="insight-card"><div className="insight-icon"><Icon type="info"/></div><div className="panel-kicker">HOW TO READ THIS</div><h2>Turn forecast misses into better decisions.</h2><p>Positive bias means the forecast expected more wind than actually generated. Negative bias means it expected less. Compare the forecast error with your demand and procurement process before making any purchasing decision.</p><button className="text-action" onClick={() => setActiveTab('methodology')}>View methodology <span>→</span></button></article></section>

                <section className="panel table-panel"><div className="panel-heading table-heading"><div><div className="panel-kicker">LARGEST FORECAST MISSES</div><h2>Intervals that need attention</h2><p>Ranked by absolute difference between forecast and actual output</p></div><button className="quiet-button" onClick={() => setActiveTab('detail')}>View all records <span>→</span></button></div><div className="table-scroll"><table><thead><tr><th>DELIVERY INTERVAL</th><th>ACTUAL</th><th>FORECAST</th><th>ERROR</th><th>FORECAST PUBLISHED</th></tr></thead><tbody>{(data.largest_errors || []).slice(0, 5).map((row) => <tr key={row.start_time}><td><strong>{fmtDateTime(row.start_time)}</strong><small>{row.period} UK time</small></td><td>{fmtNumber(row.actual_mw)} <small>MW</small></td><td>{fmtNumber(row.forecast_mw)} <small>MW</small></td><td><span className={`error-pill ${Number(row.error_mw) > 0 ? 'positive-error' : 'negative-error'}`}>{Number(row.error_mw) > 0 ? '+' : ''}{fmtNumber(row.error_mw)} MW</span></td><td>{fmtDateTime(row.publish_time)}</td></tr>)}</tbody></table></div>{(!data.largest_errors || !data.largest_errors.length) && <div className="table-empty">No forecast errors are available for the selected filter.</div>}</section>
              </>}
            </>}

            {activeTab === 'detail' && <section className="panel detail-page"><div className="panel-heading"><div><div className="panel-kicker">RECORD EXPLORER</div><h2>Forecast vs actual intervals</h2><p>Every row uses the latest forecast published no later than the previous-day cutoff.</p></div><span className="panel-tag">{fmtNumber(rows.length)} records</span></div><div className="table-scroll"><table><thead><tr><th>DELIVERY INTERVAL</th><th>ACTUAL MW</th><th>FORECAST MW</th><th>ERROR MW</th><th>ABS ERROR MW</th><th>PUBLISH TIME</th></tr></thead><tbody>{rows.map((row) => <tr key={row.start_time}><td><strong>{fmtDateTime(row.start_time)}</strong></td><td>{fmtNumber(row.actual_mw, 1)}</td><td>{fmtNumber(row.forecast_mw, 1)}</td><td>{row.error_mw === null ? '—' : <span className={Number(row.error_mw) > 0 ? 'text-positive' : 'text-negative'}>{Number(row.error_mw) > 0 ? '+' : ''}{fmtNumber(row.error_mw, 1)}</span>}</td><td>{fmtNumber(row.absolute_error_mw, 1)}</td><td>{fmtDateTime(row.publish_time)}</td></tr>)}</tbody></table></div></section>}

            {activeTab === 'methodology' && <section className="methodology-grid"><article className="panel method-main"><div className="panel-kicker">ANALYTICAL APPROACH</div><h2>Designed around the decision that mattered.</h2><p className="method-lead">For each 30-minute delivery interval, WindLens selects only the forecast that was available at the configured day-ahead cutoff. Later forecasts are excluded to avoid hindsight bias.</p><div className="method-step"><span>01</span><div><h3>Collect the required datasets</h3><p><strong>FUELHH</strong> supplies actual half-hourly generation filtered to <code>fuelType = WIND</code>. <strong>WINDFOR</strong> supplies target time, publication time and forecast generation.</p></div></div><div className="method-step"><span>02</span><div><h3>Match on delivery interval</h3><p>Actuals and selected forecast values are matched using the start time of the target 30-minute interval. Unmatched intervals remain visible in coverage figures and do not silently enter accuracy calculations.</p></div></div><div className="method-step"><span>03</span><div><h3>Choose the correct forecast vintage</h3><p>For each target delivery date, select the greatest <code>publishTime</code> not later than the configured cutoff on the previous day, in Europe/London time. The default cutoff is 11:00 UK time and is an explicit assumption because the assignment does not specify a clock time.</p></div></div><div className="method-step"><span>04</span><div><h3>Calculate error transparently</h3><p>MAE is mean absolute error; RMSE penalises larger errors; bias is forecast minus actual; WAPE divides aggregate absolute error by total actual generation. WAPE is omitted when its denominator is zero.</p></div></div></article><aside className="method-aside"><div className="panel assumption-panel"><div className="panel-kicker">IMPORTANT ASSUMPTION</div><h3>Cutoff can be changed</h3><p>The assignment says forecasts must be evaluated as available at purchase time but does not define an exact decision cutoff. This application defaults to 11:00 Europe/London the day before delivery. Change it from the Analysis window control and rerun the analysis.</p></div><div className="panel scope-panel"><div className="panel-kicker">SCOPE & LIMITATIONS</div><h3>What this pilot does — and doesn't — claim</h3><ul><li>Uses only Elexon FUELHH actual wind generation and WINDFOR forecast records.</li><li>Supports January 2026 delivery intervals only.</li><li>Does not calculate power to procure, demand gaps, wholesale cost or savings because demand and price data are outside the assignment scope.</li><li>Results depend on source API completeness and publication history available from Elexon.</li></ul></div></aside></section>}
          </>
        ) : null}

        <footer className="page-footer"><span>WindLens <b>•</b> Pilot analytics for UK wind generation</span><span>Data source: Elexon BMRS API <b>•</b> Forecast vintage aware</span></footer>
      </main>
    </div>
  );
}
