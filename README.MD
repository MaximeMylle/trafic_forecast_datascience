# Datascience syntra group-assignment ML

## Context

The general idea of the project, is to predict if traffic will be busy on a certain trajectory, based on a few datasets:

* a historical dataset containing info of sensors, with vehicule-counts, on which hour, on which date
* a dataset of some basic weather info
* some extra informatrion about the specific day, like which day of the week, was it a holiday, etc
* a dataset about train-travel times

combining all these datasets into one, we want to use machine learning to be able top predict whether or not we stay home, take the train or still take the car.

some random usecases:

* its a public holiday, the sun is shining, its hot outside. - we would assume that lots of people will be on the road, coming or returning from the seaside - better to stay home?

* its a tuesday, and its freezing with heavy snow - we would assume that more acciudents will happen, which will result in a heavier vehiculevount on the read-sensor api - better to stay home?

* its a wednesday, sunny but cold, not too much trafic - take the car?

* its weekend, good weateher
* its weekend bad weather

---

a mockup-proeject has been generated with copilot by Marc already, which should give us a general idea on what to expect.

next steps are cutting this up in clear steps, re-itterate over these steps, assign a part of the work to each team-member.

---

data scope: we would use data starting from january 2021 up untill december 2025. according to initial research, for all datasources the data should be available ( not from 2020, we want to evade the covid-period, which will impact our predictions because of lockdown - no traffic)

## project tasks

out the top of my mind, but please add if needed:

1. fetch all correct datasources -( trafic data | wheather data | data bout the day itself) in CSV format preferrably
2. combine all datasources correctly into 1 single dataframe, matching all sources on DateTime
3. Analyse the current dataset, check if we actually see spikes in the data, where we would expect it (tuesdays and thursdays, beginning of holiday-periods, etc)
4. make some classifications of the data. ( this will make the ML-part less complex and more understandable)
    * we will need to define what actually is considered to be 'trafic jams/ busy road' - devide into no trafic, light trafic, medium trafic and heavy trafic
    * simple classification for weather, or is this not needed?
    * we need to decide what the end-result should be, classification of final answer, right now, we have: stay home and take the car, or take the train.
5. make some graphs and analysis on the whole dataset, do we have missing data? some totals etc.
6. with the help of claude or another AI assistant, set up a ML-model to train data
7. check with data anlysis and comparison how accurate our ML-model is, try to figure out which features are most important/have the biggest influence on the results
8. Make a 15-min presentation of what we have done, what we achieved, including a live demo

--

## Agenda

* 02/06/2026 - everyone should understand the basics for the project, and we should already do some task-assigning to each group member
* 09/06/2026 - Marc and Maxime do their GDPR-exam from 18h15 till 19h15, after that we whould set-up a teams meeting, to go over the project all together (no need to come to syntra mechelen) 
* 16/06/2026 - again teams-meeting, by now, we should have our project up and running, this meeting more to allign and flatten out all kinks and bumps, and start making the presenation together
* 23/06/2026 - DUE DATE, we all come to syntra mechelen to present our project together

## Datasets

## railway historical dataset

https://data.gov.be/en/organisations/infrabel

### open-meteo

https://archive-api.open-meteo.com/v1/archive

### traffic data 

??? Marc where did your AI get the data? can you trace back?

i think it was DATEX II - i dont see a reference in the notebook how the data was fetched.

we need to decided what point ( or 2?) we should us, to then extrapolate this for the trajectory Ghent-Mechelen?

a suggestion by my ai-session: ( but using dataset from VDV : https://wegenenverkeer.be/DataportaalVerkeersgegevens)

```
Your route: Ghent → Mechelen (arriving 9:00 AM)
The route is E40/A10 east → Brussels Ring R0 north → E19/A1 north → Mechelen. Total ~75 km, free-flow time ~50 min, but during morning rush this can become 1.5–2.5 hours.
The route crosses three distinct bottleneck zones:

Merelbeke/Ghent exit — often already slow leaving Ghent
Aalst interchange (exit 18) — merging traffic from Ghent and local commuters
Brussels Ring (R0) — the biggest wildcard, can easily add 30–60 min alone


The best single measurement point: A10 near Wetteren
~35 km from Ghent, before the Aalst interchange, this is the ideal proxy sensor because:

It's on the open highway before the first major merge, so speed here is a clean early indicator of what the whole corridor will do
The E40/A10 through Wetteren (Oost-Vlaanderen) is a well-instrumented section — MIV has multiple detection loops there Controlewiki
If it's already slow at Wetteren at 7:45 AM, the rest will be worse. If it's free-flowing, the R0 is the main remaining uncertainty

A second sensor at Aalst (km ~50) would let you separately estimate the R0 contribution, which could improve your extrapolation meaningfully.

What VDV actually gives you (Jan 2021–Dec 2025)
The Vlaams Dataportaal Verkeersgegevens lets you download data per quarter-hour, hour, or day per road segment, from cameras, detection loops, and radars — including 24/7 highway monitoring. Agentschap Wegen en Verkeer
For your timeframe, here's what's realistic:
Data fieldGranularityAvailableVehicle count15-min / hourly✅ Jan 2021–Dec 2025Average speed (km/h)15-min / hourly✅ Jan 2021–Dec 2025Vehicle class split (car/truck/etc)hourly✅Per-lane datahourly✅ (on instrumented sections)Travel time for full route❌ not directlyMust be estimated
The data is not a full travel time from Ghent to Mechelen — it's speed and volume at individual sensor points. You extrapolate total travel time like this:
travel_time_segment = segment_length / avg_speed_at_sensor
total_trip ≈ Σ(segment_length / speed_sensor_i)
With one sensor at Wetteren you can estimate the E40 leg well. The R0 adds noise because it's a different road with its own dynamics — ideally you'd also pull a sensor from around Groot-Bijgaarden or Zellik on the R0.

Accuracy you can expect

Wetteren speed alone → full trip time: rough ±15–20 min accuracy
Wetteren + Aalst + one R0 sensor: ±8–12 min, good enough to decide "car vs train vs WFH"
Your model target (busy/not busy) is binary, so even the rough proxy works well as a feature

For a binary "is it worth taking the car today" model, a single sensor with weather + weekday + holiday is genuinely enough to get a solid model.
```

---

## Project task division

* assemble and analyse trafic-sensor dataset: Laure
* assemble and analyse train-trajectory dataset : Jack
* assemble and analyse wheather data : Maxime
* set up example mockup projecft to have headstart, and subdevide into sections again: Marc
* 
