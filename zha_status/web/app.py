import json
from flask import Flask, render_template, redirect, url_for, jsonify
from datetime import datetime, timedelta
import subprocess
import os

app = Flask(__name__)

DATA_FILE_PATH = "/app/data/zha_data.json"
COLLECTOR_SCRIPT_PATH = "/app/collector.py"

@app.route('/')
def index():
    try:
        with open(DATA_FILE_PATH, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"devices": [], "timestamp": "No data yet. Collector might not have run."}
    except json.JSONDecodeError:
        data = {"devices": [], "timestamp": "Error decoding JSON data."}

    return render_template("index.html",
                           data=data,
                           datetime_module=datetime,
                           timedelta_class=timedelta)

@app.route('/refresh')
def refresh_data():
    print("Triggering data refresh via collector.py...")
    try:
        env = os.environ.copy()
        env["HA_TOKEN"] = os.environ.get("HA_TOKEN", "")
        env["USE_SSL"] = os.environ.get("USE_SSL", "")
        env["DEBUG"] = os.environ.get("DEBUG", "false")
        # Pass OFFLINE_THRESHOLD_MINUTES to collector.py's environment
        env["OFFLINE_THRESHOLD_MINUTES"] = os.environ.get("OFFLINE_THRESHOLD_MINUTES", "60")


        result = subprocess.run(
            ['python3', COLLECTOR_SCRIPT_PATH],
            capture_output=True,
            text=True,
            env=env
        )

        print(f"Collector script exited with code: {result.returncode}")
        if result.stdout:
            print("Collector stdout:\n", result.stdout)
        if result.stderr:
            print("Collector stderr:\n", result.stderr)

        if result.returncode != 0:
            print(f"ERROR: Data refresh failed! Collector exited with code {result.returncode}. Check add-on logs.")
        else:
            print("INFO: Data refresh complete!")

    except FileNotFoundError:
        print(f"ERROR: Collector script not found at {COLLECTOR_SCRIPT_PATH}. Please check add-on configuration.")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while running collector: {e}")

    return redirect(url_for('index'))

@app.route('/api/stats')
def get_stats():
    """
    Returns ZHA device statistics as a JSON object.
    """
    stats = {
        "total_devices": 0,
        "online_devices": 0,
        "offline_devices": 0,
        "low_battery_devices": 0,
        "last_data_update": "N/A"
    }
    
    try:
        with open(DATA_FILE_PATH, 'r') as f:
            data = json.load(f)
            stats["last_data_update"] = data.get("timestamp", "N/A")
            
            devices = data.get("devices", [])
            stats["total_devices"] = len(devices)

            current_utc = datetime.utcnow()
            
            # Get OFFLINE_THRESHOLD_MINUTES from environment for consistent calculation
            offline_threshold_minutes_local = int(os.environ.get("OFFLINE_THRESHOLD_MINUTES", "60"))
            
            for d in devices:
                last_seen_str = d.get("last_seen")
                if last_seen_str:
                    last_dt = datetime.fromisoformat(last_seen_str.replace('Z', ''))
                    ago = current_utc - last_dt
                    # Use the configurable threshold here
                    if ago.total_seconds() < offline_threshold_minutes_local * 60:
                        stats["online_devices"] += 1
                    else:
                        stats["offline_devices"] += 1
                else:
                    stats["offline_devices"] += 1

                battery_level = d.get("battery_level")
                if isinstance(battery_level, (int, float)) and battery_level <= 20:
                    stats["low_battery_devices"] += 1
                    
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: Could not load or parse ZHA data for stats: {e}")
        
    return jsonify(stats)

@app.route('/raw_zha_data')
def raw_zha_data():
    """
    Returns the raw content of zha_data.json.
    """
    try:
        with open(DATA_FILE_PATH, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": f"Data file not found at {DATA_FILE_PATH}. Collector might not have run yet."}), 404
    except json.JSONDecodeError:
        return jsonify({"error": f"Error decoding JSON from {DATA_FILE_PATH}. File might be corrupt or empty."}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
