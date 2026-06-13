DATA_DIR := ./data/data_household_germany
GENERATED_DATA_DIR := $(DATA_DIR)/generated
DATASET_VERSION := 1.2.0
YEAR := 2025
GROUND_TRUTH_FILE := $(DATA_DIR)/Dataset_v$(DATASET_VERSION).xlsx

CONFIG_DIR := ./config
STOCHASTIC_OPTIMIZATION_CONFIG_FILE := $(CONFIG_DIR)/stochastic_optimization_config.yaml
BESS_FILE := $(CONFIG_DIR)/sonnenBatterie10.json

SCRIPTS_DIR := ./scripts
PYTHON := .venv/bin/python
STOC_OP_SCENARIOS := 20

WANDB_TRACKING := false

ifeq ($(WANDB_TRACKING),true)
    WANDB_FLAG := --wandb_track
else
    WANDB_FLAG :=
endif

export

.PHONY: app all

app: 
	$(PYTHON) -m streamlit run ./app/main.py

all: \
	$(GENERATED_DATA_DIR)/perfect_foresight_optimization_$(YEAR).csv \
	$(GENERATED_DATA_DIR)/simulated_rt_prices_$(YEAR).csv \
	$(GENERATED_DATA_DIR)/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_$(YEAR).csv \
	$(GENERATED_DATA_DIR)/stochastic_policy_evaluation_with_$(STOC_OP_SCENARIOS)_scenarios_$(YEAR).csv

$(GENERATED_DATA_DIR)/perfect_foresight_optimization_$(YEAR).csv: $(SCRIPTS_DIR)/perfect_foresight_optimization.py $(GROUND_TRUTH_FILE) $(BESS_FILE)
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --battery_file $(BESS_FILE) --year $(YEAR) --start_day_index 0 --num_days 365 --output_file $@

$(GENERATED_DATA_DIR)/stochastic_policy_with_$(STOC_OP_SCENARIOS)_scenarios_$(YEAR).csv: $(SCRIPTS_DIR)/stochastic_optimization.py $(GROUND_TRUTH_FILE) $(STOCHASTIC_OPTIMIZATION_CONFIG_FILE) $(BESS_FILE)
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --battery_file $(BESS_FILE) --config_file $(STOCHASTIC_OPTIMIZATION_CONFIG_FILE) --year $(YEAR) --num_scenarios $(STOC_OP_SCENARIOS) $(WANDB_FLAG) --scenario_output_file $(GENERATED_DATA_DIR)/stochastic_scenario_results_with_$(STOC_OP_SCENARIOS)_scenarios_$(YEAR).csv --output_file $@

$(GENERATED_DATA_DIR)/stochastic_policy_with_$(STOC_OP_SCENARIOS)_scenarios_evaluation_$(YEAR).csv: $(SCRIPTS_DIR)/stochastic_policy_evaluation.py $(GROUND_TRUTH_FILE) $(BESS_FILE) $(GENERATED_DATA_DIR)/stochastic_policy_with_$(STOC_OP_SCENARIOS)_scenarios_$(YEAR).csv
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --battery_file $(BESS_FILE) --policy_file $(GENERATED_DATA_DIR)/stochastic_policy_with_$(STOC_OP_SCENARIOS)_scenarios_$(YEAR).csv --config_file $(STOCHASTIC_OPTIMIZATION_CONFIG_FILE) --start_day_index 0 $(WANDB_FLAG) --output_file $@