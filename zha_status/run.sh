#!/bin/bash

# Read user-supplied HA token from config
HA_TOKEN=$(jq -r '.ha_token' /data/options.json)
if [ "${HA_TOKEN}" ]
  then
    echo "HA_TOKEN=${HA_TOKEN}"
else
    echo "HA_TOKEN not found in configuration"
fi
export HA_TOKEN

# Start Flask UI in background
cd web
python3 app.py &
cd ..

# Run collector every 60 seconds
while true; do
  python3 collector.py
  sleep 60
done

