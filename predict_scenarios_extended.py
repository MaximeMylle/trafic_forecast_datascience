"""
predict_scenarios_extended.py
==============================
Comprehensive scenario analysis for the Gent → Mechelen commute route.
Uses calibrated VC-based factors (factors.json) directly — no ML model black-box.

Decision logic (explicit and transparent):
  1. THUISWERKEN  →  weather_risk ≥ 5
                      (severe snow, heavy rain + wind, or storm conditions)
  2. TREIN        →  car_vc_est_min > train_sched_min + CAR_PREF_BUFFER_MIN
  3. AUTO         →  otherwise

Run with:
    python predict_scenarios_extended.py

Outputs:
  data/processed/scenarios_extended.png       — main multi-panel chart
  data/processed/scenarios_extended_matrix.png — weekday × month heatmap
  data/processed/scenarios_extended.csv       — full results table
"""

import subprocess, sys, json
from pathlib import Path
from itertools import product

for pkg in ["numpy", "pandas", "matplotlib", "seaborn"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg],
                              stdout=subprocess.DEVNULL)

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

ROOT  = Path(__file__).parent
PROC  = ROOT / "data" / "processed"

# =============================================================================
# 1 — LOAD CALIBRATED FACTORS
# =============================================================================

with open(ROOT / "factors.json") as f:
    FACTORS = json.load(f)

WD_REL      = FACTORS["weekday_congestion_relative"]   # Mon–Fri, mean = 1.0
WF_ADD      = FACTORS["weather_additive_factors"]      # fractional additive
VC_BASELINE = FACTORS["_meta"]["vc_baseline_min"]       # 62.7 min (highway + city)

WD_NAMES    = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}
WD_NL       = {0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag", 4: "Vrijdag"}
MONTH_NL    = {1:"Jan",2:"Feb",3:"Mrt",4:"Apr",5:"Mei",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}

# Train scheduled time: read from combined CSV, otherwise use hardcoded fallback
_comb = PROC / "combined_workdays_features.csv"
if _comb.exists():
    _df = pd.read_csv(_comb, usecols=["train_sched_min"])
    TRAIN_SCHED_MIN = float(_df["train_sched_min"].median())
else:
    TRAIN_SCHED_MIN = 58.0   # fallback
CAR_PREF_BUFFER_MIN = 10     # car must be at most this much slower than train

THRESHOLD_MIN = TRAIN_SCHED_MIN + CAR_PREF_BUFFER_MIN

print(f"VC baseline car time (mean)  : {VC_BASELINE:.1f} min")
print(f"Train scheduled time          : {TRAIN_SCHED_MIN:.0f} min")
print(f"Car decision threshold        : {THRESHOLD_MIN:.0f} min  (train + {CAR_PREF_BUFFER_MIN} min buffer)")
print()

# =============================================================================
# 2 — CORE FUNCTIONS
# =============================================================================

def weather_risk_score(rain_peak: float, wind_peak: float, temp_min: float,
                       snow_total: float, humidity_max: float) -> int:
    """Composite weather risk 0-9.  ≥5 triggers work-from-home."""
    return (
        int(rain_peak  >= 2.0)  * 2   # moderate+ rain
        + int(wind_peak >= 45.0) * 2  # strong wind
        + int(temp_min  <= 0.0)  * 1  # frost
        + int(snow_total > 0.0)  * 3  # any snow
        + int(humidity_max >= 97)* 1  # dense fog proxy
    )


def car_vc_estimate(weekday_num: int, rain_peak: float, wind_peak: float,
                    temp_min: float, snow_total: float, **_) -> float:
    """Estimate car travel time using calibrated VC factors."""
    wd_name  = WD_NAMES[weekday_num]
    wd_mult  = WD_REL[wd_name]
    base     = VC_BASELINE * wd_mult

    # Add weather contributions (additive on VC_BASELINE)
    if rain_peak >= 5.0:
        base += VC_BASELINE * WF_ADD["rain_peak_heavy"]
    elif rain_peak >= 2.0:
        base += VC_BASELINE * WF_ADD["rain_peak_moderate"]
    elif rain_peak >= 0.5:
        base += VC_BASELINE * WF_ADD["rain_peak_light"]

    if snow_total > 0:
        base += VC_BASELINE * WF_ADD["snow_any"]

    if temp_min <= -3.0:
        base += VC_BASELINE * WF_ADD["frost_severe"]
    elif temp_min <= 0.0:
        base += VC_BASELINE * WF_ADD["frost_mild"]

    if wind_peak >= 60.0:
        base += VC_BASELINE * WF_ADD["wind_storm"]
    elif wind_peak >= 45.0:
        base += VC_BASELINE * WF_ADD["wind_strong"]

    return round(base, 1)


def recommend(car_min: float, risk: int, is_public_holiday: bool = False) -> str:
    """
    Three-way decision:
      THUISWERKEN  — risk ≥ 5  (heavy conditions make both modes unreliable)
      TREIN        — car > train + buffer
      AUTO         — otherwise
    """
    if is_public_holiday:
        return "thuiswerken"
    if risk >= 5:
        return "thuiswerken"
    if car_min > THRESHOLD_MIN:
        return "trein"
    return "auto"


def risk_label(risk: int, car_min: float) -> str:
    if risk >= 5 or car_min >= 90:
        return "rood"
    if risk >= 2 or car_min >= THRESHOLD_MIN:
        return "oranje"
    return "groen"


# =============================================================================
# 3 — TYPICAL MONTHLY WEATHER (commute window averages from Open-Meteo archive)
# =============================================================================
# Values represent the *median typical* commute day for each month.
# Separate "good", "bad", and "extreme" variants are generated per month.

MONTHLY_TYPICAL = {
    #        rain_pk  wind_pk  temp_mn  snow  hum_max
    1:  dict(rain_peak=1.8,  wind_peak=35, temp_min=1.0,  snow_total=0.0, humidity_max=88),
    2:  dict(rain_peak=1.2,  wind_peak=30, temp_min=0.5,  snow_total=0.0, humidity_max=84),
    3:  dict(rain_peak=1.0,  wind_peak=28, temp_min=3.0,  snow_total=0.0, humidity_max=78),
    4:  dict(rain_peak=0.9,  wind_peak=22, temp_min=6.0,  snow_total=0.0, humidity_max=70),
    5:  dict(rain_peak=0.7,  wind_peak=19, temp_min=9.0,  snow_total=0.0, humidity_max=65),
    6:  dict(rain_peak=0.6,  wind_peak=17, temp_min=12.0, snow_total=0.0, humidity_max=62),
    7:  dict(rain_peak=0.8,  wind_peak=15, temp_min=15.0, snow_total=0.0, humidity_max=60),
    8:  dict(rain_peak=0.7,  wind_peak=14, temp_min=14.0, snow_total=0.0, humidity_max=58),
    9:  dict(rain_peak=0.8,  wind_peak=20, temp_min=9.0,  snow_total=0.0, humidity_max=68),
    10: dict(rain_peak=1.3,  wind_peak=28, temp_min=5.0,  snow_total=0.0, humidity_max=79),
    11: dict(rain_peak=1.5,  wind_peak=35, temp_min=2.0,  snow_total=0.0, humidity_max=85),
    12: dict(rain_peak=1.7,  wind_peak=34, temp_min=0.5,  snow_total=0.0, humidity_max=87),
}

# Weather condition variants: (label, delta_dict)
WEATHER_VARIANTS = [
    ("Droog / zonnig",    dict(rain_peak=0.0, wind_peak=12, temp_min=None,  snow_total=0.0, humidity_max=60)),
    ("Lichte regen",      dict(rain_peak=0.9, wind_peak=20, temp_min=None,  snow_total=0.0, humidity_max=82)),
    ("Matige regen",      dict(rain_peak=2.5, wind_peak=30, temp_min=None,  snow_total=0.0, humidity_max=90)),
    ("Zware regen",       dict(rain_peak=5.5, wind_peak=38, temp_min=None,  snow_total=0.0, humidity_max=95)),
    ("Zware regen + wind",dict(rain_peak=5.5, wind_peak=55, temp_min=None,  snow_total=0.0, humidity_max=96)),
    ("Sneeuw",            dict(rain_peak=0.5, wind_peak=20, temp_min=-1.5,  snow_total=3.0, humidity_max=96)),
    ("IJzel (vorst)",     dict(rain_peak=0.0, wind_peak=10, temp_min=-4.0,  snow_total=0.0, humidity_max=88)),
    ("Storm (code rood)", dict(rain_peak=4.0, wind_peak=85, temp_min=None,  snow_total=0.0, humidity_max=97)),
]

SCHOOL_HOLIDAY_MONTHS = {7, 8}   # July & August = summer holiday

# =============================================================================
# 4 — BUILD SCENARIO LIST  (5 weekdays × 12 months × 8 weather variants = 480)
# =============================================================================

scenarios = []

for wd_num, month, (wlabel, woverride) in product(range(5), range(1, 13), WEATHER_VARIANTS):
    base    = dict(MONTHLY_TYPICAL[month])   # copy
    # Apply temperature from typical month unless override specifies a value
    if woverride["temp_min"] is not None:
        base["temp_min"] = woverride["temp_min"]
    # Override weather values
    for k, v in woverride.items():
        if k != "temp_min" or v is not None:
            base[k] = v

    is_school = month in SCHOOL_HOLIDAY_MONTHS
    risk      = weather_risk_score(**base)
    car_min   = car_vc_estimate(wd_num, **base)
    mode      = recommend(car_min, risk)
    rl        = risk_label(risk, car_min)

    # Weekend factor boost in summer holiday months (school but not empty)
    if is_school:
        # School holidays: remove weekday factor — treat as school-holiday flat
        # (VC data shows ~30% lower base in Jul/Aug; model already handles this via
        #  is_school_holiday feature, but VC data lacks Jul/Aug measurements.
        # We apply a 0.85 discount to VC baseline for summer months.)
        car_min = round(car_min * 0.85, 1)
        mode    = recommend(car_min, risk)
        rl      = risk_label(risk, car_min)

    scenarios.append(dict(
        weekday_num   = wd_num,
        weekday_nl    = WD_NL[wd_num],
        month         = month,
        month_nl      = MONTH_NL[month],
        weather_label = wlabel,
        is_school_holiday = is_school,
        **{k: base[k] for k in ["rain_peak","wind_peak","temp_min","snow_total","humidity_max"]},
        weather_risk  = risk,
        car_vc_min    = car_min,
        train_sched_min = TRAIN_SCHED_MIN,
        mode          = mode,
        risk_label    = rl,
    ))

# Add public holidays (no commute)
for month in [1, 5, 7, 8, 11]:
    scenarios.append(dict(
        weekday_num=0, weekday_nl="Maandag", month=month, month_nl=MONTH_NL[month],
        weather_label="Feestdag", is_school_holiday=False,
        rain_peak=0.5, wind_peak=15, temp_min=8, snow_total=0, humidity_max=75,
        weather_risk=0, car_vc_min=None, train_sched_min=TRAIN_SCHED_MIN,
        mode="thuiswerken", risk_label="groen",
    ))

df = pd.DataFrame(scenarios)
print(f"Total scenarios generated : {len(df)}")

# =============================================================================
# 5 — SUMMARY STATISTICS
# =============================================================================

print("\n" + "=" * 65)
print("MODE DISTRIBUTION (ALL SCENARIOS)")
print("=" * 65)
vc = df["mode"].value_counts()
for mode, cnt in vc.items():
    print(f"  {mode:<14}: {cnt:>4}  ({cnt/len(df)*100:.1f}%)")

print("\nMODE BY WEEKDAY:")
cross_wd = pd.crosstab(df["weekday_nl"], df["mode"])
cross_wd = cross_wd.reindex(list(WD_NL.values()))
print(cross_wd.to_string())

print("\nMODE BY WEATHER CONDITION:")
cross_w = pd.crosstab(df["weather_label"], df["mode"])
print(cross_w.to_string())

print("\nMODE BY MONTH:")
cross_m = pd.crosstab(df["month_nl"], df["mode"])
print(cross_m.to_string())

# =============================================================================
# 6 — VISUALISATION
# =============================================================================

DARK   = "#0D1B2A"
PANEL  = "#112D4E"
TEAL   = "#00C8A0"
ORANGE = "#FF6B35"
GREY   = "#8B9DC3"
WHITE  = "#FFFFFF"
PURPLE = "#A060FF"
RED    = "#E53935"

MODE_COLORS = {"auto": "#1565c0", "trein": ORANGE, "thuiswerken": "#616161"}

# --------------------------------------------------------------------------
# 6a  — Stacked bar: weekday × weather condition coloured by mode
# --------------------------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(20, 14), facecolor=DARK)
fig.patch.set_facecolor(DARK)
plt.subplots_adjust(hspace=0.42, wspace=0.38)

def _style(ax, title):
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values():
        sp.set_color(PANEL)
    ax.tick_params(colors=GREY, labelsize=9)
    ax.set_title(title, color=TEAL, fontsize=11, pad=8)
    ax.xaxis.label.set_color(GREY)
    ax.yaxis.label.set_color(GREY)

# ── A: mode distribution overall ────────────────────────────────────────────
ax = axes[0, 0]
mode_order  = ["auto", "trein", "thuiswerken"]
mode_labels = ["Auto", "Trein", "Thuiswerken"]
mode_counts = [vc.get(m, 0) for m in mode_order]
bars = ax.barh(mode_labels, mode_counts,
               color=[MODE_COLORS[m] for m in mode_order],
               edgecolor=DARK, height=0.5)
for bar, cnt in zip(bars, mode_counts):
    pct = cnt / len(df) * 100
    ax.text(cnt + 1, bar.get_y() + bar.get_height()/2,
            f"{cnt}  ({pct:.1f}%)", va="center", fontsize=11, color=WHITE)
ax.set_xlim(0, max(mode_counts) * 1.5)
ax.set_xlabel("Aantal scenario's")
_style(ax, f"Aanbevolen modus\n({len(df)} scenario's totaal)")
ax.invert_yaxis()
ax.axvline(len(df)/3, color=GREY, ls=":", lw=0.8)

# ── B: mode by weekday ────────────────────────────────────────────────────
ax = axes[0, 1]
wd_order = list(WD_NL.values())
x = np.arange(len(wd_order))
w = 0.25
bottom_auto = np.zeros(5)
bottom_trein = np.zeros(5)
for i, mode in enumerate(mode_order):
    cnts = [df[(df["weekday_nl"] == wd) & (df["mode"] == mode)].shape[0]
            for wd in wd_order]
    if mode == "auto":
        ax.bar(x, cnts, w*3, label=mode.capitalize(),
               color=MODE_COLORS[mode], edgecolor=DARK)
    elif mode == "trein":
        auto_cnts = [df[(df["weekday_nl"] == wd) & (df["mode"] == "auto")].shape[0]
                     for wd in wd_order]
        ax.bar(x, cnts, w*3, bottom=auto_cnts, label=mode.capitalize(),
               color=MODE_COLORS[mode], edgecolor=DARK)
    else:
        auto_trein = [
            df[(df["weekday_nl"] == wd) & (df["mode"].isin(["auto","trein"]))].shape[0]
            for wd in wd_order]
        ax.bar(x, cnts, w*3, bottom=auto_trein, label=mode.capitalize(),
               color=MODE_COLORS[mode], edgecolor=DARK)

ax.set_xticks(x)
ax.set_xticklabels([w[:2] for w in wd_order])
ax.set_ylabel("Aantal scenario's")
ax.legend(fontsize=9, labelcolor=WHITE, facecolor=PANEL, edgecolor=PANEL)
_style(ax, "Aanbevolen modus per weekdag")

# ── C: mode by weather condition ────────────────────────────────────────────
ax = axes[1, 0]
wlabels = [w for w, _ in WEATHER_VARIANTS]
x = np.arange(len(wlabels))
for mode in mode_order:
    cnts = [df[(df["weather_label"] == wl) & (df["mode"] == mode)].shape[0]
            for wl in wlabels]
    if mode == "auto":
        ax.bar(x, cnts, 0.6, label=mode.capitalize(),
               color=MODE_COLORS[mode], edgecolor=DARK)
    elif mode == "trein":
        auto_cnts = [df[(df["weather_label"] == wl) & (df["mode"] == "auto")].shape[0]
                     for wl in wlabels]
        ax.bar(x, cnts, 0.6, bottom=auto_cnts, label=mode.capitalize(),
               color=MODE_COLORS[mode], edgecolor=DARK)
    else:
        auto_trein = [
            df[(df["weather_label"] == wl) & (df["mode"].isin(["auto","trein"]))].shape[0]
            for wl in wlabels]
        ax.bar(x, cnts, 0.6, bottom=auto_trein, label=mode.capitalize(),
               color=MODE_COLORS[mode], edgecolor=DARK)

ax.set_xticks(x)
ax.set_xticklabels([l.replace(" + ", "\n+\n").replace(" / ", "\n/\n")
                    for l in wlabels], fontsize=7.5)
ax.set_ylabel("Aantal scenario's")
ax.legend(fontsize=9, labelcolor=WHITE, facecolor=PANEL, edgecolor=PANEL)
_style(ax, "Aanbevolen modus per weersconditie")

# ── D: car vs train time — scatter ───────────────────────────────────────────
ax = axes[1, 1]
df_v = df[df["car_vc_min"].notna()].copy()
colors = [MODE_COLORS[m] for m in df_v["mode"]]
ax.scatter(df_v["car_vc_min"], [TRAIN_SCHED_MIN] * len(df_v),
           c=colors, alpha=0.25, s=25, zorder=2)
ax.axvline(THRESHOLD_MIN, color=WHITE, lw=2, ls="--", zorder=3,
           label=f"Drempel: {THRESHOLD_MIN:.0f} min")
ax.axvline(TRAIN_SCHED_MIN, color=GREY, lw=1, ls=":", zorder=3,
           label=f"Trein: {TRAIN_SCHED_MIN:.0f} min")

# Histogram of car times coloured by mode
ax2 = ax.twinx()
ax2.set_facecolor(PANEL)
for mode, color in MODE_COLORS.items():
    sub = df_v[df_v["mode"] == mode]["car_vc_min"]
    if len(sub) > 0:
        ax2.hist(sub, bins=20, color=color, alpha=0.35, edgecolor="none")
ax2.set_ylabel("Frequentie", color=GREY, fontsize=9)
ax2.tick_params(colors=GREY)

ax.set_xlabel("Geschatte auto-reistijd VC (min)")
ax.set_xlim(left=40)
ax.legend(fontsize=9, labelcolor=WHITE, facecolor=PANEL, edgecolor=PANEL)
_style(ax, "Spreiding auto-reistijden per aanbevolen modus")

patches = [mpatches.Patch(color=v, label=k.capitalize()) for k, v in MODE_COLORS.items()]
fig.legend(handles=patches, loc="upper center", ncol=3,
           fontsize=11, labelcolor=WHITE, facecolor=PANEL, edgecolor=PANEL,
           bbox_to_anchor=(0.5, 0.98))

fig.suptitle(
    "Uitgebreide Scenario-Analyse — Gent → Mechelen (480+ scenario's)\n"
    f"Thuiswerken: weerrisico ≥ 5  |  Trein: auto > {THRESHOLD_MIN:.0f} min  |  Auto: anders",
    color=WHITE, fontsize=13, fontweight="bold", y=1.04
)

out1 = PROC / "scenarios_extended.png"
plt.savefig(out1, bbox_inches="tight", dpi=130, facecolor=DARK)
plt.close()
print(f"\nHoofdplot: {out1}")

# --------------------------------------------------------------------------
# 6b  — Heatmap: weekday (rows) × month (cols) per weather condition
# --------------------------------------------------------------------------
# For the heatmap we use the "Matige regen" scenario as a representative average.

MODE_NUM = {"auto": 0, "trein": 1, "thuiswerken": 2}
MODE_LABELS_MAP = {0: "Auto", 1: "Trein", 2: "Thuiswerken"}

n_cond  = len(WEATHER_VARIANTS)
n_cols  = 4
n_rows  = (n_cond + n_cols - 1) // n_cols
fig2, axes2 = plt.subplots(n_rows, n_cols, figsize=(22, 5 * n_rows), facecolor=DARK)
fig2.patch.set_facecolor(DARK)
plt.subplots_adjust(hspace=0.55, wspace=0.35)

CMAP = plt.matplotlib.colors.ListedColormap(
    [MODE_COLORS["auto"], MODE_COLORS["trein"], MODE_COLORS["thuiswerken"]]
)

for idx, (wlabel, _) in enumerate(WEATHER_VARIANTS):
    row_i, col_i = divmod(idx, n_cols)
    ax = axes2[row_i, col_i]
    ax.set_facecolor(PANEL)

    sub = df[df["weather_label"] == wlabel]
    pivot = (
        sub.groupby(["weekday_nl", "month"])["mode"]
        .first()
        .map(MODE_NUM)
        .unstack("month")
        .reindex(index=list(WD_NL.values()), columns=range(1, 13))
    )

    im = ax.imshow(pivot.values, cmap=CMAP, vmin=0, vmax=2, aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(list(MONTH_NL.values()), fontsize=8, color=GREY)
    ax.set_yticks(range(5))
    ax.set_yticklabels([w[:2] for w in WD_NL.values()], fontsize=8, color=GREY)
    ax.set_title(wlabel, color=TEAL, fontsize=10, pad=5)

    for sp in ax.spines.values():
        sp.set_color(PANEL)

# Hide unused subplots
for idx in range(n_cond, n_rows * n_cols):
    row_i, col_i = divmod(idx, n_cols)
    axes2[row_i, col_i].set_visible(False)

# Colourbar legend
from matplotlib.cm import ScalarMappable
sm = ScalarMappable(cmap=CMAP, norm=plt.Normalize(vmin=-0.5, vmax=2.5))
sm.set_array([])
cbar = fig2.colorbar(sm, ax=axes2, orientation="vertical",
                     fraction=0.012, pad=0.02, ticks=[0, 1, 2])
cbar.ax.set_yticklabels(["Auto", "Trein", "Thuiswerken"],
                         color=WHITE, fontsize=10)
cbar.ax.yaxis.set_tick_params(color=WHITE)
for sp in cbar.ax.spines.values():
    sp.set_color(PANEL)

fig2.suptitle(
    "Aanbevolen modus per weekdag × maand × weersconditie\n"
    f"(Blauw = Auto  |  Oranje = Trein  |  Grijs = Thuiswerken)",
    color=WHITE, fontsize=14, fontweight="bold"
)

out2 = PROC / "scenarios_extended_matrix.png"
plt.savefig(out2, bbox_inches="tight", dpi=130, facecolor=DARK)
plt.close()
print(f"Matrix heatmap: {out2}")

# --------------------------------------------------------------------------
# 6c  — Clear "when does each mode win?" bar chart per weather condition
#       This is the key chart for the presentation
# --------------------------------------------------------------------------
fig3, ax3 = plt.subplots(figsize=(14, 7), facecolor=DARK)
ax3.set_facecolor(PANEL)
for sp in ax3.spines.values():
    sp.set_color(PANEL)

wlabels_ordered = [w for w, _ in WEATHER_VARIANTS]
x = np.arange(len(wlabels_ordered))
w = 0.25

auto_pct   = []
trein_pct  = []
thuis_pct  = []
for wl in wlabels_ordered:
    sub = df[df["weather_label"] == wl]
    n   = len(sub)
    auto_pct.append(  sub[sub["mode"] == "auto"].shape[0]        / n * 100)
    trein_pct.append( sub[sub["mode"] == "trein"].shape[0]       / n * 100)
    thuis_pct.append( sub[sub["mode"] == "thuiswerken"].shape[0] / n * 100)

ax3.bar(x - w, auto_pct,  w*0.9, label="Auto",         color=MODE_COLORS["auto"],        edgecolor=DARK)
ax3.bar(x,     trein_pct, w*0.9, label="Trein",        color=MODE_COLORS["trein"],       edgecolor=DARK)
ax3.bar(x + w, thuis_pct, w*0.9, label="Thuiswerken",  color=MODE_COLORS["thuiswerken"], edgecolor=DARK)

for xi, (a, t, h) in enumerate(zip(auto_pct, trein_pct, thuis_pct)):
    if a  > 3: ax3.text(xi - w, a + 1,  f"{a:.0f}%",  ha="center", fontsize=8, color=WHITE)
    if t  > 3: ax3.text(xi,     t + 1,  f"{t:.0f}%",  ha="center", fontsize=8, color=WHITE)
    if h  > 3: ax3.text(xi + w, h + 1,  f"{h:.0f}%",  ha="center", fontsize=8, color=WHITE)

ax3.set_xticks(x)
ax3.set_xticklabels(wlabels_ordered, rotation=18, ha="right", fontsize=9, color=GREY)
ax3.set_ylabel("% van scenario's", fontsize=11, color=GREY)
ax3.tick_params(colors=GREY)
ax3.set_ylim(0, 115)
ax3.axhline(50, color=GREY, ls=":", lw=1)
ax3.legend(fontsize=10, labelcolor=WHITE, facecolor=DARK, edgecolor=DARK)
ax3.set_title(
    "Aanbevolen modus per weersconditie (% van alle weekdag × maand combinaties)",
    color=TEAL, fontsize=12, pad=10
)

out3 = PROC / "scenarios_extended_by_weather.png"
plt.savefig(out3, bbox_inches="tight", dpi=130, facecolor=DARK)
plt.close()
print(f"Per-weather chart: {out3}")

# =============================================================================
# 7 — SAVE CSV
# =============================================================================

df.to_csv(PROC / "scenarios_extended.csv", index=False)
print(f"CSV: {PROC / 'scenarios_extended.csv'}")

# =============================================================================
# 8 — PRINT CLEAR DECISION RULES SUMMARY
# =============================================================================

print("\n" + "=" * 65)
print("DREMPEL-SAMENVATTING (basis voor presentatie-slide)")
print("=" * 65)
print(f"\n  VC Baseline auto-tijd (gemiddeld)  : {VC_BASELINE:.1f} min")
print(f"  Trein geplande reistijd            : {TRAIN_SCHED_MIN:.0f} min")
print(f"  Auto-voorkeursbuffer               : {CAR_PREF_BUFFER_MIN} min")
print(f"  Auto-drempel                       : {THRESHOLD_MIN:.0f} min")
print()
print("  WANNEER AUTO?")
print(f"    Auto-tijd <= {THRESHOLD_MIN:.0f} min  EN  weerrisico < 5")
print()
print("  WANNEER TREIN?")
print(f"    Auto-tijd > {THRESHOLD_MIN:.0f} min  EN  weerrisico < 5")
print()
print("  WANNEER THUISWERKEN?")
print("    Weerrisico ≥ 5  (= zware omstandigheden)")
print("    Samenstelling risicoscore:")
print("      • Regen ≥ 2 mm/u                  → +2 punten")
print("      • Wind ≥ 45 km/h                  → +2 punten")
print("      • Nachtvorst (temp_min ≤ 0°C)     → +1 punt")
print("      • Sneeuwval (> 0 cm)              → +3 punten  ← drempel snel bereikt")
print("      • Vochtigheid ≥ 97% (mist)        → +1 punt")
print("    Threshold score 5 wordt bereikt bij bijv.:")
print("      - Sneeuw + regen             (3+2 = 5)")
print("      - Sneeuw + wind              (3+2 = 5)")
print("      - Zware regen + storm        (2+2+1 frost = 5+)")
print()
print("  AUTO-REISTIJDEN PER WEEKDAG (geen slecht weer):")
for wd_num in range(5):
    t = car_vc_estimate(wd_num, rain_peak=0.0, wind_peak=12, temp_min=8,
                        snow_total=0, humidity_max=65)
    mode_c = "AUTO" if t <= THRESHOLD_MIN else "TREIN"
    print(f"    {WD_NL[wd_num]:<12}: {t:.0f} min  → {mode_c}")

print()
print("  IMPACT SLECHT WEER OP MAANDAGOCHTEND:")
ref = car_vc_estimate(0, rain_peak=0.0, wind_peak=12, temp_min=8, snow_total=0, humidity_max=65)
for wl, wd in WEATHER_VARIANTS:
    rain_pk = wd["rain_peak"]; wind_pk = wd["wind_peak"]
    temp_mn = wd.get("temp_min") if wd.get("temp_min") is not None else 8
    snow    = wd["snow_total"]; hum = wd["humidity_max"]
    t = car_vc_estimate(0, rain_peak=rain_pk, wind_peak=wind_pk,
                        temp_min=temp_mn, snow_total=snow, humidity_max=hum)
    risk = weather_risk_score(rain_pk, wind_pk, temp_mn, snow, hum)
    mode_c = recommend(t, risk)
    delta = t - ref
    print(f"    {wl:<22}: {t:.0f} min  (+{delta:.0f})  risk={risk}  → {mode_c.upper()}")
