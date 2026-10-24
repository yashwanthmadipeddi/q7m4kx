from datetime import date

from app import elexon


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fuelhh_uses_settlement_date_filters_and_wind_filter(monkeypatch):
    elexon.clear_cache()
    observed = {}

    def fake_get(url, *, params, timeout, headers):
        observed.update(url=url, params=params)
        return FakeResponse([
            {"fuelType": "WIND", "startTime": "2026-01-01T00:00:00Z", "generation": 100}
        ])

    monkeypatch.setattr(elexon.httpx, "get", fake_get)
    rows = elexon.fetch_dataset("FUELHH", date(2026, 1, 1), date(2026, 1, 31))

    assert observed["url"].endswith("/datasets/FUELHH/stream")
    assert observed["params"]["fuelType"] == "WIND"
    assert observed["params"]["settlementDateFrom"] == "2026-01-01"
    assert observed["params"]["settlementDateTo"] == "2026-01-31"
    assert "from" not in observed["params"]
    assert len(rows) == 1
    elexon.clear_cache()


def test_windfor_uses_publication_timestamp_filters_including_previous_day(monkeypatch):
    elexon.clear_cache()
    observed = {}

    def fake_get(url, *, params, timeout, headers):
        observed.update(url=url, params=params)
        return FakeResponse({"data": [
            {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T10:30:00Z", "generation": 90}
        ], "metadata": {}})

    monkeypatch.setattr(elexon.httpx, "get", fake_get)
    rows = elexon.fetch_dataset("WINDFOR", date(2026, 1, 1), date(2026, 1, 31))

    assert observed["url"].endswith("/datasets/WINDFOR/stream")
    assert observed["params"]["publishDateTimeFrom"] == "2025-12-31T00:00:00Z"
    assert observed["params"]["publishDateTimeTo"] == "2026-01-30T23:59:59Z"
    assert len(rows) == 1
    assert rows[0]["publishTime"] == "2025-12-31T10:30:00Z"
    elexon.clear_cache()
