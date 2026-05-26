# Data Science Project – From Data to Business Insights

The goal of this project is **not** to build the most advanced machine learning model.

The main objective is to demonstrate that you can:

* understand a business problem,
* analyze data,
* build a model,
* and most importantly:
* **communicate insights clearly to a non-technical audience.**

Imagine you are presenting your work to:

* a manager,
* a planner,
* a marketing team,
* or a CEO.

Your audience is **not** a data scientist.

They want to understand:

* What problem are you solving?
* What patterns did you discover?
* What drives the predictions?
* What actions should be taken based on the analysis?
* How could the model realistically be used in practice?

Your ability to explain the model and its business implications is more important than achieving the highest possible accuracy.

An important part of this project is therefore thinking beyond:

> “Can I build a predictive model?”

and also asking:

> “How would an organization actually use this model operationally?”

---

# Project Requirements

Your project should include the following components.

---

# 1. Business Problem Definition

Clearly explain:

* What is the problem?
* Why does it matter?
* Who would use this analysis?
* What business value could it create?

You should already start thinking about:

* which decisions the model could support,
* which operational processes could be influenced,
* and whether the insights are actionable in practice.

For example:

* predicting customer churn may help companies prioritize retention efforts,
* forecasting demand may support inventory decisions,
* flight delay predictions may support operational planning,
* pricing analysis may support commercial strategy.

Detailed examples are provided later in this document.

---

# 2. Exploratory Data Analysis (EDA)

Before building models, first understand the data.

Your analysis should answer questions such as:

* What is actually your data (zoomed in plots).
* What patterns do you observe on aggregated plots (making the link back to the zoomed in plots for intuition)?
* Which variables seem important?
* Are there trends or anomalies?
* Are there missing values or outliers?

Use visualizations to tell a story.

Examples:

* histograms,
* boxplots,
* scatter plots,
* heatmaps,
* time series plots,
* bar charts.

The goal is **not** to create many charts (don't overdo it!), but to create charts that communicate useful insights clearly.

You should explain:

* **Most important**: what are we actually looking at,
* why certain patterns matter,
* how stakeholders could interpret them,
* and what business implications they may have.

If you don't find useful patterns, use some visuals to show what your data is and then the EDA part is done!

---

# 3. Data Preparation

Prepare the data for modeling.

Examples:

* handling missing values,
* encoding categorical variables,
* feature engineering,
* normalization/scaling.

This part should only be in the presentation if easy to interpret.

---

# 4. Modeling

Build at least one predictive or analytical model.

Examples:

* Linear Regression
* Logistic Regression
* Random Forest
* Clustering
* Time Series Forecasting

You are encouraged to start with simple models first and don't spend too much time understanding what the model actually does, just look at results :-). Understanding will come later.

A simpler model that runs fast allows you to iterate way faster. Also a mode you can explain well (after next year ;-)) is often more valuable than a complex “black box” model that nobody understands.

---

# 5. Explain the Model

You should explain:

* What is the model actually learning?
* Does the model behave logically?
* Could stakeholders trust and use these predictions?

Your explanation should be understandable to non-technical stakeholders.

---

# 6. Evaluation

Evaluate the quality of your model using appropriate metrics, relate your metric to the problem you are actually solving and the way the business would currently measure accuracy.

However, do not focus only on the metric itself.

Also discuss:

* Is the model useful in practice?
* What are the limitations?
* When might the model fail?
* What operational risks exist if the predictions are wrong?
* How much improvement would actually be needed before a company could use the model?

---

# 7. Business Recommendations

Translate your analysis into recommendations.

This is where data science becomes valuable.

Examples:

* “Focus retention campaigns on customers with monthly contracts.”
* “Increase inventory before weekends due to recurring demand peaks.”
* “Airbnb hosts may benefit more from improving reviews than adding amenities.”

Your recommendations should follow logically from your analysis.

Most importantly:

* explain how the organization could operationalize the insights,
* discuss what actions would realistically be required,
* and identify remaining challenges even if predictions are accurate.

---

# Suggested Project Topics

## 1. Airbnb Price Prediction

Predict Airbnb prices and explain which factors influence pricing most strongly.

Dataset:

* [Inside Airbnb](https://insideairbnb.com/get-the-data/?utm_source=chatgpt.com)

---

## 2. Customer Churn Prediction

Predict which customers are likely to leave a subscription service.

Dataset:

* [IBM Telco Churn Dataset](https://www.kaggle.com/datasets/blastchar/telco-customer-churn?utm_source=chatgpt.com)

---

## 3. Retail Demand Forecasting

Forecast product sales and explain seasonal demand patterns.

Dataset:

* [Store Item Demand Forecasting](https://www.kaggle.com/competitions/demand-forecasting-kernels-only?utm_source=chatgpt.com)

---

## 4. Flight Delay Prediction

Predict flight delays and identify operational factors that contribute most strongly.

Dataset:

* [Flight Delay Dataset](https://www.kaggle.com/datasets/usdot/flight-delays?utm_source=chatgpt.com)

---

## 5. Spotify Music Analysis

Analyze which characteristics make songs popular.

Dataset:

* [Spotify API](https://developer.spotify.com/documentation/web-api?utm_source=chatgpt.com)

---

## 6. House Price Prediction

Predict house prices and identify which property characteristics drive value.

Dataset:

* [Kaggle House Prices Dataset](https://www.kaggle.com/competitions/house-prices-advanced-regression-techniques?utm_source=chatgpt.com)

---

# Deliverables

## 1. Code

* Clear and structured
* Reproducible
* Well-commented

---

## 2. Presentation or Report

Your presentation should focus on:

* the business problem,
* insights,
* interpretation,
* operational implications,
* and recommendations.

Do not only show code and metrics.

A business audience should understand:

* what you discovered,
* why it matters,
* how the organization could use the insights,
* and what limitations still exist.

---

# Evaluation Criteria

Your project will primarily be evaluated on:

| Criterion                 | Importance |
| ------------------------- | ---------- |
| Communication of insights | High       |
| Clarity of explanations   | High       |
| Quality of visualizations | High       |
| Business understanding    | High       |
| Operational thinking      | High       |
| Correct methodology       | Medium     |
| Model performance         | Medium     |
| Complexity of model       | Low        |

---

# Jouw Concrete Projectscope (Gent -> Mechelen 09:00)

## 1. Business Problem Definition

Doel:

Elke Belgische werkdag beslissen wat de beste optie is om om 09:00 in Mechelen aan te komen, vertrekkend uit Gent:

* Auto
* Trein
* Thuiswerken (fallback bij hoge verwachte reistijd of hoge onzekerheid)

Waarom dit belangrijk is:

* Betrouwbaar op tijd aankomen voor werkafspraken.
* Minder stress en minder tijdverlies.
* Operationele beslissing die elke werkdag opnieuw terugkomt.

Gebruikers:

* Forens zelf
* Teamlead/planner (afstemming aanwezigheid kantoor)

Business value:

* Minder te-laat aankomsten.
* Lager gemiddeld reistijdverlies.
* Transparante keuze per dag met duidelijke motivatie.

---

## 2. Data Scope

Minimale datasets:

* Historische weerdata (al opgehaald vanaf 2021-01-01).
* Historische verkeersdata voor traject Gent -> Mechelen (auto).
* Historische treininfo (vertraging/cancel-rate of reisduren, indien beschikbaar).
* Belgische kalender met werkdagen/feestdagen.

Tijdsfilter:

* Enkel Belgische werkdagen (ma-vr, exclusief Belgische feestdagen).

Doelvariabele(n):

* Verwachte reistijd auto naar aankomst 09:00.
* Verwachte reistijd trein naar aankomst 09:00.
* Aanbevolen modus: auto, trein, of thuiswerken.

---

## 3. Beslissingslogica (Output)

Dagelijkse output moet bevatten:

* `recommended_mode`: auto | trein | thuiswerken
* `recommended_departure_time`
* `expected_arrival_time`
* `expected_travel_time_minutes`
* `confidence_or_risk_flag`
* korte reden (bv. "verwachte file + regen", "trein vertragingrisico hoog")

Voorbeeldregel:

* "Dinsdag 07:10 vertrekken met trein. Verwachte aankomst 08:52. Kans op vertraging laag."

---

## 4. EDA Focus

Te onderzoeken patronen:

* Werkdag vs weekend (ter controle, maar model traint op werkdagen).
* Seizoenseffecten (winter/zomer, schoolperiodes).
* Weerinvloed op auto- en treinvertraging.
* Spitsuurpatronen richting 09:00.
* Outliers: uitzonderlijke incidenten/stakingen/extreem weer.

Belangrijk voor presentatie:

* Toon beperkte, duidelijke grafieken die beslissingen ondersteunen.
* Koppel elke grafiek aan een praktische conclusie.

---

## 5. Modeling Approach

Aanbevolen baseline (simpel en uitlegbaar):

1. Regressiemodel voor auto-reistijd.
2. Regressiemodel voor trein-reistijd.
3. Regels/scorelaag die de twee vergelijkt en thuiswerken kiest bij hoog risico.

Mogelijke modellen:

* Linear Regression / Random Forest Regressor
* Eventueel Quantile Regression voor onzekerheidsbanden

Features (voorbeeld):

* Dag van de week
* Maand/seizoen
* Weervariabelen (regen, wind, temperatuur)
* Historische vertragingen per modus
* Indicator Belgische feestdag/brugdag

---

## 6. Evaluatie in Business Terms

Niet alleen RMSE/MAE rapporteren, maar vooral:

* % dagen op tijd (aankomst <= 09:00)
* Gemiddelde "buffer" tot 09:00
* % foutieve moduskeuze (achteraf bleek andere modus beter)
* % dagen met aanbevolen thuiswerk

Operational risk:

* Te optimistische voorspellingen geven te-laat aankomen.
* Te conservatieve voorspellingen geven onnodig vroeg vertrekken of te vaak thuiswerk.

---

## 7. Aanbevelingen (Expected)

Mogelijke eindaanbevelingen:

* Bij regen + dinsdag/donderdag-spits vaker trein verkiezen.
* Bij voorspelde uitzonderlijke file automatisch thuiswerk voorstellen.
* Dagelijkse "vertrek om" melding om 06:30 met fallback-optie.

Operationalisatie:

* Dagelijkse batchrun (vroeg in de ochtend).
* Eenvoudig dashboard of notificatie met advies en vertrouwen.
* Maandelijkse hertraining met nieuwe data.

---

# Final Advice

A successful project is not necessarily the one with the most advanced model.

A successful project is one where:

* the analysis is clear,
* the insights are meaningful,
* the operational implications are understood,
* and a non-technical stakeholder understands the value of the work.

The strongest projects successfully connect:

* data,
* models,
* business decisions,
* and operational reality.

---

# Examples of Business Problems and Operational Impact

## Predicting Customer Churn to Improve Retention

A churn model predicts which customers are likely to leave a company or cancel a subscription.

However, the real business value does not come from the prediction itself.

The value comes from enabling the company to take proactive actions before customers leave.

Examples of operational actions:

* offering discounts or promotions to high-risk customers,
* contacting dissatisfied customers earlier,
* prioritizing customer support resources,
* identifying which customer segments require attention.

A useful business discussion is therefore:

* Which customers should the company target?
* How much should the company spend on retention?
* Is it profitable to retain every customer?
* Which churn drivers can actually be influenced?

A strong project does not only predict churn, but also explains:

* why customers leave,
* which factors matter most,
* and how the company could realistically respond.

---

## Forecasting Demand to Improve Inventory Planning

A forecasting model predicts future product demand.

But accurate forecasts alone do not automatically improve inventory planning.

The important question is:

> How will the forecast influence operational decisions?

Inventory decisions involve trade-offs:

* ordering too much inventory increases storage costs,
* ordering too little inventory creates stockouts and lost sales.

Better forecasts can help companies:

* reduce excess inventory,
* improve warehouse utilization,
* reduce waste,
* improve product availability,
* optimize replenishment timing.

However, operationalizing forecasts is often much more complex than building the forecast itself.

For example:

* How frequently should forecasts be updated?
* How should planners react to forecast uncertainty?
* How much safety stock is still required?
* Which products are most important to forecast accurately?
* What happens if suppliers have long lead times?

Even with extremely accurate forecasts, organizations still need:

* replenishment policies,
* ordering rules,
* supply chain coordination,
* and decision processes.

A useful project therefore explores not only forecast accuracy, but also:

* how forecasts would be used,
* which business decisions they support,
* and where operational limitations still exist.

---

## Predicting Flight Delays to Improve Operations

A flight delay prediction model estimates whether flights are likely to be delayed.

The operational value comes from enabling airports or airlines to react earlier and more effectively.

Possible applications:

* adjusting gate assignments,
* reallocating crews,
* informing passengers earlier,
* adapting turnaround schedules,
* reducing cascading delays across the network.

However, predicting delays is only part of the problem.

Organizations must also decide:

* How early does a prediction need to be useful?
* What confidence level is required before taking action?
* Which actions are operationally feasible?
* What are the costs of false alarms?

For example:

* reacting too aggressively to uncertain predictions may create unnecessary disruptions,
* while reacting too late reduces the value of the prediction.

A strong project therefore explains:

* how predictions could support operational decision-making,
* what actions become possible,
* and what limitations still remain.

---

## Understanding What Influences Airbnb Prices

An Airbnb pricing analysis identifies which factors influence property prices.

Examples:

* location,
* reviews,
* amenities,
* number of rooms,
* seasonality.

The business value comes from helping hosts make better pricing and investment decisions.

Possible operational or strategic actions:

* improving features that increase perceived value,
* optimizing pricing strategies,
* identifying underpriced listings,
* understanding which amenities matter most,
* adapting prices during high-demand periods.

However, interpretation is important.

For example:

* correlation does not always imply causation,
* expensive listings may simply exist in premium neighborhoods,
* some improvements may not justify their cost.

A strong project therefore focuses on:

* identifying meaningful drivers,
* explaining their impact clearly,
* and discussing which insights are actionable in practice.
