import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockmock_archiver.archiver import (  # noqa: E402
    Config,
    build_task_list,
    compute_st_date_ms,
    generate_intraday_times,
    load_cached_keys,
    append_to_cache,
    build_excel_from_cache,
    parse_final_result,
    resolve_date_range,
    split_time_premium,
    times_for_date,
)

IST = timezone(timedelta(hours=5, minutes=30))


# ---------- split_time_premium ----------

def test_split_time_premium_parses_valid_string():
    assert split_time_premium("09:16-4.3") == ("09:16", 4.3)


def test_split_time_premium_handles_zero_and_none():
    assert split_time_premium(0) == (None, None)
    assert split_time_premium("0") == (None, None)
    assert split_time_premium(None) == (None, None)


def test_split_time_premium_non_numeric_suffix_kept_as_string():
    t, p = split_time_premium("09:16-abc")
    assert t == "09:16"
    assert p == "abc"


# ---------- compute_st_date_ms ----------

def test_compute_st_date_ms_matches_ist_epoch():
    ms = compute_st_date_ms("2024-01-02", "09:16:00")
    expected = int(datetime(2024, 1, 2, 9, 16, 0, tzinfo=IST).timestamp() * 1000)
    assert ms == expected


# ---------- parse_final_result ----------

def test_parse_final_result_flattens_batches():
    payload = {
        "finalResult": [
            {
                "25JAN2024": {
                    "do": 5, "gpt": 1.2, "gpr": 0.5, "s": 21500.0, "f": 21550.0,
                    "c": [
                        [21500, "09:16-120.5", "09:16-98.2"],
                        [21600, 0, "09:16-150.0"],
                    ],
                }
            }
        ]
    }
    rows = parse_final_result(payload, "2024-01-02", "09:16:00", "nifty")
    assert len(rows) == 2
    assert rows[0]["strike"] == 21500
    assert rows[0]["CE_premium"] == 120.5
    assert rows[0]["PE_premium"] == 98.2
    assert rows[1]["CE_time"] is None
    assert rows[1]["CE_premium"] is None
    assert rows[0]["index"] == "nifty"


def test_parse_final_result_empty_batch_list_yields_no_rows():
    assert parse_final_result({"finalResult": []}, "2024-01-02", "09:16:00", "nifty") == []


def test_parse_final_result_skips_malformed_entries():
    payload = {
        "finalResult": [
            {"25JAN2024": {"c": [[21500, "09:16-1"], "not-a-list"]}}
        ]
    }
    rows = parse_final_result(payload, "2024-01-02", "09:16:00", "nifty")
    assert rows == []  # the 2-element entry is malformed (needs 3) and the string is skipped


# ---------- generate_intraday_times / times_for_date ----------

def test_generate_intraday_times_respects_interval_and_bounds():
    times = generate_intraday_times("09:16:00", "09:46:00", 15)
    assert times == ["09:16:00", "09:31:00", "09:46:00"]


def test_times_for_date_single_mode():
    config = Config(time_mode="single", selected_time="09:16:00")
    assert times_for_date("2024-01-02", config, []) == ["09:16:00"]


def test_times_for_date_multi_all_mode_returns_full_intraday_list():
    config = Config(time_mode="multi_all")
    intraday = ["09:16:00", "09:31:00"]
    assert times_for_date("2024-01-02", config, intraday) == intraday


def test_times_for_date_expiry_weekday_uses_intraday_on_expiry_day():
    # 2024-01-02 is a Tuesday (weekday 1)
    config = Config(time_mode="expiry_weekday", expiry_weekdays=[1, 3], selected_time="09:16:00")
    intraday = ["09:16:00", "09:31:00"]
    assert times_for_date("2024-01-02", config, intraday) == intraday


def test_times_for_date_expiry_weekday_uses_single_on_non_expiry_day():
    # 2024-01-03 is a Wednesday (weekday 2), not in [1, 3]
    config = Config(time_mode="expiry_weekday", expiry_weekdays=[1, 3], selected_time="09:16:00")
    assert times_for_date("2024-01-03", config, ["09:16:00", "09:31:00"]) == ["09:16:00"]


# ---------- Config.validate ----------

def test_config_validate_rejects_bad_time_mode():
    with pytest.raises(ValueError):
        Config(time_mode="bogus").validate()


def test_config_validate_rejects_non_positive_interval():
    with pytest.raises(ValueError):
        Config(intraday_interval_minutes=0).validate()


def test_config_validate_rejects_out_of_range_weekday():
    with pytest.raises(ValueError):
        Config(expiry_weekdays=[7]).validate()


def test_config_validate_rejects_start_after_end():
    with pytest.raises(ValueError):
        Config(start_date="2024-05-01", end_date="2024-01-01").validate()


def test_config_validate_accepts_defaults():
    Config().validate()  # should not raise


# ---------- resolve_date_range ----------

def test_resolve_date_range_explicit_bounds():
    config = Config(start_date="2024-01-01", end_date="2024-01-31")
    start, end = resolve_date_range(config)
    assert str(start) == "2024-01-01"
    assert str(end) == "2024-01-31"


def test_resolve_date_range_defaults_to_years_back_from_today():
    config = Config(years_back=2)
    today = datetime(2026, 8, 13, tzinfo=IST)
    start, end = resolve_date_range(config, today=today)
    assert end == today.date()
    assert start.year == today.year - 2


# ---------- build_task_list ----------

def test_build_task_list_skips_weekends():
    # 2024-01-06 and 2024-01-07 are Sat/Sun
    config = Config(time_mode="single", selected_time="09:16:00")
    from datetime import date
    tasks = build_task_list(date(2024, 1, 5), date(2024, 1, 8), config, [])
    dates = sorted(set(d for d, _ in tasks))
    assert dates == ["2024-01-05", "2024-01-08"]


# ---------- cache round trip ----------

def test_cache_round_trip(tmp_path):
    config = Config(cache_csv=str(tmp_path / "cache.csv"), output_xlsx=str(tmp_path / "out.xlsx"))
    assert load_cached_keys(config) == set()

    rows = parse_final_result(
        {"finalResult": [{"25JAN2024": {"do": 1, "gpt": 1, "gpr": 1, "s": 100, "f": 101,
                                          "c": [[100, "09:16-1.5", "09:16-2.5"]]}}]},
        "2024-01-02", "09:16:00", "nifty",
    )
    append_to_cache(config, rows)

    cached = load_cached_keys(config)
    assert ("2024-01-02", "09:16:00") in cached

    real_rows = build_excel_from_cache(config)
    assert len(real_rows) == 1
    assert os.path.exists(config.output_xlsx)
