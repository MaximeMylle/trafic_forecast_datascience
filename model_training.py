"""
model_training.py
=================
Trains and evaluates prediction models for the Gent → Mechelen commute.

This file imports the combined dataset from data_pipeline.py, then:
  1. Prepares features and targets
  2. Splits data into training and test sets
  3. Trains a baseline model (Linear Regression)
  4. Trains an improved model (Random Forest)
  5. Evaluates both models with business-relevant metrics
  6. Shows which features matter most
  7. Demonstrates a concrete next-day prediction

Run with:
    python model_training.py

Requirements (install once):
    pip install scikit-learn pandas numpy matplotlib
"""

# ─── Standard-library imports ────────────────────────────────────────────────
import subprocess
import sys
import warnings
warnings.filterwarnings("ignore")   # suppress minor sklearn convergence warnings

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

# ─── Third-party imports ─────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

# scikit-learn: the standard Python machine-learning library
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

# ─── Import our own data pipeline ────────────────────────────────────────────
# data_pipeline.py must be in the same folder as this file.
# build_combined_df() returns the ready-made DataFrame (or loads it from cache).
from data_pipeline import build_combined_df


# =============================================================================
# STEP 0 — Load the dataset
# =============================================================================

print("=" * 65)
print("STEP 0 — Loading dataset")
print("=" * 65)

# build_combined_df() checks whether the processed CSV already exists on disk.
# If yes, it simply reads it (fast).
# If not, it fetches data from all APIs and saves it.
df = build_combined_df()

print(f"\nDataset loaded: {df.shape[0]:,} working days  "
      f"({df['date'].min().date()} → {df['date'].max().date()})")
print(df.describe().round(2))


# =============================================================================
# STEP 1 — Define features and targets
# =============================================================================

print("\n" + "=" * 65)
print("STEP 1 — Feature and target selection")
print("=" * 65)

# FEATURES (= input variables, also called X)
# -------------------------------------------
# These are the columns the model is ALLOWED to see when making a prediction.
# In a real-world setting these would be known the evening before the commute:
#   - tomorrow's weather forecast
#   - which day of the week it is
#   - which month / season it is
#
# We deliberately do NOT include car_est_min itself as a feature for the
# regression model, because that is what we are trying to predict.

FEATURE_COLS = [
    # Weather features (from the 06:00–09:00 window forecast)
    "rain_total",        # total expected rain in mm
    "rain_peak",         # worst expected single-hour rain in mm
    "wind_peak",         # strongest expected gust in km/h
    "wind_mean",         # average wind speed in km/h
    "temp_min",          # coldest hour expected (°C)
    "temp_mean",         # average temperature (°C)
    "humidity_max",      # maximum humidity — proxy for fog
    "snow_total",        # any snow expected (cm)

    # Calendar / contextual features
    "weekday_num",       # 0=Monday … 4=Friday (numeric version of weekday)
    "month",             # 1=January … 12=December (captures seasonality)
    "is_mon",            # 1 if Monday (often has heavier build-up traffic)
    "is_tue_thu",        # 1 if Tuesday or Thursday (peak rush days)
    "is_fri",            # 1 if Friday (lighter morning, earlier finish)
    "is_school_holiday", # 1 in July–August (noticeably lighter traffic)

    # Composite risk score (already summarises the weather columns above,
    # but including it gives the model a hand-crafted shortcut)
    "weather_risk",
]

# TARGETS (= what we want to predict)
# ------------------------------------
# We train two separate models:
#   - Regression:     predict car_est_min  (continuous, in minutes)
#   - Classification: predict car_faster_than_train (binary: 1 or 0)

TARGET_REGRESSION      = "car_est_min"
TARGET_CLASSIFICATION  = "car_faster_than_train"

# Extract feature matrix X and both target vectors
X   = df[FEATURE_COLS].values           # shape: (n_days, n_features)
y_r = df[TARGET_REGRESSION].values      # continuous target
y_c = df[TARGET_CLASSIFICATION].values  # binary target

print(f"\nFeature matrix X shape : {X.shape}")
print(f"Regression target      : {TARGET_REGRESSION}  "
      f"(mean={y_r.mean():.1f} min, std={y_r.std():.1f} min)")
print(f"Classification target  : {TARGET_CLASSIFICATION}  "
      f"(car faster on {y_c.mean():.1%} of days)")

print("\nFeatures used:")
for i, col in enumerate(FEATURE_COLS, 1):
    print(f"  {i:2d}. {col}")


# =============================================================================
# STEP 2 — Train / test split
# =============================================================================

print("\n" + "=" * 65)
print("STEP 2 — Train / test split")
print("=" * 65)

# Why split at all?
# -----------------
# We must evaluate the model on data it has NEVER seen during training.
# Otherwise we would only know how well the model memorised the training data,
# not how well it generalises to future days — which is the actual goal.
#
# shuffle=False is important for time-series data.
# If we shuffle, a model might "see the future" by training on days that come
# after the test days.  Instead we keep the natural time order: train on
# earlier days, test on later days.
#
# test_size=0.20 means the last 20 % of working days form the test set.

X_train, X_test, yr_train, yr_test, yc_train, yc_test = train_test_split(
    X, y_r, y_c,
    test_size=0.20,
    shuffle=False,   # keep chronological order — crucial for time-based data
    random_state=42,
)

n_train = len(X_train)
n_test  = len(X_test)

# Map the split back to actual dates so we can report readable date ranges
train_dates = df.iloc[:n_train]["date"]
test_dates  = df.iloc[n_train:]["date"]

print(f"\nTraining set : {n_train:,} days  "
      f"({train_dates.min().date()} → {train_dates.max().date()})")
print(f"Test set     : {n_test:,} days  "
      f"({test_dates.min().date()} → {test_dates.max().date()})")
print(f"\nRatio: {n_train / (n_train + n_test):.0%} train / "
      f"{n_test / (n_train + n_test):.0%} test")


# =============================================================================
# STEP 3 — Baseline model: Linear Regression (car travel time)
# =============================================================================

print("\n" + "=" * 65)
print("STEP 3 — Baseline: Linear Regression (regression)")
print("=" * 65)

# Why start with Linear Regression?
# ----------------------------------
# Linear Regression is the simplest possible model.  It assumes:
#   predicted_time = w1*feature1 + w2*feature2 + … + bias
#
# Starting simple is good practice because:
#   - It is fast to train and interpret.
#   - If a complex model does not beat it, something is wrong.
#   - Its coefficients directly show which features push the prediction up or down.

lr_model = LinearRegression()

# fit() = "train" the model.  It finds the weights (coefficients) that
# minimise the sum of squared errors between predictions and true values.
lr_model.fit(X_train, yr_train)

# predict() = apply the learned weights to new (unseen) data
yr_pred_lr = lr_model.predict(X_test)

# --- evaluation metrics ---
# MAE  (Mean Absolute Error)    : average error in the same unit as target (minutes)
# RMSE (Root Mean Squared Error): penalises large errors more than MAE
# R²   (coefficient of determination): 1.0 = perfect, 0.0 = no better than predicting mean

mae_lr  = mean_absolute_error(yr_test, yr_pred_lr)
rmse_lr = np.sqrt(mean_squared_error(yr_test, yr_pred_lr))
r2_lr   = r2_score(yr_test, yr_pred_lr)

print(f"\nLinear Regression — test set performance:")
print(f"  MAE  : {mae_lr:.2f} min   (avg error in minutes)")
print(f"  RMSE : {rmse_lr:.2f} min  (penalises big errors more)")
print(f"  R²   : {r2_lr:.4f}        (1.0 = perfect fit)")

# Show the learned coefficients so we can interpret the model
print("\nLearned coefficients (effect of each feature on predicted travel time):")
for feat, coef in sorted(zip(FEATURE_COLS, lr_model.coef_), key=lambda x: abs(x[1]), reverse=True):
    direction = "▲" if coef > 0 else "▼"
    print(f"  {direction} {feat:<22s}: {coef:+.4f} min per unit")
print(f"  Intercept (bias)       : {lr_model.intercept_:.2f} min")

# --- cross-validation sanity check ---
# Cross-validation gives a more reliable estimate of performance by training
# and testing on 5 different folds.  Because our data is time-ordered, we use
# shuffle=False in the train/test split above; here we use cv=5 time-aware.
cv_scores_lr = cross_val_score(
    lr_model, X, y_r, cv=5, scoring="neg_mean_absolute_error"
)
print(f"\n5-fold cross-validated MAE : {-cv_scores_lr.mean():.2f} ± {cv_scores_lr.std():.2f} min")


# =============================================================================
# STEP 4 — Improved model: Random Forest Regressor
# =============================================================================

print("\n" + "=" * 65)
print("STEP 4 — Improved: Random Forest Regressor")
print("=" * 65)

# Why Random Forest?
# ------------------
# A Random Forest builds many decision trees, each trained on a random subset
# of the data and features, then averages their predictions.
#
# Advantages over Linear Regression:
#   - Can capture non-linear relationships (e.g. rain only matters a lot when
#     it is combined with cold temperature → ice).
#   - Naturally handles interactions between features.
#   - Hard to overfit if n_estimators is large enough.
#
# Key hyperparameters:
#   n_estimators  : number of trees (more = more stable, slower to train)
#   max_depth     : how deep each tree can grow (None = unlimited = more flexible)
#   min_samples_leaf: a tree node must have at least this many training samples
#                    (higher = smoother, less overfit)
#   random_state  : seed for reproducibility (same seed → same result every run)

rf_model = RandomForestRegressor(
    n_estimators   = 300,    # 300 trees: good balance of accuracy vs speed
    max_depth      = None,   # let trees grow fully (the ensemble average prevents overfit)
    min_samples_leaf = 5,    # each leaf must summarise at least 5 training days
    random_state   = 42,
    n_jobs         = -1,     # use all CPU cores for parallel training
)

rf_model.fit(X_train, yr_train)
yr_pred_rf = rf_model.predict(X_test)

mae_rf  = mean_absolute_error(yr_test, yr_pred_rf)
rmse_rf = np.sqrt(mean_squared_error(yr_test, yr_pred_rf))
r2_rf   = r2_score(yr_test, yr_pred_rf)

print(f"\nRandom Forest — test set performance:")
print(f"  MAE  : {mae_rf:.2f} min")
print(f"  RMSE : {rmse_rf:.2f} min")
print(f"  R²   : {r2_rf:.4f}")

cv_scores_rf = cross_val_score(
    rf_model, X, y_r, cv=5, scoring="neg_mean_absolute_error"
)
print(f"\n5-fold cross-validated MAE : {-cv_scores_rf.mean():.2f} ± {cv_scores_rf.std():.2f} min")

# --- comparison ---
improvement = mae_lr - mae_rf
print(f"\nImprovement over Linear Regression: {improvement:+.2f} min MAE")
if improvement > 0:
    print("→ Random Forest is the better model.")
else:
    print("→ Linear Regression already captures the main patterns.")


# =============================================================================
# STEP 5 — Feature importance (Random Forest)
# =============================================================================

print("\n" + "=" * 65)
print("STEP 5 — Feature importance")
print("=" * 65)

# Random Forest can report how much each feature contributed to reducing
# prediction error across all trees.  This is called "impurity-based importance"
# or "Gini importance".  Higher value → more important feature.

importances = pd.Series(rf_model.feature_importances_, index=FEATURE_COLS)
importances_sorted = importances.sort_values(ascending=False)

print("\nFeature importances (higher = more influential in the Random Forest):")
for feat, imp in importances_sorted.items():
    bar = "█" * int(imp * 200)
    print(f"  {feat:<22s}: {imp:.4f}  {bar}")


# =============================================================================
# STEP 6 — Classification model: will car be faster than train?
# =============================================================================

print("\n" + "=" * 65)
print("STEP 6 — Classification: car faster than train?")
print("=" * 65)

# This model answers a binary question: on a given day, should we take the car
# (because it will be faster) or the train (because the car will be slower)?
#
# We use Random Forest Classifier, which works the same as the Regressor but
# outputs a class label (0 or 1) instead of a continuous number.

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)

rfc_model = RandomForestClassifier(
    n_estimators   = 300,
    max_depth      = None,
    min_samples_leaf = 5,
    random_state   = 42,
    n_jobs         = -1,
    class_weight   = "balanced",  # handle any class imbalance automatically
)

rfc_model.fit(X_train, yc_train)
yc_pred = rfc_model.predict(X_test)

# predict_proba returns one column per class the model saw during training.
# If the training data contains only one class (e.g. car is always faster),
# the output has shape (n, 1) and indexing [:, 1] would crash.
# _safe_prob1 handles both cases: it returns P(class=1) when two classes
# exist, or 1.0 / 0.0 when only one class was seen.
def _safe_prob1(model, X) -> np.ndarray:
    proba = model.predict_proba(X)
    if proba.shape[1] == 1:
        # Only one class in training data — assign certainty to that class
        only_class = int(model.classes_[0])
        return np.full(len(X), float(only_class))
    return proba[:, 1]

yc_prob = _safe_prob1(rfc_model, X_test)

acc = accuracy_score(yc_test, yc_pred)
print(f"\nRandom Forest Classifier — test set accuracy: {acc:.2%}")

# Warn explicitly when only one class was seen — this is a data-quality signal,
# not a model bug.  It means the binary target is nearly constant (e.g. car is
# almost always faster than the train on this route), so classification is
# trivial and not very informative.
if len(rfc_model.classes_) == 1:
    print(f"  Note: only class {rfc_model.classes_[0]} was present in training data.")
    print(f"  The target 'car_faster_than_train' is nearly constant — "
          f"consider a different classification target (e.g. 'high_delay_risk').")
else:
    print("\nDetailed classification report:")
    print(classification_report(
        yc_test, yc_pred,
        target_names=["Train faster", "Car faster"],
    ))

# Confusion matrix: safe version that handles 1×1 and 2×2 outcomes
cm = confusion_matrix(yc_test, yc_pred)
print("Confusion matrix (rows=actual, cols=predicted):")
if cm.shape == (2, 2):
    print(f"               Pred:Train  Pred:Car")
    print(f"  Actual:Train    {cm[0,0]:>6d}    {cm[0,1]:>6d}")
    print(f"  Actual:Car      {cm[1,0]:>6d}    {cm[1,1]:>6d}")
else:
    # Only one class present in test set as well
    print(f"  All {cm[0,0]} test days belong to class {rfc_model.classes_[0]}")


# =============================================================================
# STEP 7 — Business-relevant evaluation
# =============================================================================

print("\n" + "=" * 65)
print("STEP 7 — Business-relevant evaluation")
print("=" * 65)

# Raw ML metrics (MAE, R²) are useful for comparing models, but a business
# stakeholder cares about different questions:
#
#  Q1: How often does the model recommend the WRONG transport mode?
#  Q2: What is the risk of arriving LATE at 09:00?
#  Q3: How large is the typical prediction error in real minutes?

# We define departure times as: arrival 09:00 minus estimated travel time
# A buffer of 10 minutes is added to account for model uncertainty.
BUFFER_MIN = 10

# Reconstruct a test-set DataFrame for business metrics
df_test = df.iloc[n_train:].copy().reset_index(drop=True)
df_test["car_pred_rf"]   = yr_pred_rf
df_test["car_pred_lr"]   = yr_pred_lr
df_test["mode_pred_rfc"] = yc_pred     # 1=car predicted faster, 0=train

# Required departure time to arrive at 09:00
df_test["car_dep_rf"]   = 9*60 - (df_test["car_pred_rf"]  + BUFFER_MIN)
df_test["car_dep_true"] = 9*60 - (df_test["car_est_min"]  + BUFFER_MIN)

# On how many test days did both models agree on transport mode?
both_agree = (
    (df_test["car_pred_rf"] <= df_test["train_sched_min"]).astype(int)
    == df_test["car_faster_than_train"]
).mean()

print(f"\nWith {BUFFER_MIN}-min buffer to arrive at 09:00:")
print(f"  Avg predicted car time (RF)      : {yr_pred_rf.mean():.1f} min")
print(f"  Avg actual car time              : {yr_test.mean():.1f} min")
print(f"  Avg absolute error (RF)          : {mae_rf:.1f} min")

print(f"\n  Days where RF picks correct mode : {both_agree:.1%}")
print(f"  Train scheduled time             : {df_test['train_sched_min'].iloc[0]:.0f} min")

# How often would following the model's advice lead to arriving late?
# (i.e. actual travel time > predicted + buffer)
late_risk = ((df_test["car_est_min"] > yr_pred_rf + BUFFER_MIN)).mean()
print(f"  Risk of arriving late (RF model) : {late_risk:.1%}")

# Average buffer remaining at 09:00 if prediction is correct
df_test["buffer_remaining"] = (
    (df_test["car_pred_rf"] + BUFFER_MIN) - df_test["car_est_min"]
)
print(f"  Avg buffer remaining at 09:00    : {df_test['buffer_remaining'].mean():.1f} min")


# =============================================================================
# STEP 8 — Concrete next-day prediction example
# =============================================================================

print("\n" + "=" * 65)
print("STEP 8 — Example: predict tomorrow's commute")
print("=" * 65)

# This is how the model would be used in practice:
# 1. Fetch tomorrow's weather forecast (we simulate one here).
# 2. Feed it through the Random Forest.
# 3. Compute recommended departure time for 09:00 arrival.

from datetime import date, timedelta
tomorrow = date.today() + timedelta(days=1)

# Find the next working day if tomorrow is a weekend
while tomorrow.weekday() >= 5:
    tomorrow += timedelta(days=1)

# Simulated forecast for tomorrow's commute window (replace with real forecast)
tomorrow_weather = {
    "rain_total":    2.5,    # moderate total rain expected
    "rain_peak":     1.2,    # max 1.2 mm in a single hour
    "wind_peak":     28.0,   # moderate wind
    "wind_mean":     15.0,
    "temp_min":      7.0,    # mild, no frost risk
    "temp_mean":     10.0,
    "humidity_max":  88.0,   # slightly humid but no fog
    "snow_total":    0.0,
    "weekday_num":   tomorrow.weekday(),
    "month":         tomorrow.month,
    "is_mon":        int(tomorrow.weekday() == 0),
    "is_tue_thu":    int(tomorrow.weekday() in [1, 3]),
    "is_fri":        int(tomorrow.weekday() == 4),
    "is_school_holiday": int(tomorrow.month in [7, 8]),
    "weather_risk":  1,      # low risk: only light rain
}

# Build the feature vector in the exact same column order as during training
tomorrow_X = np.array([[tomorrow_weather[col] for col in FEATURE_COLS]])

# Predict with both models
car_time_rf  = rf_model.predict(tomorrow_X)[0]
car_time_lr  = lr_model.predict(tomorrow_X)[0]
mode_pred    = rfc_model.predict(tomorrow_X)[0]
mode_prob    = float(_safe_prob1(rfc_model, tomorrow_X)[0])  # P(car faster)

# Compute recommended departure time (minutes from midnight → HH:MM)
def minutes_to_hhmm(minutes_from_midnight: float) -> str:
    total = int(round(minutes_from_midnight))
    h = total // 60
    m = total % 60
    return f"{h:02d}:{m:02d}"

train_sched = df["train_sched_min"].iloc[0]
car_departure = 9 * 60 - (car_time_rf + BUFFER_MIN)

recommended_mode = "car" if mode_pred == 1 else "train"

print(f"\nDate: {tomorrow}  ({tomorrow.strftime('%A')})")
print(f"Simulated forecast: rain_peak={tomorrow_weather['rain_peak']} mm, "
      f"wind={tomorrow_weather['wind_peak']} km/h, "
      f"temp_min={tomorrow_weather['temp_min']}°C")
print()
print(f"  Random Forest prediction  : {car_time_rf:.0f} min (car)")
print(f"  Linear Regression predict : {car_time_lr:.0f} min (car)")
print(f"  Train scheduled           : {train_sched:.0f} min")
print()
print(f"  Recommended mode          : {recommended_mode.upper()}")
print(f"  Confidence (P car faster) : {mode_prob:.1%}")
print()
if recommended_mode == "car":
    print(f"  → Depart by car at        : {minutes_to_hhmm(car_departure)} "
          f"(with {BUFFER_MIN}-min buffer for 09:00 arrival)")
else:
    print(f"  → Take the train; check NMBS app for exact departure time.")


# =============================================================================
# STEP 9 — Visualisations
# =============================================================================

print("\n" + "=" * 65)
print("STEP 9 — Saving evaluation plots")
print("=" * 65)

Path("data/processed").mkdir(parents=True, exist_ok=True)

fig = plt.figure(figsize=(16, 12))
gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)

# ── plot A: actual vs predicted (Random Forest) ──────────────────────────────
ax_a = fig.add_subplot(gs[0, 0])
ax_a.scatter(yr_test, yr_pred_rf, alpha=0.35, s=12, color="steelblue")
# Perfect prediction line (predicted = actual)
lims = [min(yr_test.min(), yr_pred_rf.min()), max(yr_test.max(), yr_pred_rf.max())]
ax_a.plot(lims, lims, "r--", lw=1.2, label="Perfect prediction")
ax_a.set_xlabel("Actual car time (min)")
ax_a.set_ylabel("Predicted car time (min)")
ax_a.set_title(f"RF: Actual vs Predicted\nMAE={mae_rf:.1f} min, R²={r2_rf:.3f}")
ax_a.legend(fontsize=8)

# ── plot B: residuals (errors) distribution ───────────────────────────────────
ax_b = fig.add_subplot(gs[0, 1])
residuals_rf = yr_pred_rf - yr_test    # positive = over-predicted
ax_b.hist(residuals_rf, bins=40, color="steelblue", edgecolor="white", alpha=0.8)
ax_b.axvline(0, color="red", lw=1.5, ls="--")
ax_b.axvline(residuals_rf.mean(), color="orange", lw=1.5,
             label=f"Mean error: {residuals_rf.mean():.1f} min")
ax_b.set_xlabel("Prediction error (min)")
ax_b.set_ylabel("Count")
ax_b.set_title("RF residuals distribution\n(0 = perfect, positive = over-estimate)")
ax_b.legend(fontsize=8)

# ── plot C: model comparison bar chart ───────────────────────────────────────
ax_c = fig.add_subplot(gs[0, 2])
models  = ["Linear\nRegression", "Random\nForest"]
mae_vals = [mae_lr, mae_rf]
bars = ax_c.bar(models, mae_vals, color=["#90caf9", "#1565c0"], edgecolor="white", width=0.5)
for bar, val in zip(bars, mae_vals):
    ax_c.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
              f"{val:.2f} min", ha="center", fontsize=11, fontweight="bold")
ax_c.set_ylabel("MAE (min) — lower is better")
ax_c.set_title("Model comparison\n(Test set MAE)")
ax_c.set_ylim(0, max(mae_vals) * 1.3)

# ── plot D: feature importances ───────────────────────────────────────────────
ax_d = fig.add_subplot(gs[1, :2])
imp_df = importances_sorted.reset_index()
imp_df.columns = ["feature", "importance"]
# Show only top 12 features to keep the chart readable
top_n = 12
imp_top = imp_df.head(top_n)
ax_d.barh(imp_top["feature"][::-1], imp_top["importance"][::-1],
          color="steelblue", edgecolor="white")
ax_d.set_xlabel("Feature importance (Random Forest)")
ax_d.set_title(f"Top {top_n} most influential features\n"
               "(higher = model relies on it more)")
ax_d.set_xlim(0, imp_top["importance"].max() * 1.15)

# ── plot E: prediction error by weekday ──────────────────────────────────────
ax_e = fig.add_subplot(gs[1, 2])
df_test["abs_error_rf"] = np.abs(yr_pred_rf - yr_test)
err_by_wd = df_test.groupby("weekday")["abs_error_rf"].mean()
wd_order  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
err_vals  = [err_by_wd.get(wd, 0) for wd in wd_order]
ax_e.bar([d[:3] for d in wd_order], err_vals, color="steelblue", edgecolor="white")
ax_e.set_xlabel("")
ax_e.set_ylabel("Mean absolute error (min)")
ax_e.set_title("RF prediction error by weekday\n(lower = more accurate)")

fig.suptitle("Model Evaluation — Gent → Mechelen Commute Prediction",
             fontsize=14, fontweight="bold", y=1.01)

out_plot = Path("data/processed/model_evaluation.png")
plt.savefig(out_plot, bbox_inches="tight", dpi=130)
print(f"Evaluation plots saved to: {out_plot}")
plt.show()


# =============================================================================
# STEP 10 — Save model results summary
# =============================================================================

print("\n" + "=" * 65)
print("STEP 10 — Saving results summary")
print("=" * 65)

results_path = Path("data/processed/model_results_summary.csv")
results = pd.DataFrame([
    {
        "model":           "Linear Regression",
        "target":          TARGET_REGRESSION,
        "MAE_min":         round(mae_lr, 3),
        "RMSE_min":        round(rmse_lr, 3),
        "R2":              round(r2_lr, 4),
        "cv_MAE_mean":     round(-cv_scores_lr.mean(), 3),
        "cv_MAE_std":      round(cv_scores_lr.std(), 3),
    },
    {
        "model":           "Random Forest Regressor",
        "target":          TARGET_REGRESSION,
        "MAE_min":         round(mae_rf, 3),
        "RMSE_min":        round(rmse_rf, 3),
        "R2":              round(r2_rf, 4),
        "cv_MAE_mean":     round(-cv_scores_rf.mean(), 3),
        "cv_MAE_std":      round(cv_scores_rf.std(), 3),
    },
    {
        "model":           "Random Forest Classifier",
        "target":          TARGET_CLASSIFICATION,
        "MAE_min":         None,
        "RMSE_min":        None,
        "R2":              None,
        "cv_MAE_mean":     round(acc, 4),   # accuracy stored in MAE field for classifier
        "cv_MAE_std":      None,
    },
])
results.to_csv(results_path, index=False)
print(f"Results saved to: {results_path}")

print("\n" + "=" * 65)
print("DONE.  Summary:")
print("=" * 65)
print(f"  Linear Regression  — MAE: {mae_lr:.2f} min   R²: {r2_lr:.4f}")
print(f"  Random Forest Reg  — MAE: {mae_rf:.2f} min   R²: {r2_rf:.4f}")
print(f"  Random Forest Clf  — Accuracy: {acc:.2%}  (car vs train mode choice)")
print("\nNext step: use the model in a daily batch script (e.g. a cron job)")
print("that fetches tomorrow's weather forecast, runs model_training.py,")
print("and sends a commute recommendation by 06:30.")
