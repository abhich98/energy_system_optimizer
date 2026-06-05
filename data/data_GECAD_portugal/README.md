# Dataset for Daily Energy Management: Renewable Generation, Consumption, and Storage

## Overview
The file includes several sheets, grouped into four main categories:

1. Full-year historical data
2. Seasonal blocks
3. Representative daily scenarios
4. Real battery charge/discharge profiles

> "The authors acquired PV generation and demand data at the GECAD research center from building N (GECAD) located at ISEP in Porto/Portugal. Additionally, the energy price data (€/MWh) were obtained from the OMIE (Operator of the Iberian Energy Market), reflecting conditions in Portugal."


> "Real battery charging and discharging data were collected from the BMS of three battery energy storage systems (BESS) with 2.4 kWh of capacity each. These BESS are located at the GECAD research center, the building N at ISEP in Porto/Portugal."

Below is a description of each sheet and its structure.

### 2023 Data Sheet
This sheet includes hourly data for the entire year of 2023. The columns are:
- **Date** (column A): Timestamp
- **PV generation** (kW) (column B)
- **Consumption** (kW) (column C)
- **Consumption** (pu) (column D): Normalized by the annual peak load
- **Energy price** (EUR/MWh) (column E)
- **Energy price** (EUR/kWh) (column F): Converted for usability

### Seasonal Data Sheets ("Winter", "Spring", "Summer", "Autumn")
Each of these seasonal sheets presents hourly data grouped by season. The structure is identical to the "2023 data" sheet.

### Representative Scenario Sheets
For each season, representative daily scenarios were created. The scenarios are grouped by the number of clusters used (3, 9, 12, 27, and 50). For example:
- "Set of 3 Winter Scenarios"
- "Set of 50 Autumn Scenarios"

Each scenario file includes the following columns:
- **Scenario** (column A): Scenario ID
- **Hour** (column B)
- **PV generation** (kW) (column C)
- **Consumption** (kW) (column D)
- **Energy price** (EUR/kWh) (column E)
- **Probability** (%) (column F): Probability of occurrence of each scenario

### Battery SOC Profiles Sheet
This sheet includes real data from three batteries tested over a 24-hour period, sampled every 15 minutes (96 intervals). The batteries were operated under different SOC conditions. Each profile is shown in a separate set of columns:
- **Period** (columns A / E / I): Index from 1 to 96
- **Time** (columns B / F / J)
- **SOC** (%) (columns C / G / K)
- **Temperature** (°C) (columns D / H / L)

## License
This dataset is released under the Creative Commons Attribution 4.0 International License (CC BY 4.0). You are free to use, share, and adapt the data, provided proper credit is given.

## Citation
If you use this dataset, please cite:

Tayenne, L., Bruno, R., Pedro, F., Luis, G., & Zita, V. (2025). Dataset for daily energy management: Renewable generation, consumption, and storage (v1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.14918474