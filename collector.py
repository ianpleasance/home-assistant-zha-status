import asyncio
import websockets
import json
from datetime import datetime
import os

# Home Assistant WebSocket API URL
HA_URL = "ws://homeassistant.local:8123/api/websocket"

# Get token from environment (set by run.sh via options.json)
LONG_LIVED_TOKEN = os.environ.get("HA_TOKEN")
OUTPUT_FILE = "/app/data/zha_data.json"

async def get_zha_data():
    async with websockets.connect(HA_URL) as ws:
        msg_id = 1

        # Authenticate
        await ws.recv()  # auth_required
        await ws.send(json.dumps({
            "type": "auth",
            "access_token": LONG_LIVED_TOKEN
        }))
        await ws.recv()  # auth_ok

        # Request all ZHA devices
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

            # Request neighbor info
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

            await asyncio.sleep(0.1)  # prevent flooding

        # Save the data to JSON file
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "devices": output
            }, f, indent=2)

if __name__ == "__main__":
    if not LONG_LIVED_TOKEN:
        raise EnvironmentError("HA_TOKEN is not set. Please provide it via the add-on configuration.")
    asyncio.run(get_zha_data())

