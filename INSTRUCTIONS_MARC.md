# Integrating a New Car Travel Time Dataset

**Route:** Gent-Sint-Pieters → Mechelen, morning commute arriving by 09:00  
**Contact:** check `data_pipeline.py` and `calibrate_factors.py` for all pipeline code

---

## 1. How car travel times work right now

We have **two car travel time columns** in the final dataset. Understanding the difference is important before plugging in new data.

### `car_vc_est_min` — PRIMARY column (used by the ML models)

This is the column the models actually use. It is built in three steps:

1. **Monthly base time** from Vlaams Verkeercentrum (VC) Excel files:
   - Files: `data/raw/reistijd*.xlsx`
   - Aggregated to: `data/processed/vc_travel_times.csv`
   - Format: `year`, `month`, `vc_car_base_min` (minutes, already reflecting real highway congestion)
   - Coverage: all months **except July and August** (VC only covers school-day traffic)

2. **Relative weekday adjustment** (loaded from `factors.json`):
   - Multiplies the monthly VC base by a per-weekday factor (mean = 1.0)
   - Example: Monday × 1.1156 means Monday is ~12% worse than average

3. **Weather adjustment** (loaded from `factors.json`):
   - Adds a fraction of the base time per active weather condition
   - Example: heavy rain (+12%), snow (+1.7%), severe frost (+4.3%), etc.

**Formula:**
```
car_vc_est_min = vc_base_for_that_month × weekday_rel_factor × weather_factor
```

### `car_est_min` — HISTORICAL / FALLBACK column

Uses the OSRM free-flow time (59.5 min, cached in `data/raw/osrm_route_gent_mechelen.json`) multiplied by **absolute** weekday and weather factors. This is used as a fallback for July/August (no VC data) and kept for backward compatibility. The models primarily use `car_vc_est_min`.

---

## 2. The combined dataset — full column reference

File: `data/processed/combined_workdays_features.csv`  
One row per Belgian working day (Mon–Fri, no public holidays), from 2021-01-04 to today.

| Column | Type | Description |
|--------|------|-------------|
| `date` | date | Working day (YYYY-MM-DD) |
| `weekday` | str | "Monday" … "Friday" |
| `weekday_num` | int | 0=Mon … 4=Fri |
| `month` | int | 1–12 |
| `year` | int | e.g. 2023 |
| `season` | str | Winter / Spring / Summer / Autumn |
| `is_school_holiday` | bool | True for July + August |
| `is_mon` | int | 1 if Monday |
| `is_tue_thu` | int | 1 if Tuesday or Thursday |
| `is_fri` | int | 1 if Friday |
| `rain_total` | float | Total rainfall 06–09h (mm) |
| `rain_peak` | float | Worst single-hour rain 06–09h (mm) |
| `wind_peak` | float | Peak wind 06–09h (km/h) |
| `wind_mean` | float | Mean wind 06–09h (km/h) |
| `temp_min` | float | Coldest hour 06–09h (°C) |
| `temp_mean` | float | Mean temperature 06–09h (°C) |
| `humidity_max` | float | Peak relative humidity 06–09h (%) |
| `snow_total` | float | Total snowfall 06–09h (cm) |
| `weather_risk` | int | Composite risk score 0–9 |
| **`car_vc_est_min`** | float | **PRIMARY car estimate (minutes)** |
| `car_est_min` | float | Historical car estimate via OSRM (minutes) |
| `train_planned_journey_min` | float | Scheduled train time (real timetable, minutes) |
| `train_actual_journey_min` | float | Actual train time incl. delays (minutes) |
| `train_delay_arr_median_s` | float | Median arrival delay (seconds) |
| `train_on_time_pct` | float | Share of trains ≤ 5 min late (0–1) |
| `train_cancelled_pct` | float | Share of trains cancelled (0–1) |
| `train_sched_min` | float | Alias of `train_planned_journey_min` |
| `car_faster_than_train` | int | Binary target: 1 if car is preferred |

---

## 3. Where to plug in new car data

Depending on what format Marc's dataset is in, there are two integration paths:

---

### Path A — Daily actual car travel times

**When to use:** Marc has per-day measured car travel times (GPS probes, floating car data, TomTom API, etc.).

**What to provide:**
```
date          car_actual_min
2021-01-04    68.5
2021-01-05    62.1
...
```
- `date`: format `YYYY-MM-DD`
- `car_actual_min`: total door-to-door travel time in minutes for the morning commute (06:00–09:00 window)

**How to integrate — `data_pipeline.py`, function `build_combined_df()`:**

1. Save the file as `data/raw/car_actual_daily.csv`

2. In `build_combined_df()`, after Step 8b (around line 1061), add:
```python
# ── Step 8c: load external daily car data (Marc's dataset) ──────────────
car_actual_path = RAW / "car_actual_daily.csv"
if car_actual_path.exists():
    df_car_actual = pd.read_csv(car_actual_path, parse_dates=["date"])
    df = df.merge(df_car_actual[["date", "car_actual_min"]], on="date", how="left")
    n_actual = df["car_actual_min"].notna().sum()
    print(f"[pipeline] External car data merged for {n_actual:,} days.")
else:
    df["car_actual_min"] = np.nan
```

3. Add `"car_actual_min"` to the `col_order` list at Step 11 (line 1150).

4. **To use it as the primary estimate**, change the `car_faster_than_train` logic:
```python
# Use actual car times where available, VC estimate as fallback
df["car_best_min"] = df["car_actual_min"].fillna(df["car_vc_est_min"])
df["car_faster_than_train"] = (
    df["car_best_min"] <= df["train_actual_journey_min"] + CAR_PREF_BUFFER_MIN
).astype(int)
```

---

### Path B — Monthly aggregate (same format as VC data)

**When to use:** Marc has a dataset that gives average car travel time per month (e.g., from ANPR cameras, AWV, or similar aggregated source).

**What to provide:**
```
year    month    car_base_min
2021    1        63.4
2021    2        61.8
...
```

**How to integrate — `data_pipeline.py`:**

Replace or supplement the VC lookup in Step 8b (around line 1049):

```python
# Load Marc's monthly data alongside VC
marc_path = RAW / "car_monthly_marc.csv"
if marc_path.exists():
    df_marc = pd.read_csv(marc_path)
    marc_lookup = df_marc.set_index(["year", "month"])["car_base_min"].to_dict()
else:
    marc_lookup = {}

def _vc_row(row):
    # Prefer Marc's data, fall back to VC, then fall back to OSRM
    base = marc_lookup.get((row["year"], row["month"])) \
        or vc_lookup.get((row["year"], row["month"]))
    if base is None:
        return row["car_est_min"]
    return car_vc_travel_time_estimate(row, base)
```

---

## 4. Recalibrate factors after adding new data

`calibrate_factors.py` derives **weekday and weather factors** from the real data. If Marc's dataset adds actual daily car travel times, those can **replace the Infrabel proxy** (which currently uses train delays scaled by ×2 to estimate car sensitivity). This would be a significant improvement.

**To use daily car data in calibration (`calibrate_factors.py`):**

At the top of the weekday section (around line 80), instead of using `train_delay_arr_median_s`, use `car_actual_min` grouped by weekday:

```python
# If you have a car_actual_daily.csv, load it here:
car_daily = pd.read_csv("data/raw/car_actual_daily.csv", parse_dates=["date"])
car_daily["weekday"] = car_daily["date"].dt.day_name()
wd_means = car_daily.groupby("weekday")["car_actual_min"].mean()
```

Then feed `wd_means` into the existing shift-then-normalise block that is already there.

For weather factors, merge car data with weather data on `date` and do the same grouped comparison (high-condition days vs clear days) that is already implemented using VC data — but now with actual per-day values instead of monthly averages.

After updating the calibration, always re-run:
```
python calibrate_factors.py      # re-derives factors.json
python data_pipeline.py          # rebuilds combined dataset
python model_training.py         # retrains models
python predict_scenarios.py      # regenerates scenario predictions
```

---

## 5. File locations summary

```
project root/
├── data_pipeline.py            ← main pipeline, edit build_combined_df() here
├── calibrate_factors.py        ← derives weekday + weather factors from real data
├── factors.json                ← output of calibrate_factors.py, read by pipeline
├── data/
│   ├── raw/
│   │   ├── reistijd*.xlsx      ← VC monthly car data (existing source)
│   │   ├── car_actual_daily.csv   ← DROP MARC'S DAILY DATA HERE (Path A)
│   │   └── car_monthly_marc.csv   ← DROP MARC'S MONTHLY DATA HERE (Path B)
│   └── processed/
│       ├── combined_workdays_features.csv  ← final dataset (rebuilt by pipeline)
│       └── vc_travel_times.csv             ← intermediate VC aggregation cache
```

---

## 6. Weather thresholds used in the model

The pipeline applies weather adjustments based on these thresholds (commute window 06–09h):

| Condition | Threshold | Factor applied |
|-----------|-----------|----------------|
| Rain light | `rain_peak >= 0.5 mm` | +2.98% on base time |
| Rain moderate | `rain_peak >= 2.0 mm` | +2.98% |
| Rain heavy | `rain_peak >= 5.0 mm` | +12.07% |
| Snow | `snow_total >= 1.0 cm` | +1.67% |
| Frost mild | `temp_min <= 0 °C` | +0.85% |
| Frost severe | `temp_min <= -3 °C` | +4.28% |
| Wind strong | `wind_peak >= 45 km/h` | +6.81% |
| Wind storm | `wind_peak >= 60 km/h` | +6.81% |

These are additive (multiple conditions stack). All values come from `factors.json` and were calibrated from real Infrabel + VC data.
