import asyncio
import websockets
import json
import os
from datetime import datetime
import ssl

# --- Configuration (from environment variables, typical for add-ons) ---
HA_TOKEN = os.environ.get("HA_TOKEN")
USE_SSL = os.environ.get("USE_SSL")
# New: DEBUG option
# Convert string environment variable to boolean. Defaults to False if not set or invalid.
DEBUG = os.environ.get("DEBUG", "false").lower() in ('true', '1', 'yes')

# --- Output File Path ---
OUTPUT_FILE = "/app/data/zha_data.json" # Standard path for add-on data storage

# --- Home Assistant WebSocket URL ---
if USE_SSL and USE_SSL.lower() == 'true': # Ensure USE_SSL is explicitly 'true' (string)
  ssl_context = ssl._create_unverified_context() # Use unverified context for self-signed certs common in HA
  HA_URL = "wss://172.30.32.1:8123/api/websocket" # Secure WebSocket URL
else:
  HA_URL = "ws://172.30.32.1:8123/api/websocket" # Insecure WebSocket URL
  ssl_context = None # No SSL context needed for ws://

# --- Helper function for logging with timestamps ---
def log_message(message, level="info"):
    """
    Prints a log message with a UTC timestamp.
    'debug' level messages are only shown if DEBUG is True.
    'info' and 'error' level messages are always shown.
    """
    timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
    if level == "debug" and not DEBUG:
        return # Skip debug messages if DEBUG is False
    print(f"[{timestamp}] {level.upper()}: {message}")

async def get_zha_data():
    """
    Connects to Home Assistant WebSocket API, fetches ZHA device data,
    and saves it to a JSON file.
    """
    log_message("Starting ZHA data collection.", level="info")

    if not HA_TOKEN:
        log_message("HA_TOKEN is not set. Please provide it via the add-on configuration.", level="error")
        raise EnvironmentError("HA_TOKEN is not set. Please provide it via the add-on configuration.")

    log_message(f"Connecting to websocket URL: {HA_URL} (SSL enabled: {USE_SSL})", level="debug")

    try:
        # Establish WebSocket connection
        async with websockets.connect(HA_URL, ssl=ssl_context, max_size=None) as ws:
            current_msg_id = 1 # Initialize message ID for API requests

            log_message("Connected to Home Assistant WebSocket.", level="debug")

            # --- Authentication Process ---
            auth_required = json.loads(await ws.recv())
            if auth_required.get("type") != "auth_required":
                log_message(f"Expected 'auth_required' message, but received: {auth_required.get('type')}", level="error")
                raise Exception("Expected 'auth_required' message, but received something else during connection.")

            log_message("Received auth_required message. Sending authentication token...", level="debug")

            await ws.send(json.dumps({
                "type": "auth",
                "access_token": HA_TOKEN
            }))

            # Wait for authentication response
            auth_response = json.loads(await ws.recv())
            if auth_response.get("type") == "auth_ok":
                log_message("Authentication successful!", level="debug")
            elif auth_response.get("type") == "auth_invalid":
                log_message(f"Authentication failed: {auth_response.get('message', 'Invalid token.')}", level="error")
                raise Exception(f"Authentication failed: {auth_response.get('message', 'Invalid token.')}")
            else:
                log_message(f"Received unexpected message type during authentication: {auth_response.get('type')}. Full response: {auth_response}", level="warning") # Use warning level for unexpected but not fatal

            # --- Fetch Area Registry ---
            area_map = {} # Maps area_id to area_name
            await ws.send(json.dumps({"id": current_msg_id, "type": "config/area_registry/list"}))
            area_response = json.loads(await ws.recv())
            current_msg_id += 1
            if area_response.get("success"):
                for area_data in area_response.get("result", []):
                    area_map[area_data["area_id"]] = area_data["name"]
                log_message(f"Fetched {len(area_map)} areas.", level="debug")
            else:
                log_message(f"Failed to fetch area registry: {area_response.get('error', 'Unknown error')}. Area names might be incomplete.", level="warning")

            # --- Fetch Entity Registry ---
            device_entities_map = {} # Maps device_id to a list of its entities
            await ws.send(json.dumps({"id": current_msg_id, "type": "config/entity_registry/list"}))
            entity_response = json.loads(await ws.recv())
            current_msg_id += 1
            if entity_response.get("success"):
                for entity_data in entity_response.get("result", []):
                    device_id = entity_data.get("device_id")
                    if device_id:
                        if device_id not in device_entities_map:
                            device_entities_map[device_id] = []
                        device_entities_map[device_id].append(entity_data)
                log_message(f"Fetched {len(entity_response.get('result', []))} entities and mapped to devices.", level="debug")
            else:
                log_message(f"Failed to fetch entity registry: {entity_response.get('error', 'Unknown error')}. Entity data might be incomplete.", level="warning")

            # --- Fetch All Current States ---
            all_states_map = {} # Maps entity_id to its state object
            await ws.send(json.dumps({"id": current_msg_id, "type": "get_states"}))
            states_response = json.loads(await ws.recv())
            current_msg_id += 1
            if states_response.get("success"): 
                for state_data in states_response.get("result", []):
                    all_states_map[state_data["entity_id"]] = state_data
                log_message(f"Fetched {len(all_states_map)} entity states.", level="debug")
            else:
                log_message(f"Failed to fetch all states: {states_response.get('error', 'Unknown error')}. State data might be incomplete.", level="warning")

            # --- Fetch ZHA Device List ---
            await ws.send(json.dumps({
                "id": current_msg_id,
                "type": "zha/devices"
            }))
            current_msg_id += 1

            devices_msg = await ws.recv()
            devices = json.loads(devices_msg).get("result", [])
            output = [] # List to store processed device data

            log_message(f"Processing {len(devices)} ZHA devices...", level="debug")

            # --- Process Each ZHA Device ---
            for device in devices:
                ieee = device.get("ieee")
                name = device.get("user_given_name") or device.get("name") or "Unknown Device"
                last_seen = device.get("last_seen")
                
                device_id = device.get("device_id") 

                # Determine Area Name
                device_area_name = "N/A"
                if device.get("area_id"): 
                    device_area_name = area_map.get(device["area_id"], "Unknown Area")
                
                exposed_sensor_entity_ids = []
                battery_level = None # Initialize battery_level for current device

                # Try to find battery level and other exposed sensors
                if device_id and device_id in device_entities_map:
                    for entity_data in device_entities_map[device_id]:
                        entity_id = entity_data.get("entity_id")
                        if entity_id:
                            exposed_sensor_entity_ids.append(entity_id) # Collect all exposed sensors

                            # Check if this entity is a battery sensor
                            if entity_data.get("device_class") == "battery" or \
                                ("battery" in entity_id.lower() and entity_data.get("unit_of_measurement") == "%"):
                                
                                if entity_id in all_states_map:
                                    state_obj = all_states_map[entity_id]
                                    try:
                                        battery_level = float(state_obj.get("state"))
                                    except (ValueError, TypeError):
                                        battery_level = None # If conversion fails, set to None
                                else:
                                    battery_level = None # If entity's state wasn't found, treat as unavailable

                # Neighbors data is not available through the working API calls
                neighbors = [] 
                log_message(f"Neighbor data not available for {name} (IEEE: {ieee}).", level="debug")


                # Append processed device data to the output list
                output.append({
                    "name": name,
                    "last_seen": last_seen,
                    "area": device_area_name, 
                    "manufacturer": device.get("manufacturer", ""),
                    "model": device.get("model", ""),
                    "quirk": device.get("quirk_class", ""),
                    "lqi": device.get("lqi"),
                    "rssi": device.get("rssi"),
                    "ieee": ieee,
                    "nwk": device.get("nwk"),
                    "device_type": device.get("device_type", ""),
                    "power_source": device.get("power_source", ""),
                    "attributes": device.get("attributes", {}),
                    "neighbors": neighbors, # This will always be an empty list
                    "exposed_sensors": exposed_sensor_entity_ids, 
                    "battery_level": battery_level 
                })

                # Small delay to avoid overwhelming the Home Assistant API
                await asyncio.sleep(0.1)

            # --- Save Processed Data to JSON File ---
            os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True) # Ensure directory exists
            with open(OUTPUT_FILE, "w") as f:
                json.dump({
                    "timestamp": datetime.utcnow().isoformat(), # Record data collection timestamp
                    "devices": output
                }, f, indent=2) # Pretty print JSON with 2-space indentation

            log_message(f"Successfully saved ZHA device data to {OUTPUT_FILE}", level="info")

    except websockets.exceptions.ConnectionClosedOK:
        log_message("WebSocket connection closed gracefully.", level="info")
    except websockets.exceptions.ConnectionClosedError as e:
        log_message(f"WebSocket connection closed with an error: {e}", level="error")
    except Exception as e:
        log_message(f"An unexpected error occurred: {e}", level="error")
        import traceback
        traceback.print_exc() # Print full traceback for debugging

if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    asyncio.run(get_zha_data())
