from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError
from ..services.material_service import MaterialService
from ..dto.material_dto import (
    MaterialCreateRequest, MaterialUpdateRequest,
    ChemicalElementCreateRequest, ChemicalElementUpdateRequest,
    AlloyCreateRequest, AlloyComponentResponse
)
from ..utils.database import get_db_session

mat_bp = Blueprint('materials', __name__, url_prefix='/api/materials')
element_bp = Blueprint('elements', __name__, url_prefix='/api/elements')
alloy_bp = Blueprint('alloys', __name__, url_prefix='/api/alloys')


def get_service():
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return MaterialService(g.db_session)


# ================= ХИМИЧЕСКИЕ ЭЛЕМЕНТЫ =================

@element_bp.route('', methods=['GET'])
def get_chemical_elements():
    """Получить все химические элементы с их типом"""
    elements = get_service().repo.get_elements_with_type()
    return jsonify([e.model_dump() for e in elements])


@element_bp.route('', methods=['POST'])
def create_chemical_element():
    """Создать химический элемент (металл, оксид, неметалл и т.д.)"""
    try:
        data = ChemicalElementCreateRequest(**request.json)
        res = get_service().create_element(data)
        g.db_session.commit()
        return jsonify(res.model_dump()), 201
    except ValidationError as e:
        g.db_session.rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500


@element_bp.route('/<int:id>', methods=['GET'])
def get_chemical_element(id):
    """Получить химический элемент по ID"""
    element = get_service().repo.get_element_by_id_with_type(id)
    if not element:
        return jsonify({"error": "Элемент не найден"}), 404
    return jsonify(element.model_dump())


@element_bp.route('/<int:id>', methods=['PUT'])
def update_chemical_element(id):
    """Обновить химический элемент"""
    try:
        # Используем тот же DTO или специальный Update DTO
        data = ChemicalElementCreateRequest(**request.json)
        res = get_service().update_element(id, data)
        g.db_session.commit()
        return jsonify(res.model_dump())
    except ValueError as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 404
    except ValidationError as e:
        g.db_session.rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500


@element_bp.route('/<int:id>', methods=['DELETE'])
def delete_chemical_element(id):
    """Удалить химический элемент (каскадно удалит связанный Material)"""
    try:
        element = get_service().repo.get_element_by_id(id)
        if not element:
            return jsonify({"error": "Элемент не найден"}), 404
        get_service().repo.delete(element.material)  # Удаляем через материальную сущность
        g.db_session.commit()
        return '', 204
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500


# ================= МАТЕРИАЛЫ (общие) =================

@mat_bp.route('', methods=['GET'])
def get_all_materials():
    """Получить все материалы (элементы + сплавы)"""
    materials = get_service().repo.get_all()
    return jsonify([m.model_dump() for m in materials])


@mat_bp.route('/<int:id>', methods=['GET'])
def get_material(id):
    """Получить материал по ID"""
    mat = get_service().repo.get_by_id(id)
    if not mat:
        return jsonify({"error": "Материал не найден"}), 404
    return jsonify(mat.model_dump())


@mat_bp.route('/<int:id>', methods=['DELETE'])
def delete_material(id):
    """Удалить материал"""
    try:
        mat = get_service().repo.get_by_id(id)
        if not mat:
            return jsonify({"error": "Not found"}), 404
        get_service().repo.delete(mat)
        g.db_session.commit()
        return '', 204
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500


# ================= СПЛАВЫ =================

@alloy_bp.route('', methods=['GET'])
def get_alloys():
    """Получить все сплавы"""
    alloys = get_service().repo.get_alloys()
    return jsonify([m.model_dump() for m in alloys])


@alloy_bp.route('', methods=['POST'])
def create_alloy():
    """Создать сплав по правилу смесей"""
    try:
        data = AlloyCreateRequest(**request.json)
        res = get_service().create_alloy(data)
        g.db_session.commit()
        return jsonify(res.model_dump()), 201
    except ValidationError as e:
        g.db_session.rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500


@alloy_bp.route('/<int:id>', methods=['GET'])
def get_alloy_details(id):
    """Получить детали сплава с составом"""
    svc = get_service()
    alloy = svc.repo.get_by_id(id)
    if not alloy:
        return jsonify({"error": "Сплав не найден"}), 404

    comps = svc.repo.get_alloy_components(id)
    return jsonify({
        "alloy": alloy.model_dump(),
        "components": [c.model_dump() for c in comps]
    })


@alloy_bp.route('/<int:id>', methods=['DELETE'])
def delete_alloy(id):
    """Удалить сплав"""
    try:
        mat = get_service().repo.get_by_id(id)
        if not mat:
            return jsonify({"error": "Not found"}), 404
        get_service().repo.delete(mat)
        g.db_session.commit()
        return '', 204
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500