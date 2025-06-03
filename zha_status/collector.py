import asyncio
import websockets
import json
from datetime import datetime
import os

HA_URL = "ws://supervisor/core/api/websocket"

LONG_LIVED_TOKEN = os.environ.get("HA_TOKEN")
OUTPUT_FILE = "/app/data/zha_data.json"


async def get_zha_data():
    async with websockets.connect(HA_URL) as ws:
        msg_id = 1

        # Step 1: receive 'hello'
        hello = await ws.recv()
        print("Received hello:", hello)

        # Step 2: send authentication
        await ws.send(json.dumps({
            "type": "auth",
            "access_token": LONG_LIVED_TOKEN
        }))

        # Step 3: wait for auth_ok
        while True:
            auth_response = json.loads(await ws.recv())
            if auth_response.get("type") == "auth_ok":
                print("Authentication successful.")
                break
            elif auth_response.get("type") == "auth_invalid":
                raise Exception(f"Authentication failed: {auth_response}")
            else:
                print("Auth negotiation message:", auth_response)

        # Step 4: send device list request
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

            # Step 5: get neighbors for each device
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

            await asyncio.sleep(0.1)  # to avoid overloading HA with requests

        # Step 6: save output
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "devices": output
            }, f, indent=2)
        print(f"ZHA data saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    if not LONG_LIVED_TOKEN:
        raise EnvironmentError("HA_TOKEN is not set. Please provide it via the add-on configuration.")
    asyncio.run(get_zha_data())

