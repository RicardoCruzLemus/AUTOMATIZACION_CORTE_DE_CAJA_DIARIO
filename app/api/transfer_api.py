from flask import Blueprint, jsonify
import json
import os

api_bp = Blueprint('api', __name__, url_prefix='/api')

LOG_FILE = 'transfer_logs.json'

@api_bp.route('/logs', methods=['GET'])
def get_logs():
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            pass
    return jsonify(logs)
