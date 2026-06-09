"""
predict_scenarios.py
====================
Uses the trained model from model_training.py to make predictions for
20 hand-crafted scenarios.  Each scenario is a realistic situation that
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

# scikit-learn — we retrain here so this file is self-contained
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split

# ─── Our own pipeline ────────────────────────────────────────────────────────
# This import fetches (or loads from cache) the full historical dataset
from data_pipeline import build_combined_df, WEEKDAY_CONGESTION


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
]

# Validate: we must have at least 15
assert len(SCENARIOS) >= 15, "Define at least 15 scenarios"


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

# We build two side-by-side charts:
#   Left  : estimated car travel time per scenario (bar chart, coloured by risk)
#   Right : count of recommended modes across all scenarios (pie chart)

RISK_COLORS = {"groen": "#4caf50", "oranje": "#ff9800", "rood": "#f44336"}

# Filter out the public holiday scenario (no car prediction)
df_plot = df_results[df_results["car_pred_min"].notna()].copy()

fig, axes = plt.subplots(1, 2, figsize=(16, 7))
plt.subplots_adjust(wspace=0.35)

# ── LEFT: car travel time per scenario ───────────────────────────────────────
bar_colors = [RISK_COLORS[r] for r in df_plot["risk_label"]]
bars = axes[0].barh(
    df_plot["name"], df_plot["car_pred_min"],
    color=bar_colors, edgecolor="white", height=0.7
)

# Add the scheduled train time as a vertical reference line
axes[0].axvline(
    TRAIN_SCHED_MIN, color="steelblue", lw=2, ls="--",
    label=f"Trein ingepland ({TRAIN_SCHED_MIN:.0f} min)"
)

# Annotate each bar with the predicted time
for bar, val in zip(bars, df_plot["car_pred_min"]):
    axes[0].text(
        val + 0.5, bar.get_y() + bar.get_height() / 2,
        f"{val:.0f}", va="center", fontsize=8.5
    )

# Legend for risk colours
legend_patches = [
    mpatches.Patch(color="#4caf50", label="Groen — normaal"),
    mpatches.Patch(color="#ff9800", label="Oranje — verhoogd risico"),
    mpatches.Patch(color="#f44336", label="Rood — hoog risico"),
    mpatches.Patch(color="steelblue", label=f"Trein ({TRAIN_SCHED_MIN:.0f} min, gestippeld)"),
]
axes[0].legend(handles=legend_patches, loc="lower right", fontsize=8)
axes[0].set_xlabel("Geschatte auto-reistijd (min)")
axes[0].set_title("Voorspelde auto-reistijd per scenario\n(kleur = risicoklasse)", fontweight="bold")
axes[0].invert_yaxis()    # first scenario at the top

# ── RIGHT: mode distribution ─────────────────────────────────────────────────
mode_counts = df_results["mode_recommended"].value_counts()
pie_colors  = {
    "auto":         "#1565c0",
    "trein":        "#f9a825",
    "thuiswerken":  "#757575",
}
axes[1].pie(
    mode_counts.values,
    labels=mode_counts.index,
    colors=[pie_colors.get(m, "grey") for m in mode_counts.index],
    autopct="%1.0f%%",
    startangle=90,
    textprops={"fontsize": 11},
    wedgeprops={"edgecolor": "white", "linewidth": 1.5},
)
axes[1].set_title(
    f"Aanbevolen reismodus\n({len(SCENARIOS)} scenario's totaal)",
    fontweight="bold"
)

fig.suptitle(
    "Scenario-voorspellingen — Gent → Mechelen (aankomst 09:00)",
    fontsize=14, fontweight="bold"
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
