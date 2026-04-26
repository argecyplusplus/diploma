# app/controllers/main_views.py
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('base.html')

@main_bp.route('/select-db')
def select_db_page():
    # Специальная страница, если редирект сработал до загрузки модалки
    return render_template('base.html')