from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError
from ..services.material_service import MaterialService
from ..dto.material_dto import (
    MaterialCreateRequest, MaterialUpdateRequest,
    ChemicalElementCreateRequest, ChemicalElementUpdateRequest,
    ChemicalElementResponse,  # 🔥 Добавлено
    AlloyCreateRequest
)
from ..utils.database import get_db_session

mat_bp = Blueprint('materials', __name__, url_prefix='/api/materials')
element_bp = Blueprint('elements', __name__, url_prefix='/api/elements')
alloy_bp = Blueprint('alloys', __name__, url_prefix='/api/alloys')

def get_service():
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return MaterialService(g.db_session)

def safe_rollback():
    if 'db_session' in g:
        g.db_session.rollback()

# 🔥 Вспомогательная функция для конвертации SQLAlchemy модели в Pydantic DTO
def to_element_response(element):
    return ChemicalElementResponse(
        chemical_element_id=element.chemical_element_id,
        name=element.name,
        type=element.type,
        material_id=element.material_id,
        density=element.material.density,
        hardness=element.material.hardness,
        thermal_conductivity=element.material.thermal_conductivity,
        heat_capacity=element.material.heat_capacity,
        melting_point=element.material.melting_point,
        thermal_expansion_coef=element.material.thermal_expansion_coef
    )

# ================= ХИМИЧЕСКИЕ ЭЛЕМЕНТЫ =================

@element_bp.route('', methods=['GET'])
def get_chemical_elements():
    try:
        elements = get_service().repo.get_elements_with_type()
        return jsonify([to_element_response(e).model_dump() for e in elements])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@element_bp.route('', methods=['POST'])
def create_chemical_element():
    try:
        data = ChemicalElementCreateRequest(**request.json)
        element = get_service().create_element(data)
        g.db_session.commit()
        # 🔥 Конвертируем в DTO перед сериализацией
        return jsonify(to_element_response(element).model_dump()), 201
    except ValidationError as e:
        safe_rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 500

@element_bp.route('/<int:id>', methods=['GET'])
def get_chemical_element(id):
    try:
        element = get_service().repo.get_element_by_id_with_type(id)
        if not element:
            return jsonify({"error": "Элемент не найден"}), 404
        return jsonify(to_element_response(element).model_dump())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@element_bp.route('/<int:id>', methods=['PUT'])
def update_chemical_element(id):
    try:
        data = ChemicalElementUpdateRequest(**request.json)
        element = get_service().update_element(id, data)
        g.db_session.commit()
        return jsonify(to_element_response(element).model_dump())
    except ValueError as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 404
    except ValidationError as e:
        safe_rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 500

@element_bp.route('/<int:id>', methods=['DELETE'])
def delete_chemical_element(id):
    try:
        element = get_service().repo.get_element_by_id(id)
        if not element:
            return jsonify({"error": "Элемент не найден"}), 404
        get_service().repo.delete(element.material)
        g.db_session.commit()
        return '', 204
    except Exception as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 500

# ================= МАТЕРИАЛЫ (общие) =================

@mat_bp.route('', methods=['GET'])
def get_all_materials():
    try:
        materials = get_service().repo.get_all()
        return jsonify([m.model_dump() for m in materials])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@mat_bp.route('/<int:id>', methods=['GET'])
def get_material(id):
    try:
        mat = get_service().repo.get_by_id(id)
        if not mat:
            return jsonify({"error": "Материал не найден"}), 404
        return jsonify(mat.model_dump())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@mat_bp.route('/<int:id>', methods=['DELETE'])
def delete_material(id):
    try:
        mat = get_service().repo.get_by_id(id)
        if not mat:
            return jsonify({"error": "Not found"}), 404
        if mat.is_alloy is False and hasattr(mat, 'chemical_elements') and mat.chemical_elements:
            return jsonify({"error": "Это химический элемент. Используйте /api/elements/{id}"}), 400
        if mat.is_alloy is True:
            return jsonify({"error": "Это сплав. Используйте /api/alloys/{id}"}), 400

        get_service().repo.delete(mat)
        g.db_session.commit()
        return '', 204
    except Exception as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 500

# ================= СПЛАВЫ =================

@alloy_bp.route('', methods=['GET'])
def get_alloys():
    try:
        alloys = get_service().repo.get_alloys()
        return jsonify([m.model_dump() for m in alloys])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@alloy_bp.route('', methods=['POST'])
def create_alloy():
    try:
        data = AlloyCreateRequest(**request.json)
        res = get_service().create_alloy(data)
        g.db_session.commit()
        return jsonify(res.model_dump()), 201
    except ValidationError as e:
        safe_rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 500

@alloy_bp.route('/<int:id>', methods=['GET'])
def get_alloy_details(id):
    try:
        svc = get_service()
        alloy = svc.repo.get_by_id(id)
        if not alloy:
            return jsonify({"error": "Сплав не найден"}), 404

        comps = svc.repo.get_alloy_components(id)
        return jsonify({
            "alloy": alloy.model_dump(),
            "components": [
                {
                    "component_material_id": c.component_material_id,
                    "component_name": c.component_material.name if c.component_material else None,
                    "mass_fraction": c.mass_fraction
                } for c in comps
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@alloy_bp.route('/<int:id>', methods=['PUT'])
def update_alloy(id):
    try:
        data = AlloyCreateRequest(**request.json)
        svc = get_service()
        alloy = svc.repo.get_by_id(id)
        if not alloy:
            return jsonify({"error": "Сплав не найден"}), 404

        alloy.name = data.name
        props = svc._calculate_properties([c.model_dump() for c in data.components])
        for k, v in props.items():
            setattr(alloy, k, v)

        svc.repo.update_alloy_composition(id, [c.model_dump() for c in data.components])
        svc.repo.update(alloy)
        g.db_session.commit()
        return jsonify(alloy.model_dump())
    except ValidationError as e:
        safe_rollback()
        return jsonify({"error": e.errors()}), 400
    except ValueError as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 500

@alloy_bp.route('/<int:id>', methods=['DELETE'])
def delete_alloy(id):
    try:
        mat = get_service().repo.get_by_id(id)
        if not mat:
            return jsonify({"error": "Сплав не найден"}), 404
        get_service().repo.delete(mat)
        g.db_session.commit()
        return '', 204
    except Exception as e:
        safe_rollback()
        return jsonify({"error": str(e)}), 500

# ================= ВСПОМОГАТЕЛЬНЫЕ ЭНДПОИНТЫ =================

@element_bp.route('/types', methods=['GET'])
def get_element_types():
    return jsonify({
        "types": ["Металл", "Неметалл", "Оксид", "Нитрид", "Карбид", "Композит", "Газ"]
    })