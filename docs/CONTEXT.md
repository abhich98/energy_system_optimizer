# PV-Battery-Grid interaction

## Energy contracts in Households in Germany

First, German households typically choose between standard fixed-rate plans (with price guarantees), flexible dynamic spot-market tariffs, or the default basic supply (Grundversorgung). Contracts operate on estimated monthly installments (Abschlag) reconciled annually, with widespread availability of 100% renewable (green) energy options. [1, 2, 3, 4] 
The main types of residential energy contracts in Germany include:
### 1. Fixed-Price Contracts with Price Guarantee (Festpreis mit Preisgarantie)

* How it works: Locks in a set price per kilowatt-hour (kWh) for a specific period (usually 12 or 24 months).
* Benefits: Protects households from sudden energy market price spikes.
* Drawbacks: You cannot take advantage if market prices drop, and cancellation terms are locked for the duration. [3] 

### 2. Flexible / Dynamic Tariffs (Dynamische Tarife / Ökostrom)

* How it works: The price fluctuates based on the current wholesale spot-market price.
* Benefits: Can be very cheap during times of high renewable energy generation (e.g., sunny/windy days) and are great for households tracking usage via smart meters.
* Drawbacks: Households take on the risk of price spikes during energy shortages. [1, 4, 5, 6, 7] 

### 3. Basic Default Supply (Grundversorgung)

* How it works: By law, if a household moves into a new home and does not actively sign an energy contract, they are automatically placed on the local Grundversorger (default regional provider) plan.
* Benefits: Offers maximum flexibility with just a two-week cancellation period.
* Drawbacks: It is nearly always the most expensive electricity or gas contract on the market. [2, 8, 9, 10] 

### Billing and Contract Features to Know

* Monthly Installments (Abschlag): Rather than paying for exact usage monthly, households pay a fixed monthly estimate based on historical consumption. [3] 
* Annual Reconciliation (Jahresabrechnung): Once a year, the provider measures actual consumption against the paid installments. If you use less, you get a refund; if you use more, you must pay the difference. [3] 
* Special Termination Right (Sonderkündigungsrecht): If you move to a new city, or if your energy provider raises their prices, you have the legal right to cancel your contract prematurely without penalties. [3, 10] 

You can compare plans and switch providers in your area using platforms like Check24 or specialized green-energy suppliers like Ostrom or Octopus Energy. [4, 11, 12, 13] 

[1] [https://checkalle.de](https://checkalle.de/electricity-comparison-prices/)
[2] [https://www.vattenfall.de](https://www.vattenfall.de/electricity-supply-germany)
[3] [https://octopusenergy.de](https://octopusenergy.de/how-german-energy-market-works)
[4] [https://www.settle-in-berlin.com](https://www.settle-in-berlin.com/electricity-provider-germany/)
[5] [https://www.lumenhaus.com](https://www.lumenhaus.com/solution/dynamic-tariff.html)
[6] [https://www.ostrom.de](https://www.ostrom.de/en/autostrom)
[7] [https://www.cleanenergywire.org](https://www.cleanenergywire.org/dossiers/carbon-free-electricity-system-europe)
[8] [https://www.ostrom.de](https://www.ostrom.de/en/post/beginners-guide-to-the-german-electricity-market)
[9] [https://germanyso.com](https://germanyso.com/en/how-to-germany/for-your-home/best-electricity-providers-germany/)
[10] [https://www.evz.de](https://www.evz.de/en/topics/living-in-germany/leaving-germany/)
[11] [https://www.bd-energy.com](https://www.bd-energy.com/en/green-energy/renewableplus/)
[12] [https://octopusenergy.de](https://octopusenergy.de/how-german-energy-market-works)
[13] [https://green-stay.eu](https://green-stay.eu/how-do-international-students-set-up-utilities-in-a-german-apartment/)

## Common Household Energy Management Framework
For a household equipped with solar panels (PV) and a Battery Energy Storage System (BESS), the goal is usually to maximize self-consumption (using your own solar power) and minimize electricity bills.

To achieve this, the system runs an **Energy Management System (EMS)**. Depending on how advanced the setup is, they schedule and manage energy using one of three levels of sophistication:


### 1. The Standard Approach: Rule-Based / Heuristic (No Optimization)

Most off-the-shelf residential systems today use simple "if-then" rules. It operates on a strict hierarchy in real-time:

* **Rule 1 (PV Priority):** Use PV generation to power the home first.
* **Rule 2 (Excess PV):** If PV generation exceeds home demand, use the extra power to charge the battery.
* **Rule 3 (Grid Last Resort):** If the battery is full and there is still excess PV, export it to the grid. If PV and battery cannot meet demand, buy from the grid.

> **The Flaw:** This approach is purely reactive. It doesn't look ahead at weather forecasts or electricity prices.

---

### 2. The Smart Approach: Deterministic Optimization (Look-Ahead)

More advanced "smart home" setups use a **Model Predictive Control (MPC)** framework. Every day (or every hour), an optimization algorithm solves a linear programming problem based on forecasts:

* **The Inputs:** 24-hour weather forecast (to predict PV yield), historical data (to predict household load), and a fixed or time-of-use (ToU) tariff schedule.
* **The Math:** A linear program calculates the mathematically optimal charging/discharging schedule for the next 24 hours to minimize the total bill.
* **The Action:** It decides ahead of time, for example: *"Keep the battery empty tonight because tomorrow will be incredibly sunny, and we can fill it for free."* or *"Pre-charge the battery from the grid at 3 AM because power is cheap, and we have a high load tomorrow morning."*

---

### 3. The Industrial Approach: Stochastic Optimization (Handling the "Unknowns")

If the household is on a **dynamic/real-time pricing tariff** (where prices change every hour based on the wholesale market), deterministic optimization starts to fail because forecasts are never perfect.

This is where **Two-Stage Stochastic Optimization** comes in (similar to the industry framework we discussed earlier):

* **First-Stage Decision:** The EMS makes a baseline commitment or "strategy" for the day ahead.
* **Second-Stage Recourse:** In real-time, if a cloud passes over (PV drops) or electricity prices suddenly spike, the system adjusts the battery charging speed or curtails usage to protect the household from high costs.

---


By shifting the household's relationship with the grid from "reactive consumer" to "active optimizer," a PV+BESS system can drop electricity bills significantly—sometimes even turning the home into a net earner by exporting power precisely when the grid needs it most.

## Big Industrial Energy Procurement

Big industries do not use household-style dynamic plans; they operate on entirely different, highly complex procurement options.
While a household simply reacts to a pre-determined day-ahead price sheet, large industrial consumers in Germany (like automotive, chemical, or steel plants) act as active financial players in the wholesale energy market. They manage millions of Euros in energy costs using advanced multi-year hedging, direct wholesale market access, and specialized power purchase agreements.
The main energy procurement options for big industries include:
### 1. Tranche and Structured Procurement (Tranchenmodell)

* How it works: Instead of buying all their energy at once or riding the daily spot market, industries buy energy in "tranches" (slices) months or even years in advance.
* The Strategy: A portfolio manager might buy 30% of their expected 2028 electricity needs in 2026, another 40% in 2027, and leave 30% for the short-term spot market. This diversifies their price risk and avoids exposure to sudden market spikes.

### 2. Direct Wholesale Market Access (OTC & Exchange)

* How it works: Massive industrial consumers bypass energy retail utilities entirely. They register directly as trading participants on the [EPEX Spot](https://www.epexspot.com/en) and EEX (European Energy Exchange) or buy Over-The-Counter (OTC) via direct contracts with generation companies.
* The Imbalance Penalty: Unlike households, big industries must submit precise consumption forecasts to the grid operators. If they consume more or less than planned, they are not protected—they are hit with severe financial penalties for creating grid imbalances, forcing them to actively trade on the intraday market to rebalance their positions.

### 3. Corporate Power Purchase Agreements (CPPAs)

* How it works: An industrial company signs a long-term contract (typically 10 to 20 years) directly with a specific renewable energy developer (e.g., an offshore wind farm operator).
* The Benefit: The industry locks in a fixed, predictable green energy price for a decade, protecting them from market volatility, while the wind farm developer secures the guaranteed revenue needed to finance construction.

### 4. Peak Shaving and Demand-Side Response (DSR)

* How it works: Large industries do not just consume energy; they actively alter their production schedules based on real-time grid needs.
* The Incentive: Under German grid regulations, industries can get paid massive subsidies or significantly lower grid fees if they agree to "shave their peaks" (shut down heavy machinery when the grid is stressed) or ramp up production when there is an oversupply of wind power.

### Overview: Households vs. Industrial Energy Procurement

| Feature | German Household (Dynamic Tariff) | Big German Industry |
|---|---|---|
| Primary Market | Day-Ahead Spot Market only. | Futures, Forwards, Day-Ahead, and Intraday Markets. |
| Price Locking | Stated 24 hours in advance. | Locked years in advance via tranches or long-term CPPAs. |
| Volume Flexibility | Unlimited; no penalties for deviation. | Strict forecasting; heavy penalties for real-time imbalances. |
| Grid Fees | Fixed regulated rates per kWh. | Heavily discounted if they optimize consumption or reduce peak load. |


## MPC and Stochastic Optimization: A Perfect Pair
Combining a two-stage stochastic optimization (for day-ahead scheduling) with Model Predictive Control (for real-time operation) is considered the industry gold standard for operating complex energy management systems.
They do not compete; instead, they operate at different timescales. The day-ahead stochastic optimization acts as the strategic planner, while the MPC acts as the tactical operator.

### The Step-by-Step Joint Workflow
#### Step 1: The Day-Ahead Strategic Layer (Two-Stage Stochastic Optimization)

* When it runs: Once per day (e.g., at 11:00 PM for the upcoming day).
* What it does: It looks at a wide range of future scenarios (weather, prices, load) and solves a massive optimization problem.
* What it passes to the MPC: It establishes the baseline rules or "targets" for the next day. These targets typically include:
1. The binding grid import schedule (to satisfy market commitments or avoid peak-demand penalties).
   2. Hourly or end-of-day State of Charge (SoC) targets for the battery, ensuring the battery has enough energy stored for the following day.

#### Step 2: The Real-Time Operational Layer (Model Predictive Control)

* When it runs: Continuously throughout the day (e.g., every 5, 15, or 30 minutes).
* What it does: As the day progresses, the MPC replaces the broad day-ahead scenarios with a highly accurate, short-term deterministic forecast (e.g., looking just 2 to 4 hours ahead).
* How it respects the Day-Ahead Policy: The MPC runs its own mini-optimization window to determine exactly what the battery should do right now. It does this by treating the day-ahead decisions as constraints or penalty factors:
* Constraint: It forces the system to try and stick to the day-ahead grid import plan.
   * Objective: It minimizes real-time deviations. If real-world PV drops unexpectedly, the MPC looks at its 2-hour predictive horizon and commands the battery to discharge now to keep the grid import exactly where the day-ahead policy commanded it to be.

#### How this applies to your specific project
If you wanted to evolve your current study into a live operational system, you would replace your "end-of-day hindsight optimization" with this rolling MPC.
Instead of waiting until the end of the day to see what happened, the MPC would dynamically adjust the battery every 15 minutes to absorb the real-time forecast errors of your PV and load, actively trying to protect the day-ahead grid policy you calculated.



## Model Predictive Control (MPC) or Rolling Horizon Control
True MPC relies on three mandatory pillars:
1) The Model: A mathematical representation of the system (e.g., how the battery's State of Charge changes based on current and power).
2) The Predictive Horizon: Looking ahead \(N\) steps into the future.
3) The Optimizer: A mathematical solver (like Linear Programming or Mixed-Integer Programming) that minimizes a cost function subject to constraints (e.g., battery power limits) across that entire horizon.


## End-of-day/Ex post recourse optimization/validation

This is the most accurate term for what I have been calling "stochastic policy evaluation" so far. It is the process of taking the day-ahead commitment from the first stage, and then optimizing a recourse problem in hindsight using the actual realized load, PV, and prices to see how well the policy would have performed.

> "To evaluate the profitability of the proposed model, we conduct a historical backtesting study. For each day in the testing dataset, the day-ahead policy is first computed. Then, a deterministic ex-post recourse optimization is executed using the actual realized load and PV profiles to determine the final realized cost."


## Backtesting and Performance Metrics

When evaluating the performance of a stochastic optimization policy for PV-Battery-Grid interaction, it's crucial to distinguish between method related metrics (like `SP`, `EV`, `EEV`, `WS`, `EVPI`, `VSS`) and out-of-sample backtest metrics that reflect real-world performance.

During backtesting, the focus shifts from theoretical stochastic-program metrics to realized operational performance.

The most relevant metrics are:

- Realized total cost: what the policy actually would have paid on historical realized load, PV, and prices.
- Savings vs baseline: compare against no battery, rule-based control, or deterministic scheduling.
- Regret vs perfect foresight: realized policy cost minus the cost of a hindsight optimal schedule on the same realized day. This is often the most intuitive benchmark.
- Recourse cost / imbalance cost: how much extra cost comes from having to correct the day-ahead plan in real time.
- First-stage commitment quality: how close the day-ahead import plan was to what was actually needed.
- Peak shaving metrics: reduction in peak grid import, if that matters for the use case.
- Battery usage metrics: throughput, number of cycles, average SOC, constraint violations if any. These matter because a policy can save money by overusing the battery unrealistically.
- Robustness metrics: mean cost, standard deviation, worst day, and quantiles such as P95 cost.

If you are backtesting over many days, the strongest portfolio metrics are usually:

- average daily realized cost
- annual realized cost
- savings relative to baseline
- average regret relative to perfect foresight
- cost variability across days
- performance as a function of forecast quality or number of scenarios

The four classical stochastic-program numbers `SP`, `EV`, `EEV`, and `WS` are still useful, but they are mostly model-based benchmarking quantities. In backtesting, the more decision-relevant question is: “When I fix a policy using only information available at the time, how much would it have actually cost on realized history?”

A clean way to frame it is:

- `SP`, `EEV`, `WS`, `EVPI`, `VSS`: useful for in-model analysis
- realized cost, savings, regret, robustness, and battery stress: useful for backtesting

If you want, I can next give you a compact table mapping each metric to “in-sample model metric” vs “out-of-sample backtest metric.”