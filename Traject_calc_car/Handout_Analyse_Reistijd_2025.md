# Hand-out: Analyse reistijd Gent -> Mechelen (2025)

## 1. Doel
- Inschatten van dagelijkse auto-reistijd richting Mechelen op basis van verkeersdrukte.
- Focus op ochtenddrukte en file-opbouw vóór de bottleneck.

## 2. Databronnen
- AWV kwartierdata 2025.
- Extra upstream meetpunten: 904548 (Neel Dofflaan 50) en 904834 (Nederlandstraat 5).
- Outputbestand: `gent_mechelen_geschatte_reistijd_volledig.csv`.

## 3. Methode (kort)
- Per dag wordt een drukteproxy berekend uit upstream tellingen.
- Drukte wordt geschaald naar een geschatte reistijdband van 60-120 minuten.
- Optionele tunnelkalibratie was in de huidige snapshot neutraal (off-peak).

## 4. Kernresultaten
- Gemiddelde geschatte reistijd: **98.7 min** (mediaan 111.5 min).
- Minimum/maximum: **60.0 / 120.0 min**.
- P10/P90: **60.1 / 120.0 min**.
- Aantal dagen: **365**.

## 5. Top 10 zwaarste dagen

| Datum      | Drukte voertuigen | Geschatte reistijd (min) |
| ---------- | ----------------: | -----------------------: |
| 2025-01-06 |            6236.0 |                    120.0 |
| 2025-01-07 |            6240.5 |                    120.0 |
| 2025-01-29 |            6283.0 |                    120.0 |
| 2025-02-05 |            6171.5 |                    120.0 |
| 2025-02-10 |            6190.5 |                    120.0 |
| 2025-02-12 |            6183.0 |                    120.0 |
| 2025-02-13 |            6284.5 |                    120.0 |
| 2025-02-14 |            6175.5 |                    120.0 |
| 2025-02-17 |            6282.0 |                    120.0 |
| 2025-02-19 |            6290.5 |                    120.0 |

## 6. Beperkingen
- Tunnel-live data was op rustig moment; geen extra vertraging waargenomen.
- Absolute reistijd blijft een modelbenadering; rangorde tussen dagen is robuuster.

## 7. Vervolgacties
1. Historische tunnelreeks of spits-snapshots toevoegen.
2. Scenario's voor tunnelimpact opnemen.
3. Weer- en kalenderfactoren uitbreiden in een verklarend model.