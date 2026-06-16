# Gent → Mechelen Commute Risk Forecast — Project Summary

> **Prepared for**: In-person presentation at Syntra Mechelen, 23/06/2026  
> **Team**: Laure, Jack, Maxime, Marc

---

## 1. Project Goal

We built a **machine-learning system that recommends the best way to commute from Gent to Mechelen**, arriving by 09:00.  
The model answers one daily question: **take the car, take the train, or work from home?**

The three options map directly to how most knowledge workers actually behave:
- **Auto (car)** — drive the E17 → R1 ring → E19 corridor (~75 km)
- **Trein (train)** — NMBS Gent-Sint-Pieters → Mechelen (1 transfer, ~58 min scheduled)
- **Thuiswerken (WFH)** — when neither mode is reliable enough

---

## 2. Why This Use Case?

The project guidelines asked us to predict traffic behaviour based on weather, calendar, and sensor data.  
We translated that into a **concrete operational problem** rather than a generic exercise:

| Requirement | Our answer |
|---|---|
| Real datasets | 6 separate sources, all publicly available |
| Classification of congestion | Weather risk score (0–9) + binary car-vs-train target |
| ML model | Random Forest (regression + classifier) + Linear Regression baseline |
| Business relevance | Daily departure-time advice, 50-scenario demonstration |
| Presentation demo | Live notebook with "Snelle Run" demo cell |

---

## 3. Team Division & Timeline

| Member | Responsibility |
|---|---|
| **Laure** | Assemble & analyse the car travel time dataset (Vlaams Verkeercentrum) |
| **Jack** | Assemble & analyse the train dataset (Infrabel punctuality history) |
| **Maxime** | Assemble & analyse weather data (Open-Meteo API) |
| **Marc** | Set up mockup project structure, subdivide tasks, coordinate pipeline |

**Agenda milestones:**

| Date | Milestone |
|---|---|
| 2026-05-26 | Full pipeline implemented: data fetching, decision logic, visualisations, presentation scripts |
| 2026-06-02 | Team meeting — task assignment, everyone understands the project |
| 2026-06-09 | Teams meeting — project running, aligned after GDPR exam break |
| 2026-06-16 | Teams meeting — final alignment, start presentation |
| **2026-06-23** | **DUE DATE — in-person presentation at Syntra Mechelen** |

---

## 4. Data Sources

We chose **six sources** to cover all dimensions of the commute decision.

### 4.1 Weather — Open-Meteo Archive API

- **URL**: `https://archive-api.open-meteo.com/v1/archive`
- **Coverage**: Hourly, 2021-01-01 → today, location: Mechelen (51.0281°N, 4.4803°E)
- **Why**: Completely free, no API key, hourly resolution back to 1940. Covers the exact arrival city.
- **Variables fetched**:
  - `temperature_2m` — air temperature (°C)
  - `precipitation` — rain + melted snow (mm)
  - `snowfall` — snowfall (cm)
  - `wind_speed_10m` — wind speed at 10 m height (km/h)
  - `relative_humidity_2m` — humidity (%, proxy for fog)
  - `weather_code` — WMO code (0 = clear, 61–67 = rain, 71–77 = snow, 95+ = storm)
- **Key insight**: Weather is aggregated over the **06:00–09:00 commute window only**. Overnight or afternoon weather does not affect the morning trip.

### 4.2 Belgian Workdays Calendar — `holidays` Python package

- **Why**: Weekends and public holidays have completely different traffic and train patterns — we filter them out entirely before modelling.
- **Coverage**: 2021–2028 (includes 2 future years for forecasting)
- **Fields created**:
  - `is_weekend`, `is_holiday`, `is_workday` (Mon–Fri AND not a public holiday)
  - `season` (meteorological: Winter/Spring/Summer/Autumn)
  - `is_school_holiday` (July + August — traffic is noticeably lighter on E17/E40)
- **Why exclude COVID period**: Data starts 2021 to avoid the 2020 lockdown distortion in traffic patterns.

### 4.3 Train Schedules — iRail API

- **URL**: `https://api.irail.be/connections/`
- **Why**: Free, open-source wrapper around the official NMBS/SNCB data feed. No registration needed.
- **Limitation**: iRail is real-time/near-future only — no multi-year delay history.
- **Usage**: Queried for the last 10 working days to get representative **scheduled journey times** (departure 06:30–09:00, Gent-Sint-Pieters → Mechelen). Used as a **fallback** when Infrabel data is unavailable.
- **Typical result**: ~58 minutes, 1 transfer.

### 4.4 Real Train Punctuality — Infrabel

- **Source**: `https://data.gov.be/en/organisations/infrabel`
- **Coverage**: Monthly files, 2021-01 → 2026-04 (48 months downloaded)
- **Why**: Unlike iRail, Infrabel publishes the **actual per-stop departure and arrival times** for every NMBS train, every day — true historical ground truth.
- **What we extract per month**:
  1. Filter rows for `GENT-SINT-PIETERS` departures between 06:00–08:59
  2. Join with `MECHELEN` arrivals on `(date, train_number)`
  3. Compute planned and actual journey times in minutes
  4. Flag cancellations (no real arrival data)
  5. Aggregate to **one row per calendar day** with:
     - `train_planned_journey_min` — median scheduled time
     - `train_actual_journey_min` — median actual time (including delays)
     - `train_delay_arr_median_s` — median arrival delay (seconds)
     - `train_on_time_pct` — share of trains arriving ≤ 5 min late
     - `train_cancelled_pct` — share of trains cancelled
- **Technical note**: Files are large (~hundreds of MB each). We download only the needed columns (`usecols`) to reduce memory by ~70%. Download is parallelised with `ThreadPoolExecutor` (4 workers).

### 4.5 Car Free-Flow Baseline — OSRM

- **URL**: `https://router.project-osrm.org/route/v1/driving/`
- **Why**: Open Source Routing Machine, built on OpenStreetMap. Free, no API key. Gives the theoretical minimum drive time (no traffic, speed limits respected).
- **Result**: ~75 km, ~50 min free-flow.
- **Usage**: Base value multiplied by weekday congestion factors and weather factors.
- **Role**: Historical reference column `car_est_min`. The primary car estimate is now the VC data (see below).

### 4.6 Real Car Travel Times — Vlaams Verkeercentrum

- **Source**: `https://indicatoren.verkeerscentrum.be/`
- **Format**: Excel files (`reistijd_*.xlsx`) downloaded manually
- **Coverage**: Monthly averages, school days only (July/August absent)
- **Why this route**: The E17 → R1 Antwerp ring → E19 via-Antwerp route is the actual fastest GPS route from Gent to Mechelen — not the direct E40, as the initial mockup assumed.
- **Road segments used**:
  1. E17/A14 (Gent → Antwerpen, richting Antwerpen)
  2. R1 buitenring (Antwerpen ring, richting Ring 2)
  3. E19/A1 (Antwerpen → Mechelen, richting Brussel)
- **Processing**: All segments summed per 5-minute time slot → average over 06:00–09:55 window → **monthly base travel time** (`vc_car_base_min`)
- **Role**: Primary source for `car_vc_est_min` (the main prediction target for car travel time)
- **Fallback**: For months without VC data (Jul/Aug), the OSRM estimate is used instead.

---

## 5. Data Pipeline (`data_pipeline.py`)

The pipeline runs all 6 sources through a **single function** (`build_combined_df()`) and outputs one CSV with one row per Belgian working day.

```
Open-Meteo API  ──→  fetch_weather()      ──→  hourly weather (2021–today)
holidays pkg    ──→  build_calendar()     ──→  daily workday flags
iRail API       ──→  fetch_train_schedule() ──→  scheduled journey times (fallback)
OSRM API        ──→  fetch_car_baseline()  ──→  free-flow distance & time
Infrabel files  ──→  fetch_infrabel_punctuality() ──→  per-day real train stats
VC Excel files  ──→  fetch_vc_travel_times() ──→  monthly car base times
                                              ↓
                    build_combined_df()  ──→  combined_workdays_features.csv
                                              ~1 000+ working days
```

**Caching strategy**: Every expensive API call saves its result to disk on first run. Subsequent runs load from cache — the entire pipeline takes < 1 second after the first run.

**Key derived columns produced**:

| Column | Formula / Logic |
|---|---|
| `rain_total` | Sum of precipitation (mm) 06–09h |
| `rain_peak` | Max single-hour precipitation (mm) 06–09h |
| `wind_peak` | Max wind gust (km/h) 06–09h |
| `snow_total` | Total snowfall (cm) 06–09h |
| `weather_risk` | Composite score 0–9: rain≥2mm (+2), wind≥45km/h (+2), frost (+1), snow (+3), humidity≥97% (+1) |
| `car_vc_est_min` | VC base × relative weekday factor × weather factor (capped 35–150 min) |
| `car_est_min` | OSRM × weekday congestion factor × weather factor (historical reference) |
| `car_faster_than_train` | 1 if `car_vc_est_min ≤ train_actual_journey_min + 10 min` buffer |

**Weekday congestion multipliers** (source: TomTom Traffic Index Belgium 2022–2024 + AWV morning-rush studies):

| Day | Factor | Reason |
|---|---|---|
| Monday | 1.28 | Traffic rebuilds after weekend |
| **Tuesday** | **1.35** | **Highest rush-hour pressure** |
| Wednesday | 1.20 | Lighter midweek |
| **Thursday** | **1.33** | Near-peak again |
| Friday | 1.15 | Lighter morning; heavier evening return |

**Weather factors** (multiplicative on top of base time):

| Condition | Factor added |
|---|---|
| Rain ≥ 5.0 mm/h | +12% |
| Rain ≥ 2.0 mm/h | +7% |
| Rain ≥ 0.5 mm/h | +3% |
| Snow ≥ 1 cm | +25% |
| Temperature ≤ −3°C | +15% |
| Temperature ≤ 0°C | +7% |
| Wind ≥ 60 km/h | +8% |
| Wind ≥ 45 km/h | +4% |

> **Why multiplicative?** Bad weather doesn't add a fixed delay — it scales with the base journey. A 10% slowdown on a 50-min trip costs 5 min; on a 90-min trip, 9 min.

---

## 6. Exploratory Data Analysis (`01_data_exploration_combined.ipynb`)

The notebook systematically explores each data source before combining them.

### 6.1 Weather EDA

- **5+ years of hourly data** (2021 → 2026): temperature, precipitation, wind, humidity, snowfall
- Key finding: **Winter and autumn months (Jan–Feb, Nov–Dec) show the highest rain probability and frost risk during commute hours** — these are the primary drivers of traffic delays.
- Key finding: **Weather is nearly uniform across weekdays** — Monday is not wetter than Friday. Day-of-week traffic patterns are driven by human behaviour (commuting patterns), not by weather.

Plots generated:
- `plot_weather_overview.png` — full 5-year time series
- `plot_commute_window_weather.png` — 06:00–09:00 window detail
- `plot_weather_by_weekday.png` — weather per weekday (confirms uniformity)

### 6.2 Calendar EDA

- **1 700+ calendar days** covered (2021–2028)
- Key finding: **May and November have the most public holidays** — those months have lighter commute pressure.
- School holidays (July + August) show noticeably lighter traffic on the VC data.

### 6.3 Train EDA (Infrabel)

- **48 months** of real punctuality data, Gent-Sint-Pieters → Mechelen, 06:00–09:00 window
- Key finding: **Tuesday and Thursday show the highest delays**, mirroring car congestion — both modes are stressed simultaneously on peak rush days.
- Overall on-time rate and cancellation rate tracked per month.

Plots generated:
- `plot_infrabel_overview.png` — delay distribution and monthly on-time rate
- `plot_infrabel_by_weekday.png` — delay patterns by weekday

### 6.4 Car EDA (OSRM + Vlaams Verkeercentrum)

- **OSRM**: Free-flow = ~50 min, but real rush-hour commute can reach 90–120+ min on bad days.
- **VC data**: Real average commute window travel times are significantly higher than OSRM free-flow, validating that the E17→R1→E19 route is the correct one.
- Key discovery: The original mockup used the E40 direct route. VC data confirmed the **E17 via Antwerp** is the realistic GPS route taken by commuters.

Plots generated:
- `plot_car_travel_model.png` — OSRM estimates with weekday/weather breakdown
- `plot_car_vs_train.png` — car vs. train comparison per weekday

### 6.5 Cross-Source EDA

- **Weather risk heatmap** (month × weekday): Jan–Feb and Nov–Dec show consistently higher risk; no single weekday stands out.
- **Car vs. train**: On a significant share of working days, the car (via VC estimate + buffer) is slower than the train — validating the relevance of the three-way recommendation.

Plot generated:
- `plot_weather_risk_heatmap.png` — weather risk by month × weekday

---

## 7. Machine Learning (`model_training.py`)

### 7.1 Features

15 features available at prediction time (all knowable the evening before):

| Feature | Type | Captures |
|---|---|---|
| `rain_total`, `rain_peak` | Weather | Rainfall intensity |
| `wind_peak`, `wind_mean` | Weather | Wind hazard |
| `temp_min`, `temp_mean` | Weather | Frost / ice risk |
| `humidity_max` | Weather | Fog probability |
| `snow_total` | Weather | Snow impact |
| `weekday_num` | Calendar | 0=Mon … 4=Fri |
| `month` | Calendar | Seasonality |
| `is_mon` | Calendar | Monday build-up |
| `is_tue_thu` | Calendar | Peak rush days |
| `is_fri` | Calendar | Lighter Friday |
| `is_school_holiday` | Calendar | Light traffic in Jul/Aug |
| `weather_risk` | Derived | Hand-crafted composite score |

### 7.2 Targets

Two separate models are trained:

| Model type | Target | Question answered |
|---|---|---|
| **Regression** | `car_est_min` | How many minutes will the car journey take? |
| **Classification** | `car_faster_than_train` | Should we take the car (1) or the train (0)? |

### 7.3 Train / Test Split

- **80% / 20% chronological split** (no shuffling — crucial for time-series data)
- Shuffling would allow the model to "see the future" during training, inflating test performance.
- Training set: 2021 → ~2025; Test set: ~2025 → 2026.

### 7.4 Models Trained

**Model 1 — Linear Regression (baseline)**
- Simplest possible model: `predicted_time = w1*feature1 + w2*feature2 + … + bias`
- Why start here: fast to train, interpretable coefficients, sets the benchmark.
- Coefficients directly show which features push travel time up or down.

**Model 2 — Random Forest Regressor**
- Builds 300 decision trees, each on a random data subset, averages predictions.
- Advantages over linear model: captures non-linear relationships (e.g. rain + frost = ice → much worse than either alone), handles feature interactions.
- Parameters: `n_estimators=300`, `min_samples_leaf=5`, `random_state=42`.

**Model 3 — Random Forest Classifier**
- Same structure as the regressor but outputs a binary class (car vs. train).
- Uses `class_weight="balanced"` to handle potential class imbalance.
- Outputs: class label + `predict_proba()` for confidence score.

### 7.5 Evaluation Metrics

| Metric | What it measures |
|---|---|
| MAE (Mean Absolute Error) | Average error in minutes — same unit as target |
| RMSE (Root Mean Squared Error) | Like MAE but penalises large errors more |
| R² | 1.0 = perfect, 0.0 = no better than predicting the mean |
| 5-fold cross-validation MAE | More reliable estimate of generalisation |
| Accuracy | Correct mode recommendations (car vs. train) |

**Business metrics** (most relevant for the use case):

| Business question | How we measure it |
|---|---|
| How often does the model pick the wrong mode? | `days_where_rf_picks_correct_mode` |
| Risk of arriving late at 09:00? | `late_risk = P(actual_time > predicted + 10min buffer)` |
| Average buffer at arrival? | `mean(predicted + buffer − actual)` |

### 7.6 Feature Importances (Random Forest)

The model's most influential features (impurity-based importance):
- **`weekday_num`** and rush-day flags (`is_tue_thu`, `is_mon`) typically dominate — the day of the week is the strongest predictor.
- **`month`** captures seasonal variation (winter = slower).
- **Weather features** (`rain_peak`, `wind_peak`, `snow_total`) add value on top of the calendar signal.
- `weather_risk` (composite score) provides the model a hand-crafted shortcut.

Saved to: `data/processed/model_evaluation.png` (6-panel plot: actual vs predicted, residuals, model comparison bar chart, feature importances, error by weekday).

---

## 8. Scenario Predictions (`predict_scenarios.py`)

50 hand-crafted realistic scenarios are run through the trained model to demonstrate the system's behaviour across a wide range of conditions:

- Every weekday (Monday–Friday)
- Good weather, moderate rain, heavy rain, snowstorm
- Black ice (frost without visible snow)
- School holidays vs. term time
- Public holiday (no commute)
- Early summer, late autumn, mid-winter
- Combination extremes (Monday + heavy rain, Tuesday + snow)

**Output per scenario**:
- `car_pred_min` — predicted car journey time (minutes)
- `mode_recommended` — auto / trein / thuiswerken
- `confidence_pct` — model confidence
- `departure_time` — latest departure to arrive at 09:00 with 10-min buffer
- `risk_label` — green / orange / red
- `advice` — human-readable Dutch explanation

**WFH trigger logic**: If `weather_risk ≥ 5` AND both car and train > 90 min → recommend working from home.

Saved to:
- `data/processed/scenario_predictions.csv`
- `data/processed/scenario_predictions.png` (horizontal bar chart, colour-coded by mode and risk)

---

## 9. Key Findings & Business Insights

1. **Tuesday and Thursday are the worst days to commute by car** — 35% and 33% above free-flow respectively.
2. **Snow has a disproportionate impact** (+25% travel time) — Belgium has limited snow-clearing capacity outside city centres.
3. **Weather is the same on all weekdays** — traffic differences between Mon–Fri are entirely human-driven (commuting patterns), not weather-driven.
4. **The train is competitive** — on a meaningful share of working days, the VC-measured car time (+ 10-min preference buffer) makes the train the better choice.
5. **January–February and November–December** are the highest-risk months for commuting by either mode.
6. **School holidays (July–August) are outliers** — traffic is significantly lighter; the VC dataset excludes those months entirely.
7. **The correct route is E17 → R1 → E19 via Antwerp** — not the direct E40. This was confirmed by comparing OSRM (which defaulted to E40) with the VC route definitions.

---

## 10. Project Structure

```
trafic_forecast_datascience/
├── data_pipeline.py              # Fetches all data, builds combined CSV
├── model_training.py             # Trains and evaluates all 3 models
├── predict_scenarios.py          # 50-scenario demonstration
├── 01_data_exploration_combined.ipynb  # EDA notebook (all 6 sources)
├── gent_mechelen_commute_risk_forecast.ipynb  # Main notebook + presentation scripts
├── README.MD                     # Project overview
├── WORKLOG.md                    # Development log (Dutch)
├── requirements.txt              # Python dependencies
└── data/
    ├── raw/
    │   ├── weather_mechelen_hourly.csv      # Open-Meteo cache
    │   ├── calendar_be.csv                  # Belgian holiday calendar
    │   ├── irail_connections_sample.csv     # iRail train schedules
    │   ├── osrm_route_gent_mechelen.json    # OSRM car route
    │   ├── reistijd_*.xlsx                  # Vlaams Verkeercentrum files (7)
    │   └── infrabel/                        # 48 monthly processed train files
    └── processed/
        ├── combined_workdays_features.csv   # Main ML dataset (~1000+ rows)
        ├── infrabel_daily_commute.csv       # Aggregated real train data
        ├── vc_travel_times.csv              # Monthly VC car base times
        ├── model_results_summary.csv        # Model metrics
        ├── scenario_predictions.csv         # 50-scenario outputs
        ├── model_evaluation.png             # 6-panel evaluation plot
        ├── scenario_predictions.png         # Scenario bar chart
        └── plot_*.png                       # EDA visualisations (11 files)
```

---

## 11. How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Step 1: Build the dataset (fetches APIs, processes Infrabel + VC files)
python data_pipeline.py

# Step 2: Train models and evaluate
python model_training.py

# Step 3: Generate 50-scenario demonstration
python predict_scenarios.py

# Interactive exploration
jupyter notebook 01_data_exploration_combined.ipynb
jupyter notebook gent_mechelen_commute_risk_forecast.ipynb
```

All scripts include auto-install for missing packages and aggressive caching — safe to re-run multiple times.

---

## 12. Choices We Made and Why

| Decision | Alternative considered | Reason for our choice |
|---|---|---|
| Start data from 2021 | 2019 or 2020 | COVID lockdowns in 2020 distort traffic patterns — not representative of normal commuting |
| Via-Antwerp route (E17→R1→E19) | Direct E40 route | VC data is published per segment; E17→R1→E19 is what Google Maps / GPS actually recommends for this trajectory |
| Open-Meteo over IRM/KMI | Belgian national weather API | Open-Meteo is free, no key, hourly data back to 1940. IRM/KMI only had forecast endpoints in the used client |
| Infrabel over iRail for history | iRail API only | iRail has no multi-year delay history — Infrabel publishes the actual ground truth per stop per train |
| 10-minute car preference buffer | Strict fastest-wins | Accounts for door-to-door convenience vs. waiting on a platform; makes car recommendations more realistic |
| Random Forest over XGBoost / neural nets | More complex models | RF is interpretable (feature importances), robust without tuning, and the dataset size (1000 rows) does not justify deep learning |
| 80/20 chronological split (no shuffle) | Random split | Time-series data must be split in order — shuffling lets the model "see the future" during training |
| WFH as 3rd option | Binary car/train | Adds real-world realism; extreme weather + slow both modes = clear WFH signal |
