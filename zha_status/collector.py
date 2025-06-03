import asyncio
import websockets
import json
import os
from datetime import datetime

# WebSocket URL for Home Assistant (internal IP)
#HA_URL = "ws://172.30.32.1:8123/api/websocket"
#HA_URL = "ws://supervisor/core/websocket"
#HA_URL = "ws://172.30.32.1:8123/api/websocket"
HA_URL = "wss://172.30.32.1:8123/api/websocket"

HA_TOKEN = os.environ.get("HA_TOKEN")
OUTPUT_FILE = "/app/data/zha_data.json"

async def get_zha_data():
    if not HA_TOKEN:
        raise EnvironmentError("HA_TOKEN is not set. Please provide it via the add-on configuration.")

    print("Connecting to websocket URL: ", HA_URL)

    # Create an SSL context that disables hostname checking and certificate verification
    # This is suitable for internal communication where the certificate is not issued
    # for the internal IP address.
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with websockets.connect(HA_URL, ssl=ssl_context) as ws:
        msg_id = 1

        print("Connected")

        # Step 1: receive 'hello'
        auth_required = json.loads(await ws.recv())
        if auth_required.get("type") != "auth_required":
            raise Exception("Expected 'auth_required', got something else")

        print("Received auth_required:", json.dumps(auth_required))

        # Step 2: send auth
        await ws.send(json.dumps({
            "type": "auth",
            "access_token": HA_TOKEN
        }))

        # Step 3: wait for auth_ok
        while True:
            response = json.loads(await ws.recv())
            print("Auth response:", response)
            if response.get("type") == "auth_ok":
                break
            elif response.get("type") == "auth_invalid":
                raise Exception("Authentication failed")

        # Step 4: request ZHA device list
        await ws.send(json.dumps({
            "id": msg_id,
            "type": "zha/devices"
        }))
        msg_id += 1

        devices_msg = await ws.recv()
        devices = json.loads(devices_msg).get("result", [])
        output = []

        for device in devices:
            ieee = device.get("ieee")
            name = device.get("user_given_name") or device.get("name") or "Unknown"
            last_seen = device.get("last_seen")

            # Request neighbors
            await ws.send(json.dumps({
                "id": msg_id,
                "type": "zha/device_neighbors",
                "ieee": ieee
            }))
            neighbors_msg = await ws.recv()
            neighbors = json.loads(neighbors_msg).get("result", [])
            msg_id += 1

            output.append({
                "name": name,
                "last_seen": last_seen,
                "area": device.get("area", ""),
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
                "neighbors": neighbors
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


if __name__ == "__main__":
    asyncio.run(get_zha_data())

