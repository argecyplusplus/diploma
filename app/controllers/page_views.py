from flask import Blueprint, render_template

page_views_bp = Blueprint('page_views', __name__)

@page_views_bp.route('/')
def index():
    return render_template('base.html')

@page_views_bp.route('/blades')
def blades_page():
    return render_template('blades.html')

@page_views_bp.route('/materials')
def materials_page():
    return render_template('base.html')

@page_views_bp.route('/simulation')
def simulation_page():
    return render_template('base.html')