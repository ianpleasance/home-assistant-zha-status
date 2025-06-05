import json
from flask import Flask, render_template, redirect, url_for # Removed flash, get_flashed_messages
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
                           timedelta_class=timedelta) # Removed messages parameter

@app.route('/refresh')
def refresh_data():
    print("Triggering data refresh via collector.py...")
    try:
        env = os.environ.copy()
        env["HA_TOKEN"] = os.environ.get("HA_TOKEN", "") 
        env["USE_SSL"] = os.environ.get("USE_SSL", "")
        env["DEBUG"] = os.environ.get("DEBUG", "false") 

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
            print("INFO: Data refresh complete!") # Log success message instead of flashing

    except FileNotFoundError:
        print(f"ERROR: Collector script not found at {COLLECTOR_SCRIPT_PATH}. Please check add-on configuration.")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while running collector: {e}")

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
