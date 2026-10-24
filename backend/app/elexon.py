"""Small, cached client for the two Elexon datasets required by the brief."""
from __future__ import annotations

import os
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

import httpx

BASE_URL = os.getenv("ELEXON_API_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1").rstrip("/")
LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc
CACHE_SECONDS = int(os.getenv("ELEXON_CACHE_SECONDS", "300"))
_TIMEOUT = float(os.getenv("ELEXON_TIMEOUT_SECONDS", "35"))
_cache: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}
_cache_lock = Lock()


class ElexonApiError(RuntimeError):
    """An upstream Elexon request failed or returned an unreadable response."""


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        # Some APIs wrap arrays one level deeper under an object.
        for value in payload.values():
            if isinstance(value, list) and all(isinstance(x, dict) for x in value):
                return value
    raise ElexonApiError("Elexon returned an unexpected JSON response shape.")


def clear_cache() -> None:
    """Clear cached responses; primarily useful in tests."""
    with _cache_lock:
        _cache.clear()


def fetch_dataset(dataset: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Fetch a date range from FUELHH or WINDFOR, caching successful responses."""
    dataset = dataset.upper()
    if dataset not in {"FUELHH", "WINDFOR"}:
        raise ValueError("Only FUELHH and WINDFOR are supported.")
    # The raw dataset streams do not share one common date-filter contract:
    # FUELHH is filtered by settlement date, while WINDFOR is filtered by
    # publication timestamp. Passing generic `from`/`to` to both endpoints can
    # produce HTTP 200 + an empty array, which looks like missing data in the UI.
    if dataset == "FUELHH":
        params: dict[str, str] = {
            "fuelType": "WIND",
            "settlementDateFrom": start_date.isoformat(),
            "settlementDateTo": end_date.isoformat(),
            "format": "json",
        }
        cache_from, cache_to = start_date.isoformat(), end_date.isoformat()
    else:
        # Forecasts for delivery on start_date can be published on the preceding
        # day, so include that day. The upper bound is the end of the day before
        # end_date, because the latest eligible forecast for a delivery date is
        # published before that delivery date. The analytics layer applies the
        # configurable cutoff to each interval after retrieval.
        publish_from = datetime.combine(
            start_date - timedelta(days=1), dt_time.min, tzinfo=LONDON
        )
        publish_to = datetime.combine(
            end_date, dt_time.min, tzinfo=LONDON
        ) - timedelta(seconds=1)
        params = {
            "publishDateTimeFrom": _iso_utc(publish_from),
            "publishDateTimeTo": _iso_utc(publish_to),
            "format": "json",
        }
        cache_from, cache_to = params["publishDateTimeFrom"], params["publishDateTimeTo"]

    cache_key = (dataset, cache_from, cache_to)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return list(cached[1])

    url = f"{BASE_URL}/datasets/{dataset}/stream"
    try:
        response = httpx.get(
            url,
            params=params,
            timeout=_TIMEOUT,
            headers={"Accept": "application/json", "User-Agent": "WindLens-Assignment/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        records = _extract_records(payload)
    except httpx.TimeoutException as exc:
        raise ElexonApiError(f"Elexon {dataset} request timed out. Please retry in a moment.") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 429:
            message = "Elexon rate-limited the request. Wait briefly, then retry."
        elif status >= 500:
            message = f"Elexon is temporarily returning HTTP {status}. Please retry later."
        else:
            detail = exc.response.text[:240].replace("\n", " ")
            message = f"Elexon rejected the {dataset} request (HTTP {status}): {detail}"
        raise ElexonApiError(message) from exc
    except httpx.RequestError as exc:
        raise ElexonApiError("Could not connect to Elexon. Check the deployment's outbound internet access and retry.") from exc
    except ValueError as exc:
        raise ElexonApiError(f"Elexon {dataset} returned invalid JSON.") from exc

    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), records)
    return list(records)


def fetch_january_pair(start_date: date, end_date: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch actuals and forecast candidates for the same target interval range."""
    # The assignment limits target delivery intervals to January 2026. Forecast
    # publishTime may be on the preceding day; the API filters here by target
    # startTime, not by publishTime, so the selected forecast vintage is retained.
    actuals = fetch_dataset("FUELHH", start_date, end_date)
    forecasts = fetch_dataset("WINDFOR", start_date, end_date)
    return actuals, forecasts
