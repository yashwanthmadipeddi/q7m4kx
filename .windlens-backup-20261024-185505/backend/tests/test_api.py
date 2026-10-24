from datetime import date

from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rejects_dates_outside_assignment_month():
    response = client.get("/api/analysis", params={"start_date": "2025-12-31", "end_date": "2026-01-02"})
    assert response.status_code == 422


def test_rejects_start_after_end():
    response = client.get("/api/analysis", params={"start_date": "2026-01-10", "end_date": "2026-01-01"})
    assert response.status_code == 422


def test_analysis_works_with_mocked_elexon(monkeypatch):
    def fake_pair(start_date: date, end_date: date):
        actuals = [{"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": 80}]
        forecasts = [{"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-01T10:00:00Z", "generation": 100}]
        return actuals, forecasts
    monkeypatch.setattr(main, "fetch_january_pair", fake_pair)
    response = client.get("/api/analysis", params={"start_date": "2026-01-02", "end_date": "2026-01-02"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["matched_intervals"] == 1
    assert payload["metrics"]["mae_mw"] == 20.0
    assert payload["records"][0]["publish_time"].startswith("2026-01-01T10:00:00")
    assert payload["source_diagnostics"] == {"fuelhh_raw_records": 1, "windfor_raw_records": 1}


def test_csv_download_uses_same_analysis(monkeypatch):
    def fake_pair(start_date: date, end_date: date):
        return (
            [{"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": 80}],
            [{"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-01T10:00:00Z", "generation": 100}],
        )
    monkeypatch.setattr(main, "fetch_january_pair", fake_pair)
    response = client.get("/api/records.csv", params={"start_date": "2026-01-02", "end_date": "2026-01-02"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "actual_mw,forecast_mw,error_mw" in response.text
    assert "80.0,100.0,20.0" in response.text
