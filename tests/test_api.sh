#!/bin/bash
# Example script to test the EsMS API with curl

# Change to script directory so relative file paths work
cd "$(dirname "$0")"

API_URL="http://localhost:8000"

echo "Testing EsMS Energy Optimization API"
echo "===================================="
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
curl -s ${API_URL}/health | python -m json.tool
echo ""
echo ""

# Test optimization endpoints with sample files 
echo "2. Running optimization with dayahead/deterministic/upload..."
curl -X POST ${API_URL}/dayahead/deterministic/upload \
  -F "batteries_json=@../resources/api/sonnenBatterie10.json" \
  -F "forecasts_csv=@../resources/api/20250424_german_household.csv" \
  -F "timestep_hours=0.25" \
  -o ../resources/api/dayahead_deterministic_schedule.csv

if [ $? -eq 0 ]; then
  echo "Optimization complete! Results saved to resources/api/dayahead_deterministic_schedule.csv"
else
  echo "Optimization failed!"
fi
echo ""

echo "3. Running optimization with dayahead/stochastic/upload..."
curl -X POST ${API_URL}/dayahead/stochastic/upload \
  -F "batteries_json=@../resources/api/sonnenBatterie10.json" \
  -F "history_csv=@../resources/api/20250325_20250423_german_household.csv" \
  -F "ahead_prices_csv=@../resources/api/20250424_german_household.csv" \
  -o ../resources/api/dayahead_stochastic_schedule.csv

if [ $? -eq 0 ]; then
  echo "Optimization complete! Results saved to resources/api/dayahead_stochastic_schedule.csv"
else
  echo "Optimization failed!"
fi
echo ""

echo "===================================="
echo "Test complete!"
