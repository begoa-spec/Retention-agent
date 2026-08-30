"""
Small local API so the dashboard can trigger the agent with a button
click instead of you running a terminal command by hand.

Run this alongside the dashboard during development:
    python agent/api.py

This is intentionally simple — it's also the starting point for the
AWS Lambda handler later, since the core logic (run_for_client) is
identical either way.
"""

from flask import Flask, jsonify
from flask_cors import CORS
from retention_agent import run_for_client

app = Flask(__name__)
CORS(app)  # allows the dashboard (a different port) to call this


@app.route("/review/<client_id>", methods=["POST"])
def review_client(client_id):
    try:
        result = run_for_client(client_id)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(port=8000, debug=True)