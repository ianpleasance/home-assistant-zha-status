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

@app.route('/refresh')
def refresh_data():
    print("Triggering data refresh via collector.py...")
    try:
        # Create a copy of the current environment variables
        env = os.environ.copy()
        # Ensure HA_TOKEN and USE_SSL are explicitly passed to the subprocess
        # This is crucial for collector.py to authenticate with Home Assistant
        env["HA_TOKEN"] = os.environ.get("HA_TOKEN", "") 
        env["USE_SSL"] = os.environ.get("USE_SSL", "")
        
        # Execute collector.py as a separate Python process
        # This will block the web request until collector.py finishes its execution.
        # For potentially long-running scripts, consider running in a separate thread
        # or using a task queue, but for this use case, blocking is usually acceptable.
        result = subprocess.run(
            ['python3', COLLECTOR_SCRIPT_PATH],
            capture_output=True, # Capture stdout and stderr from the collector script
            text=True,           # Decode stdout/stderr as text
            env=env              # Pass the environment variables
        )
        
        print(f"Collector script exited with code: {result.returncode}")
        if result.stdout:
            print("Collector stdout:\n", result.stdout)
        if result.stderr:
            print("Collector stderr:\n", result.stderr)

        if result.returncode != 0:
            print(f"ERROR: Collector script failed with non-zero exit code {result.returncode}.")
    except FileNotFoundError:
        print(f"ERROR: Collector script not found at expected path: {COLLECTOR_SCRIPT_PATH}")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while trying to run collector.py: {e}")

    # Redirect back to the main page after the refresh attempt
    return redirect(url_for('index'))


if __name__ == '__main__':
    # Ensure the host and port are correct for your add-on setup
    app.run(host='0.0.0.0', port=5000, debug=True)
