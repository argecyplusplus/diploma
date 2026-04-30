import os
from flask import Blueprint, request, jsonify, g, render_template, send_file, abort
from pydantic import ValidationError
from ..services.simulation_service import SimulationService
from ..dto.simulation_dto import SimulationCreateRequest, InitialConditionCreateRequest
from ..utils.database import get_db_session
from ..models.blade import Blade, BladeAssembly
from ..models.material import Material
from ..models.simulation import InitialCondition
from sqlalchemy import select

sim_bp = Blueprint('simulation', __name__, url_prefix='/simulation')
ic_bp = Blueprint('initial_conditions', __name__, url_prefix='/initial-conditions')

def get_service():
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return SimulationService(g.db_session)

# ================= МОДЕЛИРОВАНИЕ =================
@sim_bp.route('/')
def index():
    blades = g.db_session.scalars(select(Blade)).all()
    assemblies = g.db_session.scalars(select(BladeAssembly)).all()
    materials = g.db_session.scalars(select(Material)).all()
    ics = get_service().get_initial_conditions_list()
    sims = get_service().get_simulations_list()
    return render_template('simulation.html', blades=blades, assemblies=assemblies,
                           materials=materials, ics=ics, sims=sims)

@sim_bp.route('/create', methods=['POST'])
def create():
    try:
        data = SimulationCreateRequest(**request.json)
        sim_id = get_service().create_simulation(data)
        g.db_session.commit()
        return jsonify({"message": "Моделирование создано", "id": sim_id}), 201
    except ValidationError as e:
        g.db_session.rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500

@sim_bp.route('/<int:sim_id>/download')
def download_result(sim_id):
    path = os.path.join(os.getcwd(), 'uploads', 'simulations', f"result_{sim_id}.vtk")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True)

# ================= НАЧАЛЬНЫЕ УСЛОВИЯ =================
@ic_bp.route('/')
def ic_index():
    ics = get_service().get_initial_conditions_list()
    return render_template('initial_conditions.html', ics=ics)

@ic_bp.route('/create', methods=['POST'])
def ic_create():
    try:
        data = InitialConditionCreateRequest(**request.json)
        ic_id = get_service().create_initial_condition(data)
        g.db_session.commit()
        return jsonify({"message": "Набор сохранен", "id": ic_id}), 201
    except ValidationError as e:
        g.db_session.rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 500