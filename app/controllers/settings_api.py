import os
from flask import Blueprint, request, jsonify
from dotenv import set_key, load_dotenv
from ..utils.database import get_db_list, get_current_db, select_database, create_database, delete_database

settings_api_bp = Blueprint('settings', __name__, url_prefix='/api/settings')


@settings_api_bp.route('', methods=['GET'])
def get_settings():
    return jsonify({
        "freefem_path": os.getenv('FREEFEM_PATH', '')
    })


@settings_api_bp.route('', methods=['POST'])
def update_settings():
    try:
        data = request.json or {}
        path = data.get('freefem_path', '').strip()

        if path:
            set_key('.env', 'FREEFEM_PATH', path)
        else:
            set_key('.env', 'FREEFEM_PATH', '')

        load_dotenv(override=True)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_api_bp.route('/dbs', methods=['GET'])
def get_dbs():
    try:
        dbs, current = get_db_list()
        return jsonify({
            "databases": dbs,
            "current_db": current
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_api_bp.route('/select', methods=['POST'])
def select_db():
    try:
        name = request.json.get('name')
        if not name:
            return jsonify({"error": "Имя БД не указано"}), 400
        select_database(name)
        return jsonify({"status": "ok"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_api_bp.route('/create', methods=['POST'])
def create_db():
    try:
        name = request.json.get('name', '').strip()
        if not name:
            return jsonify({"error": "Введите имя базы данных"}), 400

        created = create_database(name)
        return jsonify({"status": "ok", "name": created}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409  # Conflict
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_api_bp.route('/delete/<name>', methods=['DELETE'])
def delete_db(name):
    try:
        delete_database(name)
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500