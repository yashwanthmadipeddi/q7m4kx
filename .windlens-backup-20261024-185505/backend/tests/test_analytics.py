from datetime import date, datetime, timezone

from app.analytics import analyze_records, calculate_metrics, decision_cutoff_for_target, normalize_actuals, select_forecast_vintages

UTC = timezone.utc


def test_normalize_actuals_filters_non_wind_and_parses_numbers():
    rows = [
        {"fuelType": "WIND", "startTime": "2026-01-01T00:00:00Z", "generation": "120.5"},
        {"fuelType": "GAS", "startTime": "2026-01-01T00:00:00Z", "generation": 400},
    ]
    result = normalize_actuals(rows)
    assert len(result) == 1
    assert list(result.values()) == [120.5]


def test_selects_latest_forecast_available_before_previous_day_cutoff():
    target = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    forecasts = [
        {"start_time": target, "publish_time": datetime(2025, 12, 31, 10, 0, tzinfo=UTC), "generation": 100},
        {"start_time": target, "publish_time": datetime(2026, 1, 1, 10, 45, tzinfo=UTC), "generation": 130},
        {"start_time": target, "publish_time": datetime(2026, 1, 1, 12, 0, tzinfo=UTC), "generation": 150},
    ]
    selected = select_forecast_vintages(forecasts, cutoff_hour=11)
    assert selected[target]["generation"] == 130
    assert selected[target]["publish_time"] == datetime(2026, 1, 1, 10, 45, tzinfo=UTC)


def test_cutoff_uses_previous_day_london_time():
    target = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    cutoff = decision_cutoff_for_target(target, cutoff_hour=11)
    assert cutoff == datetime(2026, 1, 1, 11, 0, tzinfo=UTC)


def test_metric_calculations_are_correct():
    rows = [
        {"actual_mw": 100.0, "forecast_mw": 110.0},
        {"actual_mw": 200.0, "forecast_mw": 180.0},
    ]
    metrics = calculate_metrics(rows)
    assert metrics["matched_intervals"] == 2
    assert metrics["mae_mw"] == 15.0
    assert metrics["rmse_mw"] == 15.81
    assert metrics["bias_mw"] == -5.0
    assert metrics["wape_percent"] == 10.0


def test_analyze_records_returns_matched_rows_and_missing_coverage():
    actuals = [
        {"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": 100},
        {"fuelType": "WIND", "startTime": "2026-01-02T00:30:00Z", "generation": 120},
    ]
    forecasts = [
        {"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-01T10:00:00Z", "generation": 110},
    ]
    result = analyze_records(actuals, forecasts, date(2026, 1, 2), date(2026, 1, 2), 11)
    assert len(result["records"]) == 48
    assert result["metrics"]["matched_intervals"] == 1
    assert result["coverage"]["expected_intervals"] == 48
    assert result["coverage"]["missing_forecast_intervals"] == 47
    assert result["records"][0]["error_mw"] == 10.0


def test_zero_actual_generation_has_no_wape_division_error():
    metrics = calculate_metrics([{"actual_mw": 0.0, "forecast_mw": 0.0}])
    assert metrics["wape_percent"] is None
