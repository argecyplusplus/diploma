from flask import Blueprint, render_template
from ..utils.database import get_current_db

page_views_bp = Blueprint('page_views', __name__)

@page_views_bp.route('/')
def index():
    try:
        current_db = get_current_db()
    except:
        current_db = None
    return render_template('index.html', currentDb=current_db)

@page_views_bp.route('/blades')
def blades_page():
    return render_template('blades.html')

@page_views_bp.route('/materials')
def materials_page():
    return render_template('materials.html')

@page_views_bp.route('/simulation')
def simulation_page():
    return render_template('simulation.html')