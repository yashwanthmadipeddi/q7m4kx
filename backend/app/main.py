from __future__ import annotations

import csv
import io
import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .analytics import analyze_records
from .elexon import ElexonApiError, fetch_january_pair

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(
    title="WindLens API",
    description="Historical GB wind forecast accuracy analysis using Elexon FUELHH and WINDFOR data.",
    version="1.0.0",
)


@app.get("/api/health", tags=["Operations"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "windlens-api", "data_source": "Elexon BMRS API"}


def _validate_range(start_date: date, end_date: date, cutoff_hour: int) -> None:
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    january_start, january_end = date(2026, 1, 1), date(2026, 1, 31)
    if start_date < january_start or end_date > january_end:
        raise HTTPException(status_code=422, detail="This assignment is scoped to delivery intervals in January 2026.")
    if (end_date - start_date).days > 30:
        raise HTTPException(status_code=422, detail="The selected range cannot exceed 31 days.")
    if not 0 <= cutoff_hour <= 23:
        raise HTTPException(status_code=422, detail="cutoff_hour must be between 0 and 23.")


def _build_analysis(start_date: date, end_date: date, cutoff_hour: int) -> dict[str, Any]:
    _validate_range(start_date, end_date, cutoff_hour)
    try:
        actuals, forecasts = fetch_january_pair(start_date, end_date)
        result = analyze_records(actuals, forecasts, start_date, end_date, cutoff_hour)
        # Keep upstream row counts in the payload so an empty analysis can be
        # distinguished from an API query that returned no source records.
        result["source_diagnostics"] = {
            "fuelhh_raw_records": len(actuals),
            "windfor_raw_records": len(forecasts),
        }
        return result
    except ElexonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/analysis", tags=["Analysis"])
def get_analysis(
    start_date: date = Query(default=date(2026, 1, 1), description="Inclusive UK delivery date"),
    end_date: date = Query(default=date(2026, 1, 31), description="Inclusive UK delivery date"),
    cutoff_hour: int = Query(default=int(os.getenv("DECISION_CUTOFF_HOUR", "11")), ge=0, le=23),
) -> dict[str, Any]:
    """Return matched time series, summary metrics, coverage and largest misses."""
    return _build_analysis(start_date, end_date, cutoff_hour)


@app.get("/api/records.csv", tags=["Analysis"])
def download_csv(
    start_date: date = Query(default=date(2026, 1, 1)),
    end_date: date = Query(default=date(2026, 1, 31)),
    cutoff_hour: int = Query(default=int(os.getenv("DECISION_CUTOFF_HOUR", "11")), ge=0, le=23),
) -> Response:
    result = _build_analysis(start_date, end_date, cutoff_hour)
    fieldnames = ["start_time", "date", "period", "actual_mw", "forecast_mw", "error_mw", "absolute_error_mw", "publish_time", "cutoff_time"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(result["records"])
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="windlens-january-2026.csv"'},
    )


if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    # In the production Docker image the compiled React app is served by FastAPI,
    # keeping the demo deployable as one container. API routes are registered first.
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_fallback(full_path: str) -> FileResponse:
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file() and STATIC_DIR in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
