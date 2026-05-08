import os
from flask import Blueprint, request, jsonify, g, render_template, send_file, abort
from pydantic import ValidationError
from ..services.simulation_service import SimulationService
from ..dto.simulation_dto import SimulationCreateRequest, InitialConditionCreateRequest
from ..utils.database import get_db_session
from ..models.blade import Blade, BladeAssembly
from ..models.simulation import *
from ..models.material import Material, AlloyComposition, ElValue
from ..repositories.material_repository import MaterialRepository
from ..models.material import ChemicalElement  # добавить импорт
from sqlalchemy.orm import joinedload
from sqlalchemy import select, delete

sim_bp = Blueprint('simulation', __name__, url_prefix='/simulation')
ic_bp = Blueprint('initial_conditions', __name__, url_prefix='/initial-conditions')

def get_service():
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return SimulationService(g.db_session)

# ================= МОДЕЛИРОВАНИЕ =================
@sim_bp.route('/')
def index():
    service = get_service()
    session = g.db_session

    blades = session.scalars(select(Blade)).all()
    assemblies = session.scalars(select(BladeAssembly)).all()

    # Загружаем химические элементы (как на странице материалов)
    chemical_elements = session.scalars(
        select(ChemicalElement).options(joinedload(ChemicalElement.material))
    ).all()
    # Извлекаем связанные материалы
    elements = [ce.material for ce in chemical_elements if ce.material]

    # Сплавы – это материалы с is_alloy=True
    alloys = session.scalars(
        select(Material).where(Material.is_alloy == True)
    ).all()

    ics = session.scalars(select(InitialCondition)).all()
    sims = session.scalars(select(Simulation)).all()
    return render_template('simulation.html',
                           blades=blades,
                           assemblies=assemblies,
                           elements=elements,
                           alloys=alloys,
                           ics=ics,
                           sims=sims)

@sim_bp.route('/create', methods=['POST'])
def create():
    service = get_service()
    try:
        data = SimulationCreateRequest(**request.json)
        sim_id = service.create_simulation(data)
        service.session.commit()
        return jsonify({"message": "Моделирование создано", "id": sim_id}), 201
    except ValidationError as e:
        service.session.rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500

@sim_bp.route('/<int:sim_id>/download')
def download_result(sim_id):
    sim_dir = os.path.join(os.getcwd(), 'uploads', 'simulations', f"sim_{sim_id}")
    vtk_path = os.path.join(sim_dir, "result.vtk")
    if not os.path.exists(vtk_path):
        abort(404)
    return send_file(vtk_path, as_attachment=True, download_name=f"result_{sim_id}.vtk")

@sim_bp.route('/<int:sim_id>/status', methods=['GET'])
def get_status(sim_id):
    sim = get_service().session.get(Simulation, sim_id)
    if not sim:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "status": sim.status,
        "progress": sim.progress,
        "error_message": sim.error_message   # новое поле
    })

# ================= НАЧАЛЬНЫЕ УСЛОВИЯ =================
@ic_bp.route('/api/list', methods=['GET'])
def get_initial_conditions_api():
    service = get_service()
    ics = service.get_initial_conditions_list()
    return jsonify([{"initial_conditions_id": ic.initial_conditions_id, "name": ic.name} for ic in ics])


@ic_bp.route('/')
def ic_index():
    service = get_service()
    session = g.db_session
    # Загружаем материалы (элементы и сплавы) для выпадающего списка
    elements = session.scalars(select(Material).where(Material.is_alloy == False)).all()
    alloys = session.scalars(select(Material).where(Material.is_alloy == True)).all()
    materials = elements + alloys
    ics = service.get_initial_conditions_list()
    return render_template('initial_conditions.html', ics=ics, materials=materials)


@ic_bp.route('/create', methods=['POST'])
def ic_create():
    service = get_service()
    try:
        data = InitialConditionCreateRequest(**request.json)
        ic_id = service.create_initial_condition(data)
        service.session.commit()
        return jsonify({"message": "Набор сохранен", "id": ic_id}), 201
    except ValidationError as e:
        service.session.rollback()
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500

@ic_bp.route('/<int:ic_id>', methods=['DELETE'])
def ic_delete(ic_id):
    service = get_service()
    try:
        service.delete_initial_condition(ic_id)
        service.session.commit()
        return jsonify({"message": "Удалено"}), 200
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500

@ic_bp.route('/api/<int:ic_id>', methods=['GET'])
def get_initial_condition(ic_id):
    """Получить полные данные набора начальных условий"""
    service = get_service()
    session = g.db_session
    ic = session.get(InitialCondition, ic_id)
    if not ic:
        return jsonify({"error": "Not found"}), 404

    # Загружаем связанные данные
    time_params = session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
    pot_flow = session.scalar(select(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))
    constr = session.scalar(select(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
    elasticity = session.scalar(select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
    stress = session.scalar(select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
    boundaries = session.scalars(select(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id)).all()
    chords = session.scalars(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id)).all()
    init_temps = session.scalars(select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id)).all()
    # ei_values – через elasticity
    ei_vals = []
    if elasticity:
        ei_vals = session.scalars(select(ElValue).where(ElValue.elasticity_parameters_id == elasticity.elasticity_parameters_id)).all()

    data = {
        "initial_conditions_id": ic.initial_conditions_id,
        "name": ic.name,
        "time_parameters": {
            "time": time_params.time,
            "dt": time_params.dt,
            "nbT": time_params.nbT,
            "Nplot": time_params.Nplot,
        } if time_params else {},
        "potential_flow": {
            "beta": pot_flow.beta,
            "B": pot_flow.B,
        } if pot_flow else {},
        "construction": {
            "NC": constr.NC,
            "NSp": constr.NSp,
            "NSm": constr.NSm,
            "NSpn": constr.NSpn,
            "NSpm": constr.NSpm,
        } if constr else {},
        "elasticity": {
            "b": elasticity.b,
            "nu": elasticity.nu,
            "KLT": elasticity.KLT,
        } if elasticity else {},
        "stress_output": {
            "coef": stress.coef,
            "delt": stress.delt,
            "Npt": stress.Npt,
        } if stress else {},
        "boundaries": [{"name": b.name, "value": b.value} for b in boundaries],
        "chords": [{"name": c.name, "value": c.value} for c in chords],
        "initial_temps": [{"material_id": t.material_id, "value": t.value} for t in init_temps],
        "ei_values": [{"material_id": e.material_id, "value": e.value} for e in ei_vals],
    }
    return jsonify(data)


@ic_bp.route('/api/<int:ic_id>', methods=['PUT'])
def update_initial_condition(ic_id):
    """Обновить набор начальных условий"""
    service = get_service()
    session = g.db_session
    try:
        data = request.json
        ic = session.get(InitialCondition, ic_id)
        if not ic:
            return jsonify({"error": "Not found"}), 404

        # Обновляем название
        ic.name = data['name']

        # Обновляем связанные параметры (удаляем старые и создаём новые)
        # TimeParameter
        session.execute(delete(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
        session.add(TimeParameter(initial_conditions_id=ic_id, **data['time_parameters']))
        # PotentialFlowParameter
        session.execute(delete(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))
        session.add(PotentialFlowParameter(initial_conditions_id=ic_id, **data['potential_flow']))
        # ConstructionParameter
        session.execute(delete(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
        session.add(ConstructionParameter(initial_conditions_id=ic_id, **data['construction']))
        # ElasticityParameter
        old_elasticity = session.scalar(select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
        if old_elasticity:
            # Удаляем старые Ei
            session.execute(delete(ElValue).where(ElValue.elasticity_parameters_id == old_elasticity.elasticity_parameters_id))
            session.delete(old_elasticity)
        new_elasticity = ElasticityParameter(initial_conditions_id=ic_id, **data['elasticity'])
        session.add(new_elasticity)
        session.flush()
        # Добавляем Ei
        for ei in data.get('ei_values', []):
            session.add(ElValue(
                elasticity_parameters_id=new_elasticity.elasticity_parameters_id,
                material_id=ei['material_id'],
                value=ei['value']
            ))
        # StressOutputParameter
        session.execute(delete(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
        session.add(StressOutputParameter(initial_conditions_id=ic_id, **data['stress_output']))

        # BoundaryIdentifier – заменяем
        session.execute(delete(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id))
        for b in data['boundaries']:
            session.add(BoundaryIdentifier(initial_conditions_id=ic_id, **b))
        # BladeChord
        session.execute(delete(BladeChord).where(BladeChord.initial_conditions_id == ic_id))
        for c in data['chords']:
            session.add(BladeChord(initial_conditions_id=ic_id, **c))
        # InitialTemperature
        session.execute(delete(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id))
        for t in data['initial_temps']:
            session.add(InitialTemperature(initial_conditions_id=ic_id, **t))

        session.commit()
        return jsonify({"message": "Набор обновлён"}), 200
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500

@sim_bp.route('/api/simulations', methods=['GET'])
def get_simulations_api():
    from ..utils.database import get_db_session  # если ещё не импортировано
    session = get_db_session()
    sims = session.scalars(select(Simulation).order_by(Simulation.simulation_id.desc())).all()
    result = []
    for s in sims:
        has_vtk = any(r.file_type == 'vtk' for r in s.results)
        result.append({
            "simulation_id": s.simulation_id,
            "name": s.name,
            "blade_name": s.blade.name if s.blade else '—',
            "created_at": s.results[0].created_at if s.results else '—',
            "status": s.status,
            "has_vtk": has_vtk
        })
    return jsonify(result)

@sim_bp.route('/<int:sim_id>/log')
def get_simulation_log(sim_id):
    """Возвращает содержимое console.log для симуляции"""
    sim_dir = os.path.join(os.getcwd(), 'uploads', 'simulations', f"sim_{sim_id}")
    log_path = os.path.join(sim_dir, "console.log")
    if not os.path.exists(log_path):
        return jsonify({"error": "Лог не найден"}), 404
    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({"log": content})