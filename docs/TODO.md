- In the explorer, I am showing the cost incurred by the different optimization approaches, but I am not showing the price incured wiht a BESS.

- [x] Add battery degradation cost to the cost function. This is important because aggressive use of the battery can save money on energy costs but may lead to faster degradation and higher replacement costs.

- Compare no-battery vs perfect foresight optimization vs stochastic optimization with different number of scenarios (e.g., 3, 7) (get expected values here). I have been doing something close to Ex post evaluation of the stochastic optimization, but it does not make sense to fix day-ahead grid exchange in a residential setting. Instead, it could make sense to fix the battery schedule and adapt grid exchange in real-time. Keeping both (grid exchange and battery exchange) as recourse decisions make it equivalent to perfect foresight optimization, which is not what we want.


- [x] Use the household dataset from [Germany](../resources/s41597-022-01156-1.pdf) and implement the entire EMS pipeline and perform analysis similar to Rezaeimozafar et al. (2024) [paper](../resources/1-s2.0-S235248472400372X-main.pdf).

- [] Currently, I am running optimization for a single day, and considering that each day is independent and starts at the same initial soc. This is problematic because it does not capture the inter-day dependencies. 