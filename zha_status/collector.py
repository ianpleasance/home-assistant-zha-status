import asyncio
import websockets
import json
import os
from datetime import datetime
import ssl

HA_TOKEN = os.environ.get("HA_TOKEN")
USE_SSL = os.environ.get("USE_SSL")

OUTPUT_FILE = "/app/data/zha_data.json"

# WebSocket URL for Home Assistant (internal IP)
if USE_SSL:
  # Create an SSL context that disables hostname checking and certificate verification
  # This is suitable for internal communication where the certificate is not issued
  # for the internal IP address.
  ssl_context = ssl.create_default_context()
  ssl_context.check_hostname = False
  ssl_context.verify_mode = ssl.CERT_NONE
  HA_URL = "wss://172.30.32.1:8123/api/websocket"
else:
  HA_URL = "ws://172.30.32.1:8123/api/websocket"
  ssl_context = None

async def get_zha_data():
    print(f"Connecting to websocket URL: {HA_URL} (SSL enabled: {USE_SSL})")

    try:
        async with websockets.connect(HA_URL, ssl=ssl_context if USE_SSL else None) as ws:
            print("WebSocket connection established. Sending authentication...")
            await ws.send(json.dumps({
                "id": 1,
                "type": "auth",
                "access_token": ACCESS_TOKEN
            }))
            auth_response = json.loads(await ws.recv())

            if auth_response.get("type") == "auth_ok":
                print("Authentication successful!")

                # --- NEW: Request ZHA Network Info to get neighbor data ---
                await ws.send(json.dumps({
                    "id": 2, # Unique ID for this message
                    "type": "zha/network_info"
                }))
                network_info_response = json.loads(await ws.recv())

                network_nodes = {}
                if network_info_response.get("success"):
                    # Process nodes from network_info
                    for node in network_info_response.get("result", {}).get("nodes", []):
                        network_nodes[node["ieee"]] = node # Store by IEEE for easy lookup
                    print(f"Received ZHA network info for {len(network_nodes)} nodes.")
                else:
                    print(f"Failed to get ZHA network info: {network_info_response.get('error', 'Unknown error')}")


                # Request ZHA Device Info (your existing call)
                await ws.send(json.dumps({
                    "id": 3, # New unique ID
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
                            # Add neighbors and routes from network_nodes if available
                            device['neighbors'] = network_nodes[ieee].get('neighbors', [])
                            # device['routes'] = network_nodes[ieee].get('routes', []) # Optional: if you want routes too
                        else:
                            device['neighbors'] = [] # Ensure neighbors key exists even if not found in network_info

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

            else:
                print(f"Authentication failed: {auth_response}")

    except ssl.SSLCertVerificationError as e:
        print(f"ERROR: SSL Certificate Verification Failed: {e}")
        print("This typically means the certificate is not valid for the IP you are using.")
        print("For internal connections, consider using ssl_context to disable verification or disable SSL in add-on config.")
    except websockets.exceptions.InvalidMessage as e:
        print(f"ERROR: WebSocket invalid message during handshake: {e}")
        print("This often indicates Home Assistant immediately closed the connection.")
    except EOFError as e:
        print(f"ERROR: EOFError during WebSocket connection: {e}")
        print("This means the connection was closed prematurely by the server.")
    except Exception as e:
        print(f"An unexpected error occurred during WebSocket connection or data processing: {e}")


if __name__ == "__main__":
    asyncio.run(get_zha_data())

