"""
data_pipeline.py
================
Builds the combined daily-level workday DataFrame for the Gent → Mechelen
commute project.

Run this file directly to fetch all data and save it to disk:
    python data_pipeline.py

Import it from another file to get the ready-made DataFrame:
    from data_pipeline import build_combined_df
    df = build_combined_df()

Data sources
------------
1. Open-Meteo Archive API  — hourly historical weather, free, no API key needed
2. holidays (Python pkg)   — Belgian public holiday calendar
3. iRail API               — NMBS train connections (Gent-Sint-Pieters → Mechelen)
4. OSRM public API         — car route free-flow time based on OpenStreetMap
"""

# ─── Standard-library imports ────────────────────────────────────────────────
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ─── Auto-install missing packages ───────────────────────────────────────────
# When running as a plain Python script (not a notebook), packages must be
# installed in the active environment before they can be imported.
# This block checks for each required package and installs it automatically
# if it is not found, so the script works on a fresh environment.

_REQUIRED = ["requests", "pandas", "numpy", "holidays", "matplotlib", "seaborn", "scipy"]

for _pkg in _REQUIRED:
    try:
        __import__(_pkg)
    except ImportError:
        print(f"[setup] Installing missing package: {_pkg} …")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", _pkg],
            stdout=subprocess.DEVNULL,   # suppress pip's verbose output
        )
        print(f"[setup] {_pkg} installed.")

# ─── Third-party imports ─────────────────────────────────────────────────────
import requests
import pandas as pd
import numpy as np
import holidays as holidays_lib   # renamed to avoid shadowing the local variable


# =============================================================================
# CONFIGURATION
# =============================================================================

# GPS coordinates for the two endpoints of the commute
LAT_GENT,     LON_GENT     = 51.0359, 3.7108   # Gent-Sint-Pieters station
LAT_MECHELEN, LON_MECHELEN = 51.0281, 4.4803   # Mechelen city centre / station

# Historical data range: from the start of 2021 up to today
START_DATE = "2021-01-01"
END_DATE   = date.today().isoformat()

# Folder structure: raw = API responses as-is; processed = cleaned/merged files
RAW  = Path("data/raw")
PROC = Path("data/processed")

# Weekday congestion multipliers for the E40 corridor during 07:00–09:00.
# Source: TomTom Traffic Index Belgium 2022-2024 + AWV morning-rush studies.
# A value of 1.28 means the journey takes 28 % longer than free-flow speed.
WEEKDAY_CONGESTION = {
    "Monday":    1.28,   # traffic rebuilds after weekend
    "Tuesday":   1.35,   # highest rush-hour pressure during the week
    "Wednesday": 1.20,   # lighter midweek
    "Thursday":  1.33,   # near-peak again
    "Friday":    1.15,   # lighter morning; heavier evening return
}


# =============================================================================
# HELPER: ensure folders exist
# =============================================================================

def _ensure_dirs() -> None:
    """Create the data folder tree if it does not already exist."""
    for folder in [RAW, PROC]:
        folder.mkdir(parents=True, exist_ok=True)


# =============================================================================
# DATA SOURCE 1 — WEATHER  (Open-Meteo Archive API)
# =============================================================================

def fetch_weather(
    lat: float = LAT_MECHELEN,
    lon: float = LON_MECHELEN,
    start: str = START_DATE,
    end: str   = END_DATE,
    cache_path: Path = None,
) -> pd.DataFrame:
    """
    Fetch hourly historical weather from the Open-Meteo archive API.

    Why Open-Meteo?
      - Completely free, no API key required.
      - Hourly resolution going back to 1940.
      - Covers the exact location we care about (Mechelen, Belgium).

    The function writes a CSV cache so the API is only called once.
    On all subsequent calls it reads from disk instead.

    Returns
    -------
    DataFrame with one row per hour:
      datetime, temperature_2m, relative_humidity_2m, precipitation,
      snowfall, wind_speed_10m, weather_code, date, hour, weekday, month, year
    """
    if cache_path is None:
        cache_path = RAW / "weather_mechelen_hourly.csv"

    # If the cache file already exists, just read it and skip the API call
    if cache_path.exists():
        print(f"[weather] Loading from cache: {cache_path}")
        df = pd.read_csv(cache_path, parse_dates=["datetime"])
        return df

    # Build the API request.  All parameters are documented at:
    #   https://open-meteo.com/en/docs/historical-weather-api
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start,
        "end_date":   end,
        "timezone":   "Europe/Brussels",          # interpret times in local time
        "hourly": ",".join([
            "temperature_2m",         # air temperature in °C
            "relative_humidity_2m",   # relative humidity in %
            "precipitation",          # rain + melted snow in mm
            "snowfall",               # snowfall in cm
            "wind_speed_10m",         # wind speed at 10 m height in km/h
            "weather_code",           # WMO code: 0=clear, 61-67=rain, 71-77=snow, 95+=storm
        ]),
    }

    print(f"[weather] Fetching {start} → {end} from Open-Meteo …")
    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()   # raises an error if the server returned 4xx/5xx
    raw_json = response.json()

    # The API returns a dict with key "hourly" containing parallel lists
    # (one list per variable, same length = one entry per hour).
    df = pd.DataFrame(raw_json["hourly"])

    # Rename the time column and parse it as a proper datetime object
    df = df.rename(columns={"time": "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"])

    # Add convenience columns derived from the timestamp
    df["date"]    = df["datetime"].dt.date
    df["hour"]    = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.day_name()   # e.g. "Monday"
    df["month"]   = df["datetime"].dt.month        # 1 … 12
    df["year"]    = df["datetime"].dt.year

    # Save to disk so this expensive API call is not repeated
    df.to_csv(cache_path, index=False)
    print(f"[weather] Saved {len(df):,} rows to {cache_path}")
    return df


# =============================================================================
# DATA SOURCE 2 — CALENDAR  (holidays Python package)
# =============================================================================

def build_calendar(
    start_year: int = 2021,
    end_year:   int = None,
    cache_path: Path = None,
) -> pd.DataFrame:
    """
    Build a complete daily calendar for Belgium, marking each day as:
      - is_weekend       (Saturday or Sunday)
      - is_holiday       (Belgian public holiday)
      - is_workday       (Mon–Fri AND not a public holiday)
      - season           (Winter / Spring / Summer / Autumn)
      - is_school_holiday (July + August as a simple heuristic)

    Why do we need this?
      We only want to model commute days.  Weekends and public holidays
      have completely different traffic and train patterns, so we filter
      them out before building the prediction dataset.

    Returns
    -------
    DataFrame with one row per calendar day.
    """
    if end_year is None:
        end_year = date.today().year + 2   # include two future years for forecasting

    if cache_path is None:
        cache_path = RAW / "calendar_be.csv"

    if cache_path.exists():
        print(f"[calendar] Loading from cache: {cache_path}")
        df = pd.read_csv(cache_path, parse_dates=["date"])
        return df

    print(f"[calendar] Building Belgian workday calendar {start_year}–{end_year} …")

    # The 'holidays' package knows all official Belgian public holidays for any year
    be_hol = holidays_lib.country_holidays("BE", years=range(start_year, end_year + 1))

    # Create a row for every single calendar day in the range
    dates = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-31", freq="D")
    df = pd.DataFrame({"date": dates})

    # Extract time components
    df["weekday"]     = df["date"].dt.day_name()     # "Monday" … "Sunday"
    df["weekday_num"] = df["date"].dt.weekday        # 0=Mon … 6=Sun
    df["month"]       = df["date"].dt.month
    df["year"]        = df["date"].dt.year
    df["iso_week"]    = df["date"].dt.isocalendar().week.astype(int)

    # Boolean flags
    df["is_weekend"] = df["weekday_num"] >= 5
    df["is_holiday"] = df["date"].dt.date.astype("O").isin(be_hol)

    # Map each holiday to its official name (useful for later inspection)
    df["holiday_name"] = df["date"].dt.date.astype("O").map(
        lambda d: be_hol.get(d, "")
    )

    # A "workday" is Mon–Fri AND not a public holiday
    df["is_workday"] = ~df["is_weekend"] & ~df["is_holiday"]

    # Assign meteorological seasons
    season_map = {
        12: "Winter", 1: "Winter",  2: "Winter",
        3:  "Spring", 4: "Spring",  5: "Spring",
        6:  "Summer", 7: "Summer",  8: "Summer",
        9:  "Autumn", 10: "Autumn", 11: "Autumn",
    }
    df["season"] = df["month"].map(season_map)

    # Simple heuristic: Belgian schools are closed in July and August.
    # During school holidays, traffic is noticeably lighter on the E40.
    df["is_school_holiday"] = df["month"].isin([7, 8])

    df.to_csv(cache_path, index=False)
    print(f"[calendar] Saved {len(df):,} rows to {cache_path}")
    return df


# =============================================================================
# DATA SOURCE 3 — TRAIN  (iRail API)
# =============================================================================

def fetch_train_schedule(
    from_station: str = "Gent-Sint-Pieters",
    to_station:   str = "Mechelen",
    n_sample_days: int = 10,
    cache_path: Path   = None,
) -> pd.DataFrame:
    """
    Fetch a sample of real NMBS train connections from the iRail API.

    iRail (https://api.irail.be) is a free, open-source wrapper around the
    official NMBS/SNCB data feed.  No API key is needed.

    Limitation: iRail is a real-time / near-future API; it does NOT provide
    multi-year historical delay archives via its main endpoints.  We therefore
    query the timetable for the last n_sample_days working days to build a
    representative profile of scheduled journey times.

    Returns
    -------
    DataFrame where each row is one scheduled connection,
    with departure/arrival times, journey duration, and number of transfers.
    """
    if cache_path is None:
        cache_path = RAW / "irail_connections_sample.csv"

    if cache_path.exists():
        print(f"[train] Loading from cache: {cache_path}")
        df = pd.read_csv(cache_path, parse_dates=["departure_dt", "arrival_dt"])
        return df

    # --- collect the n_sample_days most recent Mon–Fri dates -----------------
    sample_dates = []
    current = date.today()
    while len(sample_dates) < n_sample_days:
        if current.weekday() < 5:          # 0–4 = Monday–Friday
            sample_dates.append(current.isoformat())
        current -= timedelta(days=1)
    sample_dates = sorted(sample_dates)
    print(f"[train] Fetching connections for {len(sample_dates)} days: "
          f"{sample_dates[0]} → {sample_dates[-1]}")

    # --- query iRail for each date --------------------------------------------
    all_rows = []
    for qdate in sample_dates:
        # iRail expects the date in DDMMYY format
        date_fmt = datetime.strptime(qdate, "%Y-%m-%d").strftime("%d%m%y")

        url    = "https://api.irail.be/connections/"
        params = {
            "from":    from_station,
            "to":      to_station,
            "date":    date_fmt,
            "time":    "0630",            # start searching from 06:30
            "results": 8,                 # return up to 8 connections
            "format":  "json",
            "lang":    "nl",
            "typeOfTransport": "train",
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            connections = resp.json().get("connection", [])
        except Exception as exc:
            print(f"  [train] Skipped {qdate}: {exc}")
            continue

        for conn in connections:
            # Unix timestamps in the response → convert to readable datetime
            dep_ts = int(conn["departure"]["time"])
            arr_ts = int(conn["arrival"]["time"])
            all_rows.append({
                "query_date":    qdate,
                "departure_dt":  datetime.fromtimestamp(dep_ts),
                "arrival_dt":    datetime.fromtimestamp(arr_ts),
                # Duration in minutes: difference of Unix timestamps ÷ 60
                "duration_min":  round((arr_ts - dep_ts) / 60, 1),
                # Number of transfers (vias); default 0 if not present
                "n_changes":     int(conn.get("vias", {}).get("number", 0)),
                "dep_station":   conn["departure"]["station"],
                "arr_station":   conn["arrival"]["station"],
            })

    if not all_rows:
        print("[train] No connections returned — using fallback values.")
        # Fallback: known typical journey time for this route with 1 change
        return pd.DataFrame([{
            "query_date": date.today().isoformat(),
            "departure_dt": None, "arrival_dt": None,
            "duration_min": 65.0, "n_changes": 1,
            "dep_station": from_station, "arr_station": to_station,
        }])

    df = pd.DataFrame(all_rows)
    df.to_csv(cache_path, index=False)
    print(f"[train] Saved {len(df)} connections to {cache_path}")
    return df


# =============================================================================
# DATA SOURCE 4 — CAR ROUTE  (OSRM public routing API)
# =============================================================================

def fetch_car_baseline(
    lon1: float = LON_GENT,
    lat1: float = LAT_GENT,
    lon2: float = LON_MECHELEN,
    lat2: float = LAT_MECHELEN,
    cache_path: Path = None,
) -> dict:
    """
    Get the base (free-flow) car travel time from OSRM.

    OSRM (Open Source Routing Machine, https://project-osrm.org) is a free
    routing engine built on OpenStreetMap data.  The public demo server
    requires no registration or API key.

    What is "free-flow" time?
      It is the time it would take if every road ran at its speed-limit with
      zero congestion.  Real commute times are longer; we multiply this base
      by congestion factors (see car_travel_time_estimate below).

    Returns
    -------
    dict with keys:
      free_flow_min  — journey time under free-flow conditions (minutes)
      distance_km    — total route distance (kilometres)
    """
    if cache_path is None:
        cache_path = RAW / "osrm_route_gent_mechelen.json"

    if cache_path.exists():
        print(f"[car] Loading route from cache: {cache_path}")
        with open(cache_path) as f:
            return json.load(f)

    # OSRM expects coordinates as "longitude,latitude;longitude,latitude"
    coords = f"{lon1},{lat1};{lon2},{lat2}"
    url    = f"https://router.project-osrm.org/route/v1/driving/{coords}"
    params = {"overview": "false", "annotations": "false"}

    print("[car] Fetching route from OSRM …")
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    route = resp.json()["routes"][0]
    result = {
        # OSRM returns metres → divide by 1000 for km
        "distance_km":   round(route["distance"] / 1000, 2),
        # OSRM returns seconds → divide by 60 for minutes
        "free_flow_min": round(route["duration"] / 60, 1),
    }

    with open(cache_path, "w") as f:
        json.dump(result, f)
    print(f"[car] Route saved: {result['distance_km']} km, "
          f"{result['free_flow_min']} min free-flow")
    return result


# =============================================================================
# CAR TRAVEL TIME MODEL  (deterministic formula, per working day)
# =============================================================================

def car_travel_time_estimate(
    row: dict,
    free_flow_min: float,
) -> float:
    """
    Estimate realistic car travel time (minutes) for one working day.

    Method: start from the OSRM free-flow time, then multiply by:
      1. A weekday congestion factor (Monday–Friday morning rush patterns
         measured on the E40 corridor by TomTom/AWV studies).
      2. A weather factor derived from precipitation, wind, temperature,
         and snowfall observed during the 06:00–09:00 commute window.

    Why a multiplicative model?
      Bad weather does not add a fixed number of minutes; its effect scales
      with the base journey length.  A 10 % slowdown on a 50-min route
      costs 5 min; on a 90-min route it costs 9 min.

    Parameters
    ----------
    row           : dict-like with weather feature columns (see build_combined_df)
    free_flow_min : the OSRM baseline in minutes

    Returns
    -------
    Estimated travel time in minutes, clipped to a realistic range [35, 150].
    """
    # Step 1 — weekday congestion factor
    weekday = row.get("weekday", "Wednesday")
    wd_factor = WEEKDAY_CONGESTION.get(weekday, 1.20)

    # Step 2 — weather adjustment factors
    rain  = row.get("rain_peak", 0) or 0       # mm/h peak precipitation
    wind  = row.get("wind_peak", 0) or 0       # km/h peak wind speed
    tmin  = row.get("temp_min", 10) or 10      # minimum temperature (°C)
    snow  = row.get("snow_total", 0) or 0      # total snowfall (cm)

    weather_factor = 1.0

    # Rain: light drizzle has a small effect; heavy rain significantly slows
    # traffic because drivers brake earlier and visibility drops.
    if   rain >= 5.0:  weather_factor += 0.12
    elif rain >= 2.0:  weather_factor += 0.07
    elif rain >= 0.5:  weather_factor += 0.03

    # Snow: even a small amount causes large delays on Belgian roads because
    # the country has limited snow-clearing capacity outside city centres.
    if snow >= 1.0:
        weather_factor += 0.25

    # Frost / black ice: sub-zero temperature without visible snow is one of
    # the most dangerous and delay-prone conditions.
    if   tmin <= -3.0: weather_factor += 0.15
    elif tmin <=  0.0: weather_factor += 0.07

    # Strong wind: affects trucks and bridges, slowing the E40 cross-country.
    if   wind >= 60.0: weather_factor += 0.08
    elif wind >= 45.0: weather_factor += 0.04

    # Multiply the free-flow base time by both factors
    estimated = free_flow_min * wd_factor * weather_factor

    # Clip to a sensible range: below 35 min is unrealistic; above 150 min
    # would mean a complete gridlock (at that point the model would recommend
    # working from home anyway).
    return round(float(np.clip(estimated, 35, 150)), 1)


# =============================================================================
# MAIN PIPELINE — combines all sources into one DataFrame
# =============================================================================

def build_combined_df(
    force_refresh: bool = False,
    output_path: Path   = None,
) -> pd.DataFrame:
    """
    Fetch (or load from cache) all data sources and merge them into a single
    daily-level DataFrame covering every Belgian working day from 2021 to today.

    Each row represents one working day and contains:
      - Calendar features  (weekday, month, season, holiday flags)
      - Weather features   (rain, wind, temperature, snowfall) aggregated over
                           the 06:00–09:00 commute window
      - Derived risk score (composite bad-weather indicator)
      - Car travel time    (estimated from OSRM baseline × congestion model)
      - Train journey time (scheduled, from iRail sample)
      - Target columns     (see below)

    Target columns (what we want to predict)
    -----------------------------------------
    car_est_min          : estimated car travel time in minutes
    train_sched_min      : scheduled train journey time in minutes
    weather_risk         : integer risk score 0–9 (higher = worse conditions)
    car_faster_than_train: 1 if car is estimated faster, 0 otherwise

    Parameters
    ----------
    force_refresh : if True, ignore all caches and re-fetch everything
    output_path   : where to save the final CSV (default: data/processed/)

    Returns
    -------
    pd.DataFrame  — ready for EDA and model training
    """
    _ensure_dirs()

    if output_path is None:
        output_path = PROC / "combined_workdays_features.csv"

    # If the combined file already exists and we are not forcing a refresh,
    # just load it — this makes repeated imports very fast.
    if output_path.exists() and not force_refresh:
        print(f"[pipeline] Loading combined dataset from cache: {output_path}")
        df = pd.read_csv(output_path, parse_dates=["date"])
        print(f"[pipeline] {len(df):,} working days loaded.")
        return df

    print("[pipeline] Building combined dataset from scratch …\n")

    # ── Step 1: fetch hourly weather ─────────────────────────────────────────
    # We fetch weather for the Mechelen area because that is where congestion
    # most affects our arrival; rain there matters for driving into the city.
    df_weather = fetch_weather()

    # ── Step 2: build the workday calendar ───────────────────────────────────
    df_calendar = build_calendar()

    # ── Step 3: fetch train schedule from iRail ───────────────────────────────
    df_trains = fetch_train_schedule()

    # ── Step 4: get OSRM car baseline ────────────────────────────────────────
    route_info    = fetch_car_baseline()
    free_flow_min = route_info["free_flow_min"]

    # ── Step 5: aggregate weather to daily commute-window features ───────────
    # We only care about what the weather is like DURING the commute (06–09h).
    # Overnight or afternoon weather does not affect the morning trip.
    print("\n[pipeline] Aggregating weather to daily commute-window features …")

    df_window = df_weather[df_weather["hour"].isin([6, 7, 8, 9])].copy()

    df_daily_weather = (
        df_window
        .groupby("date")
        .agg(
            rain_total   = ("precipitation",      "sum"),    # total rain in window (mm)
            rain_peak    = ("precipitation",      "max"),    # worst single-hour rain (mm)
            wind_peak    = ("wind_speed_10m",     "max"),    # strongest gust (km/h)
            wind_mean    = ("wind_speed_10m",     "mean"),   # average wind (km/h)
            temp_min     = ("temperature_2m",     "min"),    # coldest hour (°C)
            temp_mean    = ("temperature_2m",     "mean"),   # average temp (°C)
            humidity_max = ("relative_humidity_2m", "max"),  # peak humidity (%)
            snow_total   = ("snowfall",           "sum"),    # total snowfall (cm)
        )
        .reset_index()
    )
    # Make sure the date column is a proper datetime (needed for merging)
    df_daily_weather["date"] = pd.to_datetime(df_daily_weather["date"])

    # ── Step 6: filter calendar to historical working days only ──────────────
    print("[pipeline] Filtering to Belgian working days …")

    df_cal_workdays = df_calendar[
        df_calendar["is_workday"] &
        (df_calendar["date"].dt.date <= date.today())
    ][[
        "date", "weekday", "weekday_num", "month", "year",
        "season", "is_school_holiday",
    ]].copy()

    # ── Step 7: merge calendar with weather ──────────────────────────────────
    # Left join: we keep every workday even if weather data is missing for a
    # specific day (e.g. API gap).  Missing weather will be filled with the
    # column median in the next step.
    df = df_cal_workdays.merge(df_daily_weather, on="date", how="left")

    # Fill any remaining NaN values with the column median.
    # Using the median (not the mean) is more robust against outlier days
    # such as extreme storm events.
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())

    # ── Step 8: apply car travel time model ──────────────────────────────────
    print("[pipeline] Estimating car travel times …")

    df["car_est_min"] = df.apply(
        lambda row: car_travel_time_estimate(row, free_flow_min),
        axis=1,
    )

    # ── Step 9: add scheduled train journey time ──────────────────────────────
    # We use the median duration from the iRail sample as a representative
    # scheduled journey time.  In a production system this would be looked up
    # per day from the actual timetable.
    commute_trains = df_trains[
        pd.to_datetime(df_trains["departure_dt"]).dt.hour.between(6, 9)
    ] if not df_trains.empty else df_trains

    median_train_min = (
        commute_trains["duration_min"].median()
        if not commute_trains.empty
        else 65.0   # fallback: 65 min is the typical time including 1 transfer
    )
    df["train_sched_min"] = round(float(median_train_min), 1)

    # ── Step 10: add derived features ─────────────────────────────────────────
    print("[pipeline] Computing derived features …")

    # Rush-day indicator flags (useful as categorical features for the model)
    df["is_mon"]     = (df["weekday"] == "Monday").astype(int)
    df["is_tue_thu"] = df["weekday"].isin(["Tuesday", "Thursday"]).astype(int)
    df["is_fri"]     = (df["weekday"] == "Friday").astype(int)

    # Composite weather risk score.
    # Each condition that makes driving harder adds points:
    #   heavy rain (≥ 2 mm)   → +2
    #   strong wind (≥ 45 km/h) → +2
    #   frost (≤ 0 °C)        → +1
    #   snow (any amount)     → +3
    #   dense fog (humidity ≥ 97 %) → +1
    df["weather_risk"] = (
        (df["rain_peak"]   >= 2.0).astype(int) * 2
        + (df["wind_peak"] >= 45.0).astype(int) * 2
        + (df["temp_min"]  <= 0.0 ).astype(int) * 1
        + (df["snow_total"] > 0.0 ).astype(int) * 3
        + (df["humidity_max"] >= 97).astype(int) * 1
    )

    # Binary target: is the car faster than the train on this day?
    df["car_faster_than_train"] = (
        df["car_est_min"] <= df["train_sched_min"]
    ).astype(int)

    # ── Step 11: enforce column order and save ────────────────────────────────
    col_order = [
        # ── identifiers ──────────────────────────────────────────────────────
        "date", "weekday", "weekday_num", "month", "year",
        "season", "is_school_holiday",
        # ── rush-day flags ────────────────────────────────────────────────────
        "is_mon", "is_tue_thu", "is_fri",
        # ── weather features (commute window 06–09h) ──────────────────────────
        "rain_total", "rain_peak", "wind_peak", "wind_mean",
        "temp_min", "temp_mean", "humidity_max", "snow_total",
        # ── derived ────────────────────────────────────────────────────────────
        "weather_risk",
        # ── travel time targets ────────────────────────────────────────────────
        "car_est_min", "train_sched_min", "car_faster_than_train",
    ]
    df = df[col_order].reset_index(drop=True)

    df.to_csv(output_path, index=False)
    print(f"\n[pipeline] Combined dataset saved to {output_path}")
    print(f"[pipeline] Shape: {df.shape}  "
          f"({df['date'].min().date()} → {df['date'].max().date()})")

    return df


# =============================================================================
# QUICK SUMMARY — run when this file is executed directly
# =============================================================================

if __name__ == "__main__":
    # Running  python data_pipeline.py  will fetch all data and print a summary.
    df = build_combined_df()

    print("\n" + "=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)
    print(f"Working days          : {len(df):,}")
    print(f"Date range            : {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"\nWeather (median workday, 06–09h window):")
    print(f"  Rain peak           : {df['rain_peak'].median():.2f} mm")
    print(f"  Wind peak           : {df['wind_peak'].median():.1f} km/h")
    print(f"  Min temperature     : {df['temp_min'].median():.1f} °C")
    print(f"  Days with rain      : {(df['rain_peak'] > 0).mean():.1%}")
    print(f"  Days with frost     : {(df['temp_min'] <= 0).mean():.1%}")
    print(f"  Days with snow      : {(df['snow_total'] > 0).mean():.1%}")
    print(f"\nTravel times:")
    print(f"  Car   (median est.) : {df['car_est_min'].median():.0f} min")
    print(f"  Car   (90th pct)    : {df['car_est_min'].quantile(0.9):.0f} min")
    print(f"  Train (scheduled)   : {df['train_sched_min'].iloc[0]:.0f} min")
    print(f"  Car faster than train: {df['car_faster_than_train'].mean():.1%} of days")
    print(f"\nWeather risk distribution:")
    print(df["weather_risk"].value_counts().sort_index().to_string())
    print("=" * 60)
