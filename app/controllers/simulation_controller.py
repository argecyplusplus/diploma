import os
import subprocess
import threading

from flask import Blueprint, request, jsonify, g, render_template, send_file, abort
from pydantic import ValidationError
from ..services.simulation_service import SimulationService
from ..dto.simulation_dto import SimulationCreateRequest, InitialConditionCreateRequest
from ..utils.database import get_db_session
from ..models.blade import Blade, BladeAssembly
from ..models.simulation import *
from ..models.material import Material, ElValue
from ..models.material import ChemicalElement
from sqlalchemy.orm import joinedload
from sqlalchemy import select, delete

sim_bp = Blueprint('simulation', __name__, url_prefix='/simulation')
ic_bp = Blueprint('initial_conditions', __name__, url_prefix='/initial-conditions')


def get_service():
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return SimulationService(g.db_session)


def get_sim_dir(service, sim_id: int) -> str:
    """Возвращает путь к папке симуляции с учётом текущей БД"""
    return os.path.join(service.upload_dir, f"sim_{sim_id}")


# ================= МОДЕЛИРОВАНИЕ =================
@sim_bp.route('/')
def index():
    service = get_service()
    session = g.db_session

    blades = session.scalars(select(Blade)).all()
    assemblies = session.scalars(select(BladeAssembly)).all()

    chemical_elements = session.scalars(
        select(ChemicalElement).options(joinedload(ChemicalElement.material))
    ).all()
    elements = [ce.material for ce in chemical_elements if ce.material]

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
    service = get_service()
    sim_dir = get_sim_dir(service, sim_id)
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
        "error_message": sim.error_message
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

    time_params = session.scalar(select(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
    pot_flow = session.scalar(select(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))
    constr = session.scalar(select(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
    elasticity = session.scalar(select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
    stress = session.scalar(select(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
    boundaries = session.scalars(select(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id)).all()
    chords = session.scalars(select(BladeChord).where(BladeChord.initial_conditions_id == ic_id)).all()
    init_temps = session.scalars(select(InitialTemperature).where(InitialTemperature.initial_conditions_id == ic_id)).all()
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

        ic.name = data['name']

        session.execute(delete(TimeParameter).where(TimeParameter.initial_conditions_id == ic_id))
        session.add(TimeParameter(initial_conditions_id=ic_id, **data['time_parameters']))
        session.execute(delete(PotentialFlowParameter).where(PotentialFlowParameter.initial_conditions_id == ic_id))
        session.add(PotentialFlowParameter(initial_conditions_id=ic_id, **data['potential_flow']))
        session.execute(delete(ConstructionParameter).where(ConstructionParameter.initial_conditions_id == ic_id))
        session.add(ConstructionParameter(initial_conditions_id=ic_id, **data['construction']))
        old_elasticity = session.scalar(select(ElasticityParameter).where(ElasticityParameter.initial_conditions_id == ic_id))
        if old_elasticity:
            session.execute(delete(ElValue).where(ElValue.elasticity_parameters_id == old_elasticity.elasticity_parameters_id))
            session.delete(old_elasticity)
        new_elasticity = ElasticityParameter(initial_conditions_id=ic_id, **data['elasticity'])
        session.add(new_elasticity)
        session.flush()
        for ei in data.get('ei_values', []):
            session.add(ElValue(
                elasticity_parameters_id=new_elasticity.elasticity_parameters_id,
                material_id=ei['material_id'],
                value=ei['value']
            ))
        session.execute(delete(StressOutputParameter).where(StressOutputParameter.initial_conditions_id == ic_id))
        session.add(StressOutputParameter(initial_conditions_id=ic_id, **data['stress_output']))

        session.execute(delete(BoundaryIdentifier).where(BoundaryIdentifier.initial_conditions_id == ic_id))
        for b in data['boundaries']:
            session.add(BoundaryIdentifier(initial_conditions_id=ic_id, **b))
        session.execute(delete(BladeChord).where(BladeChord.initial_conditions_id == ic_id))
        for c in data['chords']:
            session.add(BladeChord(initial_conditions_id=ic_id, **c))
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
    from ..utils.database import get_db_session
    session = get_db_session()
    sims = session.scalars(select(Simulation).order_by(Simulation.simulation_id.desc())).all()
    task_names = {'task1': '1', 'task2': '2', 'task3': '3', 'task4': '4'}
    result = []
    for s in sims:
        has_vtk = any(r.file_type == 'vtk' for r in s.results)
        object_name = '—'
        if s.blade_assembly_id:
            assembly = session.get(BladeAssembly, s.blade_assembly_id)
            if assembly:
                object_name = assembly.name
        elif s.blade:
            object_name = s.blade.name
        result.append({
            "simulation_id": s.simulation_id,
            "name": s.name,
            "blade_name": object_name,
            "created_at": s.results[0].created_at if s.results else '—',
            "status": s.status,
            "has_vtk": has_vtk,
            "task_display": task_names.get(s.task_type, '?')
        })
    return jsonify(result)


@sim_bp.route('/<int:sim_id>/log')
def get_simulation_log(sim_id):
    """Возвращает содержимое console.log для симуляции"""
    service = get_service()
    sim_dir = get_sim_dir(service, sim_id)
    log_path = os.path.join(sim_dir, "console.log")
    if not os.path.exists(log_path):
        return jsonify({"error": "Лог не найден"}), 404
    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({"log": content})


@sim_bp.route('/<int:sim_id>/result/<file_type>')
def download_result_file(sim_id, file_type):
    service = get_service()
    sim_dir = get_sim_dir(service, sim_id)

    file_map = {
        'vtk': 'result.vtk',
        'tfout': 'TFout.csv',
        'profout': 'Profout.csv',
        'tsout': 'TSout.csv',
        'tepsout': 'TEpsout.csv',
        'gauss_params': 'gauss_params.csv'
    }

    if file_type not in file_map:
        abort(404)

    file_path = os.path.join(sim_dir, file_map[file_type])

    if not os.path.exists(file_path):
        abort(404)

    return send_file(file_path, as_attachment=True,
                     download_name=f"{file_type}_{sim_id}{os.path.splitext(file_map[file_type])[1]}")


# ================= УДАЛЕНИЕ СИМУЛЯЦИЙ =================
@sim_bp.route('/<int:sim_id>', methods=['DELETE'])
def delete_simulation(sim_id):
    service = get_service()
    try:
        service.delete_simulation(sim_id)
        service.session.commit()
        return jsonify({"message": "Симуляция удалена"}), 200
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500


@sim_bp.route('/failed', methods=['DELETE'])
def delete_failed_simulations():
    service = get_service()
    try:
        count = service.delete_failed_simulations()
        service.session.commit()
        return jsonify({"message": f"Удалено {count} неудачных симуляций"}), 200
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500


# ================= СТРАНИЦА РЕЗУЛЬТАТОВ И ГРАФИКИ =================
@sim_bp.route('/<int:sim_id>/results')
def results_page(sim_id):
    service = get_service()
    sim = service.session.get(Simulation, sim_id)
    if not sim:
        abort(404)
    return render_template('results.html', simulation_id=sim_id, simulation_name=sim.name)


@sim_bp.route('/<int:sim_id>/plots')
def get_plots(sim_id):
    """Возвращает JSON с изображениями графиков в формате base64"""
    service = get_service()
    try:
        plots = service.generate_plots(sim_id)
        import sys
        size = sys.getsizeof(str(plots)) / 1024 / 1024
        if size > 10:
            print(f"⚠️ Внимание: графики занимают {size:.2f} MB")
        return jsonify(plots)
    except Exception as e:
        logger.error(f"Ошибка в get_plots: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@sim_bp.route('/<int:sim_id>/files')
def get_result_files(sim_id):
    service = get_service()
    sim_dir = get_sim_dir(service, sim_id)
    files = []

    candidates = [
        ('result.vtk', 'Файл VTK', 'vtk'),
        ('TFout.csv', 'Температура по контуру (TFout.csv)', 'csv'),
        ('Profout.csv', 'Профиль лопатки (Profout.csv)', 'csv'),
        ('TSout.csv', 'Напряжения (TSout.csv)', 'csv'),
        ('TEpsout.csv', 'Деформации (TEpsout.csv)', 'csv'),
        ('gauss_params.csv', 'Параметры гауссовской аппроксимации', 'csv')
    ]

    for filename, description, category in candidates:
        full_path = os.path.join(sim_dir, filename)
        if os.path.exists(full_path):
            files.append({'name': filename, 'description': description, 'category': category})

    return jsonify(files)


@sim_bp.route('/<int:sim_id>/run', methods=['POST'])
def run_simulation(sim_id):
    """Запустить расчёт (меняет статус на running)"""
    service = get_service()
    try:
        sim = service.session.get(Simulation, sim_id)
        if not sim:
            return jsonify({"error": "Симуляция не найдена"}), 404
        if sim.status != 'pending':
            return jsonify({"error": f"Расчёт уже в статусе {sim.status}"}), 400
        sim.status = 'running'
        service.session.commit()
        return jsonify({"message": "Расчёт запущен"}), 200
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500


@sim_bp.route('/<int:sim_id>/download_edp', methods=['GET'])
def download_edp(sim_id):
    """Скачать .edp файл"""
    service = get_service()
    sim_dir = get_sim_dir(service, sim_id)
    edp_path = os.path.join(sim_dir, "blade_sim.edp")
    if not os.path.exists(edp_path):
        return jsonify({"error": "Файл не найден"}), 404
    return send_file(edp_path, as_attachment=True, download_name=f"simulation_{sim_id}.edp")


@sim_bp.route('/<int:sim_id>/run_local', methods=['POST'])
def run_local(sim_id):
    import time
    import threading
    from ..utils.database import get_db_session, get_engine
    from sqlalchemy.orm import sessionmaker

    service = get_service()
    try:
        sim_dir = get_sim_dir(service, sim_id)
        edp_path = os.path.join(sim_dir, "blade_sim.edp")

        if not os.path.exists(edp_path):
            return jsonify({"error": "EDP файл не найден"}), 404

        sim = service.session.get(Simulation, sim_id)
        if not sim:
            return jsonify({"error": "Симуляция не найдена"}), 404

        if sim.status == 'running':
            return jsonify({"error": "Расчёт уже выполняется"}), 400

        # Меняем статус на running
        sim.status = "running"
        service.session.commit()

        # Открываем папку с файлом
        if os.name == 'nt':
            subprocess.Popen(f'explorer /select,"{edp_path}"', shell=True)

        # Получаем список ожидаемых файлов через метод сервиса
        expected_files = service._get_expected_output_files(sim.task_type)

        # Функция мониторинга с отдельной сессией
        def check_completion():
            engine = get_engine()
            SessionLocal = sessionmaker(bind=engine)
            db_session = SessionLocal()
            try:
                max_wait = 3600  # 1 час
                waited = 0
                while waited < max_wait:
                    time.sleep(10)
                    waited += 10
                    # Проверяем существование всех ожидаемых файлов
                    all_exist = all(os.path.exists(os.path.join(sim_dir, f)) for f in expected_files)
                    if all_exist:
                        sim_obj = db_session.get(Simulation, sim_id)
                        if sim_obj:
                            sim_obj.status = "completed"
                            sim_obj.progress = 100
                            db_session.commit()
                            print(f"✅ Симуляция {sim_id} завершена! Все ожидаемые файлы найдены.")
                        return
                    # Дополнительно проверяем наличие лога с ошибкой
                    log_path = os.path.join(sim_dir, "console.log")
                    if os.path.exists(log_path):
                        with open(log_path, 'r', encoding='utf-8') as lf:
                            content = lf.read()
                            if "error" in content.lower() or "fail" in content.lower():
                                sim_obj = db_session.get(Simulation, sim_id)
                                if sim_obj:
                                    sim_obj.status = "failed"
                                    sim_obj.error_message = "Обнаружена ошибка в логе FreeFEM"
                                    db_session.commit()
                                return
                # Таймаут
                sim_obj = db_session.get(Simulation, sim_id)
                if sim_obj and sim_obj.status == 'running':
                    sim_obj.status = "failed"
                    sim_obj.error_message = "Превышено время ожидания (1 час)"
                    db_session.commit()
            except Exception as e:
                print(f"Ошибка в check_completion: {e}")
            finally:
                db_session.close()

        thread = threading.Thread(target=check_completion, daemon=True)
        thread.start()

        return jsonify({
            "message": "Папка с файлом открыта. Дважды кликните по .edp файлу для запуска FreeFEM++",
            "edp_path": edp_path,
            "instruction": True
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sim_bp.route('/<int:sim_id>/reset_status', methods=['POST'])
def reset_simulation_status(sim_id):
    """Сбросить статус расчёта (для перезапуска)"""
    service = get_service()
    try:
        sim = service.session.get(Simulation, sim_id)
        if not sim:
            return jsonify({"error": "Симуляция не найдена"}), 404
        sim.status = 'pending'
        sim.progress = 0
        sim.error_message = None
        service.session.commit()
        return jsonify({"message": "Статус сброшен"}), 200
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500


@sim_bp.route('/<int:sim_id>/check_completion', methods=['POST'])
def check_completion_manual(sim_id):
    """Ручная проверка завершения расчёта по наличию ожидаемых файлов"""
    service = get_service()
    try:
        sim_dir = get_sim_dir(service, sim_id)

        sim = service.session.get(Simulation, sim_id)
        if not sim:
            return jsonify({"error": "Симуляция не найдена"}), 404

        expected_files = service._get_expected_output_files(sim.task_type)

        if not expected_files:
            # Для задачи 1 считаем завершённой, если процесс не в running
            if sim.status == 'running':
                sim.status = "completed"
                sim.progress = 100
                service.session.commit()
                return jsonify({"status": "completed", "message": "Расчёт завершён!"}), 200
        else:
            all_exist = all(os.path.exists(os.path.join(sim_dir, f)) for f in expected_files)
            if all_exist and sim.status == 'running':
                sim.status = "completed"
                sim.progress = 100
                service.session.commit()
                return jsonify({"status": "completed", "message": "Расчёт завершён!"}), 200

        if sim.status == 'completed':
            return jsonify({"status": "completed", "message": "Расчёт уже завершён"}), 200
        else:
            return jsonify({"status": sim.status, "message": "Расчёт ещё не завершён"}), 200
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500


@sim_bp.route('/<int:sim_id>/reset', methods=['POST'])
def reset_simulation(sim_id):
    service = get_service()
    try:
        sim = service.session.get(Simulation, sim_id)
        if not sim:
            return jsonify({"error": "Симуляция не найдена"}), 404

        sim_dir = get_sim_dir(service, sim_id)
        if os.path.exists(sim_dir):
            # Удаляем только файлы результатов, НЕ трогаем out_L.csv и .edp
            for fname in os.listdir(sim_dir):
                # Исключаем out_L.csv и blade_sim.edp
                if fname in ['out_L.csv', 'blade_sim.edp']:
                    continue
                if fname.endswith(('.csv', '.eps', '.vtk', '.log')):
                    os.remove(os.path.join(sim_dir, fname))
            # Удаляем папку plots, если она есть
            plots_dir = os.path.join(sim_dir, "plots")
            if os.path.exists(plots_dir):
                import shutil
                shutil.rmtree(plots_dir)

        sim.status = 'pending'
        sim.progress = 0
        sim.error_message = None
        service.session.commit()
        return jsonify({"message": "Статус сброшен, файлы результатов удалены"}), 200
    except Exception as e:
        service.session.rollback()
        return jsonify({"error": str(e)}), 500