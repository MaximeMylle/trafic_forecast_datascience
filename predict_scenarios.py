"""
predict_scenarios.py
====================
Uses the trained model from model_training.py to make predictions for
50 hand-crafted scenarios.  Each scenario is a realistic situation that
a commuter might face on the Gent → Mechelen route.

Scenarios are designed to cover a wide range of conditions:
  - Every weekday (Monday–Friday)
  - Good weather, bad weather, very bad weather
  - Snow and black ice
  - School holidays vs term time
  - A public holiday (no commute needed)
  - Storm conditions
  - Early summer, late autumn, mid winter
  - Combination cases (e.g. Monday + heavy rain)

Run with:
    python predict_scenarios.py

This file imports build_combined_df from data_pipeline.py to refit the
model on fresh data, then applies it to each scenario.
"""

# ─── Standard library ────────────────────────────────────────────────────────
import subprocess
import sys
from datetime import date, timedelta

# ─── Auto-install missing packages ───────────────────────────────────────────
_REQUIRED = ["numpy", "pandas", "matplotlib", "scikit-learn"]
for _pkg in _REQUIRED:
    _import_name = "sklearn" if _pkg == "scikit-learn" else _pkg
    try:
        __import__(_import_name)
    except ImportError:
        print(f"[setup] Installing {_pkg} …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", _pkg],
                              stdout=subprocess.DEVNULL)

# ─── Third-party ─────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines

# scikit-learn — we retrain here so this file is self-contained
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split

# ─── Our own pipeline ────────────────────────────────────────────────────────
# This import fetches (or loads from cache) the full historical dataset
from data_pipeline import build_combined_df, WEEKDAY_CONGESTION, CAR_PREF_BUFFER_MIN


# =============================================================================
# 1. LOAD DATA AND RE-TRAIN THE MODEL
# =============================================================================

print("Loading dataset and training model …")

df = build_combined_df()

# Feature columns (must match exactly what model_training.py uses)
FEATURE_COLS = [
    "rain_total", "rain_peak", "wind_peak", "wind_mean",
    "temp_min", "temp_mean", "humidity_max", "snow_total",
    "weekday_num", "month",
    "is_mon", "is_tue_thu", "is_fri",
    "is_school_holiday", "weather_risk",
]

X   = df[FEATURE_COLS].values
y_r = df["car_est_min"].values          # regression target: car travel time
y_c = df["car_faster_than_train"].values  # classification target

# Use the same 80/20 chronological split as in model_training.py.
# train_test_split with 3 arrays returns 6 values:
#   X_train, X_test, yr_train, yr_test, yc_train, yc_test
# We only need the training halves to refit the models here.
X_train, _X_test, yr_train, _yr_test, yc_train, _yc_test = train_test_split(
    X, y_r, y_c, test_size=0.20, shuffle=False, random_state=42
)

# Train the Random Forest models (same settings as model_training.py)
rf_reg = RandomForestRegressor(
    n_estimators=300, max_depth=None, min_samples_leaf=5,
    random_state=42, n_jobs=-1
)
rf_clf = RandomForestClassifier(
    n_estimators=300, max_depth=None, min_samples_leaf=5,
    random_state=42, n_jobs=-1, class_weight="balanced"
)
rf_reg.fit(X_train, yr_train)
rf_clf.fit(X_train, yc_train)

# Median scheduled train time from the dataset
TRAIN_SCHED_MIN = float(df["train_sched_min"].iloc[0])
BUFFER_MIN      = 10   # safety buffer added to departure time

print(f"Model trained on {len(X_train):,} working days.")
print(f"Train scheduled time: {TRAIN_SCHED_MIN:.0f} min")
print(f"Departure buffer: {BUFFER_MIN} min\n")


# =============================================================================
# 2. PREDICTION HELPER
# =============================================================================

def predict_scenario(scenario: dict) -> dict:
    """
    Run a single scenario through both models and return a full recommendation.

    Parameters
    ----------
    scenario : dict with at minimum:
        name, description, weekday_num (0=Mon…4=Fri), month,
        rain_total, rain_peak, wind_peak, wind_mean,
        temp_min, temp_mean, humidity_max, snow_total,
        is_school_holiday, is_public_holiday (bool, used only for labelling)

    Returns
    -------
    dict with all input fields plus model outputs:
        car_pred_min, mode_recommended, confidence_pct,
        departure_time, risk_label, advice
    """
    # ── if it is a public holiday, there is no commute ──
    if scenario.get("is_public_holiday", False):
        return {**scenario,
                "car_pred_min":     None,
                "mode_recommended": "thuiswerken",
                "confidence_pct":   100.0,
                "departure_time":   "n.v.t.",
                "risk_label":       "groen",
                "advice":           "Feestdag — geen woon-werkverkeer nodig."}

    # ── derive weekday flags from weekday_num ──
    wd = int(scenario["weekday_num"])
    features = {
        "rain_total":        scenario.get("rain_total", 0),
        "rain_peak":         scenario.get("rain_peak", 0),
        "wind_peak":         scenario.get("wind_peak", 0),
        "wind_mean":         scenario.get("wind_mean", 0),
        "temp_min":          scenario.get("temp_min", 10),
        "temp_mean":         scenario.get("temp_mean", 13),
        "humidity_max":      scenario.get("humidity_max", 80),
        "snow_total":        scenario.get("snow_total", 0),
        "weekday_num":       wd,
        "month":             int(scenario["month"]),
        "is_mon":            int(wd == 0),
        "is_tue_thu":        int(wd in [1, 3]),
        "is_fri":            int(wd == 4),
        "is_school_holiday": int(scenario.get("is_school_holiday", False)),
        # compute the composite weather risk score the same way as the pipeline
        "weather_risk": (
            int(scenario.get("rain_peak",  0) >= 2.0) * 2
            + int(scenario.get("wind_peak", 0) >= 45.0) * 2
            + int(scenario.get("temp_min",  10) <= 0.0) * 1
            + int(scenario.get("snow_total", 0) > 0.0)  * 3
            + int(scenario.get("humidity_max", 80) >= 97) * 1
        ),
    }

    X_row = np.array([[features[col] for col in FEATURE_COLS]])

    car_pred  = float(rf_reg.predict(X_row)[0])
    mode_bin  = int(rf_clf.predict(X_row)[0])     # 1 = car faster

    # predict_proba may return only 1 column when the classifier only saw one
    # class during training (e.g. car is almost always faster on this route).
    proba_matrix = rf_clf.predict_proba(X_row)
    if proba_matrix.shape[1] == 1:
        only_class = int(rf_clf.classes_[0])
        mode_prob  = float(only_class)   # certainty: 1.0 if car always faster
    else:
        mode_prob  = float(proba_matrix[0, 1])  # P(car faster)

    # ── decide recommended mode ──
    risk = features["weather_risk"]
    if risk >= 5 and min(car_pred, TRAIN_SCHED_MIN) >= 90:
        # extreme conditions AND both modes are very slow → work from home
        recommended = "thuiswerken"
        confidence  = 90.0
    elif mode_bin == 1:
        recommended = "auto"
        confidence  = mode_prob * 100
    else:
        recommended = "trein"
        confidence  = (1 - mode_prob) * 100

    # ── compute departure time ──
    if recommended == "auto":
        dep_min = 9 * 60 - (car_pred + BUFFER_MIN)
        dep_str = f"{int(dep_min) // 60:02d}:{int(dep_min) % 60:02d}"
    elif recommended == "trein":
        dep_min = 9 * 60 - (TRAIN_SCHED_MIN + BUFFER_MIN)
        dep_str = f"{int(dep_min) // 60:02d}:{int(dep_min) % 60:02d}"
    else:
        dep_str = "n.v.t."

    # ── risk label for colour coding ──
    if risk >= 5 or car_pred >= 90:
        risk_label = "rood"
    elif risk >= 2 or car_pred >= 75:
        risk_label = "oranje"
    else:
        risk_label = "groen"

    # ── short human-readable advice ──
    reasons = []
    if scenario.get("snow_total", 0) > 0:
        reasons.append("sneeuw verwacht")
    if scenario.get("temp_min", 10) <= 0:
        reasons.append("vorst / ijzel mogelijk")
    if scenario.get("rain_peak", 0) >= 5:
        reasons.append("zware neerslag")
    elif scenario.get("rain_peak", 0) >= 2:
        reasons.append("matige neerslag")
    if scenario.get("wind_peak", 0) >= 60:
        reasons.append("stormwind")
    elif scenario.get("wind_peak", 0) >= 45:
        reasons.append("sterke wind")
    if wd in [1, 3]:
        reasons.append("spitspiek di/do")
    if wd == 0:
        reasons.append("maandagochtend opstopping")
    if scenario.get("is_school_holiday", False):
        reasons.append("schoolvakantie (licht verkeer)")
    if not reasons:
        reasons.append("stabiele omstandigheden")

    advice = f"{recommended.upper()} — {'; '.join(reasons)}. Vertrek: {dep_str} voor aankomst 09:00."

    return {
        **scenario,
        "weather_risk":     risk,
        "car_pred_min":     round(car_pred, 1),
        "mode_recommended": recommended,
        "confidence_pct":   round(confidence, 1),
        "departure_time":   dep_str,
        "risk_label":       risk_label,
        "advice":           advice,
    }


def minutes_to_hhmm(total_min: float) -> str:
    h, m = divmod(int(round(total_min)), 60)
    return f"{h:02d}:{m:02d}"


# =============================================================================
# 3. DEFINE 20 SCENARIOS
# =============================================================================

# Each scenario is a dict describing one hypothetical commute day.
# Fields that are not specified default to mild/neutral values inside
# predict_scenario().

SCENARIOS = [
    # ── 1. Perfect conditions — Friday in May ─────────────────────────────────
    {
        "name":        "1. Ideale vrijdag",
        "description": "Droge, zachte vrijdag in mei. Geen neerslag, lichte wind.",
        "weekday_num": 4,    # Friday
        "month":       5,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   12.0, "wind_mean": 7.0,
        "temp_min":    12.0, "temp_mean": 17.0,
        "humidity_max": 65.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 2. Typical Tuesday rush ───────────────────────────────────────────────
    {
        "name":        "2. Typische dinsdag",
        "description": "Rustig weer, maar het is dinsdag — drukste spitsdag.",
        "weekday_num": 1,    # Tuesday
        "month":       3,
        "rain_total":  0.2, "rain_peak": 0.1,
        "wind_peak":   18.0, "wind_mean": 10.0,
        "temp_min":    7.0,  "temp_mean": 11.0,
        "humidity_max": 75.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 3. Heavy rain on Monday ───────────────────────────────────────────────
    {
        "name":        "3. Maandag + zware regen",
        "description": "Maandag in oktober. Flinke regenbuien tijdens het pendelen.",
        "weekday_num": 0,    # Monday
        "month":       10,
        "rain_total":  8.5, "rain_peak": 5.2,
        "wind_peak":   35.0, "wind_mean": 22.0,
        "temp_min":    9.0,  "temp_mean": 12.0,
        "humidity_max": 95.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 4. Snow day in January ────────────────────────────────────────────────
    {
        "name":        "4. Sneeuwdag januari",
        "description": "Sneeuwval in de nacht en vroege ochtend. Gladde wegen.",
        "weekday_num": 2,    # Wednesday
        "month":       1,
        "rain_total":  2.0, "rain_peak": 0.8,
        "wind_peak":   25.0, "wind_mean": 15.0,
        "temp_min":    -2.0, "temp_mean": -0.5,
        "humidity_max": 98.0, "snow_total": 4.5,
        "is_school_holiday": False,
    },
    # ── 5. Black ice — frost but no snow ─────────────────────────────────────
    {
        "name":        "5. IJzel / zwart ijs",
        "description": "Nacht van vriezing, geen neerslag maar wegen bevroren.",
        "weekday_num": 3,    # Thursday
        "month":       2,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   10.0, "wind_mean": 6.0,
        "temp_min":    -4.0, "temp_mean": -1.5,
        "humidity_max": 92.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 6. Storm — wind gusts above 80 km/h ───────────────────────────────────
    {
        "name":        "6. Stormdag (code rood)",
        "description": "Stormwaarschuwing KMI. Windstoten boven 80 km/h.",
        "weekday_num": 1,    # Tuesday
        "month":       11,
        "rain_total":  5.0, "rain_peak": 3.5,
        "wind_peak":   85.0, "wind_mean": 55.0,
        "temp_min":    8.0,  "temp_mean": 10.0,
        "humidity_max": 96.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 7. Summer school holiday — light traffic ──────────────────────────────
    {
        "name":        "7. Zomervakantie — rustig",
        "description": "Augustus, iedereen op vakantie. Wegen zijn leeg.",
        "weekday_num": 2,    # Wednesday
        "month":       8,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   15.0, "wind_mean": 8.0,
        "temp_min":    18.0, "temp_mean": 24.0,
        "humidity_max": 60.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 8. Summer school holiday + thunderstorm ────────────────────────────────
    {
        "name":        "8. Zomervakantie + onweer",
        "description": "Augustus maar met een fikse zomerstorm in de ochtend.",
        "weekday_num": 0,    # Monday
        "month":       7,
        "rain_total":  12.0, "rain_peak": 7.0,
        "wind_peak":   55.0, "wind_mean": 30.0,
        "temp_min":    16.0, "temp_mean": 20.0,
        "humidity_max": 98.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 9. Public holiday (Wapenstilstand 11 nov) ─────────────────────────────
    {
        "name":        "9. Wapenstilstand (feestdag)",
        "description": "11 november — Belgische feestdag. Niet pendelen.",
        "weekday_num": 0,    # Monday (hypothetical)
        "month":       11,
        "rain_total":  1.0, "rain_peak": 0.5,
        "wind_peak":   20.0, "wind_mean": 12.0,
        "temp_min":    5.0,  "temp_mean": 9.0,
        "humidity_max": 85.0, "snow_total": 0.0,
        "is_school_holiday": False,
        "is_public_holiday": True,   # ← model skips prediction, returns 'thuiswerken'
    },
    # ── 10. Mild autumn Thursday ─────────────────────────────────────────────
    {
        "name":        "10. Milde donderdag herfst",
        "description": "September, aangenaam weer, lichte wind.",
        "weekday_num": 3,    # Thursday
        "month":       9,
        "rain_total":  0.5, "rain_peak": 0.3,
        "wind_peak":   20.0, "wind_mean": 11.0,
        "temp_min":    10.0, "temp_mean": 16.0,
        "humidity_max": 78.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 11. Drizzle + Friday commute ─────────────────────────────────────────
    {
        "name":        "11. Vrijdag + motregen",
        "description": "Lichte motregen op vrijdag. Verkeer redelijk vlot.",
        "weekday_num": 4,    # Friday
        "month":       4,
        "rain_total":  1.2, "rain_peak": 0.8,
        "wind_peak":   22.0, "wind_mean": 14.0,
        "temp_min":    9.0,  "temp_mean": 12.0,
        "humidity_max": 88.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 12. Classic winter Wednesday ─────────────────────────────────────────
    {
        "name":        "12. Grijze decemberwoensdag",
        "description": "Typische grijze wintersdag in december, geen extremen.",
        "weekday_num": 2,    # Wednesday
        "month":       12,
        "rain_total":  2.0, "rain_peak": 1.1,
        "wind_peak":   28.0, "wind_mean": 17.0,
        "temp_min":    3.0,  "temp_mean": 5.0,
        "humidity_max": 92.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 13. Monday after a long weekend ──────────────────────────────────────
    {
        "name":        "13. Maandag na lang weekend",
        "description": "Eerste werkdag na 4-daags weekend. Iedereen terug op kantoor.",
        "weekday_num": 0,    # Monday
        "month":       5,
        "rain_total":  0.3, "rain_peak": 0.2,
        "wind_peak":   15.0, "wind_mean": 9.0,
        "temp_min":    11.0, "temp_mean": 17.0,
        "humidity_max": 70.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 14. Dense fog + frost ─────────────────────────────────────────────────
    {
        "name":        "14. Dichte mist + vorst",
        "description": "Novemberochtend met dichte mist en berijpte wegen.",
        "weekday_num": 1,    # Tuesday
        "month":       11,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   5.0,  "wind_mean": 2.0,
        "temp_min":    -1.0, "temp_mean": 1.0,
        "humidity_max": 99.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 15. Spring Tuesday — best regular commute day ─────────────────────────
    {
        "name":        "15. Lente dinsdag (zonnig)",
        "description": "Zonnige aprildag, maar het is dinsdag (spitspiek).",
        "weekday_num": 1,    # Tuesday
        "month":       4,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   18.0, "wind_mean": 10.0,
        "temp_min":    8.0,  "temp_mean": 15.0,
        "humidity_max": 65.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 16. Heavy snow blizzard ────────────────────────────────────────────────
    {
        "name":        "16. Sneeuwstorm (code rood)",
        "description": "Zware sneeuwstorm, 10 cm sneeuw verwacht. E40 mogelijk dicht.",
        "weekday_num": 3,    # Thursday
        "month":       1,
        "rain_total":  4.0, "rain_peak": 2.0,
        "wind_peak":   50.0, "wind_mean": 35.0,
        "temp_min":    -5.0, "temp_mean": -3.0,
        "humidity_max": 99.0, "snow_total": 10.0,
        "is_school_holiday": False,
    },
    # ── 17. Hot summer Friday with AC traffic ────────────────────────────────
    {
        "name":        "17. Hittegolf vrijdag",
        "description": "Hittegolf, 35°C verwacht. Verkeersdruk normaal.",
        "weekday_num": 4,    # Friday
        "month":       7,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   10.0, "wind_mean": 5.0,
        "temp_min":    24.0, "temp_mean": 33.0,
        "humidity_max": 45.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 18. Wednesday in Easter school holiday ───────────────────────────────
    {
        "name":        "18. Paasvakantie woensdag",
        "description": "Paasvakantie, licht verkeer op de E40.",
        "weekday_num": 2,    # Wednesday
        "month":       4,
        "rain_total":  0.8, "rain_peak": 0.4,
        "wind_peak":   20.0, "wind_mean": 12.0,
        "temp_min":    9.0,  "temp_mean": 14.0,
        "humidity_max": 75.0, "snow_total": 0.0,
        "is_school_holiday": True,   # Easter counts as school holiday
    },
    # ── 19. Monday after New Year ─────────────────────────────────────────────
    {
        "name":        "19. Maandag na Nieuwjaar",
        "description": "Eerste werkmaandag van het jaar. Iedereen terug na kerstvakantie.",
        "weekday_num": 0,    # Monday
        "month":       1,
        "rain_total":  3.5, "rain_peak": 2.0,
        "wind_peak":   38.0, "wind_mean": 22.0,
        "temp_min":    2.0,  "temp_mean": 5.0,
        "humidity_max": 93.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 20. Calm Thursday in October ─────────────────────────────────────────
    {
        "name":        "20. Rustige donderdag oktober",
        "description": "Bewolkt maar droog. Geen bijzonderheden.",
        "weekday_num": 3,    # Thursday
        "month":       10,
        "rain_total":  0.1, "rain_peak": 0.0,
        "wind_peak":   16.0, "wind_mean": 9.0,
        "temp_min":    8.0,  "temp_mean": 13.0,
        "humidity_max": 80.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 21. Krokusvakantie maandag ────────────────────────────────────────────
    {
        "name":        "21. Krokusvakantie maandag",
        "description": "Krokusvakantie. Scholen dicht — wegen opvallend leeg.",
        "weekday_num": 0,    # Monday
        "month":       2,
        "rain_total":  0.2, "rain_peak": 0.1,
        "wind_peak":   14.0, "wind_mean": 8.0,
        "temp_min":    3.0,  "temp_mean": 7.0,
        "humidity_max": 72.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 22. Natte januaridinsdag ──────────────────────────────────────────────
    {
        "name":        "22. Natte januaridinsdag",
        "description": "Matige regen + spits op dinsdag. Vertraging bijna zeker.",
        "weekday_num": 1,    # Tuesday
        "month":       1,
        "rain_total":  4.5, "rain_peak": 2.8,
        "wind_peak":   30.0, "wind_mean": 18.0,
        "temp_min":    4.0,  "temp_mean": 7.0,
        "humidity_max": 93.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 23. Warme junidinsdag ─────────────────────────────────────────────────
    {
        "name":        "23. Warme junidinsdag",
        "description": "Begin juni, warm en droog. Geen vakantie, normale spits.",
        "weekday_num": 1,    # Tuesday
        "month":       6,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   16.0, "wind_mean": 9.0,
        "temp_min":    14.0, "temp_mean": 22.0,
        "humidity_max": 58.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 24. Stormachtige novemberwoensdag ─────────────────────────────────────
    {
        "name":        "24. Stormachtige novemberwoensdag",
        "description": "Trekgolf boven België. Windstoten 65 km/h, matige regen.",
        "weekday_num": 2,    # Wednesday
        "month":       11,
        "rain_total":  6.0, "rain_peak": 3.8,
        "wind_peak":   68.0, "wind_mean": 42.0,
        "temp_min":    7.0,  "temp_mean": 10.0,
        "humidity_max": 96.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 25. Koude decemberdinsdag ─────────────────────────────────────────────
    {
        "name":        "25. Koude decemberdinsdag",
        "description": "Koud en helder. Vorst 's ochtends, spitspiek dinsdag.",
        "weekday_num": 1,    # Tuesday
        "month":       12,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   12.0, "wind_mean": 7.0,
        "temp_min":    -2.0, "temp_mean": 1.0,
        "humidity_max": 88.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 26. Herfstvakantie donderdag ──────────────────────────────────────────
    {
        "name":        "26. Herfstvakantie donderdag",
        "description": "Oktober herfstvakantie. Mild, lichte bries. Wegen rustig.",
        "weekday_num": 3,    # Thursday
        "month":       10,
        "rain_total":  0.8, "rain_peak": 0.4,
        "wind_peak":   18.0, "wind_mean": 10.0,
        "temp_min":    8.0,  "temp_mean": 13.0,
        "humidity_max": 76.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 27. Aprilbui woensdag ─────────────────────────────────────────────────
    {
        "name":        "27. Aprilbui woensdag",
        "description": "Typische aprilbui met matige neerslag. Normale files.",
        "weekday_num": 2,    # Wednesday
        "month":       4,
        "rain_total":  3.5, "rain_peak": 2.2,
        "wind_peak":   26.0, "wind_mean": 15.0,
        "temp_min":    8.0,  "temp_mean": 12.0,
        "humidity_max": 91.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 28. Vakantievrijdag augustus ──────────────────────────────────────────
    {
        "name":        "28. Vakantievrijdag augustus",
        "description": "Augustus, warm, droog. Schoolvakantie — weinig verkeer.",
        "weekday_num": 4,    # Friday
        "month":       8,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   13.0, "wind_mean": 7.0,
        "temp_min":    19.0, "temp_mean": 26.0,
        "humidity_max": 55.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 29. Mistige septemberdinsdag ──────────────────────────────────────────
    {
        "name":        "29. Mistige septemberdinsdag",
        "description": "Ochtendmist, hoge vochtigheid. Zicht beperkt + spitspiek.",
        "weekday_num": 1,    # Tuesday
        "month":       9,
        "rain_total":  0.3, "rain_peak": 0.1,
        "wind_peak":   8.0,  "wind_mean": 3.0,
        "temp_min":    8.0,  "temp_mean": 14.0,
        "humidity_max": 99.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 30. Koude regenachtige maandag maart ──────────────────────────────────
    {
        "name":        "30. Koude regenachtige maandag",
        "description": "Maandag in maart. Regen + koude + maandagspits.",
        "weekday_num": 0,    # Monday
        "month":       3,
        "rain_total":  5.0, "rain_peak": 3.0,
        "wind_peak":   35.0, "wind_mean": 22.0,
        "temp_min":    3.0,  "temp_mean": 6.0,
        "humidity_max": 94.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 31. Lichte sneeuw vrijdag ─────────────────────────────────────────────
    {
        "name":        "31. Lichte sneeuw vrijdag",
        "description": "Vluchtige sneeuwbui. 1-2 cm verwacht. Vrijdag = lichtste spits.",
        "weekday_num": 4,    # Friday
        "month":       3,
        "rain_total":  1.0, "rain_peak": 0.5,
        "wind_peak":   18.0, "wind_mean": 10.0,
        "temp_min":    -1.0, "temp_mean": 0.5,
        "humidity_max": 95.0, "snow_total": 1.5,
        "is_school_holiday": False,
    },
    # ── 32. Terug na kerstvakantie — donderdag ────────────────────────────────
    {
        "name":        "32. Terug na kerstvakantie",
        "description": "Eerste donderdag na Nieuwjaar. Iedereen terug op kantoor.",
        "weekday_num": 3,    # Thursday
        "month":       1,
        "rain_total":  2.5, "rain_peak": 1.5,
        "wind_peak":   32.0, "wind_mean": 20.0,
        "temp_min":    2.0,  "temp_mean": 5.0,
        "humidity_max": 90.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 33. Tropische vakantiedinsdag ─────────────────────────────────────────
    {
        "name":        "33. Tropische vakantiedinsdag",
        "description": "Augustus, 33°C, schoolvakantie. Wegen rustig ondanks warmte.",
        "weekday_num": 1,    # Tuesday
        "month":       8,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   14.0, "wind_mean": 8.0,
        "temp_min":    22.0, "temp_mean": 31.0,
        "humidity_max": 48.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 34. Winderige novembermaandag ─────────────────────────────────────────
    {
        "name":        "34. Winderige novembermaandag",
        "description": "Flinke wind maar nauwelijks regen. Maandagspits actief.",
        "weekday_num": 0,    # Monday
        "month":       11,
        "rain_total":  0.5, "rain_peak": 0.3,
        "wind_peak":   52.0, "wind_mean": 33.0,
        "temp_min":    7.0,  "temp_mean": 11.0,
        "humidity_max": 83.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 35. Kerstvakantie vrijdag ─────────────────────────────────────────────
    {
        "name":        "35. Kerstvakantie vrijdag",
        "description": "Kerstvakantie. Scholen dicht, wegen rustig, mild weer.",
        "weekday_num": 4,    # Friday
        "month":       12,
        "rain_total":  1.0, "rain_peak": 0.6,
        "wind_peak":   18.0, "wind_mean": 11.0,
        "temp_min":    4.0,  "temp_mean": 7.0,
        "humidity_max": 85.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 36. Mist + lichte regen dinsdag ──────────────────────────────────────
    {
        "name":        "36. Mist + lichte regen dinsdag",
        "description": "Laaghangende bewolking, mist, lichte drizzle. Spitspiek.",
        "weekday_num": 1,    # Tuesday
        "month":       3,
        "rain_total":  1.5, "rain_peak": 0.9,
        "wind_peak":   14.0, "wind_mean": 7.0,
        "temp_min":    4.0,  "temp_mean": 7.0,
        "humidity_max": 99.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 37. Koude zonnige woensdag februari ───────────────────────────────────
    {
        "name":        "37. Koude zonnige woensdag",
        "description": "Helder maar koud. Wegen droog, mogelijk rijp 's ochtends.",
        "weekday_num": 2,    # Wednesday
        "month":       2,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   10.0, "wind_mean": 5.0,
        "temp_min":    -3.0, "temp_mean": 2.0,
        "humidity_max": 82.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 38. Warmste lentedag donderdag mei ────────────────────────────────────
    {
        "name":        "38. Warmste lentedag donderdag",
        "description": "Mooiste dag van het jaar tot nu. Warm, zon, spitspiek do.",
        "weekday_num": 3,    # Thursday
        "month":       5,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   16.0, "wind_mean": 9.0,
        "temp_min":    12.0, "temp_mean": 22.0,
        "humidity_max": 60.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 39. Zware herfstbui maandag oktober ───────────────────────────────────
    {
        "name":        "39. Zware herfstbui maandag",
        "description": "Oktober. Zware regenbuien tijdens de maandagspits.",
        "weekday_num": 0,    # Monday
        "month":       10,
        "rain_total":  9.0, "rain_peak": 5.5,
        "wind_peak":   38.0, "wind_mean": 24.0,
        "temp_min":    8.0,  "temp_mean": 12.0,
        "humidity_max": 97.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 40. Zomerse vakantiewoensdag juli ─────────────────────────────────────
    {
        "name":        "40. Zomerse vakantiewoensdag",
        "description": "Juli, schoolvakantie. Warm, bewolkt maar droog.",
        "weekday_num": 2,    # Wednesday
        "month":       7,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   17.0, "wind_mean": 10.0,
        "temp_min":    16.0, "temp_mean": 24.0,
        "humidity_max": 62.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 41. Koude februarimaandag ─────────────────────────────────────────────
    {
        "name":        "41. Koude februarimaandag",
        "description": "Grijze februaridag. Koud, bewolkt, geen neerslag. Maandagspits.",
        "weekday_num": 0,    # Monday
        "month":       2,
        "rain_total":  0.3, "rain_peak": 0.1,
        "wind_peak":   20.0, "wind_mean": 12.0,
        "temp_min":    0.0,  "temp_mean": 3.0,
        "humidity_max": 87.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 42. Late lentestorm donderdag ─────────────────────────────────────────
    {
        "name":        "42. Late lentestorm donderdag",
        "description": "Juni onweersbui. Zware buien en wind. Spits + storm.",
        "weekday_num": 3,    # Thursday
        "month":       6,
        "rain_total":  11.0, "rain_peak": 6.5,
        "wind_peak":   62.0, "wind_mean": 35.0,
        "temp_min":    14.0, "temp_mean": 18.0,
        "humidity_max": 97.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 43. Pinkstermaandag (feestdag) ────────────────────────────────────────
    {
        "name":        "43. Pinkstermaandag (feestdag)",
        "description": "Pinksteren — Belgische feestdag. Geen woon-werkverkeer.",
        "weekday_num": 0,    # Monday
        "month":       6,
        "rain_total":  1.5, "rain_peak": 0.8,
        "wind_peak":   22.0, "wind_mean": 13.0,
        "temp_min":    13.0, "temp_mean": 19.0,
        "humidity_max": 75.0, "snow_total": 0.0,
        "is_school_holiday": False,
        "is_public_holiday": True,
    },
    # ── 44. Koude regenachtige vrijdag januari ────────────────────────────────
    {
        "name":        "44. Koude regenachtige vrijdag",
        "description": "Januari, regen en koude. Vrijdagochtend natter dan verwacht.",
        "weekday_num": 4,    # Friday
        "month":       1,
        "rain_total":  3.0, "rain_peak": 1.8,
        "wind_peak":   28.0, "wind_mean": 16.0,
        "temp_min":    2.0,  "temp_mean": 5.0,
        "humidity_max": 92.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 45. Perfecte septemberwoensdag ───────────────────────────────────────
    {
        "name":        "45. Perfecte septemberwoensdag",
        "description": "Ideale herfstdag. Aangenaam, droog, lichte wind.",
        "weekday_num": 2,    # Wednesday
        "month":       9,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   14.0, "wind_mean": 8.0,
        "temp_min":    11.0, "temp_mean": 19.0,
        "humidity_max": 63.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 46. Orkaan vrijdag maart ──────────────────────────────────────────────
    {
        "name":        "46. Orkaan vrijdag maart",
        "description": "Orkaanachtige wind uit het zuidwesten. Windstoten 90 km/h.",
        "weekday_num": 4,    # Friday
        "month":       3,
        "rain_total":  7.0, "rain_peak": 4.0,
        "wind_peak":   90.0, "wind_mean": 60.0,
        "temp_min":    9.0,  "temp_mean": 12.0,
        "humidity_max": 97.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 47. Grijs nat donderdag november ─────────────────────────────────────
    {
        "name":        "47. Grijs nat donderdag november",
        "description": "Lichte regen, koud, grijs. Spitspiek donderdag.",
        "weekday_num": 3,    # Thursday
        "month":       11,
        "rain_total":  2.0, "rain_peak": 1.3,
        "wind_peak":   25.0, "wind_mean": 14.0,
        "temp_min":    4.0,  "temp_mean": 7.0,
        "humidity_max": 93.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 48. Kerstvakantie maandag december ────────────────────────────────────
    {
        "name":        "48. Kerstvakantie maandag",
        "description": "Kerstvakantie. Scholen dicht, wegen rustig, mild decemberweer.",
        "weekday_num": 0,    # Monday
        "month":       12,
        "rain_total":  2.0, "rain_peak": 1.2,
        "wind_peak":   22.0, "wind_mean": 13.0,
        "temp_min":    5.0,  "temp_mean": 8.0,
        "humidity_max": 88.0, "snow_total": 0.0,
        "is_school_holiday": True,
    },
    # ── 49. Winterstorm dinsdag januari ───────────────────────────────────────
    {
        "name":        "49. Winterstorm dinsdag",
        "description": "Hevige winterstorm. Zware regen + storm + spitspiek.",
        "weekday_num": 1,    # Tuesday
        "month":       1,
        "rain_total":  12.0, "rain_peak": 7.5,
        "wind_peak":   78.0, "wind_mean": 50.0,
        "temp_min":    5.0,  "temp_mean": 8.0,
        "humidity_max": 98.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
    # ── 50. Nazomer vrijdag oktober ───────────────────────────────────────────
    {
        "name":        "50. Nazomer vrijdag oktober",
        "description": "Indische zomer. Warm, droog, lichtste spits van de week.",
        "weekday_num": 4,    # Friday
        "month":       10,
        "rain_total":  0.0, "rain_peak": 0.0,
        "wind_peak":   11.0, "wind_mean": 6.0,
        "temp_min":    14.0, "temp_mean": 22.0,
        "humidity_max": 60.0, "snow_total": 0.0,
        "is_school_holiday": False,
    },
]

# Validate: we must have at least 50
assert len(SCENARIOS) >= 50, "Define at least 50 scenarios"


# =============================================================================
# 4. RUN ALL PREDICTIONS
# =============================================================================

print(f"Running {len(SCENARIOS)} scenario predictions …\n")

results = [predict_scenario(s) for s in SCENARIOS]
df_results = pd.DataFrame(results)


# =============================================================================
# 5. PRINT RESULTS TABLE
# =============================================================================

WEEKDAY_NAMES = ["Ma", "Di", "Wo", "Do", "Vr"]

print("=" * 100)
print(f"{'#':<4} {'Scenario':<38} {'Dag':<4} {'Weer risk':<10} "
      f"{'Auto (min)':<12} {'Modus':<12} {'Vertrek':<9} {'Label':<8}")
print("-" * 100)

for r in results:
    wd_label = WEEKDAY_NAMES[int(r["weekday_num"])]
    car_str  = f"{r['car_pred_min']:.0f}" if r["car_pred_min"] is not None else "—"
    risk_str = str(r.get("weather_risk", "—"))
    label    = r["risk_label"].upper()

    print(f"{r['name'][:3]:<4} {r['name'][3:].strip()[:37]:<38} "
          f"{wd_label:<4} {risk_str:<10} "
          f"{car_str:<12} {r['mode_recommended']:<12} "
          f"{r['departure_time']:<9} {label:<8}")

print("=" * 100)

print("\nDetailed advice:")
for r in results:
    print(f"\n  {r['name']}")
    print(f"    {r['description']}")
    print(f"    → {r['advice']}")


# =============================================================================
# 6. VISUALISE RESULTS
# =============================================================================

# Decision threshold: car is preferred when its time ≤ train + buffer.
THRESHOLD_MIN = TRAIN_SCHED_MIN + CAR_PREF_BUFFER_MIN

MODE_COLORS = {
    "auto":        "#1565c0",   # blue  — car preferred
    "trein":       "#e65100",   # deep orange — train preferred
    "thuiswerken": "#757575",   # grey — stay home / public holiday
}
# Hatching encodes the weather risk level on top of the mode colour
RISK_HATCH = {"rood": "///", "oranje": "xx", "groen": ""}

# Sort scenarios by estimated car time ascending so the threshold line cuts
# cleanly through the chart — everything left = car zone, right = train zone.
df_plot = (
    df_results[df_results["car_pred_min"].notna()]
    .sort_values("car_pred_min", ascending=True)
    .reset_index(drop=True)
)

n          = len(df_plot)
fig_height = max(16, n * 0.40 + 3)
x_max      = df_plot["car_pred_min"].max() * 1.18

fig, (ax_main, ax_side) = plt.subplots(
    1, 2, figsize=(18, fig_height),
    gridspec_kw={"width_ratios": [3, 1]}
)
plt.subplots_adjust(wspace=0.28)

# ── Background zones: blue = car preferred, orange = train preferred ──────────
ax_main.axvspan(0,             THRESHOLD_MIN, alpha=0.07, color="#1565c0", zorder=0)
ax_main.axvspan(THRESHOLD_MIN, x_max,         alpha=0.07, color="#e65100", zorder=0)

# ── Bars coloured by recommended mode ────────────────────────────────────────
bar_colors = [MODE_COLORS[m] for m in df_plot["mode_recommended"]]
bars = ax_main.barh(
    df_plot["name"], df_plot["car_pred_min"],
    color=bar_colors, height=0.65, zorder=2,
    edgecolor="none",
)
# Apply risk hatching (overwrites bar edge colour, keep transparent fill edge)
for bar, risk in zip(bars, df_plot["risk_label"]):
    bar.set_hatch(RISK_HATCH.get(risk, ""))
    bar.set_edgecolor("white")

# ── Reference lines ───────────────────────────────────────────────────────────
ax_main.axvline(TRAIN_SCHED_MIN, color="#999999", lw=1.5, ls="--",  zorder=3)
ax_main.axvline(THRESHOLD_MIN,   color="black",   lw=2.5, ls="-",   zorder=3)

# Zone labels at the top of the chart
ax_main.text(THRESHOLD_MIN / 2, -0.85,
             "← AUTO", ha="center", va="bottom",
             fontsize=9, color="#1565c0", fontweight="bold", zorder=4)
ax_main.text(THRESHOLD_MIN + (x_max - THRESHOLD_MIN) / 2, -0.85,
             "TREIN →", ha="center", va="bottom",
             fontsize=9, color="#e65100", fontweight="bold", zorder=4)

# ── Value labels at the end of each bar ───────────────────────────────────────
for bar, val in zip(bars, df_plot["car_pred_min"]):
    ax_main.text(val + 0.4, bar.get_y() + bar.get_height() / 2,
                 f"{val:.0f}", va="center", fontsize=7.5, color="black")

# ── Legend ────────────────────────────────────────────────────────────────────
legend_handles = [
    mpatches.Patch(color="#1565c0", label="Auto aanbevolen"),
    mpatches.Patch(color="#e65100", label="Trein aanbevolen"),
    mpatches.Patch(color="#757575", label="Thuiswerken / feestdag"),
    mlines.Line2D([0], [0], color="#999", ls="--", lw=1.5,
                  label=f"Trein: {TRAIN_SCHED_MIN:.0f} min"),
    mlines.Line2D([0], [0], color="black", ls="-", lw=2.5,
                  label=f"Auto-drempel: trein + {CAR_PREF_BUFFER_MIN} min ({THRESHOLD_MIN:.0f} min)"),
    mpatches.Patch(facecolor="white", hatch="///", edgecolor="#444",
                   label="Hoog risico (rood)"),
    mpatches.Patch(facecolor="white", hatch="xx",  edgecolor="#444",
                   label="Verhoogd risico (oranje)"),
]
ax_main.legend(handles=legend_handles, loc="lower right", fontsize=8.5, framealpha=0.93)

ax_main.set_xlabel("Geschatte auto-reistijd (min)", fontsize=11)
ax_main.set_xlim(left=0, right=x_max)
ax_main.set_title(
    "Auto-reistijd per scenario vs. beslissingsdrempel\n"
    "(kleur = aanbevolen modus  |  arcering = risico-niveau)",
    fontweight="bold", fontsize=11
)
ax_main.invert_yaxis()   # shortest bar (fastest car) at top

# ── Side panel: mode count bar chart (clearer than a pie) ─────────────────────
mode_order  = ["auto", "trein", "thuiswerken"]
mode_labels = ["Auto", "Trein", "Thuiswerken"]
mode_counts = df_results["mode_recommended"].value_counts()
counts      = [mode_counts.get(m, 0) for m in mode_order]

ax_side.barh(mode_labels, counts,
             color=[MODE_COLORS[m] for m in mode_order],
             edgecolor="white", height=0.5)
for i, cnt in enumerate(counts):
    pct = cnt / len(df_results) * 100
    ax_side.text(cnt + 0.15, i, f"{cnt}  ({pct:.0f}%)", va="center", fontsize=11)
ax_side.set_xlim(0, max(counts) * 1.45)
ax_side.set_xlabel("Aantal scenario's", fontsize=10)
ax_side.set_title(
    f"Aanbevolen modus\n({len(SCENARIOS)} scenario's totaal)",
    fontweight="bold", fontsize=11
)
ax_side.invert_yaxis()

fig.suptitle(
    f"Scenario-voorspellingen — Gent → Mechelen (aankomst 09:00)\n"
    f"Auto verkozen indien auto-tijd ≤ trein ({TRAIN_SCHED_MIN:.0f} min) + buffer ({CAR_PREF_BUFFER_MIN} min) = {THRESHOLD_MIN:.0f} min",
    fontsize=13, fontweight="bold"
)

out_path = "data/processed/scenario_predictions.png"
plt.savefig(out_path, bbox_inches="tight", dpi=130)
print(f"\nPlot opgeslagen: {out_path}")
plt.show()


# =============================================================================
# 7. SAVE RESULTS TO CSV
# =============================================================================

csv_cols = [
    "name", "description", "weekday_num", "month",
    "rain_peak", "wind_peak", "temp_min", "snow_total",
    "weather_risk", "car_pred_min", "train_sched_min",
    "mode_recommended", "confidence_pct", "departure_time",
    "risk_label", "advice",
]
# train_sched_min is not in the original dicts, add it
df_results["train_sched_min"] = TRAIN_SCHED_MIN

df_results[csv_cols].to_csv("data/processed/scenario_predictions.csv", index=False)
print("CSV opgeslagen: data/processed/scenario_predictions.csv")

# ── Final summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("SAMENVATTING VAN ALLE SCENARIO'S")
print("=" * 65)
print(f"  Aantal scenario's       : {len(SCENARIOS)}")
print(f"  Aanbevolen AUTO         : {(df_results['mode_recommended'] == 'auto').sum()}")
print(f"  Aanbevolen TREIN        : {(df_results['mode_recommended'] == 'trein').sum()}")
print(f"  Aanbevolen THUISWERKEN  : {(df_results['mode_recommended'] == 'thuiswerken').sum()}")
print(f"\n  Groene dagen            : {(df_results['risk_label'] == 'groen').sum()}")
print(f"  Oranje dagen            : {(df_results['risk_label'] == 'oranje').sum()}")
print(f"  Rode dagen              : {(df_results['risk_label'] == 'rood').sum()}")

valid = df_results[df_results["car_pred_min"].notna()]
print(f"\n  Gemiddelde auto-tijd    : {valid['car_pred_min'].mean():.1f} min")
print(f"  Snelste auto-scenario   : {valid.loc[valid['car_pred_min'].idxmin(), 'name']}")
print(f"  Langzaamste auto-scenario: {valid.loc[valid['car_pred_min'].idxmax(), 'name']}")
