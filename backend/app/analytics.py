"""Forecast-vintage selection and hourly forecast error calculations.

FUELHH actuals are half-hourly. WINDFOR is evaluated at the hourly target
resolution used by the available forecast records. The two half-hour actual
MW readings within each clock hour are averaged; incomplete pairs are left
missing rather than fabricated.
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
    """Parse ISO-style timestamps into aware UTC datetimes."""
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
    """Read fields case-insensitively to tolerate source casing differences."""
    for name in names:
        if name in record:
            return record[name]
    lowered = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def normalize_actuals(records: Iterable[dict[str, Any]]) -> dict[datetime, float]:
    """Return a timestamp -> generation map for national WIND half-hours."""
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
            actuals[timestamp] = generation
    return actuals


def normalize_forecasts(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize hourly forecast target time, publication time and MW value."""
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
    """Choose the latest forecast published by the previous-day cutoff."""
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


def aggregate_actuals_hourly(actuals: dict[datetime, float]) -> dict[datetime, float]:
    """Average the :00 and :30 FUELHH values into hourly MW actuals.

    An hour is present only when both half-hour readings are present. This
    prevents incomplete data from being silently treated as a complete hour.
    Input datetimes are normalized to UTC, so half-hour boundaries are stable.
    """
    hourly: dict[datetime, float] = {}
    half_hour = timedelta(minutes=30)
    for target, first_value in actuals.items():
        if target.minute != 0 or target.second != 0 or target.microsecond != 0:
            continue
        second_value = actuals.get(target + half_hour)
        if second_value is not None:
            hourly[target] = (first_value + second_value) / 2.0
    return hourly


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def calculate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate MAE, RMSE, bias and WAPE over matched hourly records."""
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
    absolute = [abs(value) for value in errors]
    actual_total = sum(float(r["actual_mw"]) for r in valid)
    forecast_total = sum(float(r["forecast_mw"]) for r in valid)
    wape = (sum(absolute) / abs(actual_total) * 100.0) if actual_total != 0 else None
    return {
        "matched_intervals": len(valid),
        "mae_mw": _round(sum(absolute) / len(absolute)),
        "rmse_mw": _round(sqrt(sum(value * value for value in errors) / len(errors))),
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
    """Align half-hourly actuals to hourly forecasts, then score each hour."""
    actual_half_hours = normalize_actuals(actual_raw)
    actuals = aggregate_actuals_hourly(actual_half_hours)
    forecasts = normalize_forecasts(forecast_raw)
    selected = select_forecast_vintages(forecasts, cutoff_hour)

    start_local = datetime.combine(start_date, time.min, tzinfo=LONDON).astimezone(UTC)
    end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=LONDON).astimezone(UTC)
    timestamps: list[datetime] = []
    cursor = start_local
    while cursor < end_local:
        timestamps.append(cursor)
        cursor += timedelta(hours=1)

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
            "period": local_target.strftime("%H:%M"),
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
        daily.append({"date": day, **calculate_metrics(by_day[day])})

    matched = [r for r in records if r["actual_mw"] is not None and r["forecast_mw"] is not None]
    largest_errors = sorted(matched, key=lambda r: r["absolute_error_mw"] or 0, reverse=True)[:10]
    total_target_intervals = len(records)
    actual_count = sum(1 for r in records if r["actual_mw"] is not None)
    forecast_count = sum(1 for r in records if r["forecast_mw"] is not None)
    return {
        "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "cutoff_hour": cutoff_hour,
        "cutoff_description": f"Latest forecast published by {cutoff_hour:02d}:00 Europe/London on the previous day",
        "time_resolution": "hourly",
        "actual_aggregation": "Mean of the two FUELHH half-hour MW values for each hour; incomplete pairs remain unavailable.",
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
            "actual_dataset": "FUELHH filtered to fuelType=WIND; two half-hour values averaged into hourly MW actuals",
            "forecast_dataset": "WINDFOR",
            "matching_key": "Hourly startTime target",
            "vintage_selection": "latest publishTime not later than the configured day-before cutoff for each hourly target",
            "error_sign": "forecast minus actual; positive bias means overforecasting",
            "wape_note": "WAPE is omitted when total actual generation is zero; the selected series contains only matched records in its denominator.",
        },
    }