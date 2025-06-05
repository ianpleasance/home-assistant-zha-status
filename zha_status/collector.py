import asyncio
import websockets
import json
import os
from datetime import datetime
import ssl

HA_TOKEN = os.environ.get("HA_TOKEN")
USE_SSL = os.environ.get("USE_SSL")

OUTPUT_FILE = "/app/data/zha_data.json"

if USE_SSL:
  ssl_context = ssl._create_unverified_context()
  HA_URL = "wss://172.30.32.1:8123/api/websocket"
else:
  HA_URL = "ws://172.30.32.1:8123/api/websocket"
  ssl_context = None

async def get_zha_data():
    if not HA_TOKEN:
        raise EnvironmentError("HA_TOKEN is not set. Please provide it via the add-on configuration.")

    print(f"Connecting to websocket URL: {HA_URL} (SSL enabled: {USE_SSL})")

    try:
        async with websockets.connect(HA_URL, ssl=ssl_context, max_size=None) as ws:
            current_msg_id = 1 

            print("Connected")

            auth_required = json.loads(await ws.recv())
            if auth_required.get("type") != "auth_required":
                raise Exception("Expected 'auth_required', got something else")

            print("Received auth_required:", json.dumps(auth_required))

            await ws.send(json.dumps({
                "type": "auth",
                "access_token": HA_TOKEN
            }))

            while True:
                response = json.loads(await ws.recv())
                print("Auth response:", response)
                if response.get("type") == "auth_ok":
                    print("Authentication successful!")
                    break
                elif response.get("type") == "auth_invalid":
                    raise Exception("Authentication failed")
                else:
                    print(f"WARNING: Received unexpected message type during authentication: {response.get('type')}. Full response: {response}")


            # --- Fetch Area Registry ---
            area_map = {}
            await ws.send(json.dumps({"id": current_msg_id, "type": "config/area_registry/list"}))
            area_response = json.loads(await ws.recv())
            if area_response.get("success"):
                for area_data in area_response.get("result", []):
                    area_map[area_data["area_id"]] = area_data["name"]
                print(f"Fetched {len(area_map)} areas.")
            else:
                print(f"Failed to fetch area registry: {area_response.get('error', 'Unknown error')}")
            current_msg_id += 1

            # --- Fetch Entity Registry ---
            device_entities_map = {} 
            await ws.send(json.dumps({"id": current_msg_id, "type": "config/entity_registry/list"}))
            entity_response = json.loads(await ws.recv())
            if entity_response.get("success"):
                for entity_data in entity_response.get("result", []):
                    device_id = entity_data.get("device_id")
                    if device_id:
                        if device_id not in device_entities_map:
                            device_entities_map[device_id] = []
                        device_entities_map[device_id].append(entity_data)
                print(f"Fetched {len(entity_response.get('result', []))} entities.")
            else:
                print(f"Failed to fetch entity registry: {entity_response.get('error', 'Unknown error')}")
            current_msg_id += 1

            # --- Fetch all states ---
            all_states_map = {} 
            await ws.send(json.dumps({"id": current_msg_id, "type": "get_states"}))
            states_response = json.loads(await ws.recv())
            if states_response.get("success"): 
                for state_data in states_response.get("result", []):
                    all_states_map[state_data["entity_id"]] = state_data
                print(f"Fetched {len(all_states_map)} entity states.")
            else:
                print(f"Failed to fetch states: {states_response.get('error', 'Unknown error')}")
            current_msg_id += 1

            # --- Fetch ZHA Network Info (contains neighbors) ---
            network_info_map = {} # Map IEEE -> neighbors list
            await ws.send(json.dumps({
                "id": current_msg_id,
                "type": "zha/network_info"
            }))
            network_info_raw = await ws.recv()
            print(f"Raw ZHA network info response: {network_info_raw}") # *** NEW DEBUG PRINT HERE ***
            network_info_response = json.loads(network_info_raw)
            current_msg_id += 1
            
            if network_info_response.get("success"):
                for dev_info in network_info_response.get("result", {}).get("devices", []):
                    network_info_map[dev_info["ieee"]] = dev_info.get("neighbors", [])
                print(f"Fetched network info for {len(network_info_map)} devices.")
            else:
                print(f"WARNING: Failed to fetch ZHA network info: {network_info_response.get('error', 'Unknown error')}. Neighbors data might be incomplete.")


            # --- Request ZHA device list (your original request type) ---
            await ws.send(json.dumps({
                "id": current_msg_id,
                "type": "zha/devices"
            }))
            current_msg_id += 1

            devices_msg = await ws.recv()
            devices = json.loads(devices_msg).get("result", [])
            output = []

            print(f"Processing {len(devices)} ZHA devices...")

            for device in devices:
                ieee = device.get("ieee")
                name = device.get("user_given_name") or device.get("name") or "Unknown"
                last_seen = device.get("last_seen")
                
                device_id = device.get("device_id") 

                device_area_name = "N/A"
                if device.get("area_id"): 
                    device_area_name = area_map.get(device["area_id"], "Unknown Area")
                

                exposed_sensor_entity_ids = []
                battery_level = None 
                
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
                                        battery_level = state_obj.get("state") 

                # --- Get neighbors from network_info_map ---
                neighbors = network_info_map.get(ieee, [])
                if not neighbors:
                    print(f"No neighbors found in network_info for {name} (IEEE: {ieee}) or network_info call failed.")


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
                    "neighbors": neighbors, 
                    "exposed_sensors": exposed_sensor_entity_ids, 
                    "battery_level": battery_level 
                })

                await asyncio.sleep(0.1)

            # Save output
            os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
            with open(OUTPUT_FILE, "w") as f:
                json.dump({
                    "timestamp": datetime.utcnow().isoformat(),
                    "devices": output
                }, f, indent=2)

            print(f"Saved ZHA device data to {OUTPUT_FILE}")

    except websockets.exceptions.ConnectionClosedOK:
        print("WebSocket connection closed gracefully.")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"ERROR: WebSocket connection closed with an error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    asyncio.run(get_zha_data())

