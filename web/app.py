from flask import Flask, render_template, redirect, url_for
import json
import os
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def index():
    try:
        with open("/app/data/zha_data.json") as f:
            data = json.load(f)
    except:
        data = {"devices": []}
    return render_template("index.html", data=data)

@app.route('/refresh')
def refresh():
    os.system("python3 /app/collector.py")
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
