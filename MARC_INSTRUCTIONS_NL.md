# Nieuwe autorijtijdendata integreren

**Route:** Gent-Sint-Pieters → Mechelen, ochtendspits aankomst voor 09:00  
**Code:** zie `data_pipeline.py` en `calibrate_factors.py` voor de volledige pijplijn

---

## 1. Hoe autorijtijden momenteel werken

Er zijn **twee kolommen** voor autorijtijd in de finale dataset. Het verschil begrijpen is belangrijk voordat je nieuwe data integreert.

### `car_vc_est_min` — PRIMAIRE kolom (gebruikt door de ML-modellen)

Dit is de kolom die de modellen effectief gebruiken. Ze wordt opgebouwd in drie stappen:

1. **Maandelijkse basistijd** vanuit Vlaams Verkeercentrum (VC) Excel-bestanden:
   - Bestanden: `data/raw/reistijd*.xlsx`
   - Samengevoegd naar: `data/processed/vc_travel_times.csv`
   - Formaat: `year`, `month`, `vc_car_base_min` (minuten, weerspiegelt reële snelwegcongestie)
   - Dekking: alle maanden **behalve juli en augustus** (VC dekt enkel schooldagverkeer)

2. **Relatieve weekdagcorrectie** (uit `factors.json`):
   - Vermenigvuldigt de maandelijkse VC-basis met een factor per weekdag (gemiddelde = 1,0)
   - Voorbeeld: maandag × 1,1156 betekent maandag is ~12% slechter dan gemiddeld

3. **Weercorrectie** (uit `factors.json`):
   - Voegt een fractie van de basistijd toe per actieve weerconditie
   - Voorbeeld: zware regen (+12%), sneeuw (+1,7%), strenge vorst (+4,3%), ...

**Formule:**
```
car_vc_est_min = vc_basis_die_maand × weekdag_relatieve_factor × weer_factor
```

### `car_est_min` — HISTORISCHE / FALLBACK kolom

Gebruikt de OSRM vrije-doorstroommtijd (59,5 min, gecached in `data/raw/osrm_route_gent_mechelen.json`) vermenigvuldigd met **absolute** weekdag- en weerfactoren. Wordt als fallback gebruikt voor juli/augustus (geen VC-data) en bewaard voor achterwaartse compatibiliteit. De modellen gebruiken hoofdzakelijk `car_vc_est_min`.

---

## 2. De gecombineerde dataset — volledige kolomreferentie

Bestand: `data/processed/combined_workdays_features.csv`  
Één rij per Belgische werkdag (ma–vr, geen feestdagen), van 2021-01-04 tot vandaag.

| Kolom | Type | Beschrijving |
|-------|------|--------------|
| `date` | datum | Werkdag (YYYY-MM-DD) |
| `weekday` | tekst | "Monday" … "Friday" |
| `weekday_num` | int | 0=ma … 4=vr |
| `month` | int | 1–12 |
| `year` | int | bijv. 2023 |
| `season` | tekst | Winter / Spring / Summer / Autumn |
| `is_school_holiday` | bool | True voor juli + augustus |
| `is_mon` | int | 1 als maandag |
| `is_tue_thu` | int | 1 als dinsdag of donderdag |
| `is_fri` | int | 1 als vrijdag |
| `rain_total` | float | Totale neerslag 06–09u (mm) |
| `rain_peak` | float | Zwaarste uur neerslag 06–09u (mm) |
| `wind_peak` | float | Piekwindsnelheid 06–09u (km/u) |
| `wind_mean` | float | Gemiddelde windsnelheid 06–09u (km/u) |
| `temp_min` | float | Koudste uur 06–09u (°C) |
| `temp_mean` | float | Gemiddelde temperatuur 06–09u (°C) |
| `humidity_max` | float | Piekluochtvochtigheid 06–09u (%) |
| `snow_total` | float | Totale sneeuwval 06–09u (cm) |
| `weather_risk` | int | Samengestelde risicoscore 0–9 |
| **`car_vc_est_min`** | float | **PRIMAIRE autorijtijdschatting (minuten)** |
| `car_est_min` | float | Historische schatting via OSRM (minuten) |
| `train_planned_journey_min` | float | Geplande reistijd trein (minuten) |
| `train_actual_journey_min` | float | Werkelijke reistijd trein incl. vertraging (minuten) |
| `train_delay_arr_median_s` | float | Mediaan aankomstvertraging (seconden) |
| `train_on_time_pct` | float | Aandeel treinen ≤ 5 min te laat (0–1) |
| `train_cancelled_pct` | float | Aandeel geannuleerde treinen (0–1) |
| `train_sched_min` | float | Alias voor `train_planned_journey_min` |
| `car_faster_than_train` | int | Binaire doelvariabele: 1 als auto preferabel is |

---

## 3. Waar nieuwe data inpluggen

Afhankelijk van het formaat van Marc's dataset zijn er twee integratiepaden:

---

### Pad A — Dagelijkse gemeten autorijtijden

**Wanneer gebruiken:** je hebt per-dag gemeten autorijtijden (GPS-probes, drijvende voertuigdata, TomTom API, enz.).

**Wat aanleveren:**
```
date          car_actual_min
2021-01-04    68.5
2021-01-05    62.1
...
```
- `date`: formaat `YYYY-MM-DD`
- `car_actual_min`: totale deur-tot-deur reistijd in minuten voor de ochtendspits (venster 06:00–09:00)

**Hoe integreren — `data_pipeline.py`, functie `build_combined_df()`:**

1. Sla het bestand op als `data/raw/car_actual_daily.csv`

2. In `build_combined_df()`, na Stap 8b (rond regel 1061), voeg toe:
```python
# ── Stap 8c: externe dagelijkse autodata laden (dataset Marc) ────────────
car_actual_path = RAW / "car_actual_daily.csv"
if car_actual_path.exists():
    df_car_actual = pd.read_csv(car_actual_path, parse_dates=["date"])
    df = df.merge(df_car_actual[["date", "car_actual_min"]], on="date", how="left")
    n_actual = df["car_actual_min"].notna().sum()
    print(f"[pipeline] Externe autodata samengevoegd voor {n_actual:,} dagen.")
else:
    df["car_actual_min"] = np.nan
```

3. Voeg `"car_actual_min"` toe aan de `col_order`-lijst in Stap 11 (regel 1150).

4. **Om het als primaire schatting te gebruiken**, pas de `car_faster_than_train`-logica aan:
```python
# Gebruik werkelijke autorijtijden waar beschikbaar, anders VC-schatting
df["car_best_min"] = df["car_actual_min"].fillna(df["car_vc_est_min"])
df["car_faster_than_train"] = (
    df["car_best_min"] <= df["train_actual_journey_min"] + CAR_PREF_BUFFER_MIN
).astype(int)
```

---

### Pad B — Maandelijkse aggregaten (zelfde formaat als VC-data)

**Wanneer gebruiken:** je hebt een dataset met gemiddelde autorijtijd per maand (bv. ANPR-camera's, AWV, of een gelijkaardige geaggregeerde bron).

**Wat aanleveren:**
```
year    month    car_base_min
2021    1        63.4
2021    2        61.8
...
```

**Hoe integreren — `data_pipeline.py`:**

Vervang of vul de VC-opzoeking aan in Stap 8b (rond regel 1049):

```python
# Marc's maanddata laden naast VC
marc_path = RAW / "car_monthly_marc.csv"
if marc_path.exists():
    df_marc = pd.read_csv(marc_path)
    marc_lookup = df_marc.set_index(["year", "month"])["car_base_min"].to_dict()
else:
    marc_lookup = {}

def _vc_row(row):
    # Marc's data krijgt voorrang, daarna VC, daarna OSRM als fallback
    base = marc_lookup.get((row["year"], row["month"])) \
        or vc_lookup.get((row["year"], row["month"]))
    if base is None:
        return row["car_est_min"]
    return car_vc_travel_time_estimate(row, base)
```

---

## 4. Factoren hercalibreren na het toevoegen van nieuwe data

`calibrate_factors.py` leidt **weekdag- en weerfactoren** af uit de reële data. Als Marc's dataset dagelijkse autorijtijden toevoegt, kunnen die de **Infrabel-proxy** vervangen (die momenteel treinvertragingen × 2 gebruikt als schatting van autogevoeligheid). Dit zou een significante verbetering zijn.

**Dagelijkse autodata gebruiken in de kalibratie (`calibrate_factors.py`):**

Bovenaan de weekdagsectie (rond regel 80), in plaats van `train_delay_arr_median_s`, gebruik je `car_actual_min` gegroepeerd per weekdag:

```python
# Als je een car_actual_daily.csv hebt, laad die hier:
car_daily = pd.read_csv("data/raw/car_actual_daily.csv", parse_dates=["date"])
car_daily["weekday"] = car_daily["date"].dt.day_name()
wd_means = car_daily.groupby("weekday")["car_actual_min"].mean()
```

Geef `wd_means` dan mee aan het bestaande shift-dan-normaliseer-blok dat er al staat.

Voor weerfactoren: voeg de autodata samen met de weerdata op `date` en doe dezelfde gegroepeerde vergelijking (hoge-conditiedagen vs heldere dagen) die al geïmplementeerd is met de VC-data — maar nu met werkelijke dagwaarden in plaats van maandgemiddelden.

Na het aanpassen van de kalibratie altijd opnieuw uitvoeren:
```
python calibrate_factors.py      # herleidt factors.json
python data_pipeline.py          # herbouwt de gecombineerde dataset
python model_training.py         # hertraint de modellen
python predict_scenarios.py      # genereert de scenariovoorspellingen opnieuw
```

---

## 5. Bestandslocaties overzicht

```
projectroot/
├── data_pipeline.py            ← hoofdpijplijn, pas build_combined_df() hier aan
├── calibrate_factors.py        ← leidt weekdag- + weerfactoren af uit reële data
├── factors.json                ← output van calibrate_factors.py, gelezen door pijplijn
├── data/
│   ├── raw/
│   │   ├── reistijd*.xlsx         ← VC maandelijkse autodata (bestaande bron)
│   │   ├── car_actual_daily.csv   ← MARC'S DAGELIJKSE DATA HIER PLAATSEN (Pad A)
│   │   └── car_monthly_marc.csv   ← MARC'S MAANDELIJKSE DATA HIER PLAATSEN (Pad B)
│   └── processed/
│       ├── combined_workdays_features.csv  ← finale dataset (herbouwd door pijplijn)
│       └── vc_travel_times.csv             ← tussentijdse VC-aggregatiecache
```

---

## 6. Weerdrempelwaarden gebruikt in het model

De pijplijn past weercorrecties toe op basis van deze drempelwaarden (venster 06–09u):

| Conditie | Drempelwaarde | Toegepaste factor |
|----------|---------------|-------------------|
| Lichte regen | `rain_peak >= 0,5 mm` | +2,98% op basistijd |
| Matige regen | `rain_peak >= 2,0 mm` | +2,98% |
| Zware regen | `rain_peak >= 5,0 mm` | +12,07% |
| Sneeuw | `snow_total >= 1,0 cm` | +1,67% |
| Milde vorst | `temp_min <= 0 °C` | +0,85% |
| Strenge vorst | `temp_min <= -3 °C` | +4,28% |
| Stevige wind | `wind_peak >= 45 km/u` | +6,81% |
| Storm | `wind_peak >= 60 km/u` | +6,81% |

Deze factoren zijn additief (meerdere condities stapelen op). Alle waarden komen uit `factors.json` en werden gekalibreerd op basis van reële Infrabel- en VC-data.
