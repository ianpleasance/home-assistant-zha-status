import asyncio
import websockets
import json
from datetime import datetime
import os

# Internal hostname used inside Supervisor network
HA_URL = "ws://172.30.32.1:8123/api/websocket"
OUTPUT_FILE = "/app/data/zha_data.json"


async def get_zha_data():
    async with websockets.connect(HA_URL) as ws:
        msg_id = 1

        # Step 1: receive 'hello'
        hello = await ws.recv()
        print("Received hello:", hello)

        # Step 2: NO auth needed — Supervisor handles it internally

        # Step 3: wait for auth_ok or ready
        while True:
            response = json.loads(await ws.recv())
            print("Received:", response)
            if response.get("type") in ("auth_ok", "ready"):
                break
            elif response.get("type") == "auth_required":
                raise Exception("Unexpected: auth_required without auth_needed")
            elif response.get("type") == "auth_invalid":
                raise Exception(f"Authentication failed: {response}")

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

            # Get neighbors for each device
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

        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "devices": output
            }, f, indent=2)
        print(f"Saved ZHA device data to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(get_zha_data())

