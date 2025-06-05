import json
from flask import Flask, render_template
from datetime import datetime, timedelta # <-- Make sure these are imported

app = Flask(__name__)

DATA_FILE_PATH = "/app/data/zha_data.json" # Ensure this path is correct for your environment

@app.route('/')
def index():
    try:
        with open(DATA_FILE_PATH, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        # Provide default empty data if file doesn't exist yet
        data = {"devices": [], "timestamp": "No data yet. Collector might not have run."}
    except json.JSONDecodeError:
        # Handle cases where JSON might be malformed
        data = {"devices": [], "timestamp": "Error decoding JSON data."}

    # Pass datetime and timedelta classes to the template
    return render_template("index.html",
                           data=data,
                           datetime_module=datetime, # Pass the datetime module itself
                           timedelta_class=timedelta) # Pass the timedelta class

if __name__ == '__main__':
    # Ensure the host and port are correct for your add-on setup
    app.run(host='0.0.0.0', port=5000, debug=True)
