import asyncio
import websockets
import json
import os
from datetime import datetime
import ssl

# --- Configuration (from environment variables, typical for add-ons) ---
HA_TOKEN = os.environ.get("HA_TOKEN")
USE_SSL = os.environ.get("USE_SSL")

# --- Output File Path ---
OUTPUT_FILE = "/app/data/zha_data.json" # Standard path for add-on data storage

# --- Home Assistant WebSocket URL ---
if USE_SSL and USE_SSL.lower() == 'true': # Ensure USE_SSL is explicitly 'true' (string)
  ssl_context = ssl._create_unverified_context() # Use unverified context for self-signed certs common in HA
  HA_URL = "wss://172.30.32.1:8123/api/websocket" # Secure WebSocket URL
else:
  HA_URL = "ws://172.30.32.1:8123/api/websocket" # Insecure WebSocket URL
  ssl_context = None # No SSL context needed for ws://

async def get_zha_data():
    """
    Connects to Home Assistant WebSocket API, fetches ZHA device data,
    and saves it to a JSON file.
    """
    if not HA_TOKEN:
        # Exit if authentication token is not provided
        raise EnvironmentError("HA_TOKEN is not set. Please provide it via the add-on configuration.")

    print(f"Connecting to websocket URL: {HA_URL} (SSL enabled: {USE_SSL})")

    try:
        # Establish WebSocket connection
        async with websockets.connect(HA_URL, ssl=ssl_context, max_size=None) as ws:
            current_msg_id = 1 # Initialize message ID for API requests

            print("Connected to Home Assistant WebSocket.")

            # --- Authentication Process ---
            auth_required = json.loads(await ws.recv())
            if auth_required.get("type") != "auth_required":
                raise Exception("Expected 'auth_required' message, but received something else during connection.")

            print("Received auth_required message. Sending authentication token...")

            await ws.send(json.dumps({
                "type": "auth",
                "access_token": HA_TOKEN
            }))

            # Wait for authentication response
            auth_response = json.loads(await ws.recv())
            if auth_response.get("type") == "auth_ok":
                print("Authentication successful!")
            elif auth_response.get("type") == "auth_invalid":
                raise Exception(f"Authentication failed: {auth_response.get('message', 'Invalid token.')}")
            else:
                print(f"WARNING: Received unexpected message type during authentication: {auth_response.get('type')}. Full response: {auth_response}")
            
            # --- Fetch Area Registry ---
            area_map = {} # Maps area_id to area_name
            await ws.send(json.dumps({"id": current_msg_id, "type": "config/area_registry/list"}))
            area_response = json.loads(await ws.recv())
            current_msg_id += 1
            if area_response.get("success"):
                for area_data in area_response.get("result", []):
                    area_map[area_data["area_id"]] = area_data["name"]
                print(f"Fetched {len(area_map)} areas.")
            else:
                print(f"WARNING: Failed to fetch area registry: {area_response.get('error', 'Unknown error')}. Area names might be incomplete.")

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
                print(f"Fetched {len(entity_response.get('result', []))} entities and mapped to devices.")
            else:
                print(f"WARNING: Failed to fetch entity registry: {entity_response.get('error', 'Unknown error')}. Entity data might be incomplete.")

            # --- Fetch All Current States ---
            all_states_map = {} # Maps entity_id to its state object
            await ws.send(json.dumps({"id": current_msg_id, "type": "get_states"}))
            states_response = json.loads(await ws.recv())
            current_msg_id += 1
            if states_response.get("success"): 
                for state_data in states_response.get("result", []):
                    all_states_map[state_data["entity_id"]] = state_data
                print(f"Fetched {len(all_states_map)} entity states.")
            else:
                print(f"WARNING: Failed to fetch all states: {states_response.get('error', 'Unknown error')}. State data might be incomplete.")

            # --- Fetch ZHA Device List ---
            # Note: The zha/network_info and zha/device_neighbors commands
            # were removed due to "Unknown command" errors on your system.
            # Neighbor data will not be collected directly via API in this version.
            await ws.send(json.dumps({
                "id": current_msg_id,
                "type": "zha/devices"
            }))
            current_msg_id += 1

            devices_msg = await ws.recv()
            devices = json.loads(devices_msg).get("result", [])
            output = [] # List to store processed device data

            print(f"Processing {len(devices)} ZHA devices...")

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
                                        # Attempt to convert state to float for battery level
                                        battery_level = float(state_obj.get("state"))
                                    except (ValueError, TypeError):
                                        # If conversion fails (e.g., state is 'unavailable', 'unknown'),
                                        # set battery_level to None to indicate it's not a valid number.
                                        battery_level = None
                                else:
                                    # If entity's state wasn't found, treat as unavailable
                                    battery_level = None
                                # Assuming a device generally has one primary battery sensor,
                                # we can assign the first one found. If multiple, this picks one.

                # Neighbors data is not available through the working API calls
                neighbors = [] 
                print(f"Neighbor data not available for {name} (IEEE: {ieee}).") # Informative message


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

            print(f"Successfully saved ZHA device data to {OUTPUT_FILE}")

    except websockets.exceptions.ConnectionClosedOK:
        print("WebSocket connection closed gracefully.")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"ERROR: WebSocket connection closed with an error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during data collection: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging

if __name__ == "__main__":
    # Ensure the output directory exists before running
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    asyncio.run(get_zha_data()) # Run the asynchronous data collection function
