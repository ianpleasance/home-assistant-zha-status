import json
import asyncio
import os
import ssl
import websockets
import time
from datetime import datetime
import logging

# --- Configure logging for websockets (Optional, but good for debugging) ---
logging.basicConfig(level=logging.INFO) # Set overall logging to INFO, change to DEBUG for more verbosity
logging.getLogger("websockets.client").setLevel(logging.INFO)
logging.getLogger("websockets.server").setLevel(logging.INFO)
logging.getLogger("websockets.protocol").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.INFO)
# --- End logging config ---

# Define the path where data will be stored inside the add-on
DATA_FILE_PATH = "/data/zha_devices.json"

print(f"collector.py started. websockets library version: {websockets.__version__}")

# Read from environment variables (set in run.sh)
HA_IP = "172.30.32.1"
HA_PORT = 8123

USE_SSL = os.environ.get("USE_SSL", "true").lower() == "true"
if USE_SSL:
    HA_PROTOCOL = "wss://"
    # This creates a context that explicitly does not verify certificates
    ssl_context = ssl._create_unverified_context()
    # Explicitly set minimum TLS version (Python 3.8+ defaults to TLS 1.2)
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
else:
    HA_PROTOCOL = "ws://"
    ssl_context = None

HA_URL = f"{HA_PROTOCOL}{HA_IP}:{HA_PORT}/api/websocket"
ACCESS_TOKEN = os.environ.get("HA_TOKEN")

async def get_zha_data():
    if not ACCESS_TOKEN:
        print("ERROR: HA_TOKEN is not set. Please provide it via the add-on configuration.")
        return # Exit if no token

    # Obfuscate token for logs for security
    print(f"Connecting to websocket URL: {HA_URL} (SSL enabled: {USE_SSL}) HA_TOKEN: {'*' * (len(ACCESS_TOKEN) - 10) + ACCESS_TOKEN[-10:] if ACCESS_TOKEN else 'None'}")

    try:
        async with websockets.connect(HA_URL, ssl=ssl_context if USE_SSL else None) as ws:
            print("WebSocket connection established.")

            # --- Home Assistant WebSocket Authentication Flow ---
            # Step 1: Receive the initial 'auth_required' message from Home Assistant
            initial_response_raw = await ws.recv()
            print(f"Received initial raw response from HA: {initial_response_raw}")
            initial_response = json.loads(initial_response_raw)

            if initial_response.get("type") != "auth_required":
                print(f"ERROR: Expected 'auth_required' as first message, but got: {initial_response.get('type')}. Full response: {initial_response}")
                return # Exit if unexpected first message

            # Step 2: Send authentication message
            auth_message_payload = {
                "type": "auth",
                "access_token": ACCESS_TOKEN
            }
            auth_message_json = json.dumps(auth_message_payload)
            print(f"Sending authentication message (token masked for log): {auth_message_json[:50]}...") # Log partial token for privacy

            await ws.send(auth_message_json)

            # Step 3: Wait for authentication result (auth_ok or auth_invalid)
            auth_result_raw = await ws.recv()
            print(f"Received raw authentication result: {auth_result_raw}")
            auth_response = json.loads(auth_result_raw)

            if auth_response.get("type") == "auth_ok":
                print("Authentication successful!")

                # --- Data Collection Logic (with neighbor info) ---
                # Request ZHA Network Info to get neighbor data
                await ws.send(json.dumps({
                    "id": 2, # Unique ID for this message
                    "type": "zha/network_info"
                }))
                network_info_response = json.loads(await ws.recv())

                network_nodes = {}
                if network_info_response.get("success"):
                    for node in network_info_response.get("result", {}).get("nodes", []):
                        network_nodes[node["ieee"]] = node # Store by IEEE for easy lookup
                    print(f"Received ZHA network info for {len(network_nodes)} nodes.")
                else:
                    print(f"Failed to get ZHA network info: {network_info_response.get('error', 'Unknown error')}")


                # Request ZHA Device Info
                await ws.send(json.dumps({
                    "id": 3, # Unique ID for this message
                    "type": "zha/devices/info"
                }))
                devices_info_response = json.loads(await ws.recv())

                final_devices_data = []
                if devices_info_response.get("success"):
                    devices_list = devices_info_response.get("result", [])
                    print(f"Received ZHA device info for {len(devices_list)} devices.")

                    # Merge device info with network info (especially neighbors)
                    for device in devices_list:
                        ieee = device.get("ieee")
                        if ieee and ieee in network_nodes:
                            device['neighbors'] = network_nodes[ieee].get('neighbors', [])
                        else:
                            device['neighbors'] = [] # Ensure neighbors key exists even if not found

                        final_devices_data.append(device)

                else:
                    print(f"Failed to get ZHA device info: {devices_info_response.get('error', 'Unknown error')}")
                
                current_time_utc = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
                output_data = {
                    "last_updated": current_time_utc,
                    "devices": final_devices_data
                }

                with open(DATA_FILE_PATH, "w") as f:
                    json.dump(output_data, f, indent=4)
                print(f"ZHA data saved to {DATA_FILE_PATH}")

            elif auth_response.get("type") == "auth_invalid":
                print(f"Authentication failed: {auth_response.get('message', 'Invalid token')}")
            else:
                print(f"Authentication failed with unexpected response type: {auth_response}")

    except ssl.SSLCertVerificationError as e:
        print(f"ERROR: SSL Certificate Verification Failed: {e}")
        print("This typically means the certificate is not valid for the IP you are using.")
        print("For internal connections, consider using ssl_context to disable verification or disable SSL in add-on config.")
    except websockets.exceptions.InvalidMessage as e:
        print(f"ERROR: WebSocket invalid message during handshake or communication: {e}")
        print("This often indicates Home Assistant immediately closed the connection or sent unexpected data.")
    except EOFError as e:
        print(f"ERROR: EOFError during WebSocket connection: {e}")
        print("This means the connection was closed prematurely by the server.")
    except Exception as e:
        print(f"An unexpected error occurred during WebSocket connection or data processing: {e}")

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DATA_FILE_PATH), exist_ok=True)
    asyncio.run(get_zha_data())
    scan_interval_minutes = int(os.environ.get("SCAN_INTERVAL_MINUTES", 10))
    print(f"Scheduling data collection every {scan_interval_minutes} minutes.")
    while True:
        time.sleep(scan_interval_minutes * 60)
        asyncio.run(get_zha_data())

