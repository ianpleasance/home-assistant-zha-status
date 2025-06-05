from flask import Flask, render_template, redirect, url_for, jsonify
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_FILE_PATH = "/app/data/zha_data.json"

@app.route('/')
def index():
    try:
        with open(DATA_FILE_PATH, 'r') as f:
            data = json.load(f)
        # devices = data.get('devices', []) # No need to extract, pass 'data' directly if index.html uses data.devices
        # last_updated = data.get('timestamp', 'N/A') # No need to extract if index.html uses data.timestamp
    except FileNotFoundError:
        data = {"devices": [], "timestamp": "No data yet. Collector might not have run."}
    except json.JSONDecodeError:
        data = {"devices": [], "timestamp": "Error decoding JSON data."}

    # Pass datetime and timedelta to the template
    return render_template("index.html",
                           data=data,
                           datetime_module=datetime,
                           timedelta_class=timedelta)


@app.route('/refresh')
def refresh():
    os.system("python3 /app/collector.py")
    return redirect(url_for('index'))

@app.route("/api/zha_raw_data")
def zha_raw_data():
    """
    Returns the raw content of zha_data.json for debugging purposes.
    """
    if os.path.exists(DATA_FILE_PATH):
        try:
            with open(DATA_FILE_PATH, 'r') as f:
                raw_data = json.load(f)
            return jsonify(raw_data)
        except json.JSONDecodeError as e:
            # Handle cases where the JSON file might be corrupted or incomplete
            return jsonify({"error": f"Error decoding JSON from file: {e}"}), 500
    else:
        # Return a 404 if the file does not exist
        return jsonify({"error": "zha_data.json not found. Data collection may not have run yet."}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
