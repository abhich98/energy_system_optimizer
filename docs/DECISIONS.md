This document serves as a comprehensive decision log for the key methodological choices made in this project.

## K-medoids for Scenario Generation

Since, the goal is to generate representative scenarios from a limited historical dataset (the last 90 or less days of PV and load profiles), I chose K-medoids over K-means for clustering.

- The historical data window is short is short in my study, so K-medoids selects actual days from the dataset as cluster centers, whereas K-means would create synthetic average profiles that may not be realistic.

- K-medoids is more robust to outliers, which is important when working with a small dataset where a single anomalous day (e.g., an extreme weather event) could skew generated scenarios if K-means were used.

- Also, I wanted to test two different strategies in my study, considering load and PV profiles from the last few days (3-15 days) as scenarios vs. using generating scenarios from a larger historical window (30-90 days). K-medoids allows me to select representative days from the historical window which makes the coparison between the two strategies more meaningful and grounded in actual data.

* (Preserving Time-Step Correlations) By averaging time steps, K-means can destroy the variance and temporal characteristics unique to specific weather patterns. K-medoids preserves the exact hour-to-hour trajectory and correlation of the chosen historical day.


## Scenario Generation with Load and PV

When using K-medoids for scenario generation, I can either cluster load and PV profiles separately or jointly.

Decision: **Jointly**

It is crucial to **jointly cluster the load and PV profiles together** because load and PV profiles are often correlated (e.g., sunny days may have higher loads due to air conditioning), and also this gives one probability for each scenario that captures the joint distribution of load and PV.

But, for calculating the distance metric, I calculated the distances for PV and load separately and then added them together before running K-medoids. 

- This is a more rigorous approach than simply concatenating the load and PV vectors into a single vector and calculating distance on that. In the latter case, the distance metric would treat all 48 elements (24 for load and 24 for PV) equally, which is generally not ideal since the load and PV profiles may have different scales and variances.

- Also, by splitting the calculation, I gain precise control over how each variable influences the clustering process. Once I calculated the individual distance matrices for the past `P` days, I could combine them using a weighted sum:

$$D_{joint}(A, B) = \alpha \cdot D_{PV}(A, B) + \beta \cdot D_{Load}(A, B)$$

Where $\alpha$ and $\beta$ are weights that sum to 1 ($\alpha + \beta = 1$). This let me adjust the optimization's sensitivity based on what I want to achieve or what my system constraints look like:

* **Balanced Framework ($\alpha = 0.5, \beta = 0.5$):** PV volatility and load patterns are given equal importance in defining what a "representative day" looks like.
* **Solar-Driven Framework ($\alpha = 0.7, \beta = 0.3$):** If the household has a massive PV array but very small or stable base loads, the financial risk mostly comes from clouds. Weighting PV higher forces K-medoids to focus on capturing pristine vs. highly volatile solar profiles, while keeping load as a secondary grouping factor.
* **Load-Driven Framework ($\alpha = 0.3, \beta = 0.7$):** If a household features highly unpredictable heavy loads (like irregular EV charging or a heat pump turning on randomly) but the weather in the area is consistently sunny, scenarios should prioritize capturing human behavior variance over weather variance.

### Step-by-Step Implementation Workflow

1. Create a $P \times 24$ matrix for PV and scale it by its peak capacity ($PV / PV_{cap}$) and create a $P \times 24$ matrix for Load and scale it by its historical maximum peak ($Load / Load_{max}$).


2. **Compute Distance Matrices Separately:**
* Calculate a $P \times P$ pairwise distance matrix for the PV data ($Mat_{PV}$) using standard Manhattan distance. Do the same with the Load data to get $Mat_{Load}$.

3. **Linear Combination:** * Multiply each matrix by chosen weights and add them together to form final $P \times P$ joint distance matrix ($Mat_{Joint}$).
4. **Feed into K-medoids:** Pass this custom $Mat_{Joint}$ directly into K-medoids algorithm (`kmedoids` package in Python allows to input a precomputed distance matrix) to perform clustering and scenario selection.


### Distance Metrics

I used **Manhattan Distance (L1 norm)** instead of Euclidean Distance (L2 norm) for the individual metrics.

Because Manhattan distance sums the absolute vertical differences hour-by-hour rather than squaring them, it acts linearly. In energy systems, financial grid tariffs are linear (one pays per kWh consumed). Manhattan distance translates much more naturally to the actual "energy volume difference" between two days, which will pass cleaner, more meaningful scenario probabilities into the downstream two-stage stochastic optimization model.

## Consumption profile form 2019 and price profile from 2025

By merging the 2019 consumption profile with the 2025 price profile, I am essentially assuming that the household's energy consumption patterns remain unchanged over time, while the electricity prices evolve according to the recent market conditions.

## Synthesyzing Dynamic Tariffs for household customers in Germany

Following the electricity price/charge breakdown provided in this article (https://www.cleanenergywire.org/factsheets/what-german-households-pay-electricity), the average retail price of electricity for households in Germany was around **38 cents per kWh** (0.38 €/kWh) in the year 2025. Of this 0.38 €/kWh, crudely **~35%** (~0.133 €/kWh) is the 'average' spot market price, while the remaining **~65%** (~0.247 €/kWh) consists of taxes, levies, and grid fees. I will add this fixed component of 0.247 €/kWh to the spot market price to create a more realistic dynamic tariff for household customers for the optimization model.

## Parameter Selection for the sonnenBatterie 10 (5.5 kWh Variant)
The parameters provided for the smaller **5.5 kWh variant** of the sonnenBatterie 10 based on the technical datasheet:

```json
{
  "id": "sonnenBatterie_10_5.5kWh",
  "capacity": 5.5,
  "max_charge": 3.4,
  "max_discharge": 3.4,
  "charge_efficiency": 0.954,
  "discharge_efficiency": 0.959,
  "initial_soc": 2.75,
  "min_soc": 0.5,
  "max_soc": 5.0,
  "degradation_cost": 0.05 # read below for how I got to this value
}

```


### Is there information in the document to calculate degradation cost?

There are differnt ways to model battery degradation, to keep it simple and transparent, I chose to use a **cycle-based degradation cost** approach. This means that every time the battery goes through a full charge-discharge cycle, it incurs a certain cost that reflects the wear and tear on the battery.

The document provides the core physical metric needed to establish a degradation baseline: it explicitly states that the Lithium Iron Phosphate (LFP) cell technology is rated for **10,000 cycles** (*Zyklen*). To convert this cycle life into a financial penalty measured in **Euros/kWh**, I combined this physical limit with the external financial asset value.

Formula used:

$$\text{Degradation Cost (€/kWh)} = \frac{\text{Investment Cost of the Battery System (€)}}{\text{Usable Capacity (kWh)} \times \text{Total Cycle Life} \times \text{Round-Trip Efficiency}}$$

#### Example Calculation:

Assuming a realistic market purchase and installation cost of **€5,500**** in Germany for this specific 5.5 kWh sonnen system.

1. **Usable Capacity:** $5.0\text{ kWh}$.

2. **Cycle Life:** $10,000$ cycles.

3. **Round-Trip Efficiency ($\eta_{rt}$):** $0.954 \times 0.959 \approx 0.915$ ($91.5\%$).


$$\text{Degradation Cost} = \frac{5500}{5.0 \times 10000 \times 0.915} = \frac{5500}{45750} \approx \mathbf{0.120\text{ Euros/kWh}}$$

>> But, this value of 0.120 €/kWh turned out to be quite high, with very small incentive for the optimization model to use the battery at all. So, I decided to be more conservative and set the degradation cost to **0.05 €/kWh** to allow the model to use the battery more freely while still accounting for degradation in a simplified way.