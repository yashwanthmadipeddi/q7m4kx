"""Forecast-vintage selection and forecast error calculations.

Only Elexon FUELHH actual wind generation and WINDFOR forecasts are used.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
from typing import Any, Iterable
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc


def parse_datetime(value: Any, *, naive_timezone=UTC) -> datetime | None:
    """Parse ISO-style timestamps to aware datetimes, tolerate trailing Z.

    Elexon timestamps generally include an offset. Naive timestamps are treated
    as UTC by default to avoid host-local timezone differences.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=naive_timezone)
    return parsed.astimezone(UTC)


def as_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _field(record: dict[str, Any], *names: str) -> Any:
    """Read fields in a forgiving way when upstream casing varies."""
    for name in names:
        if name in record:
            return record[name]
    lowered = {str(k).lower(): v for k, v in record.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def normalize_actuals(records: Iterable[dict[str, Any]]) -> dict[datetime, float]:
    """Return a timestamp -> generation map for national WIND actuals."""
    actuals: dict[datetime, float] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        fuel_type = _field(item, "fuelType", "fuel_type")
        if fuel_type and str(fuel_type).upper() != "WIND":
            continue
        timestamp = parse_datetime(_field(item, "startTime", "start_time"))
        generation = as_number(_field(item, "generation"))
        if timestamp is not None and generation is not None:
            # If a duplicate interval exists, keep the last source record.
            actuals[timestamp] = generation
    return actuals


def normalize_forecasts(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize forecast target time, publication time, and MW value."""
    output: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        target = parse_datetime(_field(item, "startTime", "start_time"))
        published = parse_datetime(_field(item, "publishTime", "publish_time"))
        generation = as_number(_field(item, "generation"))
        if target is None or published is None or generation is None:
            continue
        output.append({"start_time": target, "publish_time": published, "generation": generation})
    return output


def decision_cutoff_for_target(target_utc: datetime, cutoff_hour: int = 11) -> datetime:
    """Return the local day-before cutoff as a UTC instant."""
    target_local = target_utc.astimezone(LONDON)
    cutoff_local = datetime.combine(
        target_local.date() - timedelta(days=1), time(hour=cutoff_hour), tzinfo=LONDON
    )
    return cutoff_local.astimezone(UTC)


def select_forecast_vintages(
    forecasts: Iterable[dict[str, Any]], cutoff_hour: int = 11
) -> dict[datetime, dict[str, Any]]:
    """Choose the most recently published forecast available by day-ahead cutoff.

    Each target half-hour is assessed independently. Any forecasts published
    after that target's configured decision cutoff are excluded.
    """
    selected: dict[datetime, dict[str, Any]] = {}
    for item in forecasts:
        target = item.get("start_time")
        published = item.get("publish_time")
        generation = as_number(item.get("generation"))
        if not isinstance(target, datetime) or not isinstance(published, datetime) or generation is None:
            continue
        cutoff = decision_cutoff_for_target(target, cutoff_hour)
        if published > cutoff:
            continue
        existing = selected.get(target)
        if existing is None or published > existing["publish_time"]:
            selected[target] = {
                "generation": generation,
                "publish_time": published,
                "cutoff_time": cutoff,
            }
    return selected


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def calculate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate MAE, RMSE, bias, and WAPE for matched records."""
    valid = [r for r in records if r.get("actual_mw") is not None and r.get("forecast_mw") is not None]
    if not valid:
        return {
            "matched_intervals": 0,
            "mae_mw": None,
            "rmse_mw": None,
            "bias_mw": None,
            "wape_percent": None,
            "actual_total_mw": 0.0,
            "forecast_total_mw": 0.0,
        }
    errors = [float(r["forecast_mw"]) - float(r["actual_mw"]) for r in valid]
    absolute = [abs(x) for x in errors]
    actual_total = sum(float(r["actual_mw"]) for r in valid)
    forecast_total = sum(float(r["forecast_mw"]) for r in valid)
    wape = (sum(absolute) / abs(actual_total) * 100.0) if actual_total != 0 else None
    return {
        "matched_intervals": len(valid),
        "mae_mw": _round(sum(absolute) / len(absolute)),
        "rmse_mw": _round(sqrt(sum(x * x for x in errors) / len(errors))),
        "bias_mw": _round(sum(errors) / len(errors)),
        "wape_percent": _round(wape),
        "actual_total_mw": _round(actual_total),
        "forecast_total_mw": _round(forecast_total),
    }


def analyze_records(
    actual_raw: Iterable[dict[str, Any]],
    forecast_raw: Iterable[dict[str, Any]],
    start_date: date,
    end_date: date,
    cutoff_hour: int = 11,
) -> dict[str, Any]:
    """Match actuals against the selected day-ahead forecast vintage."""
    actuals = normalize_actuals(actual_raw)
    forecasts = normalize_forecasts(forecast_raw)
    selected = select_forecast_vintages(forecasts, cutoff_hour)

    # Keep only target half-hours in requested local dates (UK market time).
    start_local = datetime.combine(start_date, time.min, tzinfo=LONDON).astimezone(UTC)
    end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=LONDON).astimezone(UTC)
    # Build the complete expected half-hour grid so missing intervals remain
    # visible in coverage statistics instead of disappearing from the dataset.
    timestamps: list[datetime] = []
    cursor = start_local
    while cursor < end_local:
        timestamps.append(cursor)
        cursor += timedelta(minutes=30)

    records: list[dict[str, Any]] = []
    for target in timestamps:
        actual = actuals.get(target)
        forecast = selected.get(target)
        forecast_mw = forecast["generation"] if forecast else None
        error = (forecast_mw - actual) if forecast_mw is not None and actual is not None else None
        local_target = target.astimezone(LONDON)
        records.append({
            "start_time": local_target.isoformat(),
            "date": local_target.date().isoformat(),
            "period": f"{local_target.strftime('%H:%M')}",
            "actual_mw": _round(actual),
            "forecast_mw": _round(forecast_mw),
            "error_mw": _round(error),
            "absolute_error_mw": _round(abs(error)) if error is not None else None,
            "publish_time": forecast["publish_time"].astimezone(LONDON).isoformat() if forecast else None,
            "cutoff_time": forecast["cutoff_time"].astimezone(LONDON).isoformat() if forecast else None,
        })

    metrics = calculate_metrics(records)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_day[record["date"]].append(record)
    daily = []
    for day in sorted(by_day):
        day_records = by_day[day]
        day_metrics = calculate_metrics(day_records)
        daily.append({"date": day, **day_metrics})

    matched = [r for r in records if r["actual_mw"] is not None and r["forecast_mw"] is not None]
    largest_errors = sorted(matched, key=lambda r: r["absolute_error_mw"] or 0, reverse=True)[:10]
    total_target_intervals = len(records)
    actual_count = sum(1 for r in records if r["actual_mw"] is not None)
    forecast_count = sum(1 for r in records if r["forecast_mw"] is not None)
    return {
        "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "cutoff_hour": cutoff_hour,
        "cutoff_description": f"Latest forecast published by {cutoff_hour:02d}:00 Europe/London on the previous day",
        "metrics": {
            **metrics,
            "actual_intervals": actual_count,
            "forecast_intervals_available_by_cutoff": forecast_count,
            "candidate_actual_or_forecast_intervals": total_target_intervals,
        },
        "coverage": {
            "actual_intervals": actual_count,
            "forecast_intervals_selected": forecast_count,
            "matched_intervals": metrics["matched_intervals"],
            "expected_intervals": total_target_intervals,
            "missing_actual_intervals": total_target_intervals - actual_count,
            "missing_forecast_intervals": total_target_intervals - forecast_count,
        },
        "daily": daily,
        "largest_errors": largest_errors,
        "records": records,
        "methodology": {
            "actual_dataset": "FUELHH filtered to fuelType=WIND",
            "forecast_dataset": "WINDFOR",
            "matching_key": "startTime (30-minute target interval)",
            "vintage_selection": "latest publishTime not later than the configured day-before cutoff for each target interval",
            "error_sign": "forecast minus actual; positive bias means overforecasting",
            "wape_note": "WAPE is omitted when total actual generation is zero; the selected series contains only matched records in its denominator.",
        },
    }
