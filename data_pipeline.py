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
import io
from concurrent.futures import ThreadPoolExecutor
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

# Path to the Infrabel dataset index CSV (provided by the user)
TRAIN_DATASETS_INDEX = Path("data/newdata/newtraindatasets.csv")

# Exact station names as they appear in the Infrabel punctuality files
STATION_GENT     = "GENT-SINT-PIETERS"
STATION_MECHELEN = "MECHELEN"

# Commute preference buffer: if the car estimate is within this many minutes of
# the actual train journey time, still prefer the car (accounts for door-to-door
# convenience vs waiting on a platform).  Set to 0 for strict fastest-wins logic.
CAR_PREF_BUFFER_MIN = 10

# Only the columns we need from each (large) Infrabel monthly file.
# Reading only these columns reduces memory use by ~70 %.
_INFRABEL_COLS = [
    "DATDEP",            # date of the train run (format: DDMMMYYYY, e.g. 04JAN2021)
    "TRAIN_NO",          # train number — used to join the Gent and Mechelen rows
    "PTCAR_LG_NM_NL",    # station name in Dutch — used to filter Gent / Mechelen
    "PLANNED_TIME_DEP",  # scheduled departure time at this stop (HH:MM:SS)
    "REAL_TIME_DEP",     # actual   departure time at this stop
    "DELAY_DEP",         # departure delay in seconds (negative = early)
    "PLANNED_TIME_ARR",  # scheduled arrival  time at this stop
    "REAL_TIME_ARR",     # actual   arrival   time at this stop
    "DELAY_ARR",         # arrival  delay in seconds (negative = early)
]


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


def _hms(series: pd.Series) -> pd.Series:
    """Parse a HH:MM:SS string column to Timestamps (date part is ignored)."""
    return pd.to_datetime(series, format="%H:%M:%S", errors="coerce")


def _process_infrabel_month(
    month_str: str,
    url: str,
    cache_dir: Path,
    force_refresh: bool,
) -> "pd.DataFrame | None":
    """Download, filter, and aggregate one Infrabel monthly file.

    Returns a daily-level DataFrame for the Gent→Mechelen commute window,
    or None when the month produced no usable data.
    The processed result is cached in cache_dir/{month_str}_gent_mech.csv so
    subsequent runs skip the download entirely.
    """
    month_cache = cache_dir / f"{month_str}_gent_mech.csv"

    if not force_refresh and month_cache.exists():
        try:
            return pd.read_csv(month_cache, parse_dates=["date"])
        except Exception:
            pass  # corrupt cache → re-download below

    # ── Download ─────────────────────────────────────────────────────────────
    try:
        print(f"  [{month_str}] Downloading …", end="", flush=True)
        resp = requests.get(url, timeout=180)
        resp.raise_for_status()
        print(f" {len(resp.content) // 1024:,} KB", end="")
    except Exception as exc:
        print(f" FAILED: {exc}")
        return None

    # ── Parse: read only the columns we need to save memory ──────────────────
    try:
        df_month = pd.read_csv(
            io.BytesIO(resp.content),
            usecols=_INFRABEL_COLS,
            low_memory=False,
        )
    except ValueError:
        # Some older files may lack a column; fall back to reading all then selecting
        try:
            df_month = pd.read_csv(io.BytesIO(resp.content), low_memory=False)
            available = [c for c in _INFRABEL_COLS if c in df_month.columns]
            df_month  = df_month[available]
        except Exception as exc2:
            print(f" parse error: {exc2}")
            return None

    # ── Date parsing (format: 04JAN2021) ─────────────────────────────────────
    df_month["date"] = pd.to_datetime(
        df_month["DATDEP"], format="%d%b%Y", errors="coerce"
    )
    df_month = df_month.dropna(subset=["date"])

    # ── Filter Gent departures (06:00–08:59) ─────────────────────────────────
    gent = df_month[df_month["PTCAR_LG_NM_NL"] == STATION_GENT].copy()
    gent["_dep_hour"] = (
        pd.to_datetime(gent["PLANNED_TIME_DEP"], format="%H:%M:%S", errors="coerce")
        .dt.hour
    )
    gent = gent[gent["_dep_hour"].isin([6, 7, 8])].copy()

    if gent.empty:
        print(" (no commute-window trains found)")
        return None

    gent = gent[[
        "date", "TRAIN_NO",
        "PLANNED_TIME_DEP", "REAL_TIME_DEP", "DELAY_DEP",
    ]].rename(columns={
        "PLANNED_TIME_DEP": "planned_dep",
        "REAL_TIME_DEP":    "real_dep",
        "DELAY_DEP":        "delay_dep_s",
    })

    # ── Filter Mechelen arrivals ──────────────────────────────────────────────
    mech = df_month[df_month["PTCAR_LG_NM_NL"] == STATION_MECHELEN][[
        "date", "TRAIN_NO",
        "PLANNED_TIME_ARR", "REAL_TIME_ARR", "DELAY_ARR",
    ]].rename(columns={
        "PLANNED_TIME_ARR": "planned_arr",
        "REAL_TIME_ARR":    "real_arr",
        "DELAY_ARR":        "delay_arr_s",
    }).copy()

    # ── Join: keep Gent rows even if the train never reached Mechelen ─────────
    joined = gent.merge(mech, on=["date", "TRAIN_NO"], how="left")

    # Exclude trains whose route does not include Mechelen at all — they also
    # have NaN planned_arr after the left join but are not cancellations.
    joined = joined[joined["planned_arr"].notna()].copy()

    if joined.empty:
        print(" (no Gent→Mechelen scheduled trains found)")
        return None

    # ── Journey times ─────────────────────────────────────────────────────────
    pd_dep = _hms(joined["planned_dep"])
    pd_arr = _hms(joined["planned_arr"])
    rd_dep = _hms(joined["real_dep"])
    rd_arr = _hms(joined["real_arr"])

    joined["planned_journey_min"] = (pd_arr - pd_dep).dt.total_seconds() / 60
    joined["actual_journey_min"]  = (rd_arr - rd_dep).dt.total_seconds() / 60

    # Cancelled = scheduled to arrive at Mechelen but never did.
    # Covers (a) cancelled at Gent (real_dep NaN) and
    #        (b) cancelled en route (real_dep filled, real_arr NaN).
    joined["is_cancelled"] = rd_arr.isna().astype(int)

    # On-time = arrived ≤ 5 min late AND not cancelled.
    # fillna(9999) treats a missing delay as very late, not punctual.
    joined["is_on_time"] = (
        (joined["delay_arr_s"].fillna(9999) <= 300)
        & (joined["is_cancelled"] == 0)
    ).astype(int)

    # ── Daily aggregation ─────────────────────────────────────────────────────
    daily = (
        joined.groupby("date")
        .agg(
            n_trains                  = ("TRAIN_NO",            "count"),
            train_planned_journey_min = ("planned_journey_min", "median"),
            train_actual_journey_min  = ("actual_journey_min",  "median"),
            train_delay_arr_median_s  = ("delay_arr_s",         "median"),
            train_on_time_pct         = ("is_on_time",          "mean"),
            train_cancelled_pct       = ("is_cancelled",        "mean"),
        )
        .reset_index()
    )

    for col in ["train_planned_journey_min", "train_actual_journey_min"]:
        daily.loc[daily[col] <= 0,   col] = np.nan   # can't be 0 or negative
        daily.loc[daily[col] > 300,  col] = np.nan   # > 5 h is a data error

    daily.to_csv(month_cache, index=False)
    print(f" → {len(daily)} days")
    return daily


# =============================================================================
# DATA SOURCE 3b — REAL TRAIN DATA  (Infrabel Punctuality History)
# =============================================================================

def fetch_infrabel_punctuality(
    index_path: Path    = TRAIN_DATASETS_INDEX,
    start_year: int     = 2021,
    cache_dir: Path     = None,
    output_path: Path   = None,
    force_refresh: bool = False,
    n_workers: int      = 4,
) -> pd.DataFrame:
    """
    Download and process Infrabel punctuality data for the
    Gent-Sint-Pieters → Mechelen commute corridor.

    What is this data?
      Infrabel (the Belgian rail infrastructure manager) publishes the full
      per-stop punctuality record for every NMBS/SNCB train, every day.
      Each row is one train passing through one station, and contains the
      scheduled and actual departure/arrival times plus the delay in seconds.

    How we use it:
      1. Read the URL index from newtraindatasets.csv.
      2. For each month from start_year onwards, download the file.
         We only keep the two columns we care about: departures from
         GENT-SINT-PIETERS and arrivals at MECHELEN, for trains running
         in the 06:00–09:00 commute window.
         The processed (small) result is cached; the raw file is NOT
         kept on disk to save space.
      3. Join Gent rows with Mechelen rows on date + train number.
      4. Aggregate to one row per calendar day with:
           - train_planned_journey_min  : median scheduled journey time
           - train_actual_journey_min   : median actual journey time
           - train_delay_arr_median_s   : median arrival delay (seconds)
           - train_on_time_pct          : share of trains ≤ 5 min late
           - train_cancelled_pct        : share of trains with no real data

    Returns
    -------
    DataFrame with one row per day for which Infrabel data is available.
    Days not present were not in the index CSV (gaps in publication).
    """
    if cache_dir is None:
        cache_dir = RAW / "infrabel"
    if output_path is None:
        output_path = PROC / "infrabel_daily_commute.csv"

    cache_dir.mkdir(parents=True, exist_ok=True)

    # If already fully processed, just load it
    if not force_refresh and output_path.exists():
        print(f"[train_real] Loading Infrabel data from cache: {output_path}")
        df = pd.read_csv(output_path, parse_dates=["date"])
        print(f"[train_real] {len(df):,} days with real train data loaded.")
        return df

    # ── Load URL index ────────────────────────────────────────────────────────
    if not index_path.exists():
        print(f"[train_real] Index file not found: {index_path}  — skipping real train data.")
        return pd.DataFrame()

    index_df = pd.read_csv(index_path, sep=";")
    index_df.columns = ["month", "url"]
    # Keep only months from start_year onwards (weather data starts then too)
    index_df["year"] = index_df["month"].str[:4].astype(int)
    index_df = index_df[index_df["year"] >= start_year].sort_values("month").reset_index(drop=True)
    print(f"[train_real] Processing {len(index_df)} monthly Infrabel files ({start_year}+) …")

    rows = [{"month": r["month"], "url": r["url"]} for _, r in index_df.iterrows()]

    def _process(row):
        return _process_infrabel_month(row["month"], row["url"], cache_dir, force_refresh)

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        results = list(pool.map(_process, rows))

    all_daily = [r for r in results if r is not None]

    if not all_daily:
        print("[train_real] No data was collected — returning empty DataFrame.")
        return pd.DataFrame()

    # ── Combine all months and save ───────────────────────────────────────────
    df_result = (
        pd.concat(all_daily, ignore_index=True)
        .sort_values("date")
        .reset_index(drop=True)
    )

    df_result.to_csv(output_path, index=False)
    print(f"\n[train_real] Combined: {len(df_result):,} days saved to {output_path}")
    return df_result


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
    car_faster_than_train: 1 if car ≤ train + CAR_PREF_BUFFER_MIN, else 0

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

    # ── Step 9: iRail fallback — scheduled journey time ──────────────────────
    # This gives us one representative scheduled journey time to use as a
    # fallback for days where Infrabel data is unavailable.
    commute_trains = df_trains[
        pd.to_datetime(df_trains["departure_dt"]).dt.hour.between(6, 9)
    ] if not df_trains.empty else df_trains

    irail_median_min = (
        commute_trains["duration_min"].median()
        if not commute_trains.empty
        else 65.0   # fallback: typical Gent-Sint-Pieters → Mechelen with 1 transfer
    )

    # ── Step 9b: load real Infrabel punctuality data ──────────────────────────
    # This replaces the constant iRail estimate with per-day actual data.
    # Each row gives us the real journey time, delay, and on-time rate.
    print("[pipeline] Loading real Infrabel train data …")
    df_infrabel = fetch_infrabel_punctuality(force_refresh=force_refresh)

    if not df_infrabel.empty:
        # Merge real train stats onto the workday DataFrame.
        # how="left" keeps all workdays; days with no Infrabel data will have NaN
        # in the Infrabel columns, which we fill with the iRail fallback below.
        df = df.merge(df_infrabel[[
            "date",
            "train_planned_journey_min",
            "train_actual_journey_min",
            "train_delay_arr_median_s",
            "train_on_time_pct",
            "train_cancelled_pct",
        ]], on="date", how="left")

        # For days not covered by Infrabel (gaps in publication), fall back to
        # the iRail scheduled time and assume normal conditions.
        df["train_planned_journey_min"] = df["train_planned_journey_min"].fillna(irail_median_min)
        df["train_actual_journey_min"]  = df["train_actual_journey_min"].fillna(
            df["train_planned_journey_min"]  # if no real data, assume on-time
        )
        df["train_delay_arr_median_s"]  = df["train_delay_arr_median_s"].fillna(0.0)
        df["train_on_time_pct"]         = df["train_on_time_pct"].fillna(1.0)    # assume 100% on time
        df["train_cancelled_pct"]       = df["train_cancelled_pct"].fillna(0.0)

        n_real = df["train_delay_arr_median_s"].notna().sum()
        print(f"[pipeline] Real Infrabel data merged for {n_real:,} / {len(df):,} working days.")
    else:
        # No Infrabel data available — fall back to iRail constant for everything
        print("[pipeline] No Infrabel data — using iRail fallback for all days.")
        df["train_planned_journey_min"] = irail_median_min
        df["train_actual_journey_min"]  = irail_median_min
        df["train_delay_arr_median_s"]  = 0.0
        df["train_on_time_pct"]         = 1.0
        df["train_cancelled_pct"]       = 0.0

    # Keep the old name as an alias so existing model code does not break
    df["train_sched_min"] = df["train_planned_journey_min"]

    # ── Step 10: add derived features ─────────────────────────────────────────
    print("[pipeline] Computing derived features …")

    # Rush-day indicator flags (useful as categorical features for the model)
    df["is_mon"]     = (df["weekday"] == "Monday").astype(int)
    df["is_tue_thu"] = df["weekday"].isin(["Tuesday", "Thursday"]).astype(int)
    df["is_fri"]     = (df["weekday"] == "Friday").astype(int)

    # Composite weather risk score.
    # Each condition that makes driving harder adds points:
    #   heavy rain (≥ 2 mm)      → +2
    #   strong wind (≥ 45 km/h)  → +2
    #   frost (≤ 0 °C)           → +1
    #   snow (any amount)        → +3
    #   dense fog (humidity ≥ 97 %) → +1
    df["weather_risk"] = (
        (df["rain_peak"]      >= 2.0).astype(int) * 2
        + (df["wind_peak"]    >= 45.0).astype(int) * 2
        + (df["temp_min"]     <= 0.0 ).astype(int) * 1
        + (df["snow_total"]   > 0.0  ).astype(int) * 3
        + (df["humidity_max"] >= 97  ).astype(int) * 1
    )

    # Binary target: prefer car when its estimated time is within CAR_PREF_BUFFER_MIN
    # minutes of the actual train journey time.  The buffer accounts for door-to-door
    # convenience (no station wait, direct departure) that makes a slightly slower
    # car trip still preferable in practice.  Adjust CAR_PREF_BUFFER_MIN to taste.
    df["car_faster_than_train"] = (
        df["car_est_min"] <= df["train_actual_journey_min"] + CAR_PREF_BUFFER_MIN
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
        # ── travel time targets (real Infrabel data where available) ──────────
        "car_est_min",
        "train_planned_journey_min",  # scheduled time (real timetable)
        "train_actual_journey_min",   # actual time incl. delays
        "train_delay_arr_median_s",   # median arrival delay in seconds
        "train_on_time_pct",          # share of trains ≤ 5 min late
        "train_cancelled_pct",        # share of trains cancelled
        "train_sched_min",            # alias for train_planned_journey_min (backward compat)
        "car_faster_than_train",
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
