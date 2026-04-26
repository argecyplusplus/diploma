# app/controllers/settings_api.py
from flask import Blueprint, request, jsonify
from ..utils.database import get_db_list, create_database, select_database, delete_database

settings_api_bp = Blueprint('settings_api', __name__)

@settings_api_bp.route('/config', methods=['GET'])
def get_config():
    dbs, current = get_db_list()
    return jsonify({"databases": dbs, "current_db": current})

@settings_api_bp.route('/create', methods=['POST'])
def create():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "Имя обязательно"}), 400
    try:
        created = create_database(name)
        return jsonify({"message": "Создана", "name": created}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

@settings_api_bp.route('/select', methods=['POST'])
def select():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "Имя обязательно"}), 400
    try:
        select_database(name)
        return jsonify({"message": "Выбрана", "name": name}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@settings_api_bp.route('/delete/<name>', methods=['DELETE'])
def delete(name):
    try:
        delete_database(name)
        return jsonify({"message": "Удалена"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404