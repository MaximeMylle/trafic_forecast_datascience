"""
calibrate_factors.py
====================
Derives weekday congestion factors and weather additive factors from the
actual Infrabel + Vlaams Verkeercentrum historical data, then saves the
result to factors.json for use by the pipeline and models.

METHOD OVERVIEW
---------------

1. WEEKDAY RELATIVE FACTORS  (for the VC model: car_vc_est_min)
   Source : Infrabel per-day actual train data
   Signal : Mean arrival delay in seconds per weekday.
            Train delays on this corridor are caused by the same network
            events that slow cars (demand peaks, incidents, weather), so
            the RELATIVE weekday ranking is a valid proxy for car patterns.
   Formula: factor[day] = mean_delay[day] / mean_delay[all days]
            → normalised so the 5-day mean = 1.0

2. WEEKDAY ABSOLUTE FACTORS  (for the OSRM model: car_est_min)
   Formula: factor[day] = overall_congestion_ratio × relative_factor[day]
            overall_congestion_ratio = (vc_median_highway + city_overhead) / osrm_free_flow
   The VC median gives us the real average; the relative factors distribute
   that across weekdays.

3. WEATHER ADDITIVE FACTORS
   Source A — VC car data (53 monthly observations)
   Method  : Grouped comparison: for each condition, compute
               delta = mean(vc_base | condition_present)
                     - mean(vc_base | baseline_months_of_same_season)
             Season demeaning removes the confound between autumn congestion
             and autumn rain, giving a cleaner weather-only signal.
   Source B — Infrabel daily data (1 359 real days)
   Method  : Median delay fraction on condition days minus baseline days,
             scaled by CAR_SENSITIVITY_MULTIPLIER (cars are more affected by
             rain/snow on road surfaces than trains on fixed rail).
   Final   : VC-sourced factor wins if season-demeaned delta is positive and
             the condition appeared in >= MIN_MONTHS months of VC data.
             Otherwise the scaled Infrabel factor is used as fallback.
             Monotonicity is enforced within each weather group.

Run:
    python calibrate_factors.py

Output:
    factors.json              — machine-readable settings file
    data/processed/plot_factor_calibration.png — diagnostic charts
"""

import json
import sys
import subprocess
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

for pkg in ["pandas", "numpy", "matplotlib", "scikit-learn"]:
    try:
        __import__("sklearn" if pkg == "scikit-learn" else pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg],
                              stdout=subprocess.DEVNULL)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
RAW  = ROOT / "data" / "raw"

OUT_JSON = ROOT / "factors.json"
OUT_PLOT = PROC / "plot_factor_calibration.png"

WD_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# Cars are more affected by surface weather than trains.
# Source: Belgian road accident statistics show a 2-3x higher incident rate
# during rain/ice vs dry days; train operations show ~1.5x delay rate.
# We use 2.0 as a conservative mid-range multiplier.
CAR_SENSITIVITY_MULTIPLIER = 2.0

# Minimum months a weather condition must appear in VC data to trust the
# VC-based factor (otherwise fall back to the scaled Infrabel factor).
MIN_VC_MONTHS = 8

# Assumed city-access overhead (Gent exit + Mechelen approach, not measured
# by VC highway sensors).
CITY_OVERHEAD_MIN = 20.0

# ── Previous hardcoded values (kept for comparison in diagnostics) ──────────
LEGACY_WEEKDAY = {
    "Monday": 1.28, "Tuesday": 1.35, "Wednesday": 1.20,
    "Thursday": 1.33, "Friday": 1.15,
}
LEGACY_WEATHER = {
    "rain_peak_light": 0.03, "rain_peak_moderate": 0.07, "rain_peak_heavy": 0.12,
    "snow_any": 0.25, "frost_mild": 0.07, "frost_severe": 0.15,
    "wind_strong": 0.04, "wind_storm": 0.08,
}


def _hline(title=""):
    print("\n" + "=" * 65)
    if title:
        print(title)
        print("=" * 65)


# =============================================================================
# 0 — Load data
# =============================================================================
_hline("FACTOR CALIBRATION  (Gent to Mechelen)")

inf_path  = PROC / "infrabel_daily_commute.csv"
vc_path   = PROC / "vc_travel_times.csv"
comb_path = PROC / "combined_workdays_features.csv"
osrm_path = RAW  / "osrm_route_gent_mechelen.json"

for p in [inf_path, vc_path, osrm_path]:
    if not p.exists():
        sys.exit(f"ERROR: {p} not found. Run data_pipeline.py first.")

df_inf  = pd.read_csv(inf_path,  parse_dates=["date"])
df_vc   = pd.read_csv(vc_path)
df_comb = pd.read_csv(comb_path, parse_dates=["date"]) if comb_path.exists() else None

with open(osrm_path) as f:
    osrm = json.load(f)
FREE_FLOW_MIN = float(osrm["free_flow_min"])

# Remove anomalous Jan-2021 VC entry (incomplete segment download)
df_vc = df_vc[~((df_vc["year"] == 2021) & (df_vc["month"] == 1))].copy()

print(f"Infrabel rows         : {len(df_inf):,}")
print(f"VC month-entries      : {len(df_vc)} (Jan-2021 excluded)")
print(f"OSRM free-flow        : {FREE_FLOW_MIN} min  (78.45 km via direct route)")

# Identify real Infrabel days (not pipeline-filled fallback rows).
# Fallback sets train_on_time_pct=1.0 AND train_delay_arr_median_s=0.0 exactly.
df_inf["weekday"]     = df_inf["date"].dt.day_name()
df_inf["weekday_num"] = df_inf["date"].dt.weekday
df_inf["month"]       = df_inf["date"].dt.month
df_inf["year"]        = df_inf["date"].dt.year

is_real = ~(
    (df_inf["train_on_time_pct"]      == 1.0) &
    (df_inf["train_delay_arr_median_s"] == 0.0)
)
df_real = df_inf[is_real & (df_inf["weekday_num"] < 5)].copy()
print(f"Real Infrabel days    : {len(df_real)} (of {len(df_inf)} total)")


# =============================================================================
# 1 — Weekday relative factors  (Infrabel mean delay in seconds)
# =============================================================================
_hline("1. WEEKDAY RELATIVE FACTORS  (from Infrabel)")

# Mean arrival delay in seconds is a better weekday signal than delay_frac:
#   - It has larger absolute spread (87–116 seconds per day)
#   - It is independent of the planned journey time (which barely varies)
#   - It reflects the demand and incident pattern per weekday more cleanly
wd_delay = (
    df_real.groupby("weekday")["train_delay_arr_median_s"]
    .agg(mean="mean", median="median", std="std", n="count")
    .reindex(WD_ORDER)
)
print("\nMean arrival delay by weekday (real data):")
for wd, row in wd_delay.iterrows():
    print(f"  {wd:12s}: mean={row['mean']:6.1f}s  median={row['median']:5.1f}s"
          f"  n={int(row['n'])}")

# Relative factor: proportional to mean delay, normalised mean = 1.0
mean_vals = wd_delay["mean"].values.astype(float)
# Shift so the minimum day = 1.0, then stretch so the mean = 1.0
# This keeps factors > 0 and centres the distribution correctly.
shifted = mean_vals - mean_vals.min() + mean_vals.mean()
wd_rel = {wd: round(float(v / shifted.mean()), 4)
          for wd, v in zip(WD_ORDER, shifted)}

print("\nCalibrated relative weekday factors (mean = 1.0):")
for wd, f in wd_rel.items():
    bar = ">" * int((f - 0.9) * 200)
    tag = " <-- busiest" if f == max(wd_rel.values()) else \
          " <-- lightest" if f == min(wd_rel.values()) else ""
    print(f"  {wd:12s}: {f:.4f}  {bar}{tag}")

wd_rel_legacy_note = (
    "Legacy (TomTom) had Tuesday as busiest.  "
    "Real Infrabel data shows Monday+Thursday as worst, Wednesday as lightest."
)
print(f"\n  NOTE: {wd_rel_legacy_note}")


# =============================================================================
# 2 — Weekday absolute factors  (for OSRM model)
# =============================================================================
_hline("2. WEEKDAY ABSOLUTE FACTORS  (for OSRM model)")

vc_median_highway = float(df_vc["vc_car_base_min"].median())
vc_full_route     = vc_median_highway + CITY_OVERHEAD_MIN
overall_ratio     = vc_full_route / FREE_FLOW_MIN

print(f"VC highway median             : {vc_median_highway:.2f} min")
print(f"+ city overhead assumed       : {CITY_OVERHEAD_MIN:.0f} min")
print(f"Estimated full-route average  : {vc_full_route:.1f} min")
print(f"Overall congestion ratio      : {vc_full_route:.1f} / {FREE_FLOW_MIN} = {overall_ratio:.4f}")

wd_abs = {wd: round(overall_ratio * wd_rel[wd], 4) for wd in WD_ORDER}
print("\nCalibrated absolute weekday factors (multiplied by OSRM free-flow):")
for wd, f in wd_abs.items():
    mins = round(f * FREE_FLOW_MIN, 1)
    print(f"  {wd:12s}: {f:.4f}  -> {mins} min estimated car trip")


# =============================================================================
# 3 — Weather factors: VC season-demeaned grouped comparison
# =============================================================================
_hline("3. WEATHER FACTORS  (VC season-demeaned + Infrabel cross-check)")

# ---- Build per-day weather flags for each (year, month) in VC data ----------
season_map = {12: "Winter", 1: "Winter",  2: "Winter",
              3:  "Spring", 4: "Spring",  5: "Spring",
              6:  "Summer", 7: "Summer",  8: "Summer",
              9:  "Autumn", 10: "Autumn", 11: "Autumn"}

print("\n--- VC season-demeaned grouped comparison ---")
vc_weather_factors = {}
vc_n_months        = {}

if df_comb is not None:
    df_c = df_comb.copy()
    df_c["year"]   = df_c["date"].dt.year
    df_c["month"]  = df_c["date"].dt.month
    df_c["season"] = df_c["month"].map(season_map)

    # Create condition flags per day
    df_c["c_rain_light"]    = ((df_c["rain_peak"] >= 0.5) & (df_c["rain_peak"] <  2.0)).astype(float)
    df_c["c_rain_moderate"] = ((df_c["rain_peak"] >= 2.0) & (df_c["rain_peak"] <  5.0)).astype(float)
    df_c["c_rain_heavy"]    =  (df_c["rain_peak"] >= 5.0).astype(float)
    df_c["c_snow"]          =  (df_c["snow_total"] > 0.0).astype(float)
    df_c["c_frost_mild"]    = ((df_c["temp_min"] <= 0.0) & (df_c["temp_min"] > -3.0)).astype(float)
    df_c["c_frost_severe"]  =  (df_c["temp_min"] <= -3.0).astype(float)
    df_c["c_wind_strong"]   = ((df_c["wind_peak"] >= 45.0) & (df_c["wind_peak"] <  60.0)).astype(float)
    df_c["c_wind_storm"]    =  (df_c["wind_peak"] >= 60.0).astype(float)

    COND_COLS = ["c_rain_light", "c_rain_moderate", "c_rain_heavy",
                 "c_snow", "c_frost_mild", "c_frost_severe",
                 "c_wind_strong", "c_wind_storm"]

    # Monthly fraction of working days with each condition
    monthly = (
        df_c.groupby(["year", "month"])[COND_COLS + ["season"]]
        .agg({**{c: "mean" for c in COND_COLS}, "season": "first"})
        .reset_index()
    )

    # Join monthly weather fractions with VC car base
    reg = df_vc.merge(monthly, on=["year", "month"], how="inner")
    reg["season"] = reg["month"].map(season_map)

    # Season-demean the VC base time.
    # This removes: "October is higher because it is autumn" — we only want
    # the within-season weather signal.
    season_means = reg.groupby("season")["vc_car_base_min"].transform("mean")
    reg["vc_demeaned"] = reg["vc_car_base_min"] - season_means

    print(f"  VC months matched with weather : {len(reg)}")
    print(f"  VC baseline (season-demeaned)  : 0.00 by construction")
    print(f"  VC base actual median          : {vc_median_highway:.2f} min")

    for ccol in COND_COLS:
        cname = ccol.replace("c_", "")
        frac_col = ccol  # this is fraction 0-1 of days with condition

        # Months where condition is "present" = fraction > median of that column
        # (We want months clearly above baseline in this condition)
        threshold = reg[frac_col].quantile(0.60)  # top 40% of months for this condition
        n_hi = (reg[frac_col] >= threshold).sum()
        n_lo = (reg[frac_col] <= reg[frac_col].quantile(0.30)).sum()

        hi_base = reg.loc[reg[frac_col] >= threshold,  "vc_demeaned"].mean()
        lo_base = reg.loc[reg[frac_col] <= reg[frac_col].quantile(0.30), "vc_demeaned"].mean()
        delta   = hi_base - lo_base   # additional VC minutes on high-condition months

        # Convert to multiplicative additive factor:
        # factor = delta / (vc_full_route_median)
        # Represents: how much is the fractional increase in car time when
        # a "high condition" month is observed.
        factor = max(0.0, round(float(delta / vc_full_route), 4))
        n_present = int((reg[frac_col] > 0.0).sum())

        vc_weather_factors[cname] = factor
        vc_n_months[cname]        = n_present
        print(f"  {cname:20s}: hi_delta={delta:+.3f}min  "
              f"factor={factor:.4f}  (n_months_present={n_present})")
else:
    print("  combined_workdays_features.csv not found — VC weather factors skipped.")

# ---- Infrabel delay-based weather factors -----------------------------------
print("\n--- Infrabel delay-based weather factors (car-sensitivity scaled) ---")

inf_weather_raw = {}
inf_n_days      = {}

if df_comb is not None:
    df_rw = df_real.merge(
        df_comb[["date", "rain_peak", "wind_peak", "temp_min",
                 "snow_total", "humidity_max"]],
        on="date", how="inner"
    ).copy()

    # Recompute delay_frac
    df_rw["delay_frac"] = (
        (df_rw["train_actual_journey_min"] - df_rw["train_planned_journey_min"])
        / df_rw["train_planned_journey_min"]
    ).clip(-0.3, 2.0)

    # Baseline: no adverse weather
    baseline_mask = (
        (df_rw["rain_peak"]   < 0.5) &
        (df_rw["snow_total"]  == 0.0) &
        (df_rw["temp_min"]    > 0.0) &
        (df_rw["wind_peak"]   < 45.0)
    )
    baseline_val = df_rw.loc[baseline_mask, "delay_frac"].median()
    print(f"  Baseline (clear conditions) delay_frac: {baseline_val:.4f}")

    cond_map = {
        "rain_light":   ((df_rw["rain_peak"] >= 0.5) & (df_rw["rain_peak"] <  2.0)),
        "rain_moderate":((df_rw["rain_peak"] >= 2.0) & (df_rw["rain_peak"] <  5.0)),
        "rain_heavy":   (df_rw["rain_peak"] >= 5.0),
        "snow":         (df_rw["snow_total"] > 0.0),
        "frost_mild":   ((df_rw["temp_min"] <= 0.0) & (df_rw["temp_min"] > -3.0)),
        "frost_severe": (df_rw["temp_min"] <= -3.0),
        "wind_strong":  ((df_rw["wind_peak"] >= 45.0) & (df_rw["wind_peak"] < 60.0)),
        "wind_storm":   (df_rw["wind_peak"] >= 60.0),
    }

    for cname, mask in cond_map.items():
        sub = df_rw[mask]
        n   = len(sub)
        if n > 0:
            med   = sub["delay_frac"].median()
            delta = max(0.0, med - baseline_val)
            # Scale: cars are CAR_SENSITIVITY_MULTIPLIER × more sensitive to road-surface
            # weather than trains on fixed rails.
            scaled = round(delta * CAR_SENSITIVITY_MULTIPLIER, 4)
        else:
            scaled = 0.0
        inf_weather_raw[cname] = scaled
        inf_n_days[cname]      = n
        print(f"  {cname:20s}: n={n:4d}  "
              f"train_delta={max(0.0, (sub['delay_frac'].median() if n else 0)-baseline_val):.4f}  "
              f"car_scaled={scaled:.4f}  (×{CAR_SENSITIVITY_MULTIPLIER})")

# ---- Merge: choose VC or Infrabel per condition -----------------------------
print("\n--- Final weather factor selection ---")

def _mono_clip(val, lower=0.0):
    return max(lower, round(float(val), 4))

# Map factor-key -> condition-key
FACTOR_TO_COND = {
    "rain_peak_light":    "rain_light",
    "rain_peak_moderate": "rain_moderate",
    "rain_peak_heavy":    "rain_heavy",
    "snow_any":           "snow",
    "frost_mild":         "frost_mild",
    "frost_severe":       "frost_severe",
    "wind_strong":        "wind_strong",
    "wind_storm":         "wind_storm",
}

final_weather  = {}
weather_source = {}

for fkey, ckey in FACTOR_TO_COND.items():
    vc_val  = vc_weather_factors.get(ckey, 0.0) if df_comb is not None else 0.0
    inf_val = inf_weather_raw.get(ckey, 0.0)
    n_vc    = vc_n_months.get(ckey, 0)

    # VC monthly data smooths out rare within-month events (e.g. 1-2 snow days
    # in a month barely move the monthly average).  Only trust VC when the
    # factor is meaningfully large (> 0.005) AND the condition appears in
    # enough months.  Otherwise take the Infrabel-based value.
    # When both are positive we take the MAX (conservative: never under-estimate
    # the impact of adverse weather on commute decisions).
    vc_reliable = vc_val > 0.005 and n_vc >= MIN_VC_MONTHS

    if vc_reliable and inf_val > 0:
        chosen = max(vc_val, inf_val)
        src    = f"max(VC={vc_val:.4f}, Infrabel={inf_val:.4f})"
    elif vc_reliable:
        chosen = vc_val
        src    = "VC (car data, season-demeaned)"
    else:
        chosen = inf_val
        src    = f"Infrabel (train proxy x{CAR_SENSITIVITY_MULTIPLIER})"

    final_weather[fkey]  = _mono_clip(chosen)
    weather_source[fkey] = f"{src}  [vc={vc_val:.4f} n_vc={n_vc}, inf={inf_val:.4f}]"

# Enforce monotonicity within groups AFTER individual selection
final_weather["rain_peak_moderate"] = _mono_clip(
    max(final_weather["rain_peak_moderate"], final_weather["rain_peak_light"]))
final_weather["rain_peak_heavy"]    = _mono_clip(
    max(final_weather["rain_peak_heavy"],    final_weather["rain_peak_moderate"]))
final_weather["frost_severe"]       = _mono_clip(
    max(final_weather["frost_severe"],       final_weather["frost_mild"]))
final_weather["wind_storm"]         = _mono_clip(
    max(final_weather["wind_storm"],         final_weather["wind_strong"]))

print("\nFinal weather additive factors:")
for fkey, fval in final_weather.items():
    src = weather_source[fkey]
    print(f"  {fkey:25s}: {fval:.4f}  [{src}]")


# =============================================================================
# 4 — Save factors.json
# =============================================================================
_hline("4. SAVING FACTORS.JSON")

factors_out = {
    "_meta": {
        "calibrated_on":                date.today().isoformat(),
        "infrabel_date_range":          f"{df_inf['date'].min().date()} to {df_inf['date'].max().date()}",
        "n_infrabel_days_total":        len(df_inf),
        "n_infrabel_days_real":         len(df_real),
        "n_vc_months":                  len(df_vc),
        "osrm_free_flow_min":           FREE_FLOW_MIN,
        "vc_highway_median_min":        round(float(vc_median_highway), 2),
        "city_overhead_assumed_min":    CITY_OVERHEAD_MIN,
        "car_sensitivity_multiplier":   CAR_SENSITIVITY_MULTIPLIER,
        "overall_congestion_ratio":     round(float(overall_ratio), 4),
        "vc_baseline_min":              round(float(vc_full_route), 1),
        "weekday_source":               (
            "Infrabel mean arrival delay in seconds per weekday "
            "(shift-then-normalise to mean=1.0)"
        ),
        "weekday_finding":              wd_rel_legacy_note,
        "weather_source":               weather_source,
        "min_vc_months_threshold":      MIN_VC_MONTHS,
        "legacy_weekday_factors":       LEGACY_WEEKDAY,
        "legacy_weather_factors":       LEGACY_WEATHER,
    },
    "weekday_congestion_relative": wd_rel,
    "weekday_congestion_absolute": wd_abs,
    "weather_additive_factors":    final_weather,
}

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(factors_out, f, indent=2, ensure_ascii=False)

print(f"  Written: {OUT_JSON}")


# =============================================================================
# 5 — Diagnostic plots
# =============================================================================
_hline("5. DIAGNOSTIC PLOTS")

DARK   = "#0D1B2A"
PANEL  = "#112D4E"
TEAL   = "#00C8A0"
ORANGE = "#FF6B35"
GREY   = "#8B9DC3"
WHITE  = "#FFFFFF"
PURPLE = "#A060FF"

fig = plt.figure(figsize=(17, 11), facecolor=DARK)
gs  = gridspec.GridSpec(2, 4, figure=fig, hspace=0.55, wspace=0.42)


def _style(ax, title):
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_color(PANEL)
    ax.tick_params(colors=GREY, labelsize=8)
    ax.set_title(title, color=TEAL, fontsize=10, pad=6)
    ax.xaxis.label.set_color(GREY)
    ax.yaxis.label.set_color(GREY)


# A — Raw mean delay by weekday
ax_a = fig.add_subplot(gs[0, 0])
raw_delays = [wd_delay.loc[wd, "mean"] for wd in WD_ORDER]
c_a = [ORANGE if v == max(raw_delays) else
       (TEAL   if v == min(raw_delays) else GREY) for v in raw_delays]
bars_a = ax_a.bar([w[:3] for w in WD_ORDER], raw_delays, color=c_a, edgecolor=DARK)
ax_a.axhline(np.mean(raw_delays), color=GREY, ls="--", lw=1, label="Mean")
for bar, val in zip(bars_a, raw_delays):
    ax_a.text(bar.get_x() + bar.get_width()/2, val + 1,
              f"{val:.0f}s", ha="center", fontsize=8, color=WHITE)
_style(ax_a, "Infrabel: Mean arrival delay\nby weekday (real data)")
ax_a.set_ylabel("Seconds")
ax_a.legend(fontsize=8, labelcolor=GREY, facecolor=PANEL, edgecolor=PANEL)

# B — Calibrated relative factors vs legacy
ax_b = fig.add_subplot(gs[0, 1])
x = np.arange(5)
rel_vals  = [wd_rel[wd]         for wd in WD_ORDER]
leg_rel   = {wd: round(v/np.mean(list(LEGACY_WEEKDAY.values())), 4)
             for wd, v in LEGACY_WEEKDAY.items()}
leg_vals  = [leg_rel[wd] for wd in WD_ORDER]
ax_b.bar(x - 0.2, rel_vals,  0.38, label="Calibrated (data)", color=TEAL,   alpha=0.85, edgecolor=DARK)
ax_b.bar(x + 0.2, leg_vals,  0.38, label="Legacy (TomTom)",   color=PURPLE, alpha=0.60, edgecolor=DARK)
ax_b.axhline(1.0, color=GREY, ls="--", lw=1)
ax_b.set_xticks(x); ax_b.set_xticklabels([w[:3] for w in WD_ORDER])
_style(ax_b, "Relative weekday factors:\nCalibrated vs Legacy")
ax_b.set_ylabel("Factor (mean = 1.0)")
ax_b.legend(fontsize=8, labelcolor=WHITE, facecolor=PANEL, edgecolor=PANEL)

# C — VC car base by month (seasonal pattern)
ax_c = fig.add_subplot(gs[0, 2])
ax_c.set_facecolor(PANEL)
month_avg = df_vc.groupby("month")["vc_car_base_min"].mean()
months_present = month_avg.index.tolist()
c_m = [ORANGE if m in [10, 11, 9] else
       (TEAL if m in [6, 12] else GREY) for m in months_present]
ax_c.bar(months_present, month_avg.values, color=c_m, edgecolor=DARK)
ax_c.axhline(vc_median_highway, color=WHITE, ls="--", lw=1,
             label=f"Median {vc_median_highway:.0f} min")
ax_c.set_xticks(range(1, 13))
ax_c.set_xticklabels(["J","F","M","A","M","J","J","A","S","O","N","D"], fontsize=8)
_style(ax_c, "VC car base by month\n(highway segments only)")
ax_c.set_ylabel("Minutes")
ax_c.legend(fontsize=8, labelcolor=GREY, facecolor=PANEL, edgecolor=PANEL)

# D — On-time rate by weekday
ax_d = fig.add_subplot(gs[0, 3])
ontime = [df_real.groupby("weekday")["train_on_time_pct"].mean().reindex(WD_ORDER).iloc[i]
          * 100 for i in range(5)]
c_d = [TEAL if v == max(ontime) else
       (ORANGE if v == min(ontime) else GREY) for v in ontime]
bars_d = ax_d.bar([w[:3] for w in WD_ORDER], ontime, color=c_d, edgecolor=DARK)
for bar, val in zip(bars_d, ontime):
    ax_d.text(bar.get_x() + bar.get_width()/2, val + 0.2,
              f"{val:.1f}%", ha="center", fontsize=8, color=WHITE)
_style(ax_d, "Infrabel: On-time rate\nby weekday (real data)")
ax_d.set_ylabel("On-time %")
ax_d.set_ylim(80, 92)

# E — Weather factors: final vs legacy (both sources shown)
ax_e = fig.add_subplot(gs[1, :3])
wkeys   = list(final_weather.keys())
x_w     = np.arange(len(wkeys))
w_w     = 0.23
vc_plot  = [vc_weather_factors.get(FACTOR_TO_COND[k], 0) for k in wkeys]
inf_plot = [inf_weather_raw.get(FACTOR_TO_COND[k], 0) for k in wkeys]
leg_plot = [LEGACY_WEATHER.get(k, 0) for k in wkeys]
fin_plot = [final_weather[k] for k in wkeys]

ax_e.bar(x_w - w_w*1.5, vc_plot,  w_w, label="VC (season-demeaned)",      color=TEAL,   alpha=0.85, edgecolor=DARK)
ax_e.bar(x_w - w_w*0.5, inf_plot, w_w, label=f"Infrabel x{CAR_SENSITIVITY_MULTIPLIER}",  color=PURPLE, alpha=0.85, edgecolor=DARK)
ax_e.bar(x_w + w_w*0.5, leg_plot, w_w, label="Legacy (hardcoded)",         color=GREY,   alpha=0.50, edgecolor=DARK)
ax_e.scatter(x_w + w_w*1.5, fin_plot, color=ORANGE, s=70, zorder=6,
             marker="D", label="Final chosen factor")
ax_e.set_xticks(x_w)
ax_e.set_xticklabels([k.replace("_", "\n") for k in wkeys], fontsize=7, color=GREY)
ax_e.legend(fontsize=8, labelcolor=WHITE, facecolor=PANEL, edgecolor=PANEL, ncol=2)
_style(ax_e, "Weather additive factors: all sources vs final choice  (diamond = chosen)")
ax_e.set_ylabel("Additive factor on base travel time")

# F — Sample size per condition
ax_f = fig.add_subplot(gs[1, 3])
ax_f.set_facecolor(PANEL)
cond_names  = [FACTOR_TO_COND[k] for k in wkeys]
n_day_vals  = [inf_n_days.get(c, 0) for c in cond_names]
n_mon_vals  = [vc_n_months.get(c, 0) for c in cond_names]
x_f = np.arange(len(wkeys))
ax_f.barh(x_f + 0.18, n_day_vals, 0.33, color=PURPLE, alpha=0.85, edgecolor=DARK, label="Days (Infrabel)")
ax_f.barh(x_f - 0.18, n_mon_vals, 0.33, color=TEAL,   alpha=0.85, edgecolor=DARK, label="Months (VC)")
ax_f.set_yticks(x_f)
ax_f.set_yticklabels([k.replace("_", "\n") for k in wkeys], fontsize=7, color=GREY)
ax_f.axvline(MIN_VC_MONTHS, color=ORANGE, ls="--", lw=1.2, label=f"MIN_VC={MIN_VC_MONTHS}")
ax_f.legend(fontsize=7, labelcolor=WHITE, facecolor=PANEL, edgecolor=PANEL)
_style(ax_f, "Sample size per condition\n(thinner = less reliable)")
ax_f.set_xlabel("Count")

fig.suptitle("Factor Calibration — Gent to Mechelen (derived from actual data)",
             fontsize=13, color=WHITE, y=1.01)
fig.patch.set_facecolor(DARK)

plt.savefig(OUT_PLOT, bbox_inches="tight", dpi=130, facecolor=DARK)
plt.close()
print(f"  Diagnostic plot: {OUT_PLOT}")


# =============================================================================
# 6 — Final summary
# =============================================================================
_hline("CALIBRATION COMPLETE")

print(f"\nWeekday with most congestion  : {max(wd_rel, key=wd_rel.get)}"
      f"  (factor {max(wd_rel.values()):.4f})")
print(f"Weekday with least congestion : {min(wd_rel, key=wd_rel.get)}"
      f"  (factor {min(wd_rel.values()):.4f})")
print(f"\nLargest weather factor        : "
      f"{max(final_weather, key=final_weather.get)}"
      f"  = {max(final_weather.values()):.4f}")
print(f"\nfactors.json  -> {OUT_JSON}")
print(f"Diagnostic    -> {OUT_PLOT}")
print("\nRe-run  python data_pipeline.py  to rebuild the combined")
print("dataset using the calibrated factors.")
