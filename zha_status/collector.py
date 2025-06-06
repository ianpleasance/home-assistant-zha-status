import asyncio
import websockets
import json
import os
from datetime import datetime, timedelta # Import timedelta for time calculations
import ssl

# --- Configuration (from environment variables, typical for add-ons) ---
HA_TOKEN = os.environ.get("HA_TOKEN")
USE_SSL = os.environ.get("USE_SSL")
DEBUG = os.environ.get("DEBUG", "false").lower() in ('true', '1', 'yes')

# New: Configurable time for a device to be considered offline, in minutes
OFFLINE_THRESHOLD_MINUTES = int(os.environ.get("OFFLINE_THRESHOLD_MINUTES", "60"))

# --- File Paths ---
OUTPUT_FILE = "/app/data/zha_data.json" # Main data output
OFFLINE_COUNTS_FILE = "/app/data/offline_counts.json" # New file for persistent offline tracking

# --- Home Assistant WebSocket URL ---
if USE_SSL and USE_SSL.lower() == 'true':
  ssl_context = ssl._create_unverified_context()
  HA_URL = "wss://172.30.32.1:8123/api/websocket"
else:
  HA_URL = "ws://172.30.32.1:8123/api/websocket"
  ssl_context = None

# --- Helper function for logging with timestamps ---
def log_message(message, level="info"):
    timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
    if level == "debug" and not DEBUG:
        return
    print(f"[{timestamp}] {level.upper()}: {message}")

async def get_zha_data():
    """
    Connects to Home Assistant WebSocket API, fetches ZHA device data,
    calculates offline status and counts, and saves data to JSON files.
    """
    log_message("Starting ZHA data collection.", level="info")

    if not HA_TOKEN:
        log_message("HA_TOKEN is not set. Please provide it via the add-on configuration.", level="error")
        raise EnvironmentError("HA_TOKEN is not set. Please provide it via the add-on configuration.")

    log_message(f"Connecting to websocket URL: {HA_URL} (SSL enabled: {USE_SSL})", level="debug")

    # --- Load Persistent Offline Tracking Data ---
    offline_tracking_data = {} # Stores {"ieee": {"count": N, "was_offline": True/False}}
    try:
        os.makedirs(os.path.dirname(OFFLINE_COUNTS_FILE), exist_ok=True) # Ensure directory exists
        with open(OFFLINE_COUNTS_FILE, 'r') as f:
            offline_tracking_data = json.load(f)
        log_message(f"Loaded offline tracking data for {len(offline_tracking_data)} devices.", level="debug")
    except (FileNotFoundError, json.JSONDecodeError):
        log_message("Offline tracking data file not found or is empty/corrupt. Starting fresh for counts.", level="debug")
    except Exception as e:
        log_message(f"ERROR: Could not load offline tracking data: {e}", level="error")


    try:
        async with websockets.connect(HA_URL, ssl=ssl_context, max_size=None) as ws:
            current_msg_id = 1 

            log_message("Connected to Home Assistant WebSocket.", level="debug")

            auth_required = json.loads(await ws.recv())
            if auth_required.get("type") != "auth_required":
                log_message(f"Expected 'auth_required' message, but received: {auth_required.get('type')}", level="error")
                raise Exception("Expected 'auth_required' message, but received something else during connection.")

            log_message("Received auth_required message. Sending authentication token...", level="debug")

            await ws.send(json.dumps({
                "type": "auth",
                "access_token": HA_TOKEN
            }))

            auth_response = json.loads(await ws.recv())
            if auth_response.get("type") == "auth_ok":
                log_message("Authentication successful!", level="debug")
            elif auth_response.get("type") == "auth_invalid":
                log_message(f"Authentication failed: {auth_response.get('message', 'Invalid token.')}", level="error")
                raise Exception(f"Authentication failed: {auth_response.get('message', 'Invalid token.')}")
            else:
                log_message(f"Received unexpected message type during authentication: {auth_response.get('type')}. Full response: {auth_response}", level="warning")
            
            # Fetch registries and states
            area_map = {}
            await ws.send(json.dumps({"id": current_msg_id, "type": "config/area_registry/list"}))
            area_response = json.loads(await ws.recv())
            current_msg_id += 1
            if area_response.get("success"):
                for area_data in area_response.get("result", []):
                    area_map[area_data["area_id"]] = area_data["name"]
                log_message(f"Fetched {len(area_map)} areas.", level="debug")
            else:
                log_message(f"Failed to fetch area registry: {area_response.get('error', 'Unknown error')}. Area names might be incomplete.", level="warning")

            device_entities_map = {}
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

            all_states_map = {}
            await ws.send(json.dumps({"id": current_msg_id, "type": "get_states"}))
            states_response = json.loads(await ws.recv())
            current_msg_id += 1
            if states_response.get("success"): 
                for state_data in states_response.get("result", []):
                    all_states_map[state_data["entity_id"]] = state_data
                log_message(f"Fetched {len(all_states_map)} entity states.", level="debug")
            else:
                log_message(f"Failed to fetch all states: {states_response.get('error', 'Unknown error')}. State data might be incomplete.", level="warning")

            await ws.send(json.dumps({
                "id": current_msg_id,
                "type": "zha/devices"
            }))
            current_msg_id += 1

            devices_msg = await ws.recv()
            devices = json.loads(devices_msg).get("result", [])
            output = [] 

            log_message(f"Processing {len(devices)} ZHA devices...", level="debug")

            current_utc = datetime.utcnow() # Define current_utc once for consistency

            # --- Process Each ZHA Device ---
            for device in devices:
                ieee = device.get("ieee")
                name = device.get("user_given_name") or device.get("name") or "Unknown Device"
                last_seen_str = device.get("last_seen") # Renamed to avoid clash with timedelta
                
                device_id = device.get("device_id") 

                device_area_name = "N/A"
                if device.get("area_id"): 
                    device_area_name = area_map.get(device["area_id"], "Unknown Area")
                
                exposed_sensor_entity_ids = []
                battery_level = None

                # --- Calculate Offline Status and Count ---
                device_offline_tracking = offline_tracking_data.get(ieee, {"count": 0, "was_offline": False})
                offline_count = device_offline_tracking["count"]
                was_previously_offline = device_offline_tracking["was_offline"]
                is_currently_offline = False # Default assumption is online

                if last_seen_str:
                    try:
                        last_dt = datetime.fromisoformat(last_seen_str.replace('Z', ''))
                        time_since_last_seen = current_utc - last_dt
                        # If time since last seen is greater than threshold, device is currently offline
                        if time_since_last_seen.total_seconds() > OFFLINE_THRESHOLD_MINUTES * 60:
                            is_currently_offline = True
                    except ValueError:
                        log_message(f"Could not parse last_seen '{last_seen_str}' for {name} (IEEE: {ieee}). Treating as offline.", level="warning")
                        is_currently_offline = True # Treat unparseable last_seen as offline
                else:
                    # If last_seen is None or empty, device is considered offline
                    is_currently_offline = True
                
                # Increment offline count if device just transitioned from online to offline
                if is_currently_offline and not was_previously_offline:
                    offline_count += 1
                    log_message(f"Device {name} (IEEE: {ieee}) just went offline. New count: {offline_count}", level="debug")
                
                # Update current offline status for next run's tracking
                offline_tracking_data[ieee] = {
                    "count": offline_count,
                    "was_offline": is_currently_offline
                }
                # --- End Offline Status and Count Calculation ---


                # --- Battery Level Detection ---
                if device_id and device_id in device_entities_map:
                    for entity_data in device_entities_map[device_id]:
                        entity_id = entity_data.get("entity_id")
                        if entity_id:
                            exposed_sensor_entity_ids.append(entity_id)

                            if entity_data.get("device_class") == "battery" or \
                                ("battery" in entity_id.lower() and entity_data.get("unit_of_measurement") == "%"):
                                
                                if entity_id in all_states_map:
                                    state_obj = all_states_map[entity_id]
                                    try:
                                        battery_level = float(state_obj.get("state"))
                                    except (ValueError, TypeError):
                                        battery_level = None
                                else:
                                    battery_level = None
                
                neighbors = [] # Still not collecting neighbors via working API calls
                log_message(f"Neighbor data not available for {name} (IEEE: {ieee}).", level="debug")


                output.append({
                    "name": name,
                    "last_seen": last_seen_str, # Use the original string here
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
                    "neighbors": neighbors, 
                    "exposed_sensors": exposed_sensor_entity_ids, 
                    "battery_level": battery_level,
                    "offline_count": offline_count, # NEW: Add the offline count
                    "is_currently_offline": is_currently_offline # NEW: Add current offline status
                })

                await asyncio.sleep(0.05) # Reduced sleep slightly for faster processing

            # --- Save Main Data to JSON File ---
            os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
            with open(OUTPUT_FILE, "w") as f:
                json.dump({
                    "timestamp": datetime.utcnow().isoformat(),
                    "devices": output
                }, f, indent=2)

            log_message(f"Successfully saved ZHA device data to {OUTPUT_FILE}", level="info")

            # --- Save Persistent Offline Tracking Data ---
            try:
                os.makedirs(os.path.dirname(OFFLINE_COUNTS_FILE), exist_ok=True)
                with open(OFFLINE_COUNTS_FILE, "w") as f:
                    json.dump(offline_tracking_data, f, indent=2)
                log_message(f"Saved offline tracking data to {OFFLINE_COUNTS_FILE}", level="debug")
            except Exception as e:
                log_message(f"ERROR: Could not save offline tracking data: {e}", level="error")


    except websockets.exceptions.ConnectionClosedOK:
        log_message("WebSocket connection closed gracefully.", level="info")
    except websockets.exceptions.ConnectionClosedError as e:
        log_message(f"ERROR: WebSocket connection closed with an error: {e}", level="error")
    except Exception as e:
        log_message(f"An unexpected error occurred: {e}", level="error")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    asyncio.run(get_zha_data())
