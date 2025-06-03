#!/bin/bash

# Export token to environment
export HA_TOKEN=$(jq -r '.ha_token' /data/options.json)
export USE_SSL=$(jq -r '.use_ssl' /data/options.json)

# Start Flask UI in background
cd web
echo "Starting Flask UI"
python3 app.py &
cd ..

# Run collector every 60 seconds
while true; do
  echo "Running collector.py"
  python3 collector.py
  sleep 60
done

