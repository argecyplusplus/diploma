from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError
from ..services.blade_service import BladeService
from ..dto.blade_dto import (
    BladeCreateRequest, BladeUpdateRequest,
    ProfileCoordinateRequest,
    BladeAssemblyCreateRequest, BladeAssemblyUpdateRequest
)
# Импортируем функцию получения сессии
from ..utils.database import get_db_session

blade_bp = Blueprint('blade_api', __name__, url_prefix='/api/blades')
assembly_bp = Blueprint('assembly_api', __name__, url_prefix='/api/assemblies')

def get_service():
    # Если сессии еще нет в контексте запроса — создаем её
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return BladeService(g.db_session)

# ================= BLADES =================
@blade_bp.route('', methods=['GET'])
def list_blades():
    return jsonify([b.model_dump() for b in get_service().get_all_blades()])

@blade_bp.route('', methods=['POST'])
def create_blade():
    try:
        data = BladeCreateRequest(**request.json)
        return jsonify(get_service().create_blade(data).model_dump()), 201
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@blade_bp.route('/<int:blade_id>', methods=['GET'])
def get_blade(blade_id):
    blade = get_service().get_blade(blade_id)
    return jsonify(blade.model_dump()) if blade else (jsonify({"error": "Not found"}), 404)

@blade_bp.route('/<int:blade_id>', methods=['PUT'])
def update_blade(blade_id):
    try:
        data = BladeUpdateRequest(**request.json)
        return jsonify(get_service().update_blade(blade_id, data).model_dump())
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@blade_bp.route('/<int:blade_id>', methods=['DELETE'])
def delete_blade(blade_id):
    try:
        get_service().delete_blade(blade_id)
        return '', 204
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

# ================= COORDINATES =================
@blade_bp.route('/<int:blade_id>/coordinates', methods=['GET'])
def get_coordinates(blade_id):
    return jsonify([c.model_dump() for c in get_service().get_coordinates(blade_id)])

@blade_bp.route('/<int:blade_id>/coordinates', methods=['POST'])
def add_coordinates(blade_id):
    try:
        json_data = request.json
        if isinstance(json_data, list):
            dtos = [ProfileCoordinateRequest(**item) for item in json_data]
            saved = get_service().bulk_add_coordinates(blade_id, dtos)
        else:
            dto = ProfileCoordinateRequest(**json_data)
            saved = [get_service().add_coordinate(blade_id, dto)]
        return jsonify([c.model_dump() for c in saved]), 201
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@blade_bp.route('/<int:blade_id>/coordinates', methods=['DELETE'])
def clear_coordinates(blade_id):
    get_service().clear_coordinates(blade_id)
    return '', 204

# ================= ASSEMBLIES (MERGE) =================
@assembly_bp.route('', methods=['GET'])
def list_assemblies():
    return jsonify([a.model_dump() for a in get_service().get_all_assemblies()])

@assembly_bp.route('', methods=['POST'])
def create_assembly():
    try:
        data = BladeAssemblyCreateRequest(**request.json)
        return jsonify(get_service().create_assembly(data).model_dump()), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@assembly_bp.route('/<int:assembly_id>', methods=['PUT'])
def update_assembly(assembly_id):
    try:
        data = BladeAssemblyUpdateRequest(**request.json)
        return jsonify(get_service().update_assembly(assembly_id, data).model_dump())
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@assembly_bp.route('/<int:assembly_id>', methods=['DELETE'])
def delete_assembly(assembly_id):
    try:
        get_service().delete_assembly(assembly_id)
        return '', 204
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@assembly_bp.route('/<int:assembly_id>/members', methods=['GET'])
def get_members(assembly_id):
    return jsonify([m.model_dump() for m in get_service().get_assembly_members(assembly_id)])