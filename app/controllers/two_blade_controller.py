import os
from flask import Blueprint, render_template, request, jsonify, g, send_file, abort
from pydantic import ValidationError
from sqlalchemy import select

from app.services.two_blade_service import TwoBladeService
from app.dto.two_blade_dto import TwoBladeCreateRequest
from app.utils.database import get_db_session
from app.models.blade import Blade

two_blade_bp = Blueprint('two_blade', __name__, url_prefix='/two-blade')

def get_service():
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return TwoBladeService(g.db_session)

@two_blade_bp.route('/')
def index():
    session = get_db_session()
    blades = session.scalars(select(Blade)).all()
    return render_template('two_blade.html', blades=blades)

@two_blade_bp.route('/run', methods=['POST'])
def run():
    service = get_service()
    try:
        data = TwoBladeCreateRequest(**request.json)
        sim_id = service.run_simulation(data)
        return jsonify({"sim_id": sim_id}), 202
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@two_blade_bp.route('/status/<int:sim_id>')
def status(sim_id):
    # Пока просто проверяем наличие папки и .edp (заглушка)
    sim_dir = os.path.join(os.getcwd(), 'uploads', 'two_blade_simulations', f"sim_{sim_id}")
    if not os.path.exists(sim_dir):
        return jsonify({"status": "not_found"}), 404
    # Можно анализировать наличие выходных файлов
    if os.path.exists(os.path.join(sim_dir, "tlT.csv")):
        return jsonify({"status": "completed"})
    elif os.path.exists(os.path.join(sim_dir, "AeroTherm_gen.edp")):
        return jsonify({"status": "running"})
    else:
        return jsonify({"status": "pending"})

@two_blade_bp.route('/results/<int:sim_id>')
def results(sim_id):
    sim_dir = os.path.join(os.getcwd(), 'uploads', 'two_blade_simulations', f"sim_{sim_id}")
    if not os.path.exists(sim_dir):
        abort(404)
    # Список файлов для скачивания
    files = []
    for f in os.listdir(sim_dir):
        if f.endswith('.csv') or f.endswith('.eps') or f.endswith('.vtk') or f == 'console.log':
            files.append(f)
    return render_template('two_blade_results.html', sim_id=sim_id, files=files)

@two_blade_bp.route('/download/<int:sim_id>/<filename>')
def download(sim_id, filename):
    sim_dir = os.path.join(os.getcwd(), 'uploads', 'two_blade_simulations', f"sim_{sim_id}")
    file_path = os.path.join(sim_dir, filename)
    if not os.path.exists(file_path):
        abort(404)
    return send_file(file_path, as_attachment=True)