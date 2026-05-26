# Werklogboek

Dit bestand houdt acties en denknotities bij voor dit project.

## 2026-05-26

### Acties
- Notebook geconfigureerd en uitgevoerd om de fout in cel 2 te reproduceren.
- Runtime-fout vastgesteld: asyncio.run kan niet in een reeds draaiende notebook-eventloop.
- Cel 2 aangepast van asyncio.run(main()) naar await main().
- Uitvoering opnieuw getest: actuele weerdata wordt correct opgehaald.
- Historische datawens toegevoegd: vanaf 2021-01-01.
- Vastgesteld dat irm_kmi_api client in deze setup enkel forecast-methodes toont.
- Nieuwe historische datacel toegevoegd met Open-Meteo Archive API.
- Historische dataset succesvol opgehaald en gevalideerd.
- CSV opgeslagen als weather_history_mechelen_2021_now.csv.
- Nieuwe merge-cel toegevoegd om verkeersdata en weerdata op uur te koppelen.
- Merge-cel uitgevoerd en gecontroleerd op robuuste foutmelding bij ontbrekend verkeersbestand.

### Denknotities
- In notebooks is await direct bruikbaar; dat voorkomt eventloop-conflicten.
- Voor historische data was een externe archive-endpoint nodig omdat de gebruikte IRM/KMI-client dit niet direct bood.
- Merge-logica is defensief opgezet: automatische tijdkolomdetectie en duidelijke foutboodschap bij ontbrekende input.

### Openstaande stap
- Zet in cel 4 het juiste pad voor TRAFFIC_CSV_PATH en voer de cel opnieuw uit om traffic_weather_merged.csv te genereren.

---

## Bijwerkregels
- Nieuwe acties toevoegen met datum en tijd.
- Per wijziging kort noteren: wat gedaan, waarom, resultaat.
- Denknotities compact houden (beslissing en reden in 1-2 zinnen).

### Laatste update
- 2026-05-26: gebruiker bevestigt dat alle acties en denknotities blijvend moeten worden bijgehouden.
- Vanaf dit punt wordt elke relevante wijziging in deze sessie automatisch toegevoegd aan dit logbestand.

## 2026-05-26 (aanvulling)

### Acties
- Opdrachtbestand geanalyseerd om het generieke projectkader te vertalen naar een concreet use-case doel.
- first_data_science_project.md uitgebreid met specifieke projectscope: Gent -> Mechelen aankomst 09:00.
- Beslissingskader toegevoegd voor moduskeuze: auto, trein, of thuiswerken.
- Belgische werkdagen expliciet als analyse- en modelscope opgenomen.

### Denknotities
- De opdracht beoordeelt vooral communicatie en business impact, dus een expliciet operationeel besliskader is belangrijker dan modelcomplexiteit.
- Door thuiswerken als derde beslissingsoptie op te nemen blijft de oplossing realistisch bij hoge onzekerheid of extreem risico.

## 2026-05-26 (werkdagenfilter)

### Acties
- Nieuwe cel 5 toegevoegd in het notebook om data te filteren op Belgische werkdagen (ma-vr, exclusief BE feestdagen).
- Cel 5 uitgevoerd en gevalideerd.
- Outputbestand aangemaakt: traffic_weather_workdays_be.csv.

### Denknotities
- De filtercel gebruikt `df_merged` indien beschikbaar; anders valt ze automatisch terug op `df_hist` zodat de workflow niet blokkeert.
- Dit maakt het mogelijk om alvast op werkdagen te analyseren, ook wanneer verkeersdata nog niet gekoppeld is.

## 2026-05-26 (eerste patroonanalyse)

### Acties
- Nieuwe cel 6 toegevoegd voor voorlopige moduskeuze-patronen (auto/trein/thuiswerk) op basis van werkdag-weerdata in het pendelvenster 07:00-09:00.
- Eenvoudige risicoscore en adviesregels toegepast.
- Patronen per weekdag berekend en geëxporteerd naar weekday_mode_pattern_weather_only.csv.

### Denknotities
- Zonder echte auto- en treinduurdata blijft dit een weer-gedreven proxy en dus een voorlopige indicatie.
- Eerste resultaat: alle weekdagen dominantie voor auto; donderdag en maandag tonen relatief iets hoger treinadvies binnen de gebruikte heuristiek.

## 2026-05-26 (volledige uitwerking)

### Acties
- Nieuwe markdown-sectie en 2 extra codecellen toegevoegd om de volledige pendelbeslissing uit te werken.
- Dagelijkse features gebouwd in het venster 06:00-09:00 (regen, wind, temperatuur, vochtigheid, weekdag).
- Volledige beslislaag toegevoegd met:
	- geschatte auto- en treinreistijd,
	- buffers voor betrouwbare aankomst om 09:00,
	- aanbevolen modus,
	- aanbevolen vertrekuur,
	- motivatie per dag.
- Resultaten geëxporteerd naar:
	- daily_commute_features.csv
	- daily_commute_recommendations.csv
	- weekday_mode_pattern_full.csv

### Denknotities
- Omdat nog geen echte verkeers- en treinreistijdreeksen zijn gekoppeld, gebruikt de volledige pipeline momenteel een transparante heuristiek op basis van weer + weekdag.
- Deze structuur is meteen bruikbaar voor presentatie en operationalisatie, en kan later zonder structurele herbouw overschakelen naar echte modeltargets.

## 2026-05-26 (operationeel weekbeleid)

### Acties
- Extra sectie toegevoegd in notebook om van dagelijkse adviezen naar een vast weekbeleid te gaan.
- Policy-cel gebouwd en uitgevoerd met:
	- default modus per weekdag,
	- standaard vertrekuur,
	- expliciete thuiswerk-triggers voor uitzonderlijke omstandigheden.
- Outputs geëxporteerd naar:
	- weekday_commute_policy.csv
	- homework_trigger_rules.csv

### Denknotities
- Gebruiker vroeg om volledige uitwerking; daarom naast modeloutput ook beleidslaag toegevoegd die direct operationeel inzetbaar is.
- Realistische vervolgstap blijft het vervangen van heuristische reistijd door echte auto- en treinobservaties zodra beschikbaar.

## 2026-05-26 (Vlaams Verkeerscentrum bronkoppeling)

### Acties
- Gevalideerd dat publieke DATEX II feeds van Vlaams Verkeerscentrum direct opvraagbaar zijn:
	- https://www.verkeerscentrum.be/uitwisseling/datex2v3
	- https://www.verkeerscentrum.be/uitwisseling/datex2v3full
- Nieuwe notebooksectie toegevoegd om feed op te halen, XML lokaal op te slaan en records naar tabelformaat te parseren.
- Resultaat van run: 141 situation records opgehaald.
- Outputbestanden aangemaakt:
	- vvc_datex2v3.xml
	- vvc_datex2v3_records.csv

### Denknotities
- Voor deze feed is geen extra login vereist; dit is een bruikbare real-time verkeersbron.
- Het Vlaams Dataportaal Verkeersgegevens (VDV) blijft relevant voor uitgebreidere verkeerstellingen, maar vraagt aanmelding met digitale sleutel.

## 2026-05-26 (visualisaties weer vs weekdag)

### Acties
- Nieuwe visualisatie-sectie toegevoegd in het notebook voor weer versus dag van de week.
- 4 grafieken gegenereerd voor pendelvenster 06:00-09:00: gemiddelde temperatuur, gemiddelde wind, kans op neerslag, en neerslagspreiding.
- Rechteronder-plot aangepast naar alleen natte uren (precipitation > 0) om verschil per weekdag zichtbaar te maken.

### Denknotities
- Zonder filtering op natte uren wordt de neerslagboxplot vrijwel vlak door het grote aandeel nulwaarden.
- De aangepaste visualisaties zijn beter bruikbaar voor businessuitleg in de presentatie.

## 2026-05-26 (visualisaties verkeer)

### Acties
- Nieuwe verkeersvisualisatie-cel toegevoegd op basis van DATEX II snapshotdata.
- Grafieken gebouwd voor:
	- top verkeers-eventtypes,
	- verdeling van filelengtes,
	- aandeel records met/zonder file,
	- locatiepunten in Lambert72.
- Snapshot logging toegevoegd naar vvc_snapshots_log.csv voor toekomstige weekdaganalyse verkeer.
- Parsing robuuster gemaakt voor ontbrekende eventkolommen en gemixte tijdzones.

### Denknotities
- Een enkele snapshot geeft een goed momentbeeld, maar geen betrouwbaar weekdagpatroon; daarvoor zijn meerdere dagen snapshots nodig.
- Het hoge aandeel 'unknown' eventtypes wijst op beperkte semantische labels in de huidige feedextractie, niet noodzakelijk op gebrek aan verkeersproblemen.

## 2026-05-26 (voorspelling voor 27 mei)

### Acties
- Nieuwe notebooksectie toegevoegd om een dagadvies voor morgen (2026-05-27) te berekenen op basis van forecastweer + bestaande beslisregels.
- Belgische werkdagcontrole toegevoegd vóór de voorspelling.
- Voorspelling uitgevoerd en geëxporteerd naar tomorrow_prediction_2026-05-27.csv.

### Denknotities
- Voorspelling blijft heuristisch zolang echte historische auto- en treinreistijden niet als modeltarget zijn gekoppeld.
- Structuur en outputformaat zijn al operationeel bruikbaar voor dagelijkse run richting aankomst 09:00.

## 2026-05-26 (voorspelling voor overmorgen)

### Acties
- Voorspellingscel aangepast van vaste datum naar dynamische parameter `DAYS_AHEAD = 2`.
- Voorspelling uitgevoerd voor 2026-05-28 en geëxporteerd naar prediction_2026-05-28.csv.

### Denknotities
- Een dynamische dag-offset voorkomt manuele datumswijziging bij dagelijkse hergebruik.
- Resultaat voor donderdag wijst op treinvoorkeur door de ingestelde spitsdagregel, ondanks laag weer-risico.

## 2026-05-26 (planning volgende week)

### Acties
- Nieuwe notebooksectie toegevoegd om een volledig advies voor volgende week (ma-vr) te genereren.
- Forecast voor een volledige weekrange opgehaald en per dag vertaald naar modus + vertrekuur om 09:00 aan te komen.
- Output geëxporteerd naar next_week_commute_plan_2026-06-01_2026-06-05.csv.

### Denknotities
- De weekplanning volgt consistent de ingestelde spitsdaglogica: dinsdag en donderdag vaker trein, overige dagen auto bij stabiele weersverwachting.
- Voor hogere betrouwbaarheid blijft het nodig om echte reistijdtargets (auto/trein) in plaats van heuristische reistijd te gebruiken.

## 2026-05-26 (refactor + rolling backtest + optimalisatie + presentatie)

### Acties
- Projectstructuur gerefactord met logische mappen: `data/raw`, `data/processed`, `outputs/features`, `outputs/recommendations`, `outputs/predictions`, `outputs/policies`, `outputs/reports`, `docs`.
- Bestaande outputbestanden hernoemd en verplaatst naar semantische paden.
- Nieuwe notebooksectie toegevoegd voor rolling walk-forward backtest en parameteroptimalisatie.
- Backtestdataset opgebouwd op werkdagniveau (06:00-09:00 venster) met deterministische proxy-observaties voor evaluatie.
- Rolling backtest uitgevoerd met 800 parametercombinaties en fold-based evaluatie.
- Resultaten opgeslagen naar:
	- outputs/reports/rolling_backtest_results.csv
	- outputs/reports/optimized_model_best_params.csv
	- outputs/reports/optimized_model_predictions_vs_proxy.csv
- Presentatiebestand automatisch gegenereerd:
	- docs/commute_model_presentation.md

### Denknotities
- Met beperkte realtime labels is proxy-evaluatie een pragmatische tussenstap om modelgedrag te vergelijken, maar finale validatie moet op echte gerealiseerde reistijden gebeuren.
- Rolling backtest geeft stabiel hoge score, wat aangeeft dat de gekozen structuur consistent is; risico op overschatting blijft bestaan zolang proxy-targets uit afgeleide logica komen.

## 2026-05-26 (rode-dagen-kalender 2026-2027)

### Acties
- Nieuwe notebooksectie toegevoegd om een werkdagkalender met risicoklassen (groen/oranje/rood) te bouwen voor 2026-2027.
- Kalender gebaseerd op historische maand-weekdagprofielen uit de pendelfeatures.
- Risicoclassificatie aangepast naar percentielgebaseerde drempels om een praktische spreiding te krijgen.
- Output geëxporteerd naar `outputs/predictions/risk_calendar_2026_2027.csv`.

### Denknotities
- Deze kalender is climatologisch/patroongebaseerd en niet dag-exact zoals een korte termijn forecast.
- Rode dagen zijn bedoeld als planningswaarschuwing (vermijden indien mogelijk), niet als absolute blokkade.

## 2026-05-26 (notebook hernoemd)

### Acties
- Hoofdnotebook hernoemd naar een duidelijke, projectgerichte naam:
	- `GetWeatherData.ipynb` -> `gent_mechelen_commute_risk_forecast.ipynb`

### Denknotities
- Een beschrijvende notebooknaam maakt navigatie, versiebeheer en presentatie van het project duidelijker.

## 2026-05-26 (notebook structuur verbeterd)

### Acties
- Nieuwe startpagina toegevoegd bovenaan de notebook met titel, inhoudsopgave en aanbevolen uitvoervolgorde.
- Sectiekoppen toegevoegd voor de vroege en middenblokken zodat de flow duidelijk is:
	- setup en actuele weerscheck
	- historische data en preprocessing
	- beslislogica en operationeel beleid
	- verkeersvisualisatie, forecasts en modelanalyse

### Denknotities
- De notebook blijft functioneel identiek, maar is nu sneller navigeerbaar voor jezelf en voor presentatie/docevaluatie.

## 2026-05-26 (snelle run toegevoegd)

### Acties
- Nieuwe compacte sectie toegevoegd: `Snelle Run (demo/presentatie)`.
- Snelle run-cel toegevoegd die direct kernresultaten toont vanuit bestaande outputbestanden:
	- backtest KPI's,
	- laatste pendeladviezen,
	- maandelijkse risicodistributie,
	- beste modelparameters,
	- overzicht van rapportbestanden.
- Snelle run-cel succesvol uitgevoerd en gevalideerd.

### Denknotities
- Deze sectie is ideaal voor demo en evaluatie omdat ze zonder zware herberekening direct de businessrelevante output toont.

## 2026-05-26 (presentatie op 10 minuten gezet)

### Acties
- Markdown-sectie in de notebook bijgewerkt naar een volledig tijdsgebonden spreekscript van 10 minuten.
- Blokken toegevoegd per tijdvenster (context, data, model, validatie, resultaten, risicokalender, conclusie, next steps).
- Demostructuur afgestemd op de bestaande snelle run-cel zodat live presentatie compact blijft.

### Denknotities
- Met expliciete timing blijft de presentatie binnen tijd en is de verhaallijn consistenter bij evaluatie.

## 2026-05-26 (backup presentatie 5 minuten)

### Acties
- Extra markdown-sectie toegevoegd in de notebook met een volledig 5-minuten spreekscript als fallback.
- Structuur afgestemd op dezelfde snelle run-cel zodat je zonder extra uitvoering kunt schakelen tussen 10-minuten en 5-minuten presentatie.

### Denknotities
- Deze backup voorkomt timingproblemen bij jury/demo-context met beperkte spreektijd.
