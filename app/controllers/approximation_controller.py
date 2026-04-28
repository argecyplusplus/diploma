import io
import base64
import numpy as np
import matplotlib

matplotlib.use('Agg')  # Важно для работы без графического интерфейса
import matplotlib.pyplot as plt
from flask import Blueprint, render_template, request, jsonify, g
from sqlalchemy import select

from ..services.approximation_service import ApproximationService
from ..models.blade import (
    Approximation,
    LegendreCoefficient,
    ApproximationParameter,
    TransformedCoordinate
)
from ..utils.database import get_db_session
from ..utils.approximation_math import Lezh

approx_bp = Blueprint('approximation', __name__, url_prefix='/approximation')


def get_service():
    if 'db_session' not in g:
        g.db_session = get_db_session()
    return ApproximationService(g.db_session)


@approx_bp.route('/')
def index():
    return render_template('approximation.html')


@approx_bp.route('/blades', methods=['GET'])
def get_blades():
    session = g.db_session if 'db_session' in g else get_db_session()
    from ..models.blade import Blade
    blades = session.scalars(select(Blade)).all()
    return jsonify([{"id": b.blade_id, "name": b.name} for b in blades])


@approx_bp.route('/execute/<int:blade_id>', methods=['POST'])
def execute(blade_id):
    try:
        res = get_service().execute_approximation(blade_id)
        g.db_session.commit()
        return jsonify(res)
    except Exception as e:
        g.db_session.rollback()
        return jsonify({"error": str(e)}), 400


@approx_bp.route('/results/<int:blade_id>', methods=['GET'])
def get_results(blade_id):
    session = g.db_session if 'db_session' in g else get_db_session()

    # Ищем последнюю аппроксимацию для этой лопатки
    stmt = select(Approximation).where(Approximation.blade_id == blade_id).order_by(
        Approximation.approximation_id.desc())
    approx = session.scalar(stmt)
    if not approx:
        return jsonify({"error": "Аппроксимация не выполнена"}), 404

    # Получаем данные
    coords = session.scalars(
        select(TransformedCoordinate).where(TransformedCoordinate.approximation_id == approx.approximation_id)).all()

    # ИСПРАВЛЕНИЕ: Берем только первые 10 коэффициентов, чтобы соответствовать функции Lezh
    coeffs = session.scalars(
        select(LegendreCoefficient)
        .where(LegendreCoefficient.approximation_id == approx.approximation_id)
        .order_by(LegendreCoefficient.legendre_coefficients_id)
        .limit(10)  # Ограничиваем выборку
    ).all()

    params = session.scalars(
        select(ApproximationParameter).where(ApproximationParameter.approximation_id == approx.approximation_id)).all()

    return jsonify({
        "approximation_id": approx.approximation_id,
        "transformed_coords": [{"type": c.profile_type, "x": c.x_transformed, "y": c.y_transformed} for c in coords],
        "legendre_coeffs": [{"idx": i, "upper": lc.upper_value, "lower": lc.lower_value} for i, lc in
                            enumerate(coeffs)],
        "approximation_params": [
            {"type": p.profile_type, "max_val": p.max_profile_value, "x_max": p.x_coordinate_max, "r2": p.r_squared} for
            p in params]
    })


@approx_bp.route('/plot/<int:blade_id>', methods=['GET'])
def get_plot(blade_id):
    session = g.db_session if 'db_session' in g else get_db_session()

    stmt = select(Approximation).where(Approximation.blade_id == blade_id).order_by(
        Approximation.approximation_id.desc())
    approx = session.scalar(stmt)
    if not approx:
        return jsonify({"error": "Нет данных"}), 404

    coeffs = session.scalars(
        select(LegendreCoefficient)
        .where(LegendreCoefficient.approximation_id == approx.approximation_id)
        .order_by(LegendreCoefficient.legendre_coefficients_id)
        .limit(10)
    ).all()

    L_u = np.array([c.upper_value for c in coeffs], dtype=float)
    L_l = np.array([c.lower_value for c in coeffs], dtype=float)

    if len(L_u) < 10:
        L_u = np.pad(L_u, (0, 10 - len(L_u)), 'constant')
        L_l = np.pad(L_l, (0, 10 - len(L_l)), 'constant')

    x_plot = np.linspace(0, 1, 200)
    plt.figure(figsize=(8, 4.5))

    coords = session.scalars(
        select(TransformedCoordinate).where(TransformedCoordinate.approximation_id == approx.approximation_id)).all()

    x_u = [c.x_transformed for c in coords if c.profile_type == 'upper']
    y_u = [c.y_transformed for c in coords if c.profile_type == 'upper']
    x_l = [c.x_transformed for c in coords if c.profile_type == 'lower']
    y_l = [c.y_transformed for c in coords if c.profile_type == 'lower']

    if x_u and y_u:
        plt.plot(x_u, y_u, 'o', markersize=4, label='Верхний профиль (точки)')
    if x_l and y_l:
        plt.plot(x_l, y_l, '+', markersize=5, label='Нижний профиль (точки)')

    lezh_matrix = Lezh(x_plot)
    plt.plot(x_plot, np.dot(L_u, lezh_matrix), '-', linewidth=2, label='Аппрокс. верхний')
    plt.plot(x_plot, np.dot(L_l, lezh_matrix), '--', linewidth=2, label='Аппрокс. нижний')

    plt.legend(), plt.grid(True, alpha=0.6), plt.xlabel('X'), plt.ylabel('Y')
    plt.title(f'Аппроксимация лопатки ID: {blade_id}')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()

    # ✅ Исправленный data URI
    return jsonify({"image": f"data:image/png;base64,{img_b64}"})