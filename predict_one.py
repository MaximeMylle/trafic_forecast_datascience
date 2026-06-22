# -*- coding: utf-8 -*-
"""
predict_one.py — één pendeladvies, live (Gent → Mechelen, aankomst 09:00)
=========================================================================
Traint het model en geeft voor ÉÉN dag het advies (auto / trein / thuiswerken)
op basis van weer + kalender. Bedoeld als live-demo tijdens de presentatie.

Standaard gebruikt het het EERLIJKE model: getrainde op de GEMETEN auto-reistijd
(car_real_min, AWV 2025). Met --synthetic gebruik je het oude formule-model.

Voorbeelden
-----------
  # rustige lentevrijdag
  python predict_one.py --weekday vr --month 5 --rain 0 --wind 10 --temp 14

  # natte dinsdagspits in november
  python predict_one.py --weekday di --month 11 --rain 5 --wind 30 --temp 6

  # sneeuwdag in januari  -> thuiswerken
  python predict_one.py --weekday do --month 1 --snow 8 --temp -3

  # schoolvakantie (lichter verkeer)
  python predict_one.py --weekday wo --month 8 --schoolvakantie

  # feestdag  -> thuiswerken
  python predict_one.py --feestdag

  # vergelijk met het oude (synthetische) model
  python predict_one.py --synthetic --weekday di --month 11 --rain 5
"""
import argparse
import subprocess
import sys
from datetime import date

# ─── Auto-install ─────────────────────────────────────────────────────────────
for _pkg in ["numpy", "pandas", "scikit-learn"]:
    _imp = "sklearn" if _pkg == "scikit-learn" else _pkg
    try:
        __import__(_imp)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", _pkg], stdout=subprocess.DEVNULL)

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from data_pipeline import build_combined_df, CAR_PREF_BUFFER_MIN

# ─── Config (zelfde features & buffers als de rest van het project) ───────────
FEATURE_COLS = [
    "rain_total", "rain_peak", "wind_peak", "wind_mean",
    "temp_min", "temp_mean", "humidity_max", "snow_total",
    "weekday_num", "month", "is_mon", "is_tue_thu", "is_fri",
    "is_school_holiday", "weather_risk",
]
CAR_BUFFER_MIN   = 14   # zie notebook §14: ~95% op tijd voor de auto
TRAIN_BUFFER_MIN = 6    # de trein rijdt dicht bij schema
WD_MAP = {
    "ma": 0, "di": 1, "wo": 2, "do": 3, "vr": 4,
    "maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3, "vrijdag": 4,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4,
}
WD_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag"]


def parse_weekday(val: str) -> int:
    v = str(val).strip().lower()
    if v.isdigit():
        return int(v) % 5
    if v in WD_MAP:
        return WD_MAP[v]
    raise SystemExit(f"Onbekende weekdag: {val!r} (gebruik ma/di/wo/do/vr of 0–4)")


def weather_risk(rain_peak, wind_peak, temp_min, snow_total, humidity_max) -> int:
    """Zelfde samengestelde risicoscore (0–9) als de pipeline."""
    return (int(rain_peak >= 2.0) * 2
            + int(wind_peak >= 45.0) * 2
            + int(temp_min <= 0.0) * 1
            + int(snow_total > 0.0) * 3
            + int(humidity_max >= 97) * 1)


def train_models(use_real: bool):
    """Train RF-regressor (reistijd) + RF-classifier (auto/trein)."""
    df = build_combined_df()
    if use_real:
        df = df[(df["date"].dt.year == 2025) & df["car_real_min"].notna()].copy()
        if df.empty:
            raise SystemExit("Geen gemeten auto-data gevonden — gebruik --synthetic.")
        target = "car_real_min"
        df["car_faster_than_train"] = (
            df["car_real_min"] <= df["train_actual_journey_min"] + CAR_PREF_BUFFER_MIN
        ).astype(int)
    else:
        target = "car_est_min"

    X = df[FEATURE_COLS].values
    reg = RandomForestRegressor(n_estimators=300, min_samples_leaf=5, random_state=42, n_jobs=-1)
    reg.fit(X, df[target].values)
    clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, random_state=42,
                                 n_jobs=-1, class_weight="balanced")
    clf.fit(X, df["car_faster_than_train"].values)

    train_sched = float(df["train_planned_journey_min"].median())
    return reg, clf, train_sched, len(df), target


def p_car_faster(clf, X) -> float:
    proba = clf.predict_proba(X)
    if proba.shape[1] == 1:          # classifier zag maar één klasse
        return float(clf.classes_[0])
    return float(proba[0, 1])


def hhmm(minutes_from_midnight: float) -> str:
    t = int(round(minutes_from_midnight))
    return f"{t // 60:02d}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser(
        description="Eén pendeladvies Gent → Mechelen (aankomst 09:00).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--weekday", default="di", help="ma/di/wo/do/vr of 0–4 (standaard: di)")
    ap.add_argument("--month", type=int, default=date.today().month, help="maand 1–12 (standaard: deze maand)")
    ap.add_argument("--rain", type=float, default=0.0, help="piekneerslag mm/u (standaard 0)")
    ap.add_argument("--rain-total", type=float, default=None, help="totale neerslag mm (optioneel)")
    ap.add_argument("--wind", type=float, default=15.0, help="windstoot km/u (standaard 15)")
    ap.add_argument("--temp", type=float, default=10.0, help="minimumtemperatuur °C (standaard 10)")
    ap.add_argument("--snow", type=float, default=0.0, help="sneeuw cm (standaard 0)")
    ap.add_argument("--humidity", type=float, default=80.0, help="max. luchtvochtigheid 0-100 (standaard 80)")
    ap.add_argument("--schoolvakantie", action="store_true", help="schoolvakantie (lichter verkeer)")
    ap.add_argument("--feestdag", action="store_true", help="feestdag → geen pendel")
    ap.add_argument("--synthetic", action="store_true", help="gebruik het oude formule-model i.p.v. de gemeten data")
    args = ap.parse_args()

    wd = parse_weekday(args.weekday)
    risk = weather_risk(args.rain, args.wind, args.temp, args.snow, args.humidity)

    bar = "═" * 60
    print("\n" + bar)
    print("  PENDELADVIES   ·   Gent → Mechelen   ·   aankomst 09:00")
    print(bar)
    print(f"  Dag            : {WD_NL[wd]}, maand {args.month}"
          + ("  · schoolvakantie" if args.schoolvakantie else ""))
    print(f"  Weer           : regen {args.rain:.1f} mm/u · wind {args.wind:.0f} km/u · "
          f"temp {args.temp:.0f}°C · sneeuw {args.snow:.0f} cm")
    print(f"  Weerrisico     : {risk}/9")
    print("  " + "─" * 58)

    # ── Feestdag: geen woon-werkverkeer ──────────────────────────────────────
    if args.feestdag:
        print("  AANBEVELING    : THUISWERKEN  (feestdag — geen pendel nodig)")
        print(bar + "\n")
        return

    # ── Model trainen + voorspellen ──────────────────────────────────────────
    reg, clf, train_sched, n, target = train_models(use_real=not args.synthetic)

    feats = {
        "rain_total":  args.rain_total if args.rain_total is not None else round(args.rain * 1.5, 1),
        "rain_peak":   args.rain,
        "wind_peak":   args.wind, "wind_mean": round(args.wind * 0.6, 1),
        "temp_min":    args.temp,  "temp_mean": args.temp + 4,
        "humidity_max": args.humidity, "snow_total": args.snow,
        "weekday_num": wd, "month": args.month,
        "is_mon": int(wd == 0), "is_tue_thu": int(wd in (1, 3)), "is_fri": int(wd == 4),
        "is_school_holiday": int(args.schoolvakantie),
        "weather_risk": risk,
    }
    X = np.array([[feats[c] for c in FEATURE_COLS]])
    car_min = float(reg.predict(X)[0])
    prob_car = p_car_faster(clf, X)

    # ── Beslissing (zelfde regels als predict_scenarios.py) ──────────────────
    if risk >= 5 or args.snow >= 3.0:
        mode, conf, reason = "THUISWERKEN", 90.0, "zwaar weer — weg én spoor onbetrouwbaar"
        dep = None
    elif int(clf.predict(X)[0]) == 1:
        mode, conf, reason = "AUTO", prob_car * 100, "auto naar verwachting sneller"
        dep = 9 * 60 - (car_min + CAR_BUFFER_MIN)
    else:
        mode, conf, reason = "TREIN", (1 - prob_car) * 100, "trein sneller/betrouwbaarder"
        dep = 9 * 60 - (train_sched + TRAIN_BUFFER_MIN)

    print(f"  Auto (model)   : {car_min:.0f} min   ·   Trein (gepland): {train_sched:.0f} min")
    print("  " + "─" * 58)
    print(f"  AANBEVELING    : {mode}   ({reason})")
    if dep is not None:
        buf = CAR_BUFFER_MIN if mode == "AUTO" else TRAIN_BUFFER_MIN
        print(f"  Vertrek        : {hhmm(dep)}   (met {buf} min buffer voor 09:00)")
    print(f"  Zekerheid      : {conf:.0f}%")
    print("  " + "─" * 58)
    mdl = "gemeten auto-data (car_real_min, 2025)" if not args.synthetic else "synthetisch formule-model (car_est_min)"
    print(f"  Model          : {mdl} — getraind op {n:,} dagen")
    print(bar + "\n")


if __name__ == "__main__":
    main()
